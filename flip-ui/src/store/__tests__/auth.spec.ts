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

import {
    confirmResetPassword,
    confirmSignIn,
    fetchAuthSession,
    fetchUserAttributes,
    getCurrentUser,
    resetPassword,
    setUpTOTP,
    signIn,
    signOut,
    updateMFAPreference,
    verifyTOTPSetup
} from "aws-amplify/auth";
import { createPinia, setActivePinia } from "pinia";

import { routeChange } from "@/router";
import { getMfaStatus, getUserPermissions } from "@/services/user-service";
import { useAuthStore } from "@/store/auth";

// Amplify auth functions are all called via named imports; mock every
// symbol the store touches. Individual tests re-arm these via
// vi.mocked(fn).mockResolvedValue(...) / mockRejectedValue(...).
vi.mock("aws-amplify/auth", () => ({
    confirmResetPassword: vi.fn(),
    confirmSignIn: vi.fn(),
    fetchAuthSession: vi.fn(),
    fetchUserAttributes: vi.fn(),
    getCurrentUser: vi.fn(),
    resetPassword: vi.fn(),
    setUpTOTP: vi.fn(),
    signIn: vi.fn(),
    signOut: vi.fn(),
    updateMFAPreference: vi.fn(),
    verifyTOTPSetup: vi.fn()
}));

vi.mock("@/services/user-service", () => ({
    getMfaStatus: vi.fn(),
    getUserPermissions: vi.fn()
}));

// The store imports @/router only to call routeChange.gotoLogin from
// signOut — stub the module so importing it does not instantiate a real
// router with generated pages.
vi.mock("@/router", () => ({
    default: { push: vi.fn() },
    routeChange: { gotoLogin: vi.fn() }
}));

