/*
 * Copyright (c) 2026 Guy's and St Thomas' NHS Foundation Trust & King's College London
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *     http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { _http } from "@/services/api";
import { getMfaStatus, resetUserMfa } from "@/services/user-service";

// Stub the low-level axios wrapper so each test can assert the URL + payload
// without spinning up a real HTTP client.
vi.mock("@/services/api", () => ({
    _http: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        delete: vi.fn()
    }
}));

describe("user-service", () => {
    beforeEach(() => {
        vi.mocked(_http.get).mockReset();
        vi.mocked(_http.post).mockReset();
    });

    describe("resetUserMfa", () => {
        it("POSTs to /users/{userId}/mfa/reset with no body", async () => {
            vi.mocked(_http.post).mockResolvedValue({ data: undefined } as never);

            await resetUserMfa("abc-123");

            expect(_http.post).toHaveBeenCalledTimes(1);
            expect(_http.post).toHaveBeenCalledWith("/users/abc-123/mfa/reset");
        });

        it("propagates the underlying error", async () => {
            // The admin users page relies on this throwing so the snackbar
            // shows a failure message — catching here would silently look
            // like success to the caller.
            vi.mocked(_http.post).mockRejectedValue(new Error("403 Forbidden"));

            await expect(resetUserMfa("abc-123")).rejects.toThrow("403 Forbidden");
        });
    });

    describe("getMfaStatus", () => {
        it("GETs /users/me/mfa/status and unwraps response.data", async () => {
            // The backend returns both enabled (is a TOTP device active?) and
            // required (does this environment demand MFA?) — the store
            // relies on both fields being passed through untouched.
            vi.mocked(_http.get).mockResolvedValue({
                data: { enabled: true, required: true }
            } as never);

            const result = await getMfaStatus();

            expect(_http.get).toHaveBeenCalledWith("/users/me/mfa/status");
            expect(result).toEqual({ enabled: true, required: true });
        });

        it("returns enabled=false, required=false for an unenrolled dev caller", async () => {
            vi.mocked(_http.get).mockResolvedValue({
                data: { enabled: false, required: false }
            } as never);

            const result = await getMfaStatus();

            expect(result).toEqual({ enabled: false, required: false });
        });
    });
});
