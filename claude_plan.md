# Per-Trust API Keys

## Context

All trusts currently share a single `PRIVATE_API_KEY`. If the key leaks from any trust, an attacker can impersonate any other trust — polling their tasks, submitting fake results, or sending heartbeats. Trust identity today is just a `trust_name` URL path parameter with no cryptographic binding to the caller.

**Goal:** Each trust gets a unique API key. The hub validates the key and binds it to a specific trust, preventing cross-trust impersonation.

## Design

### 1. Hub Config — `TRUST_API_KEY_HASHES` env var

**File:** `flip-api/src/flip_api/config.py`

Add a new setting to the hub:
```python
TRUST_API_KEY_HASHES: dict[str, str] = {}  # {"Trust_1": "sha256hex...", "Trust_2": "sha256hex..."}
```

This is a JSON dict mapping trust names → SHA-256 hex digests of their API keys. Loaded from the `TRUST_API_KEY_HASHES` env var. Same pattern as `TRUST_NAMES` (a JSON list already read from env).

Make `PRIVATE_API_KEY` optional (`str | None = None`) — no longer required on the hub. Keep `PRIVATE_API_KEY_HEADER` as-is (still needed to read the header name).

### 2. New Auth Dependency — `authenticate_trust`

**File:** `flip-api/src/flip_api/auth/access_manager.py`

Create a new FastAPI dependency `authenticate_trust` that:
1. Extracts the API key from the request header (reuses existing `api_key_header_scheme`)
2. Computes `hashlib.sha256(key.encode()).hexdigest()`
3. Looks up the computed hash in `get_settings().TRUST_API_KEY_HASHES` (reverse lookup: find the trust name whose hash matches)
4. Returns the trust name if found
5. Raises 401 if no matching trust

No DB dependency needed — purely reads from settings. Build a reverse lookup dict (`hash → trust_name`) at module load time for O(1) lookups.

Remove the old `check_authorization_token` function once all endpoints are migrated.

### 3. Update All Private Endpoints

Replace `Depends(check_authorization_token)` → `Depends(authenticate_trust)` on all 7 private endpoints. The dependency now returns a trust name (str) that's cryptographically bound to the API key.

**Files to modify:**

| File | Endpoint | Additional validation |
|---|---|---|
| `flip-api/src/flip_api/private_services/trust_tasks.py` | `GET /tasks/{trust_name}/pending` | Assert `authenticated_trust_name == trust_name` |
| `flip-api/src/flip_api/private_services/trust_tasks.py` | `POST /tasks/{trust_name}/{task_id}/result` | Assert `authenticated_trust_name == trust_name` |
| `flip-api/src/flip_api/private_services/trust_tasks.py` | `POST /trust/{trust_name}/heartbeat` | Assert `authenticated_trust_name == trust_name` |
| `flip-api/src/flip_api/private_services/receive_cohort_results.py` | `POST /cohort/results` | Look up Trust by `authenticated_trust_name`, assert `trust.id == cohort_results.trust_id` |
| `flip-api/src/flip_api/private_services/save_training_metrics.py` | `POST /model/{model_id}/metrics` | Assert `authenticated_trust_name == training_metrics.trust` |
| `flip-api/src/flip_api/private_services/add_log.py` | `POST /model/{model_id}/logs` | Assert `authenticated_trust_name == training_log.trust` |
| `flip-api/src/flip_api/private_services/invoke_model_status_update.py` | `POST /model/{model_id}/status/{status}` | No further validation (key identifies the trust) |

For `trust_tasks.py` endpoints: the `_get_trust_by_name()` DB lookup is still needed (to get the Trust UUID for task queries), but the trust name is now validated by auth. Add a 403 check: if `authenticated_trust_name != trust_name` path param, reject before hitting the DB.

For `receive_cohort_results.py`: need to look up the Trust by `authenticated_trust_name` from DB to get the UUID, then validate it matches `cohort_results.trust_id`.

