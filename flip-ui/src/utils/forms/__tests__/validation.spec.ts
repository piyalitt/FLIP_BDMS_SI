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

import { describe, expect, test } from "vitest";

import { emailValidation, passwordValidation } from "../validation";

describe("passwordValidation", () => {
    test("rejects an empty string with the user-facing required message", async () => {
        // The custom message is what login / change-password / reset-password
        // forms surface — yup's default ("this is a required field") would
        // regress the UX silently if a future refactor drops the override.
        await expect(passwordValidation.validate("")).rejects.toThrow(
            "A password is required"
        );
    });

    test("rejects a too-short password before the character-class matchers", async () => {
        // The character-class matchers run before `min(8)` in yup's order,
        // so a short string like "Aa1!" trips min(8) only when the
        // character-class checks pass. Use a string that satisfies all
        // matchers but is under 8 chars to pin the min(8) message.
        await expect(passwordValidation.validate("Aa1!")).rejects.toThrow(
            "Your password must be at least 8 characters"
        );
    });

    test("rejects a password without a digit", async () => {
        await expect(passwordValidation.validate("Password!")).rejects.toThrow(
            "Your password must contain a number"
        );
    });

    test("rejects a password without an uppercase letter", async () => {
        await expect(passwordValidation.validate("password1!")).rejects.toThrow(
            "Your password must contain an uppercase character"
        );
    });

    test("rejects a password without a special character", async () => {
        await expect(passwordValidation.validate("Password1")).rejects.toThrow(
            "Your password must contain a special character"
        );
    });

    test("accepts a fully-valid password", async () => {
        await expect(
            passwordValidation.validate("Password1!")
        ).resolves.toBe("Password1!");
    });
});

describe("emailValidation", () => {
    test("rejects an empty string with the required message", async () => {
        await expect(emailValidation.validate("")).rejects.toThrow(
            "An email address is required"
        );
    });

    test("rejects a malformed address with the format message", async () => {
        await expect(emailValidation.validate("not-an-email")).rejects.toThrow(
            "Please enter a valid email address"
        );
    });

    test("accepts a well-formed address", async () => {
        await expect(emailValidation.validate("u@e.com")).resolves.toBe(
            "u@e.com"
        );
    });
});
