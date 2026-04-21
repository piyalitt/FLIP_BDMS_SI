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

import { fetchAuthSession } from "aws-amplify/auth";
import { Hub } from "aws-amplify/utils";
import { StoreGeneric } from "pinia";
import { NavigationGuardNext, RouteLocationNormalized } from "vue-router";

import router, { routeChange } from "@/router";
import { useAuthStore } from "@/store/auth";
import { useErrorStore } from "@/store/error";

import { Snackbar } from "./snackbar";

/**
 * By default all routes are guarded and authentication is required.
 * This serves as an allowed list of routes which will bypass the auth check.
 * @type {string[]}
 */
const unguardedRoutes: string[] = [
    "/auth/login",
    "/auth/new-password",
    "/auth/change-password",
    "/auth/access-request",
    "/auth/mfa-setup",
    "/auth/mfa-verify",
    "/privacy-policy",
    "/terms-of-service"
];

/**
 * Checks auth status for the requested route.
 * Bypasses check for any routes that are included in the unguarded routes list.
 * On any error getting the authenticated user:
 * 1. clear down any existing auth state
 * 2. clear localStorage (aws-amplify stores tokens here)
 * 3. Redirect to login page
 * 4. Give the user some indication as to what's going on
 */
export const authCheck = async (
    to: RouteLocationNormalized,
    _from: RouteLocationNormalized,
    next: NavigationGuardNext
): Promise<void> => {
    const errorStore = useErrorStore();
    const auth = useAuthStore();

    try {
        errorStore.clearError();

        if (unguardedRoutes.includes(to.path)) {
            return next();
        }

        if (process.env.VITE_LOCAL === "true") {
            return next();
        }

        // Check if user has a valid session
        try {
            await fetchAuthSession();
        } catch {
            // No valid session, redirect to login
            auth.user = null;
            auth.signInStep = null;
            return next("/auth/login");
        }

        // If we are in new-password challenge
        if (auth.signInStep === 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED') {
            return next('/auth/new-password');
        }

        // First-time MFA enrollment (TOTP setup with QR code), sign-in chain
        if (auth.signInStep === 'CONTINUE_SIGN_IN_WITH_TOTP_SETUP') {
            return next('/auth/mfa-setup');
        }

        // Returning user — enter the code from their authenticator app
        if (auth.signInStep === 'CONFIRM_SIGN_IN_WITH_TOTP_CODE') {
            return next('/auth/mfa-verify');
        }

        // Load user info if needed (page reload after sign-in). This also
        // populates `mfaEnabled` from the backend so the MFA-gate check
        // below has a definitive answer to work with.
        if (!auth.user || auth.mfaEnabled === null) {
            await auth.fetchInfo();
        }

        // Admin-reset users (or anyone Cognito signed in without MFA)
        // can only reach the enrolment page until they finish setup.
        if (auth.mfaEnabled === false && to.path !== '/auth/mfa-setup') {
            return next('/auth/mfa-setup');
        }

        return next();

    } catch (error) {
        auth.$reset();
        localStorage.clear();
        routeChange.gotoLogin();
        Snackbar.error({
            title: "You've been signed out",
            text: "Please log in again to confirm your identity."
        });
    }
};

export const isUserUnconfirmedCheck = async (
    authStore: StoreGeneric
): Promise<boolean> => {
    // True only when the caller is genuinely in the new-password
    // challenge step this page handles. Everything else — fully signed
    // in, mid-TOTP, signed out, or a challenge we don't own — should be
    // redirected away by the caller (usually to viewProjects, where the
    // router guard sorts them out).
    return authStore.signInStep === "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED";
};

export const apiGateway = "CentralHubAPIGateway";

const devMode = process.env.NODE_ENV === "development";

// Read Cognito config at runtime from window.* (populated by public/js/window.js
// in dev and dist/js/window.js in prod — both loaded synchronously before main.ts).
// `process.env.VITE_*` is substituted at build time by vite; in the deploy build
// those vars are unset and vite folds them to `undefined`, which makes Amplify
// throw "Auth UserPool not configured" at signIn. `window.*` is the single
// runtime source of truth — matches the pattern `api.ts` uses for AWS_BASE_URL.
export const authConfig = {
    Auth: {
        Cognito: {
            region: window.AWS_REGION || process.env.VITE_AWS_REGION || 'eu-west-2',
            userPoolId: window.AWS_USER_POOL_ID || process.env.VITE_AWS_USER_POOL_ID,
            userPoolClientId: window.AWS_CLIENT_ID || process.env.VITE_AWS_CLIENT_ID
        }
    }
};

let tokenRefreshTimeout = 0;

// Routes where a tokenRefresh_failure or background 401 must NOT force
// the user to log in. Two classes of page:
//   1. No session exists yet — login, new-password (pre-auth challenge),
//      change-password (forgot-password flow), access-request. Amplify
//      emits `tokenRefresh_failure` periodically on these because there
//      are no tokens to refresh; forwarding that to gotoLogin would
//      interrupt the user mid-form (e.g. filling in a reset code).
//   2. Mid-challenge flows — mfa-setup, mfa-verify. A yank to login
//      would lose challenge state or interrupt TOTP enrolment.
export const NO_FORCED_SIGNOUT_PATHS = new Set<string>([
    "/auth/login",
    "/auth/new-password",
    "/auth/change-password",
    "/auth/access-request",
    "/auth/mfa-setup",
    "/auth/mfa-verify"
]);

const listener = (data: { payload: { event: string } }) => {
    const store = useAuthStore();

    switch (data.payload.event) {
        case "tokenRefresh_failure":
            // Compare against path (no query/fragment) so a whitelisted
            // route with a `?redirect=...` or `#frag` still skips the
            // forced sign-out. `fullPath` would miss the membership test.
            if (NO_FORCED_SIGNOUT_PATHS.has(router.currentRoute.value.path)) {
                break;
            }

            if (tokenRefreshTimeout) {
                clearTimeout(tokenRefreshTimeout);
                tokenRefreshTimeout = 0;
            }

            tokenRefreshTimeout = window.setTimeout(() => {
                Snackbar.error({
                    title: "You've been signed out",
                    text: "Your session has expired. Please log in again."
                }, 60_000);

                routeChange.gotoLogin();
                store.$reset();
            }, 100);
            break;
    }
};

Hub.listen("auth", listener);
