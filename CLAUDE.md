# CLAUDE.md

## Project Overview

FLIP (Federated Learning Interoperability Platform) is an open-source platform for federated training and evaluation of medical imaging AI models across healthcare institutions while preserving data privacy. Developed by the London AI Centre with Guy's and St Thomas' NHS Foundation Trust and King's College London.

**License**: Apache 2.0 — all source files must include the copyright header.

## Repository Structure

Mono-repo with these key services:

```
FLIP/
├── flip-api/           # Central Hub API (Python/FastAPI)
├── flip-ui/            # Frontend UI (Vue 3 / TypeScript / TailwindCSS)
├── trust/
│   ├── trust-api/      # Trust API gateway (Python/FastAPI)
│   ├── data-access-api/# OMOP database queries (Python/FastAPI)
│   ├── imaging-api/    # DICOM image retrieval (Python/FastAPI)
│   ├── omop-db/        # Mocked OMOP database (PostgreSQL)
│   ├── orthanc/        # Mocked PACS server
│   └── xnat/           # Mocked XNAT neuroimaging service
├── deploy/             # Docker Compose files (dev/prod, flower/nvflare)
├── docs/               # Sphinx documentation (ReadTheDocs)
└── scripts/            # Utility scripts
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend APIs | Python 3.12+, FastAPI, SQLAlchemy/SQLModel, Pydantic |
| Frontend | Vue 3, TypeScript, Vite, TailwindCSS, Pinia |
| Database | PostgreSQL (asyncpg) |
| Package mgmt (Python) | UV (`uv sync`, `uv add`) |
| Package mgmt (JS) | npm |
| Containers | Docker, Docker Compose, Docker Swarm (XNAT) |
| FL frameworks | NVIDIA FLARE, Flower |
| Auth | AWS Cognito |
| Storage | AWS S3 |
| CI/CD | GitHub Actions |

## Common Commands

### Running Services

```bash
make up                    # Start all services (requires AWS access)
make up-no-trust           # Start central hub only
make up-trusts             # Start trust services only
make down                  # Stop all services
make restart               # Stop and restart all
make build                 # Build all Docker images
make ui                    # Start UI only
```

### Testing

```bash
# From root — run all unit tests across all services
make unit_test

# From root — run flip-ui + flip-api tests
make tests

# From a service directory (e.g., flip-api/)
make test                  # Lint + mypy + pytest (unit + integration)
make unit_test             # Unit tests only
make integration_test      # Integration tests only
make local_test            # Tests without Docker