### 4. Key Generation Script + Make Target

**New file:** `flip-api/src/flip_api/scripts/generate_trust_key.py`

Script that:
1. Accepts `--trust-name` argument
2. Generates a key via `secrets.token_urlsafe(32)`
3. Computes SHA-256 hex digest
4. Saves the plaintext key to `trust/trust-keys/<trust-name>.key`
5. Prints both the key and hash to stdout
6. No DB access needed

**New directory:** `trust/trust-keys/` — gitignored, stores plaintext trust API keys (one file per trust)

**File:** `.gitignore` — Add `trust/trust-keys/`

**File:** `flip-api/Makefile` — Add `generate-trust-key` target:
```makefile
generate-trust-key:
	uv run python -m flip_api.scripts.generate_trust_key --trust-name $(TRUST_NAME)
```

Output example:
```
Trust: Trust_1
API Key saved to: trust/trust-keys/Trust_1.key
Key Hash (add to TRUST_API_KEY_HASHES on the hub): a1b2c3...
```

This means both the key and hash persist locally across deployments. During full-deploy:
- The hash is in Terraform variables → pushed to Secrets Manager
- The plaintext key is in `trust/trust-keys/` → deployed to the trust host via Ansible or manual copy

### 5. Trust-Side — No Code Changes

Trust-api already reads `PRIVATE_API_KEY` from env and sends it in the header. The only operational change is that each trust gets a **unique** value during onboarding.

### 6. Env, Compose & Makefile Updates

#### Development key distribution

**File:** `.env.development.example`
- Replace single `PRIVATE_API_KEY=<...>` with:
  ```
  # Per-trust API keys (each trust gets a unique key)
  PRIVATE_API_KEY_TRUST_1=<dev-key-for-trust-1>
  PRIVATE_API_KEY_TRUST_2=<dev-key-for-trust-2>

  # Hub: JSON dict mapping trust names to SHA-256 hashes of their API keys
  TRUST_API_KEY_HASHES={"Trust_1": "<sha256-of-trust-1-key>", "Trust_2": "<sha256-of-trust-2-key>"}
  ```

**File:** `trust/Makefile`
- In `TRUST_1_VARS` (line 66): add `PRIVATE_API_KEY=${PRIVATE_API_KEY_TRUST_1}`
- In `TRUST_2_VARS` (line 83): add `PRIVATE_API_KEY=${PRIVATE_API_KEY_TRUST_2}`
- The compose file already references `${PRIVATE_API_KEY}` — picks up the correct value per trust

**File:** `trust/compose_trust.development.yml` — No changes needed

**Files:** `deploy/compose.development.yml`, `deploy/compose.production.yml`
- Remove `PRIVATE_API_KEY` from the flip-api (hub) service environment block
- Add `TRUST_API_KEY_HASHES=${TRUST_API_KEY_HASHES}` to the flip-api (hub) service
- Keep `PRIVATE_API_KEY_HEADER` on the hub

#### Production key distribution

1. Admin runs `make -C flip-api generate-trust-key TRUST_NAME=Trust_1` — gets plaintext key + hash
2. Admin adds the hash to the hub's `TRUST_API_KEY_HASHES` env var (in Secrets Manager or `.env`)
3. Admin deploys the plaintext key to the trust's host as `PRIVATE_API_KEY`

### 7. No DB Model Changes

The `Trust` model is unchanged. Key hashes live in env vars, not the database. The `Trust` table continues to store only `id`, `name`, and `last_heartbeat`.

### 8. AWS Terraform / Secrets Manager

In production, secrets are **not** passed as env vars. They're stored in AWS Secrets Manager and fetched at runtime by the app (see `flip-api/src/flip_api/utils/get_secrets.py` and `encryption.py:29`). The compose file even comments this out: `# AES_KEY_BASE64 — in production, retrieved from AWS Secrets Manager`.

`TRUST_API_KEY_HASHES` follows the same pattern:

