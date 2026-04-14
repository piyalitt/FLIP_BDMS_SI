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
    signIn,
    signOut
} from "aws-amplify/auth";

import { defineStore } from "pinia";

import { IChangePassword } from "@/interfaces/auth/interfaces";
import { routeChange } from "@/router";
import { getUserPermissions, revokeToken } from "@/services/user-service";

/**
 * Available User Permissions
 */
export type UserPermissions =
    | "CanManageUsers"
    | "CanManageProjects"
    | "CanApproveProjects"
    | "CanDeleteAnyProject"
    | "CanUnstageProjects"
    | "CanManageSiteBanner"
    | "CanManageDeployments"
    | "CanAccessAdminPanel";

type Attributes = {
    sub: string;
    email: string;
};

type AmplifyUser = {
  username: string;
  userId: string;
  attributes: Attributes;
  permissions: string[];
};

type UserCredentials = {
    username: string;
    password: string;
};

/**
 * Sign-in steps for the user.
 * - "DONE" means fully signed in.
 * - "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED" indicates the user needs to set a new password.
 * - "CONTINUE_SIGN_IN_WITH_TOTP_SETUP" indicates the user must enroll an authenticator (QR + code).
 * - "CONFIRM_SIGN_IN_WITH_TOTP_CODE" indicates the user has MFA enabled and must enter a code.
 * - Other strings can be used for additional steps as needed.
 */
type SignInStep =
    | "DONE"
    | "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED"
    | "CONTINUE_SIGN_IN_WITH_TOTP_SETUP"
    | "CONFIRM_SIGN_IN_WITH_TOTP_CODE"
    | string;

/**
 * TOTP setup details returned by Cognito/Amplify during MFA enrollment.
 * `setupUri` is a `otpauth://` URL suitable for rendering as a QR code;
 * `sharedSecret` is the base32 secret users can type manually.
 */
type TotpSetupDetails = {
    sharedSecret: string;
    setupUri: string;
};

type AuthState = {
  user: AmplifyUser | null;
  signInStep: SignInStep | null; // track v6 nextStep
  totpSetup: TotpSetupDetails | null;
};

const buildUserWithPermissions = async (
  base: Pick<AmplifyUser, "username" | "userId">
): Promise<AmplifyUser> => {
  const attributes = (await fetchUserAttributes()) as Attributes;
  const permsRes = await getUserPermissions(attributes.sub);

  return {
    ...base,
    attributes,
    permissions: permsRes.permissions ?? []
  };
};


export const useAuthStore = defineStore("auth", {
    state: (): AuthState => ({
        user: null,
        signInStep: null,
        totpSetup: null
    }),

    getters: {
        getUser: (state) => state.user,
        confirmedUser: (state) => state.signInStep === "DONE" && !!state.user
    },
    actions: {
        async fetchInfo() {
            // Get the currently signed-in user (no sign-in step here)
            const { username, userId } = await getCurrentUser();
            this.user = await buildUserWithPermissions({ username, userId });
            this.signInStep = "DONE";
        },

        async signIn(details: UserCredentials) {
            // Always clear stale user state at the start of login
            this.user = null;
            this.signInStep = null;
            this.totpSetup = null;

            const out = await signIn({
                username: details.username,
                password: details.password
            });

            // Extract next step
            const step = out.nextStep?.signInStep as SignInStep | undefined;

            if (step) {
                this.signInStep = step;
            }

            // NEW PASSWORD REQUIRED
            if (step === "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED") {
                // No session exists yet — do not try to fetch user info
                return;
            }

            // TOTP ENROLLMENT REQUIRED (first-time MFA setup)
            if (step === "CONTINUE_SIGN_IN_WITH_TOTP_SETUP") {
                // Amplify provides a TotpSetupDetails object with getSetupUri()
                // and sharedSecret. We surface both so the setup page can render
                // a QR code and a copy-paste fallback.
                const details = (out.nextStep as { totpSetupDetails?: {
                    sharedSecret: string;
                    getSetupUri: (appName: string, username?: string) => URL;
                } }).totpSetupDetails;
                if (details) {
                    this.totpSetup = {
                        sharedSecret: details.sharedSecret,
                        setupUri: details.getSetupUri("FLIP", details.sharedSecret).toString()
                    };
                }
                return;
            }

            // TOTP CODE CHALLENGE (user already enrolled)
            if (step === "CONFIRM_SIGN_IN_WITH_TOTP_CODE") {
                return;
            }

            if (out.isSignedIn) {
                // Fully signed in
                const { username, userId } = await getCurrentUser();
                this.user = await buildUserWithPermissions({ username, userId });
                this.signInStep = "DONE";
                return;
            }
        },

        async changePassword(newPassword: string) {
            const out = await confirmSignIn({ challengeResponse: newPassword });

            // After a new password, Cognito may chain into a TOTP setup step
            // (because mfa_configuration = "ON" on the user pool). Honour the
            // nextStep instead of assuming the user is signed in.
            const step = out.nextStep?.signInStep as SignInStep | undefined;
            if (step) {
                this.signInStep = step;
            }

            if (step === "CONTINUE_SIGN_IN_WITH_TOTP_SETUP") {
                const details = (out.nextStep as { totpSetupDetails?: {
                    sharedSecret: string;
                    getSetupUri: (appName: string, username?: string) => URL;
                } }).totpSetupDetails;
                if (details) {
                    this.totpSetup = {
                        sharedSecret: details.sharedSecret,
                        setupUri: details.getSetupUri("FLIP", details.sharedSecret).toString()
                    };
                }
                return;
            }

            if (out.isSignedIn) {
                const { username, userId } = await getCurrentUser();
                this.user = await buildUserWithPermissions({ username, userId });
                this.signInStep = "DONE";
            }
        },

        async confirmTotpSetup(code: string) {
            const out = await confirmSignIn({ challengeResponse: code });

            if (out.isSignedIn) {
                const { username, userId } = await getCurrentUser();
                this.user = await buildUserWithPermissions({ username, userId });
                this.signInStep = "DONE";
                this.totpSetup = null;
            }
        },

        async confirmTotpChallenge(code: string) {
            const out = await confirmSignIn({ challengeResponse: code });

            if (out.isSignedIn) {
                const { username, userId } = await getCurrentUser();
                this.user = await buildUserWithPermissions({ username, userId });
                this.signInStep = "DONE";
            }
        },

        async signOut() {
            try {
                const session = await fetchAuthSession();
                const refreshToken = session.tokens?.refreshToken?.toString();

                await signOut({ global: true });

                if (refreshToken) {
                    await revokeToken(refreshToken);
                }
            } catch (error) {
                console.error("Sign out error:", error);
            }

            this.$reset();
            routeChange.gotoLogin();
        },

        async resetPassword(email: string) {
            const response = await resetPassword({
                username: email,
                options: {
                clientMetadata: {
                    source: "web-app"
                }
                }
            });
            return response;
        },

        async updateForgottenPassword({ email, code, newPassword }: IChangePassword) {
            const response = await confirmResetPassword({
                username: email,
                confirmationCode: code,
                newPassword,
                options: {
                    clientMetadata: {
                        source: "web-app"
                    }
                }
            });
            return response;
        },

        hasPermissions(permissions: UserPermissions[]) {
            return permissions.every(perm => this.user?.permissions?.includes(perm));
        }
    }
});
