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




import { mount } from "@vue/test-utils";

import AiConfirmModal from "../AiConfirmModal.vue";

describe("Ai ConfirmModal", () => {
    test("Renders Component", () => {
        const comp = mount(AiConfirmModal);

        expect(comp.element).toMatchSnapshot();
    });

    test("escapes HTML in confirmationText to prevent XSS", () => {
        const payload = "<img src=x onerror=alert(1)>";

        const comp = mount(AiConfirmModal, {
            global: { renderStubDefaultSlot: true },
            props: {
                dialog: true,
                continueAction: () => {},
                confirmationText: payload
            }
        });

        const html = comp.html();

        expect(html).not.toContain("<img");
        expect(html).toContain("&lt;img");

        comp.unmount();
    });

    test("renders the confirmation slot when provided", () => {
        const comp = mount(AiConfirmModal, {
            global: { renderStubDefaultSlot: true },
            props: {
                dialog: true,
                continueAction: () => {}
            },
            slots: {
                confirmation: "<strong data-test=\"slot-marker\">slot content</strong>"
            }
        });

        const html = comp.html();

        expect(html).toContain("data-test=\"slot-marker\"");
        expect(html).toContain("slot content");

        comp.unmount();
    });
});
