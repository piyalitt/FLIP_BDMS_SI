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
            Enter your verification code
        </h1>
        <p class="mb-4 text-sm">
            Open your authenticator app and enter the 6-digit code for FLIP.
        </p>
        <Form
            :validation-schema="schema"
            class="flex flex-col flex-grow p-0 space-y-4"
            @submit="submit"
        >
            <AiInput
                name="code"
                type="text"
                data-test="mfa-verify-code"
                label="6-digit verification code"
                :pre-icon="LockOutline"
                :input-props="{inputmode: 'numeric', autocomplete: 'one-time-code', maxlength: 6}"
            />
            <div class="flex-grow" />
            <div class="flex flex-row">
                <div class="flex-grow" />
                <AiButton
                    primary
                    data-test="mfa-verify-btn"
                    :loading="loading"
                    type="submit"
                >
                    Verify
                </AiButton>
            </div>
        </Form>
    </section>
</template>

<script setup lang="ts">
import { Form } from "vee-validate";
import { onMounted, ref } from "vue";
import { object, string } from "yup";

import AiButton from "@/components/AiButton/AiButton.vue";
import AiInput from "@/components/AiInput/AiInput.vue";
import { routeChange } from "@/router";
import { useAuthStore } from "@/store/auth";
import { Snackbar } from "@/utils/snackbar";
import LockOutline from "~icons/mdi/lock-outline";

const authStore = useAuthStore();
const loading = ref(false);

const schema = object().shape({
    code: string()
        .required("Please enter the 6-digit code")
        .matches(/^\d{6}$/, "Code must be exactly 6 digits")
});

interface IMfaForm {
    code: string;
}

onMounted(() => {
    // Only valid while we have an outstanding TOTP code challenge.
    if (authStore.signInStep !== "CONFIRM_SIGN_IN_WITH_TOTP_CODE") {
        routeChange.gotoLogin();
    }
});

const submit = async (v: unknown): Promise<void> => {
    const { code } = v as IMfaForm;

    loading.value = true;
    try {
        await authStore.confirmTotpChallenge(code);
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
