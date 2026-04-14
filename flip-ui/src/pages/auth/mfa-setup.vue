<!--
    Copyright (c) 2026 Guy's and St Thomas' NHS Foundation Trust & King's College London
    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at
        http://www.apache.org/licenses/LICENSE-2.0
    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
-->

<route lang="yaml">
meta:
    layout: AuthLayout
</route>

<template>
    <section class="flex flex-col h-full">
        <h1 class="mb-3 text-xl font-heading md:text-2xl">
            Set up two-factor authentication
        </h1>
        <p class="mb-4 text-sm">
            Scan the QR code below with an authenticator app
            (Google Authenticator, Authy, 1Password, etc.), then enter the
            6-digit code to finish setting up your account.
        </p>
        <div v-if="qrDataUrl" class="flex justify-center mb-4">
            <img
                :src="qrDataUrl"
                alt="TOTP QR code"
                class="w-48 h-48 border border-gray-200 rounded"
                data-test="mfa-qr-code"
            />
        </div>
        <details v-if="sharedSecret" class="mb-4 text-sm">
            <summary class="cursor-pointer">Can't scan? Enter this secret manually</summary>
            <code
                class="block px-2 py-1 mt-2 font-mono break-all bg-gray-100 rounded dark:bg-gray-800"
                data-test="mfa-shared-secret"
            >{{ sharedSecret }}</code>
        </details>
        <Form
            :validation-schema="schema"
            class="flex flex-col flex-grow p-0 space-y-4"
            @submit="submit"
        >
            <AiInput
                name="code"
                type="text"
                data-test="mfa-setup-code"
                label="6-digit verification code"
                :pre-icon="LockOutline"
                :input-props="{inputmode: 'numeric', autocomplete: 'one-time-code', maxlength: 6}"
            />
            <div class="flex-grow" />
            <div class="flex flex-row">
                <div class="flex-grow" />
                <AiButton
                    primary
                    data-test="mfa-setup-btn"
                    :loading="loading"
                    type="submit"
                >
                    Verify and continue
                </AiButton>
            </div>
        </Form>
    </section>
</template>

<script setup lang="ts">
import QRCode from "qrcode";
import { Form } from "vee-validate";
import { computed, onMounted, ref, watch } from "vue";
import { object, string } from "yup";

import AiButton from "@/components/AiButton/AiButton.vue";
import AiInput from "@/components/AiInput/AiInput.vue";
import { routeChange } from "@/router";
import { useAuthStore } from "@/store/auth";
import { Snackbar } from "@/utils/snackbar";
import LockOutline from "~icons/mdi/lock-outline";

const authStore = useAuthStore();
const loading = ref(false);
const qrDataUrl = ref<string | null>(null);

const sharedSecret = computed(() => authStore.totpSetup?.sharedSecret ?? null);
const setupUri = computed(() => authStore.totpSetup?.setupUri ?? null);

const schema = object().shape({
    code: string()
        .required("Please enter the 6-digit code")
        .matches(/^\d{6}$/, "Code must be exactly 6 digits")
});

interface IMfaForm {
    code: string;
}

const renderQr = async (uri: string) => {
    try {
        qrDataUrl.value = await QRCode.toDataURL(uri, { margin: 1, width: 192 });
    } catch {
        // Users can still enter the shared secret manually.
        qrDataUrl.value = null;
    }
};

onMounted(() => {
    // If the user landed here without an active TOTP setup challenge, bounce
    // them back to login. Otherwise render the QR code from the setup URI.
    if (authStore.signInStep !== "CONTINUE_SIGN_IN_WITH_TOTP_SETUP" || !setupUri.value) {
        routeChange.gotoLogin();
        return;
    }
    renderQr(setupUri.value);
});

watch(setupUri, (uri) => {
    if (uri) renderQr(uri);
});

const submit = async (v: unknown): Promise<void> => {
    const { code } = v as IMfaForm;

    loading.value = true;
    try {
        await authStore.confirmTotpSetup(code);
        routeChange.viewProjects();
    } catch {
        Snackbar.show({
            type: "error",
            title: "Invalid code",
            text: "That code did not match. Please try again."
        });
    } finally {
        loading.value = false;
    }
};
</script>