# Direct pytest invocation
uv run pytest --tb=short --disable-warnings --cov=src/ --cov-report=term-missing
```

### Linting & Type Checking

```bash
uv run ruff check . --fix  # Lint with auto-fix
uv run mypy .              # Static type checking
```

### Debugging

```bash
make debug SERVICE=flip-api        # Start a service in debug mode
make debug SERVICE=trust-api       # Available: flip-api, trust-api, imaging-api, data-access-api
make debug-off SERVICE=flip-api    # Stop debug mode
```

### Test Data

```bash
make -C flip-api create_testing_projects   # Create test projects
make -C flip-api delete_testing_projects   # Clean up test data
```

## Workflow Requirements

### Always Use Make Commands

When a `Makefile` target exists for the task at hand, **always use it** instead of running raw commands. Make targets encapsulate the correct flags, environment setup, and command sequences. Key rules:

- Use `make test` (from a service directory) rather than invoking `uv run ruff`, `uv run mypy`, and `uv run pytest` separately — it runs all three in the correct order.
- Use `make unit_test` (from root or service directory) for running unit tests.
- Use `make build` instead of raw `docker compose build`.
- Use `make up` / `make down` instead of raw `docker compose` commands.
- Check each service's `Makefile` for available targets before writing manual commands.

### Always Verify Changes

After making any code changes, **always run verification before committing**:

1. **Identify affected services** — determine which service(s) your changes touch.
2. **Run the service-level test suite** — from the affected service directory:
   ```bash
   make test        # Runs ruff + mypy + pytest (unit + integration)
   ```
   If only unit tests are needed (e.g., no Docker available):
   ```bash
   make unit_test   # Unit tests only
   ```
3. **For cross-service changes**, run the root-level test suite:
   ```bash
   make unit_test   # All services from root
   ```
4. **Fix all failures** before committing — do not commit code that fails linting, type checking, or tests.
5. **For frontend changes** (`flip-ui/`), also run:
   ```bash
   cd flip-ui && npm run lint && npm run test:unit
   ```

### Check If Documentation Needs Updating

After making changes, **always evaluate whether documentation needs to be updated**. Check the following:

| Change Type | Documentation to Review |
|-------------|------------------------|
| New service or component | `README.md` (root), `CONTRIBUTING.md` (Adding a new service section), `docs/source/2_components.rst` |
| New API endpoints | `docs/source/5_api_reference.rst`, service-level `README.md` |
| Changed environment variables | `.env.development.example`, `CONTRIBUTING.md` (Environment variables section), `docs/source/3_sys-admin.rst` |
| New dependencies or tooling | `CONTRIBUTING.md` (Prerequisites section), service `README.md` |
| Changed Docker/deployment config | `deploy/README.md`, `docs/source/3_sys-admin.rst` |
| New Make targets | `README.md` (root), this file (`CLAUDE.md`) |
| Changed user-facing workflows | `docs/source/4_user-guides.rst` and files in `docs/source/user-guides/` |
| New FL framework features | `docs/source/components/component-fl-nodes.rst` |
| Trust service changes | `trust/README.md`, relevant `trust/*/README.md` |
| New user roles or auth changes | `docs/source/components/component-user-roles.rst` |

Documentation files in this repo:
- **`README.md`** (root) — project overview, quickstart, prerequisites
- **`CONTRIBUTING.md`** — development setup, coding style, PR process
- **`docs/source/`** — Sphinx/ReadTheDocs documentation (`.rst` files)
- **Service-level `README.md`** files — per-service setup and usage (in `flip-api/`, `flip-ui/`, `trust/*/`)
- **`deploy/README.md`** — deployment instructions
- **This file (`CLAUDE.md`)** — AI assistant reference

When in doubt, update the docs. Outdated documentation is worse than no documentation.

## Code Style & Conventions

### Python

- **Line length**: 120 characters
- **Linter/Formatter**: Ruff (`select = ['I', 'F', 'E', 'W', 'PT']`)
- **Type checker**: mypy (all code must have type hints)
- **Docstrings**: Google style guide
- **Naming**: snake_case for functions, variables, modules
- **Imports**: Alphabetically sorted (enforced by ruff `I` rule)
- **Source layout**: `src/[service_name]/` per service
- **Test files**: `test_*.py` or `*_test.py` in `tests/unit/` and `tests/integration/`
- **Test fixtures**: pytest fixtures in `conftest.py`, factory_boy for data generation
- **Dependency injection**: FastAPI `Depends()`
- **Async DB**: asyncpg with async context managers

### JavaScript/TypeScript (flip-ui)

- **Line length**: 120 characters
- **Linter**: ESLint with TypeScript + Vue plugins
- **Components**: PascalCase names, organized in `src/partials/` (reusable) and `src/pages/`
- **State management**: Pinia stores in `src/stores/`
- **Styling**: TailwindCSS utility classes (dark mode via `dark:` prefix)
- **Testing**: Vitest (unit), Cypress (e2e)
- **Icons**: Heroicons (`@heroicons/vue`)

### General

- All files must include the Apache 2.0 copyright header
- Commits must be signed off (DCO): `git commit -s`
- PRs target the `develop` branch
- Branch naming: `[ticket_id]-[task_name]` (e.g., `19-ci-pipeline-setup`)

## Environment Setup

1. Copy env template: `cp .env.development.example .env.development`
2. Install Python deps per service: `cd <service-dir> && uv sync`
3. Install UI deps: `cd flip-ui && npm install`
4. Configure AWS: `aws configure sso` (required for `flip-api` and `make up`)
5. Docker networks: `make create-networks`

### Key Environment Variables

- `FL_BACKEND` — `flower` (default) or `nvflare`
- `PROD` — `true` (production), `stag` (staging), unset (development)
- `AES_KEY_BASE64` — encryption key for trust communication
- `PRIVATE_API_KEY` — service-to-service auth

## CI/CD

GitHub Actions workflows in `.github/workflows/`:

- **Test**: `test_flip_api.yml`, `test_flip_ui.yml`, `test_trust_*.yml`
- **Build**: `docker_build_*.yml` for each service
- **Security**: `secret-scanning.yml` (TruffleHog + detect-secrets)
- **Docs**: `docs.yml` (Sphinx → ReadTheDocs)
- **PR checks**: `pr_acceptance_criteria.yml`

Run CI locally: `make ci` (uses [act](https://github.com/nektos/act))

## Pre-commit Hooks

Configured in `.pre-commit-config.yaml`:
- TruffleHog (secret scanning)
- detect-secrets (with `.secrets.baseline`)
- Large file check (max 1000KB)
- Merge conflict markers, YAML validation, private key detection
- Environment variable validation

Install: `pre-commit install`

## Security Rules

- Never commit secrets or credentials — pre-commit hooks enforce this
- Never bypass TLS certificate validation (`curl -k` is prohibited)
- Use `AES_KEY_BASE64` for encrypted trust communication
- AWS Cognito for hub authentication, private API keys for inter-service auth
- Do not hardcode environment values in Dockerfiles or compose files

## Related Repositories

| Repository | Purpose |
|-----------|---------|
| [FLIP](https://github.com/londonaicentre/FLIP) | Main mono-repo (this repo) |
| [flip-fl-base](https://github.com/londonaicentre/flip-fl-base) | NVIDIA FLARE FL base library |
| [flip-fl-base-flower](https://github.com/londonaicentre/flip-fl-base-flower) | Flower FL base library |