**During `make full-deploy` → `apply` step:**
Terraform stores the hashes in the FLIP_API Secrets Manager secret.

**File:** `deploy/providers/AWS/variables.tf`
- Add `TRUST_API_KEY_HASHES` variable (type `string`, JSON-encoded dict)

**File:** `deploy/providers/AWS/main.tf` (lines 174-176)
- Update the `flip_api_secret` secret JSON:
  ```hcl
  secret_string = jsonencode({
    aes_key              = var.AES_KEY_BASE64
    trust_api_key_hashes = var.TRUST_API_KEY_HASHES
  })
  ```

**File:** `deploy/providers/AWS/Makefile` (line 50)
- Add `export TF_VAR_TRUST_API_KEY_HASHES=${TRUST_API_KEY_HASHES}`

**At container runtime:**
The hub fetches `trust_api_key_hashes` from Secrets Manager, same as `aes_key`.

**File:** `flip-api/src/flip_api/auth/access_manager.py`
- In `authenticate_trust`, load hashes from:
  - `get_settings().TRUST_API_KEY_HASHES` in development (env var)
  - `get_secret("trust_api_key_hashes")` in production (Secrets Manager), following the same pattern as `get_aes_key()` in `encryption.py:29`

**File:** `deploy/compose.production.yml`
- Remove `PRIVATE_API_KEY` from hub service (line 50)
- Do NOT add `TRUST_API_KEY_HASHES` — it comes from Secrets Manager, not env vars

**Operational flow for adding a new trust:**
1. Generate key: `make -C flip-api generate-trust-key TRUST_NAME=Trust_3`
2. Update `TRUST_API_KEY_HASHES` in the Terraform variables (`.env.stag` or `terraform.tfvars`)
3. Run `make apply` to update Secrets Manager
4. Restart hub containers to pick up the new secret
5. Deploy the new trust with its unique `PRIVATE_API_KEY`

### 9. Ansible Playbooks

**File:** `deploy/providers/AWS/site.yml`
- No changes needed — Ansible provisions directories and downloads FL kits. Secrets come from Secrets Manager at container runtime, not via Ansible.

**File:** `deploy/providers/local/site_local_trust.yml`
- No changes needed — on-prem trusts get their `PRIVATE_API_KEY` via their `.env` file, which is already manually configured by the admin. The playbook doesn't manage secrets.

### 10. CI/CD Updates

**File:** `.github/SECRETS.md`
- Update section 2 (`PRIVATE_API_KEY`): explain it's now per-trust, add `TRUST_API_KEY_HASHES` as a new secret
- Update the CI workflow pattern to inject `TRUST_API_KEY_HASHES` into `.env.development`
- Update fallback values section

