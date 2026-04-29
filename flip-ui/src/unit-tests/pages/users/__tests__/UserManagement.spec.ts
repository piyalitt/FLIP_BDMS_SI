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
import { flushPromises, mount, VueWrapper } from "@vue/test-utils";
import { ref } from "vue";
import { vi } from "vitest";

import UserManagement from "@/pages/admin/users.vue";
import { updateUserRoles } from "@/services/user-service";
import { Snackbar } from "@/utils/snackbar";

const mockRole = {
    id: "role-new",
    rolename: "Admin",
    roledescription: "New role"
};

// `setSelectedUser` in users.vue stores `user.roles` by reference; rebuild per call so
// mutations from one test don't leak into the next.
function buildUser() {
    return {
        id: "user-1",
        email: "alice@example.com",
        isDisabled: false,
        roles: [
            { id: "role-existing", rolename: "Researcher", roledescription: "Existing role" }
        ]
    };
}

function swrvImpl(keyFn: () => string) {
    const key = keyFn();
    if (key === "/roles") {
        return { data: ref({ roles: [mockRole] }), mutate: vi.fn(), error: ref(null) };
    }
    return { data: ref({ data: [buildUser()], page: 1, totalPages: 1 }), mutate: vi.fn(), error: ref(null) };
}

vi.mock("swrv", () => ({ default: vi.fn(swrvImpl) }));

vi.mock("@/services/user-service", async (importOriginal) => ({
    ...await importOriginal<typeof import("@/services/user-service")>(),
    updateUserRoles: vi.fn()
}));

vi.mock("@/utils/snackbar", () => ({
    Snackbar: { success: vi.fn(), error: vi.fn() }
}));

vi.mock("@/utils/route-validator", () => ({
    canAccessRoute: vi.fn().mockResolvedValue(true)
}));

vi.mock("@/router", () => ({
    routeChange: { viewProjects: vi.fn() }
}));

const SlotPassthrough = { template: "<div><slot /></div>" };

const VTableStub = {
    props: ["data"],
    template: "<div><slot name='body' :rows='data ?? []' /></div>"
};

function mountUsers() {
    return mount(UserManagement, {
        global: {
            plugins: [createTestingPinia({ createSpy: vi.fn, stubActions: false })],
            stubs: {
                AiCard: SlotPassthrough,
                AiPagination: true,
                AiSkeleton: true,
                AiLabel: true,
                AiConfirmModal: true,
                RegisterUserModal: true,
                VTable: VTableStub,
                Popover: SlotPassthrough,
                PopoverButton: SlotPassthrough,
                PopoverGroup: SlotPassthrough,
                PopoverPanel: SlotPassthrough,
                transition: SlotPassthrough,
                Transition: SlotPassthrough
            }
        }
    });
}

async function mountAndAddAdminRole(): Promise<VueWrapper> {
    const wrapper = mountUsers();
    await wrapper.find("[data-test='user']").trigger("click");
    await wrapper.find("[data-test='add-admin-btn']").trigger("click");
    return wrapper;
}

describe("User Management", () => {
    beforeEach(() => {
        vi.mocked(updateUserRoles).mockReset();
        vi.mocked(Snackbar.success).mockReset();
        vi.mocked(Snackbar.error).mockReset();
    });

    it("renders the component successfully", () => {
        expect(mountUsers().exists()).toBe(true);
    });

    describe("saveUser", () => {
        it("calls updateUserRoles, clears dirty, and shows a success snackbar on success", async () => {
            vi.mocked(updateUserRoles).mockResolvedValue([]);

            const wrapper = await mountAndAddAdminRole();
            const saveBtn = wrapper.find("[data-test='save-user-btn']");
            expect(saveBtn.attributes("disabled")).toBeUndefined();

            await saveBtn.trigger("click");
            await flushPromises();

            expect(updateUserRoles).toHaveBeenCalledWith("user-1", ["role-existing", "role-new"]);
            expect(Snackbar.success).toHaveBeenCalledWith({
                text: "The user's permissions have been updated.",
                title: "User updated"
            });
            expect(Snackbar.error).not.toHaveBeenCalled();
            expect(wrapper.find("[data-test='save-user-btn']").attributes("disabled")).toBeDefined();
        });

        it("shows an error snackbar and keeps dirty state when updateUserRoles rejects", async () => {
            vi.mocked(updateUserRoles).mockRejectedValue(new Error("API error"));

            const wrapper = await mountAndAddAdminRole();
            await wrapper.find("[data-test='save-user-btn']").trigger("click");
            await flushPromises();

            expect(updateUserRoles).toHaveBeenCalledWith("user-1", ["role-existing", "role-new"]);
            expect(Snackbar.error).toHaveBeenCalledWith({
                text: "The user could not be updated, please try again.",
                title: "Update failed"
            });
            expect(Snackbar.success).not.toHaveBeenCalled();
            expect(wrapper.find("[data-test='save-user-btn']").attributes("disabled")).toBeUndefined();
        });
    });
});
