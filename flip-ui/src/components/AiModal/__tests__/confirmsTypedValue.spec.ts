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

import { confirmsTypedValue } from "../confirmsTypedValue";

describe("confirmsTypedValue", () => {
    test("returns true when no confirmation word is required", () => {
        expect(confirmsTypedValue(undefined, "")).toBe(true);
        expect(confirmsTypedValue("anything", "")).toBe(true);
        expect(confirmsTypedValue(null, "")).toBe(true);
    });

    test("returns false when a confirmation word is required and the input is empty / undefined", () => {
        // First validation pass: vee-validate calls the schema with an
        // undefined `confirmation` field. The function must coalesce
        // safely instead of throwing on .toUpperCase().
        expect(confirmsTypedValue(undefined, "DELETE")).toBe(false);
        expect(confirmsTypedValue(null, "DELETE")).toBe(false);
        expect(confirmsTypedValue("", "DELETE")).toBe(false);
    });

    test("returns true on a case-insensitive match", () => {
        expect(confirmsTypedValue("DELETE", "DELETE")).toBe(true);
        expect(confirmsTypedValue("delete", "DELETE")).toBe(true);
        expect(confirmsTypedValue("Delete", "delete")).toBe(true);
        expect(confirmsTypedValue("dElEtE", "DELETE")).toBe(true);
    });

    test("returns false on a non-match", () => {
        expect(confirmsTypedValue("REMOVE", "DELETE")).toBe(false);
        expect(confirmsTypedValue("delete project", "delete")).toBe(false);
        expect(confirmsTypedValue("delet", "delete")).toBe(false);
    });

    test("coerces non-string inputs through .toString()", () => {
        // Defensive — yup's `string()` schema usually casts before this
        // runs, but the helper still needs to handle whatever
        // this.parent.confirmation hands it.
        expect(confirmsTypedValue(42, "42")).toBe(true);
        expect(confirmsTypedValue(true, "TRUE")).toBe(true);
    });
});
