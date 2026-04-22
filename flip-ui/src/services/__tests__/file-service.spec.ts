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

import { beforeEach, describe, expect, it, vi } from "vitest";

const httpGet = vi.fn();
const fetchJobTypesMock = vi.fn();

vi.mock("@/services/api", () => ({
    _http: {
        get: (...args: unknown[]) => httpGet(...args),
        delete: vi.fn(),
        post: vi.fn()
    }
}));

vi.mock("@/services/model-service", async () => {
    const actual = await vi.importActual<typeof import("@/services/model-service")>(
        "@/services/model-service"
    );
    return {
        ...actual,
        fetchJobTypes: (...args: unknown[]) => fetchJobTypesMock(...args)
    };
});

import { getJobTypeFromConfig, resolveModelConfigState } from "@/services/file-service";
import { FileUploadStatus } from "@/interfaces/model/types";
import { DEFAULT_JOB_TYPE } from "@/services/model-service";

const jobTypes = {
    standard: ["trainer.py", "config.json"],
    diffusion: ["trainer.py", "config.json", "diffusion.py"]
};

const configBlob = (payload: unknown): { data: Blob } => ({
    data: new Blob([JSON.stringify(payload)], { type: "application/json" })
});

describe("getJobTypeFromConfig", () => {
    beforeEach(() => {
        httpGet.mockReset();
        fetchJobTypesMock.mockReset();
    });

    it("returns the job_type from config.json when it is valid", async () => {
        httpGet.mockResolvedValueOnce(configBlob({ job_type: "diffusion" }));
        const result = await getJobTypeFromConfig("model-1", jobTypes);
        expect(result).toBe("diffusion");
        expect(fetchJobTypesMock).not.toHaveBeenCalled();
    });

    it("falls back to DEFAULT_JOB_TYPE when job_type is not in the job types map", async () => {
        httpGet.mockResolvedValueOnce(configBlob({ job_type: "unknown" }));
        const result = await getJobTypeFromConfig("model-2", jobTypes);
        expect(result).toBe(DEFAULT_JOB_TYPE);
    });

    it("falls back to DEFAULT_JOB_TYPE when config.json has no job_type field", async () => {
        httpGet.mockResolvedValueOnce(configBlob({ something_else: true }));
        const result = await getJobTypeFromConfig("model-3", jobTypes);
        expect(result).toBe(DEFAULT_JOB_TYPE);
    });

    it("falls back to DEFAULT_JOB_TYPE when config.json cannot be parsed", async () => {
        httpGet.mockResolvedValueOnce({
            data: new Blob(["not-json"], { type: "application/json" })
        });
        const result = await getJobTypeFromConfig("model-4", jobTypes);
        expect(result).toBe(DEFAULT_JOB_TYPE);
    });

    it("falls back to DEFAULT_JOB_TYPE when the download fails", async () => {
        httpGet.mockRejectedValueOnce(new Error("boom"));
        const result = await getJobTypeFromConfig("model-5", jobTypes);
        expect(result).toBe(DEFAULT_JOB_TYPE);
    });

    it("fetches job types from the API when none are provided", async () => {
        fetchJobTypesMock.mockResolvedValueOnce(jobTypes);
        httpGet.mockResolvedValueOnce(configBlob({ job_type: "diffusion" }));
        const result = await getJobTypeFromConfig("model-6");
        expect(fetchJobTypesMock).toHaveBeenCalledTimes(1);
        expect(result).toBe("diffusion");
    });
});

describe("resolveModelConfigState", () => {
    beforeEach(() => {
        httpGet.mockReset();
        fetchJobTypesMock.mockReset();
    });

    it("reports no change when config.json status matches previous status", async () => {
        const files = [{ name: "config.json", status: FileUploadStatus.COMPLETED }];
        const result = await resolveModelConfigState(
            files,
            FileUploadStatus.COMPLETED,
            jobTypes,
            "model-id"
        );
        expect(result.changed).toBe(false);
        expect(result.configStatus).toBe(FileUploadStatus.COMPLETED);
        expect(httpGet).not.toHaveBeenCalled();
    });

    it("reports no change when config.json is absent and previous status was null", async () => {
        const files = [{ name: "trainer.py", status: FileUploadStatus.COMPLETED }];
        const result = await resolveModelConfigState(files, null, jobTypes, "model-id");
        expect(result.changed).toBe(false);
        expect(result.configStatus).toBeNull();
        expect(httpGet).not.toHaveBeenCalled();
    });

    it("transitions to SCANNING without downloading config.json", async () => {
        const files = [{ name: "config.json", status: FileUploadStatus.SCANNING }];
        const result = await resolveModelConfigState(files, null, jobTypes, "model-id");
        expect(result.changed).toBe(true);
        expect(result.configStatus).toBe(FileUploadStatus.SCANNING);
        expect(result.jobType).toBe(DEFAULT_JOB_TYPE);
        expect(result.requiredFiles).toEqual(jobTypes.standard);
        expect(httpGet).not.toHaveBeenCalled();
    });

    it("downloads config.json and resolves the job type once status becomes COMPLETED", async () => {
        httpGet.mockResolvedValueOnce(configBlob({ job_type: "diffusion" }));
        const files = [{ name: "config.json", status: FileUploadStatus.COMPLETED }];
        const result = await resolveModelConfigState(
            files,
            FileUploadStatus.SCANNING,
            jobTypes,
            "model-id"
        );
        expect(result.changed).toBe(true);
        expect(result.configStatus).toBe(FileUploadStatus.COMPLETED);
        expect(result.jobType).toBe("diffusion");
        expect(result.requiredFiles).toEqual(jobTypes.diffusion);
        expect(httpGet).toHaveBeenCalledTimes(1);
    });

    it("resets to defaults when config.json is removed", async () => {
        const files = [{ name: "trainer.py", status: FileUploadStatus.COMPLETED }];
        const result = await resolveModelConfigState(
            files,
            FileUploadStatus.COMPLETED,
            jobTypes,
            "model-id"
        );
        expect(result.changed).toBe(true);
        expect(result.configStatus).toBeNull();
        expect(result.jobType).toBe(DEFAULT_JOB_TYPE);
        expect(result.requiredFiles).toEqual(jobTypes.standard);
        expect(httpGet).not.toHaveBeenCalled();
    });
});