**GitHub Actions workflows** that use `PRIVATE_API_KEY`:
- Need a `TRUST_API_KEY_HASHES` GitHub secret with test values
- CI can use a single shared test key per trust (security isolation isn't needed in CI, just functional correctness)

### 11. Documentation Updates

| File | Change |
|---|---|
| `flip-api/README.md` (line 70) | Update `PRIVATE_API_KEY` description: "Per-trust secret key for inter-service auth. Hub stores hashes in `TRUST_API_KEY_HASHES`." Add `TRUST_API_KEY_HASHES` row. |
| `trust/trust-api/README.md` (line 67) | Update `PRIVATE_API_KEY` description: "Unique secret key for this trust to authenticate with the Central Hub (generated via `make generate-trust-key`)" |
| `deploy/providers/AWS/README.md` | Add note about `TRUST_API_KEY_HASHES` in Secrets Manager |
| `CONTRIBUTING.md` | Update Environment variables section if it references `PRIVATE_API_KEY` |
| `CLAUDE.md` | Update Security Rules section to mention per-trust keys |

## Tests

### Unit Tests to Update

**File:** `flip-api/tests/unit/auth/test_access_manager.py`
- Add tests for `authenticate_trust`: valid key → returns trust name, invalid key → 401, missing key → 401, empty TRUST_API_KEY_HASHES → 401

**File:** `flip-api/tests/unit/private_services/test_trust_tasks.py`
- Update `mock_auth` fixture to override `authenticate_trust` instead of `check_authorization_token`
- Add test: authenticated as Trust_1 but requesting `/tasks/Trust_2/pending` → 403

### New Tests

- Test key generation script: generates key, hash matches `sha256(key)`
- Test trust name mismatch on all endpoint types
- Test cohort results: authenticated trust doesn't match body trust_id → 403

## Verification

1. **Unit tests:** `cd flip-api && make unit_test`
2. **Integration test (manual):**
   - Set per-trust keys in `.env.development`
   - Start services: `make up`
   - Verify Trust_1 can poll its own tasks
   - Verify Trust_1's key cannot poll Trust_2's tasks (returns 403)
   - Verify a random invalid key returns 401
3. **Lint + type check:** `cd flip-api && make test`

## Files Changed (Summary)

### Application code
| File | Change |
|---|---|
| `flip-api/src/flip_api/config.py` | Add `TRUST_API_KEY_HASHES`, make `PRIVATE_API_KEY` optional |
| `flip-api/src/flip_api/auth/access_manager.py` | Add `authenticate_trust`, remove `check_authorization_token` |
| `flip-api/src/flip_api/private_services/trust_tasks.py` | Use `authenticate_trust`, add name validation (403) |
| `flip-api/src/flip_api/private_services/receive_cohort_results.py` | Use `authenticate_trust`, validate trust_id |
| `flip-api/src/flip_api/private_services/save_training_metrics.py` | Use `authenticate_trust`, validate trust name |
| `flip-api/src/flip_api/private_services/add_log.py` | Use `authenticate_trust`, validate trust name |
| `flip-api/src/flip_api/private_services/invoke_model_status_update.py` | Use `authenticate_trust` |
| `flip-api/src/flip_api/scripts/generate_trust_key.py` | **New** — key generation script (no DB needed) |

### Build & config
| File | Change |
|---|---|
| `flip-api/Makefile` | Add `generate-trust-key` target |
| `trust/Makefile` | Add `PRIVATE_API_KEY` to `TRUST_1_VARS` and `TRUST_2_VARS` |
| `trust/trust-keys/` | **New** — gitignored directory for plaintext trust API keys |
| `.gitignore` | Add `trust/trust-keys/` |
| `.env.development.example` | Add per-trust keys + `TRUST_API_KEY_HASHES` |
| `deploy/compose.development.yml` | Replace `PRIVATE_API_KEY` with `TRUST_API_KEY_HASHES` on hub |

### Infrastructure
| File | Change |
|---|---|
| `deploy/providers/AWS/variables.tf` | Add `TRUST_API_KEY_HASHES` variable |
| `deploy/providers/AWS/main.tf` | Add `trust_api_key_hashes` to FLIP_API secret |
| `deploy/providers/AWS/Makefile` | Export `TF_VAR_TRUST_API_KEY_HASHES` |
| `deploy/compose.production.yml` | Remove `PRIVATE_API_KEY` from hub service |

### Tests
| File | Change |
|---|---|
| `flip-api/tests/unit/auth/test_access_manager.py` | Add `authenticate_trust` tests |
| `flip-api/tests/unit/private_services/test_trust_tasks.py` | Update auth fixture, add cross-trust 403 tests |

### Documentation
| File | Change |
|---|---|
| `flip-api/README.md` | Update env var table |
| `trust/trust-api/README.md` | Update `PRIVATE_API_KEY` description |
| `deploy/providers/AWS/README.md` | Add `TRUST_API_KEY_HASHES` to Secrets Manager section |
| `.github/SECRETS.md` | Add `TRUST_API_KEY_HASHES`, update `PRIVATE_API_KEY` section |
| `CLAUDE.md` | Update Security Rules to mention per-trust keys |
