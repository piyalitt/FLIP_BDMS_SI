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

import { createTestingPinia } from "@pinia/testing";
import { mount } from "@vue/test-utils";
import { describe, expect, test, vi } from "vitest";

import ProjectUsers from "../ProjectUsers.vue";

vi.mock("@/services/user-service", () => ({ validateUser: vi.fn() }));

function mountProjectUsers(props: Record<string, unknown> = {}) {
    // Cast: the component declares `users` as required, but the whole
    // point of these tests is to exercise the `withDefaults` fallback
    // when the prop is omitted at runtime — TypeScript can't model that.
    return mount(ProjectUsers, {
        props: props as never,
        global: {
            plugins: [
                createTestingPinia({
                    createSpy: vi.fn,
                    initialState: {
                        auth: {
                            user: {
                                username: "u",
                                userId: "current-user",
                                attributes: {
                                    sub: "s",
                                    email: "u@e.com"
                                },
                                permissions: []
                            }
                        }
                    }
                })
            ],
            directives: { tippy: () => {} },
            stubs: {
                AiAlert: { template: "<div><slot /></div>" },
                AiButton: { template: "<button><slot /></button>" },
                AiInput: { template: "<input />" },
                Form: { template: "<form><slot /></form>" }
            }
        }
    });
}

describe("ProjectUsers — defensive prop default", () => {
    test("renders the empty-state placeholder when the users prop is omitted", () => {
        const wrapper = mountProjectUsers();
        expect(wrapper.text()).toContain("No Project Users");
    });

    test("renders the empty-state placeholder when users is an empty array", () => {
        const wrapper = mountProjectUsers({ users: [] });
        expect(wrapper.text()).toContain("No Project Users");
    });

    test("lists each user row when users is populated", () => {
        const wrapper = mountProjectUsers({
            users: [
                {
                    id: "u1",
                    email: "alice@e.com",
                    isDisabled: false
                },
                {
                    id: "u2",
                    email: "bob@e.com",
                    isDisabled: false
                }
            ]
        });
        expect(wrapper.text()).toContain("alice@e.com");
        expect(wrapper.text()).toContain("bob@e.com");
    });

    test("filters out the current user from the displayed list", () => {
        // Self-row would let a project owner remove themselves; the
        // `displayUsers` computed drops `currentUserId` to prevent that.
        const wrapper = mountProjectUsers({
            users: [
                {
                    id: "current-user",
                    email: "self@e.com",
                    isDisabled: false
                },
                {
                    id: "u2",
                    email: "bob@e.com",
                    isDisabled: false
                }
            ]
        });
        expect(wrapper.text()).not.toContain("self@e.com");
        expect(wrapper.text()).toContain("bob@e.com");
    });
});
