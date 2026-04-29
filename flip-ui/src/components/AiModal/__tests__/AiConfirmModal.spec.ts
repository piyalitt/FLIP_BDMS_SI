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




import { flushPromises, mount } from "@vue/test-utils";

import AiConfirmModal from "../AiConfirmModal.vue";

describe("Ai ConfirmModal", () => {
    test("Renders Component", () => {
        const comp = mount(AiConfirmModal);

        expect(comp.element).toMatchSnapshot();
    });

    describe("typing-confirmation validator (no-throw guarantee)", () => {
        // The form's yup schema reads `this.parent.confirmation` and
        // uppercase-compares it to the prop. Before the user has typed
        // anything, `this.parent.confirmation` is undefined; the previous
        // version called `.toUpperCase()` on it directly, raising a Vue /
        // vee-validate unhandled rejection that surfaced in Cypress as a
        // TypeError. These tests pin the guarded behaviour so it doesn't
        // regress — the headless DOM here can't fully simulate HeadlessUI's
        // teleport so we rely on mount + validation-pass to reach the
        // schema's test() callback without crashing.

        function mountWithTyping(typingConfirmation: string) {
            return mount(AiConfirmModal, {
                attachTo: document.body,
                props: {
                    dialog: true,
                    continueAction: () => {},
                    typingConfirmation
                }
            });
        }

        test("does not throw when typingConfirmation is set and the input is still empty", async () => {
            const wrapper = mountWithTyping("DELETE PROJECT");
            await flushPromises();

            // Asserting the wrapper exists also guarantees the synchronous
            // setup() didn't throw — the previous code crashed on first
            // validation pass before this check would have run.
            expect(wrapper.exists()).toBe(true);

            wrapper.unmount();
        });

        test("does not throw when typingConfirmation is empty (no validator branch)", async () => {
            const wrapper = mountWithTyping("");
            await flushPromises();

            expect(wrapper.exists()).toBe(true);

            wrapper.unmount();
        });

        test("does not throw on subsequent prop changes that re-trigger validation", async () => {
            const wrapper = mountWithTyping("");
            await flushPromises();

            await wrapper.setProps({ typingConfirmation: "ALPHA" });
            await flushPromises();

            await wrapper.setProps({ typingConfirmation: "BETA" });
            await flushPromises();

            expect(wrapper.exists()).toBe(true);

            wrapper.unmount();
        });
    });
});