describe("authStore", () => {
    let store: ReturnType<typeof useAuthStore>;

    beforeEach(() => {
        setActivePinia(createPinia());
        store = useAuthStore();
        vi.mocked(signIn).mockReset();
        vi.mocked(confirmSignIn).mockReset();
        vi.mocked(signOut).mockReset();
        vi.mocked(getCurrentUser).mockReset();
        vi.mocked(fetchUserAttributes).mockReset();
        vi.mocked(setUpTOTP).mockReset();
        vi.mocked(verifyTOTPSetup).mockReset();
        vi.mocked(updateMFAPreference).mockReset();
        vi.mocked(resetPassword).mockReset();
        vi.mocked(confirmResetPassword).mockReset();
        vi.mocked(getMfaStatus).mockReset();
        vi.mocked(getUserPermissions).mockReset();
        vi.mocked(routeChange.gotoLogin).mockReset();
        vi.mocked(fetchAuthSession).mockReset();
        // Default: tokens are visible immediately so waitForSessionTokens
        // resolves without triggering the forceRefresh fallback. Tests that
        // exercise the race re-arm this with mockResolvedValueOnce.
        vi.mocked(fetchAuthSession).mockResolvedValue({
            tokens: { idToken: { toString: () => "id-token" } as never, accessToken: {} as never }
        } as never);
    });

    describe("initial state & getters", () => {
        it("initialises with nulls", () => {
            expect(store.user).toBeNull();
            expect(store.signInStep).toBeNull();
            expect(store.totpSetup).toBeNull();
            expect(store.mfaEnabled).toBeNull();
        });

        it("getUser returns the current user", () => {
            expect(store.getUser).toBeNull();
            store.user = {
                username: "u",
                userId: "id",
                attributes: { sub: "s", email: "e@f.com" },
                permissions: []
            };
            expect(store.getUser).toEqual(store.user);
        });

        it("confirmedUser is true only when DONE + user + mfaEnabled=true", () => {
            expect(store.confirmedUser).toBe(false);

            store.signInStep = "DONE";
            store.user = {
                username: "u",
                userId: "id",
                attributes: { sub: "s", email: "e@f.com" },
                permissions: []
            };
            store.mfaEnabled = true;
            expect(store.confirmedUser).toBe(true);

            store.mfaEnabled = false;
            expect(store.confirmedUser).toBe(false);

            store.mfaEnabled = null;
            expect(store.confirmedUser).toBe(false);
        });

        it("needsMfaEnrolment is true only when DONE + mfaEnabled=false", () => {
            expect(store.needsMfaEnrolment).toBe(false);

            store.signInStep = "DONE";
            store.mfaEnabled = false;
            expect(store.needsMfaEnrolment).toBe(true);

            store.mfaEnabled = true;
            expect(store.needsMfaEnrolment).toBe(false);

            store.mfaEnabled = null;
            expect(store.needsMfaEnrolment).toBe(false);
        });
    });

    describe("hydrate", () => {
        it("with mfa enabled, populates user with permissions via backend", async () => {
            vi.mocked(getCurrentUser).mockResolvedValue({
                username: "u",
                userId: "id"
            } as never);
            vi.mocked(getMfaStatus).mockResolvedValue({ enabled: true });
            vi.mocked(fetchUserAttributes).mockResolvedValue({
                sub: "s",
                email: "e@f.com"
            } as never);
            vi.mocked(getUserPermissions).mockResolvedValue({
                permissions: ["CanManageUsers"]
            });

            await store.hydrate();

            expect(store.signInStep).toBe("DONE");
            expect(store.mfaEnabled).toBe(true);
            expect(store.user).toEqual({
                username: "u",
                userId: "id",
                attributes: { sub: "s", email: "e@f.com" },
                permissions: ["CanManageUsers"]
            });
            expect(getUserPermissions).toHaveBeenCalledWith("id");
            expect(getMfaStatus).toHaveBeenCalledTimes(1);
        });

        it("defaults permissions to empty array when backend omits them", async () => {
            vi.mocked(getCurrentUser).mockResolvedValue({
                username: "u",
                userId: "id"
            } as never);
            vi.mocked(getMfaStatus).mockResolvedValue({ enabled: true });
            vi.mocked(fetchUserAttributes).mockResolvedValue({
                sub: "s",
                email: "e@f.com"
            } as never);
            // getUserPermissions returns an object with no permissions key
            vi.mocked(getUserPermissions).mockResolvedValue({} as never);

            await store.hydrate();

            expect(store.user?.permissions).toEqual([]);
        });

        it("with mfa disabled, skips permissions fetch and leaves permissions empty", async () => {
            vi.mocked(getCurrentUser).mockResolvedValue({
                username: "u",
                userId: "id"
            } as never);
            vi.mocked(getMfaStatus).mockResolvedValue({ enabled: false });
            vi.mocked(fetchUserAttributes).mockResolvedValue({
                sub: "s",
                email: "e@f.com"
            } as never);

            await store.hydrate();

            expect(store.signInStep).toBe("DONE");
            expect(store.mfaEnabled).toBe(false);
            expect(store.user).toEqual({
                username: "u",
                userId: "id",
                attributes: { sub: "s", email: "e@f.com" },
                permissions: []
            });
            expect(getUserPermissions).not.toHaveBeenCalled();
        });

        it("accepts a knownMfaEnabled override and skips the backend call", async () => {
            vi.mocked(getCurrentUser).mockResolvedValue({
                username: "u",
                userId: "id"
            } as never);
            vi.mocked(fetchUserAttributes).mockResolvedValue({
                sub: "s",
                email: "e@f.com"
            } as never);
            vi.mocked(getUserPermissions).mockResolvedValue({ permissions: [] });

            await store.hydrate(true);

            expect(getMfaStatus).not.toHaveBeenCalled();
            expect(store.mfaEnabled).toBe(true);
        });
    });

    describe("fetchInfo", () => {
        it("delegates to hydrate", async () => {
            vi.mocked(getCurrentUser).mockResolvedValue({
                username: "u",
                userId: "id"
            } as never);
            vi.mocked(getMfaStatus).mockResolvedValue({ enabled: false });
            vi.mocked(fetchUserAttributes).mockResolvedValue({
                sub: "s",
                email: "e@f.com"
            } as never);

            await store.fetchInfo();

            expect(store.signInStep).toBe("DONE");
            expect(store.mfaEnabled).toBe(false);
        });
    });

    describe("finaliseSignIn", () => {
        it("delegates to hydrate", async () => {
            vi.mocked(getCurrentUser).mockResolvedValue({
                username: "u",
                userId: "id"
            } as never);
            vi.mocked(getMfaStatus).mockResolvedValue({ enabled: true });
            vi.mocked(fetchUserAttributes).mockResolvedValue({
                sub: "s",
                email: "e@f.com"
            } as never);
            vi.mocked(getUserPermissions).mockResolvedValue({ permissions: [] });

            await store.finaliseSignIn();

            expect(store.signInStep).toBe("DONE");
            expect(store.mfaEnabled).toBe(true);
        });
    });

    describe("signIn", () => {
        it("resets state then hydrates when Amplify reports isSignedIn", async () => {
            // Pre-set state that must be cleared before sign-in runs.
            store.user = {
                username: "stale",
                userId: "stale",
                attributes: { sub: "", email: "" },
                permissions: []
            };
            store.signInStep = "DONE";
            store.mfaEnabled = true;
            vi.mocked(signIn).mockResolvedValue({
                isSignedIn: true,
                nextStep: { signInStep: "DONE" }
            } as never);
            vi.mocked(getCurrentUser).mockResolvedValue({
                username: "u",
                userId: "id"
            } as never);
            vi.mocked(getMfaStatus).mockResolvedValue({ enabled: true });
            vi.mocked(fetchUserAttributes).mockResolvedValue({
                sub: "s",
                email: "e@f.com"
            } as never);
            vi.mocked(getUserPermissions).mockResolvedValue({ permissions: [] });

            await store.signIn({ username: "u", password: "p" });

            expect(signIn).toHaveBeenCalledWith({
                username: "u",
                password: "p",
                options: { authFlowType: "USER_PASSWORD_AUTH" }
            });
            expect(store.signInStep).toBe("DONE");
            expect(store.mfaEnabled).toBe(true);
            expect(store.user?.username).toBe("u");
        });

        it("captures TOTP setup details when Cognito demands first-time enrolment", async () => {
            const setupUri = new URL("otpauth://totp/FLIP:u?secret=ABCD");
            vi.mocked(signIn).mockResolvedValue({
                isSignedIn: false,
                nextStep: {
                    signInStep: "CONTINUE_SIGN_IN_WITH_TOTP_SETUP",
                    totpSetupDetails: {
                        sharedSecret: "ABCD",
                        getSetupUri: vi.fn(() => setupUri)
                    }
                }
            } as never);

            await store.signIn({ username: "u", password: "p" });

            expect(store.signInStep).toBe("CONTINUE_SIGN_IN_WITH_TOTP_SETUP");
            expect(store.totpSetup).toEqual({
                sharedSecret: "ABCD",
                setupUri: setupUri.toString()
            });
            // Did NOT hydrate — we're mid-challenge.
            expect(getCurrentUser).not.toHaveBeenCalled();
        });

        it("returns early for new-password challenge without hydrating", async () => {
            vi.mocked(signIn).mockResolvedValue({
                isSignedIn: false,
                nextStep: {
                    signInStep: "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED"
                }
            } as never);

            await store.signIn({ username: "u", password: "p" });

            expect(store.signInStep).toBe("CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED");
            expect(getCurrentUser).not.toHaveBeenCalled();
        });

        it("returns early for TOTP-code challenge without hydrating", async () => {
            vi.mocked(signIn).mockResolvedValue({
                isSignedIn: false,
                nextStep: { signInStep: "CONFIRM_SIGN_IN_WITH_TOTP_CODE" }
            } as never);

            await store.signIn({ username: "u", password: "p" });

            expect(store.signInStep).toBe("CONFIRM_SIGN_IN_WITH_TOTP_CODE");
            expect(getCurrentUser).not.toHaveBeenCalled();
        });

        it("tolerates a response with no nextStep", async () => {
            vi.mocked(signIn).mockResolvedValue({
                isSignedIn: false,
                nextStep: undefined
            } as never);

            await store.signIn({ username: "u", password: "p" });

            expect(store.signInStep).toBeNull();
            expect(getCurrentUser).not.toHaveBeenCalled();
        });

        it("forces a session refresh when tokens are not yet visible after signIn", async () => {
            // Amplify v6 can resolve signIn before fetchAuthSession sees the
            // cached tokens; this race used to surface as a 401 on the very
            // first post-signIn backend call. Arm fetchAuthSession to return
            // empty on the first read, then populated on the forceRefresh
            // retry, and confirm hydrate still runs to completion.
            vi.mocked(fetchAuthSession)
                .mockReset()
                .mockResolvedValueOnce({ tokens: undefined } as never)
                .mockResolvedValueOnce({
                    tokens: { idToken: { toString: () => "id" } as never }
                } as never);
            vi.mocked(signIn).mockResolvedValue({
                isSignedIn: true,
                nextStep: { signInStep: "DONE" }
            } as never);
            vi.mocked(getCurrentUser).mockResolvedValue({
                username: "u",
                userId: "id"
            } as never);
            vi.mocked(getMfaStatus).mockResolvedValue({ enabled: true });
            vi.mocked(fetchUserAttributes).mockResolvedValue({
                sub: "s",
                email: "e@f.com"
            } as never);
            vi.mocked(getUserPermissions).mockResolvedValue({ permissions: [] });

            await store.signIn({ username: "u", password: "p" });

            expect(fetchAuthSession).toHaveBeenCalledTimes(2);
            expect(fetchAuthSession).toHaveBeenNthCalledWith(2, { forceRefresh: true });
            expect(store.user?.username).toBe("u");
        });

        it("rethrows post-signIn hydrate failures so Login.vue surfaces them", async () => {
            // Cognito accepted the creds (isSignedIn=true) but the follow-up
            // backend call failed. The store must log the underlying error and
            // rethrow so the login page can tell the user something went wrong
            // — silently resolving here lets a broken session masquerade as
            // success and the next route-guarded call 401s.
            vi.mocked(signIn).mockResolvedValue({
                isSignedIn: true,
                nextStep: { signInStep: "DONE" }
            } as never);
            vi.mocked(getCurrentUser).mockResolvedValue({
                username: "u",
                userId: "id"
            } as never);
            vi.mocked(getMfaStatus).mockRejectedValue(
                new Error("Request failed with status code 401")
            );
            const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

            await expect(
                store.signIn({ username: "u", password: "p" })
            ).rejects.toThrow("Request failed with status code 401");

            expect(consoleSpy).toHaveBeenCalledWith(
                "Post-signIn hydrate failed:",
                expect.objectContaining({ message: "Request failed with status code 401" }),
                expect.any(Object)
            );
            consoleSpy.mockRestore();
        });
    });

    describe("changePassword", () => {
        it("hydrates after a successful password change", async () => {
            vi.mocked(confirmSignIn).mockResolvedValue({
                isSignedIn: true,
                nextStep: { signInStep: "DONE" }
            } as never);
            vi.mocked(getCurrentUser).mockResolvedValue({
                username: "u",
                userId: "id"
            } as never);
            vi.mocked(getMfaStatus).mockResolvedValue({ enabled: false });
            vi.mocked(fetchUserAttributes).mockResolvedValue({
                sub: "s",
                email: "e@f.com"
            } as never);

            await store.changePassword("newPassword123!");

            expect(confirmSignIn).toHaveBeenCalledWith({
                challengeResponse: "newPassword123!"
            });
            expect(store.signInStep).toBe("DONE");
            expect(store.mfaEnabled).toBe(false);
        });

        it("captures TOTP setup details when next step is MFA setup", async () => {
            const setupUri = new URL("otpauth://totp/FLIP:u?secret=XYZ");
            vi.mocked(confirmSignIn).mockResolvedValue({
                isSignedIn: false,
                nextStep: {
                    signInStep: "CONTINUE_SIGN_IN_WITH_TOTP_SETUP",
                    totpSetupDetails: {
                        sharedSecret: "XYZ",
                        getSetupUri: vi.fn(() => setupUri)
                    }
                }
            } as never);

            await store.changePassword("newPassword123!");

            expect(store.signInStep).toBe("CONTINUE_SIGN_IN_WITH_TOTP_SETUP");
            expect(store.totpSetup).toEqual({
                sharedSecret: "XYZ",
                setupUri: setupUri.toString()
            });
            expect(getCurrentUser).not.toHaveBeenCalled();
        });

        it("does nothing special on unknown step + not signed in", async () => {
            vi.mocked(confirmSignIn).mockResolvedValue({
                isSignedIn: false,
                nextStep: { signInStep: "DONE" }
            } as never);

            await store.changePassword("newPassword123!");

            expect(store.signInStep).toBe("DONE");
            expect(getCurrentUser).not.toHaveBeenCalled();
        });
    });

    describe("confirmTotpChallenge", () => {
        it("returns early when Cognito reports not signed in", async () => {
            vi.mocked(confirmSignIn).mockResolvedValue({
                isSignedIn: false,
                nextStep: undefined
            } as never);

            await store.confirmTotpChallenge("123456");

            expect(store.signInStep).toBeNull();
            expect(getCurrentUser).not.toHaveBeenCalled();
        });

        it("hydrates with known-true MFA when challenge clears", async () => {
            vi.mocked(confirmSignIn).mockResolvedValue({
                isSignedIn: true,
                nextStep: undefined
            } as never);
            vi.mocked(getCurrentUser).mockResolvedValue({
                username: "u",
                userId: "id"
            } as never);
            vi.mocked(fetchUserAttributes).mockResolvedValue({
                sub: "s",
                email: "e@f.com"
            } as never);
            vi.mocked(getUserPermissions).mockResolvedValue({ permissions: [] });

            await store.confirmTotpChallenge("123456");

            // Did NOT call getMfaStatus — hydrate(true) short-circuits it.
            expect(getMfaStatus).not.toHaveBeenCalled();
            expect(store.signInStep).toBe("DONE");
            expect(store.mfaEnabled).toBe(true);
        });

        it("swallows post-success hydrate failures and leaves mfaEnabled=null", async () => {
            vi.mocked(confirmSignIn).mockResolvedValue({
                isSignedIn: true,
                nextStep: undefined
            } as never);
            vi.mocked(getCurrentUser).mockRejectedValue(new Error("Network Error"));
            const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

            await expect(store.confirmTotpChallenge("123456")).resolves.toBeUndefined();

            expect(store.signInStep).toBe("DONE");
            expect(store.mfaEnabled).toBeNull();
            expect(consoleSpy).toHaveBeenCalled();
            consoleSpy.mockRestore();
        });
    });

    describe("confirmTotpSetup", () => {
        it("returns early when Cognito reports not signed in", async () => {
            vi.mocked(confirmSignIn).mockResolvedValue({
                isSignedIn: false,
                nextStep: undefined
            } as never);

            await store.confirmTotpSetup("123456");

            expect(updateMFAPreference).not.toHaveBeenCalled();
            expect(store.totpSetup).toBeNull();
        });

        it("sets MFA preference, clears totpSetup, then hydrates with known-true MFA", async () => {
            store.totpSetup = { sharedSecret: "ABC", setupUri: "otpauth://..." };
            vi.mocked(confirmSignIn).mockResolvedValue({
                isSignedIn: true,
                nextStep: undefined
            } as never);
            vi.mocked(updateMFAPreference).mockResolvedValue(undefined as never);
            vi.mocked(getCurrentUser).mockResolvedValue({
                username: "u",
                userId: "id"
            } as never);
            vi.mocked(fetchUserAttributes).mockResolvedValue({
                sub: "s",
                email: "e@f.com"
            } as never);
            vi.mocked(getUserPermissions).mockResolvedValue({ permissions: [] });

            await store.confirmTotpSetup("123456");

            expect(updateMFAPreference).toHaveBeenCalledWith({ totp: "PREFERRED" });
            expect(store.totpSetup).toBeNull();
            expect(store.mfaEnabled).toBe(true);
            expect(store.signInStep).toBe("DONE");
            expect(getMfaStatus).not.toHaveBeenCalled();
        });

        it("swallows updateMFAPreference failure but still hydrates", async () => {
            vi.mocked(confirmSignIn).mockResolvedValue({
                isSignedIn: true,
                nextStep: undefined
            } as never);
            vi.mocked(updateMFAPreference).mockRejectedValue(
                new Error("Cognito boom")
            );
            vi.mocked(getCurrentUser).mockResolvedValue({
                username: "u",
                userId: "id"
            } as never);
            vi.mocked(fetchUserAttributes).mockResolvedValue({
                sub: "s",
                email: "e@f.com"
            } as never);
            vi.mocked(getUserPermissions).mockResolvedValue({ permissions: [] });
            const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

            await expect(store.confirmTotpSetup("123456")).resolves.toBeUndefined();

            expect(consoleSpy).toHaveBeenCalledWith(
                "Failed to set MFA preference post-setup:",
                expect.any(Error)
            );
            expect(store.mfaEnabled).toBe(true);
            consoleSpy.mockRestore();
        });

        it("swallows hydrate failure and leaves mfaEnabled=null for router guard", async () => {
            vi.mocked(confirmSignIn).mockResolvedValue({
                isSignedIn: true,
                nextStep: undefined
            } as never);
            vi.mocked(updateMFAPreference).mockResolvedValue(undefined as never);
            vi.mocked(getCurrentUser).mockRejectedValue(new Error("Network"));
            const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

            await expect(store.confirmTotpSetup("123456")).resolves.toBeUndefined();

            expect(consoleSpy).toHaveBeenCalledWith(
                "Failed to hydrate user post-MFA setup:",
                expect.any(Error)
            );
            expect(store.signInStep).toBe("DONE");
            expect(store.mfaEnabled).toBeNull();
            consoleSpy.mockRestore();
        });
    });

    describe("captureTotpSetupDetails", () => {
        it("uses pendingUsername as the account label, not the sharedSecret", () => {
            const url = new URL("otpauth://totp/FLIP:u?secret=SEC");
            const getSetupUri = vi.fn(() => url);
            store.pendingUsername = "u@e.com";
            store.captureTotpSetupDetails({
                totpSetupDetails: { sharedSecret: "SEC", getSetupUri }
            });

            expect(getSetupUri).toHaveBeenCalledWith("FLIP", "u@e.com");
            expect(store.totpSetup).toEqual({
                sharedSecret: "SEC",
                setupUri: url.toString()
            });
        });

        it("omits the account label when pendingUsername is null", () => {
            const url = new URL("otpauth://totp/FLIP?secret=SEC");
            const getSetupUri = vi.fn(() => url);
            store.pendingUsername = null;
            store.captureTotpSetupDetails({
                totpSetupDetails: { sharedSecret: "SEC", getSetupUri }
            });

            expect(getSetupUri).toHaveBeenCalledWith("FLIP", undefined);
        });

        it("is a no-op when totpSetupDetails are missing", () => {
            store.captureTotpSetupDetails({});
            expect(store.totpSetup).toBeNull();

            store.captureTotpSetupDetails({ totpSetupDetails: undefined });
            expect(store.totpSetup).toBeNull();
        });
    });

    describe("beginMfaEnrolment", () => {
        it("records shared secret and setup URI from Amplify", async () => {
            const url = new URL("otpauth://totp/FLIP:u?secret=SEC");
            const getSetupUri = vi.fn(() => url);
            vi.mocked(setUpTOTP).mockResolvedValue({
                sharedSecret: "SEC",
                getSetupUri
            } as never);
            store.user = {
                username: "u",
                userId: "id",
                attributes: { sub: "s", email: "e@f.com" },
                permissions: []
            };

            await store.beginMfaEnrolment();

            expect(getSetupUri).toHaveBeenCalledWith("FLIP", "e@f.com");
            expect(store.totpSetup).toEqual({
                sharedSecret: "SEC",
                setupUri: url.toString()
            });
        });

        it("falls back to empty string when Amplify omits sharedSecret", async () => {
            const url = new URL("otpauth://totp/FLIP:u");
            vi.mocked(setUpTOTP).mockResolvedValue({
                sharedSecret: undefined,
                getSetupUri: vi.fn(() => url)
            } as never);
            // No user in the store — appName arg should still be "FLIP" and
            // email undefined (we just want the call not to crash).
            await store.beginMfaEnrolment();

            expect(store.totpSetup?.sharedSecret).toBe("");
        });
    });

    describe("completeMfaEnrolment", () => {
        it("verifies code, sets MFA preference, clears setup, and hydrates known-true", async () => {
            store.totpSetup = { sharedSecret: "ABC", setupUri: "otpauth://..." };
            vi.mocked(verifyTOTPSetup).mockResolvedValue(undefined as never);
            vi.mocked(updateMFAPreference).mockResolvedValue(undefined as never);
            vi.mocked(getCurrentUser).mockResolvedValue({
                username: "u",
                userId: "id"
            } as never);
            vi.mocked(fetchUserAttributes).mockResolvedValue({
                sub: "s",
                email: "e@f.com"
            } as never);
            vi.mocked(getUserPermissions).mockResolvedValue({ permissions: [] });

            await store.completeMfaEnrolment("123456");

            expect(verifyTOTPSetup).toHaveBeenCalledWith({ code: "123456" });
            expect(updateMFAPreference).toHaveBeenCalledWith({ totp: "PREFERRED" });
            expect(store.totpSetup).toBeNull();
            expect(store.mfaEnabled).toBe(true);
            expect(store.signInStep).toBe("DONE");
        });

        it("propagates verifyTOTPSetup errors (invalid code)", async () => {
            vi.mocked(verifyTOTPSetup).mockRejectedValue(new Error("Invalid code"));

            await expect(store.completeMfaEnrolment("000000")).rejects.toThrow(
                "Invalid code"
            );
            expect(updateMFAPreference).not.toHaveBeenCalled();
        });

        it("swallows updateMFAPreference failure but still hydrates", async () => {
            vi.mocked(verifyTOTPSetup).mockResolvedValue(undefined as never);
            vi.mocked(updateMFAPreference).mockRejectedValue(new Error("Boom"));
            vi.mocked(getCurrentUser).mockResolvedValue({
                username: "u",
                userId: "id"
            } as never);
            vi.mocked(fetchUserAttributes).mockResolvedValue({
                sub: "s",
                email: "e@f.com"
            } as never);
            vi.mocked(getUserPermissions).mockResolvedValue({ permissions: [] });
            const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

            await store.completeMfaEnrolment("123456");

            expect(consoleSpy).toHaveBeenCalledWith(
                "Failed to set MFA preference post-enrolment:",
                expect.any(Error)
            );
            expect(store.mfaEnabled).toBe(true);
            consoleSpy.mockRestore();
        });

        it("swallows hydrate failure and leaves mfaEnabled=null", async () => {
            vi.mocked(verifyTOTPSetup).mockResolvedValue(undefined as never);
            vi.mocked(updateMFAPreference).mockResolvedValue(undefined as never);
            vi.mocked(getCurrentUser).mockRejectedValue(new Error("Network"));
            const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

            await store.completeMfaEnrolment("123456");

            expect(consoleSpy).toHaveBeenCalledWith(
                "Failed to hydrate user post-MFA enrolment:",
                expect.any(Error)
            );
            expect(store.signInStep).toBe("DONE");
            expect(store.mfaEnabled).toBeNull();
            consoleSpy.mockRestore();
        });
    });

    describe("signOut", () => {
        it("calls Amplify global sign-out, resets store, and routes to login", async () => {
            vi.mocked(signOut).mockResolvedValue(undefined as never);
            store.user = {
                username: "u",
                userId: "id",
                attributes: { sub: "s", email: "e@f.com" },
                permissions: []
            };
            store.signInStep = "DONE";

            await store.signOut();

            expect(signOut).toHaveBeenCalledWith({ global: true });
            expect(store.user).toBeNull();
            expect(store.signInStep).toBeNull();
            expect(routeChange.gotoLogin).toHaveBeenCalledTimes(1);
        });

        it("still resets state and routes to login when Amplify signOut throws", async () => {
            vi.mocked(signOut).mockRejectedValue(new Error("network"));
            const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
            store.user = {
                username: "u",
                userId: "id",
                attributes: { sub: "s", email: "e@f.com" },
                permissions: []
            };

            await store.signOut();

            expect(consoleSpy).toHaveBeenCalledWith(
                "Sign out error:",
                expect.any(Error)
            );
            expect(store.user).toBeNull();
            expect(routeChange.gotoLogin).toHaveBeenCalledTimes(1);
            consoleSpy.mockRestore();
        });
    });

    describe("resetPassword", () => {
        it("proxies to Amplify resetPassword with web-app metadata", async () => {
            const amplifyResponse = { isPasswordReset: false } as never;
            vi.mocked(resetPassword).mockResolvedValue(amplifyResponse);

            const result = await store.resetPassword("u@e.com");

            expect(resetPassword).toHaveBeenCalledWith({
                username: "u@e.com",
                options: { clientMetadata: { source: "web-app" } }
            });
            expect(result).toBe(amplifyResponse);
        });
    });

    describe("updateForgottenPassword", () => {
        it("proxies to Amplify confirmResetPassword with web-app metadata", async () => {
            const amplifyResponse = undefined as never;
            vi.mocked(confirmResetPassword).mockResolvedValue(amplifyResponse);

            const result = await store.updateForgottenPassword({
                email: "u@e.com",
                code: "123456",
                newPassword: "new-pw!"
            });

            expect(confirmResetPassword).toHaveBeenCalledWith({
                username: "u@e.com",
                confirmationCode: "123456",
                newPassword: "new-pw!",
                options: { clientMetadata: { source: "web-app" } }
            });
            expect(result).toBe(amplifyResponse);
        });
    });

    describe("hasPermissions", () => {
        it("returns true when user has every required permission", () => {
            store.user = {
                username: "u",
                userId: "id",
                attributes: { sub: "s", email: "e@f.com" },
                permissions: ["CanManageUsers", "CanManageProjects"]
            };

            expect(store.hasPermissions(["CanManageUsers"])).toBe(true);
            expect(
                store.hasPermissions(["CanManageUsers", "CanManageProjects"])
            ).toBe(true);
        });

        it("returns false when any required permission is missing", () => {
            store.user = {
                username: "u",
                userId: "id",
                attributes: { sub: "s", email: "e@f.com" },
                permissions: ["CanManageUsers"]
            };

            expect(store.hasPermissions(["CanManageProjects"])).toBe(false);
            expect(
                store.hasPermissions(["CanManageUsers", "CanManageProjects"])
            ).toBe(false);
        });

        it("returns true for an empty permissions list (vacuously satisfied)", () => {
            store.user = {
                username: "u",
                userId: "id",
                attributes: { sub: "s", email: "e@f.com" },
                permissions: []
            };

            expect(store.hasPermissions([])).toBe(true);
        });

        it("returns false when user is null", () => {
            expect(store.hasPermissions(["CanManageUsers"])).toBe(false);
        });
    });
});
