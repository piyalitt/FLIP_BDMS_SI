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

import { execFileSync } from "node:child_process";
import path from "node:path";

import { checkViteLocal } from "../check-build-flags.mjs";

// Resolved once because every spec runs the script as a child process,
// and resolving relative to __dirname keeps the test order-independent
// (vitest's cwd is not stable across runners).
const SCRIPT = path.resolve(__dirname, "../check-build-flags.mjs");

describe("checkViteLocal", () => {
    it("returns null when VITE_LOCAL is unset", () => {
        expect(checkViteLocal({})).toBeNull();
    });

    it("returns null when VITE_LOCAL is the string 'false'", () => {
        expect(checkViteLocal({ VITE_LOCAL: "false" })).toBeNull();
    });

    it("returns null for any value that is not exactly 'true'", () => {
        // Vite's build-time replacement only matches the exact string
        // "true" — anything else is dead-code-eliminated. Mirror that
        // here so the guard and the runtime stay in lockstep.
        expect(checkViteLocal({ VITE_LOCAL: "TRUE" })).toBeNull();
        expect(checkViteLocal({ VITE_LOCAL: "1" })).toBeNull();
        expect(checkViteLocal({ VITE_LOCAL: "yes" })).toBeNull();
        expect(checkViteLocal({ VITE_LOCAL: "" })).toBeNull();
    });

    it("returns a non-empty error message when VITE_LOCAL='true'", () => {
        const reason = checkViteLocal({ VITE_LOCAL: "true" });
        expect(reason).not.toBeNull();
        expect(reason).toContain("Refusing to build");
        expect(reason).toContain("VITE_LOCAL");
    });

    it("mentions Cognito so the operator sees the security stake", () => {
        // The whole point of failing the build is to flag the auth
        // bypass — a generic "config error" message would let an
        // operator paper over it by tweaking env vars without
        // understanding what they were turning off.
        const reason = checkViteLocal({ VITE_LOCAL: "true" });
        expect(reason).toMatch(/Cognito/i);
    });
});

describe("check-build-flags.mjs CLI", () => {
    it("exits 0 when VITE_LOCAL is unset", () => {
        const env = { ...process.env };
        delete env.VITE_LOCAL;

        // Throws on non-zero exit, so a successful return == exit 0.
        expect(() => execFileSync("node", [SCRIPT], { env })).not.toThrow();
    });

    it("exits 0 when VITE_LOCAL='false'", () => {
        const env = {
            ...process.env,
            VITE_LOCAL: "false"
        };
        expect(() => execFileSync("node", [SCRIPT], { env })).not.toThrow();
    });

    it("exits non-zero and prints the reason on stderr when VITE_LOCAL='true'", () => {
        const env = {
            ...process.env,
            VITE_LOCAL: "true"
        };

        let caught: { status: number | null; stderr: string } | null = null;
        try {
            execFileSync("node", [SCRIPT], {
                env,
                stdio: "pipe"
            });
        } catch (e) {
            const err = e as { status: number | null; stderr: Buffer };
            caught = {
                status: err.status,
                stderr: err.stderr.toString()
            };
        }

        expect(caught).not.toBeNull();
        expect(caught?.status).toBe(1);
        expect(caught?.stderr).toContain("Refusing to build");
        expect(caught?.stderr).toMatch(/Cognito/i);
    });
});
