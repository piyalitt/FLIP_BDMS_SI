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




import type { AxiosResponse } from "axios";
import { FileUploadStatus } from "@/interfaces/model/types";
import { _http } from "./api";
import {
    DEFAULT_JOB_TYPE,
    fetchJobTypes,
    getRequiredFilesForJobType,
    isValidJobType,
    type JobType,
    type JobTypesResponse
} from "./model-service";

/**
 * Interface for the config.json file structure.
 * Only includes fields relevant for determining required files.
 */
export interface IModelConfig {
    job_type?: string;
    [key: string]: unknown;
}

export const downloadModelFile = async (url: string): Promise<Blob> => {
  const response: AxiosResponse<Blob> = await _http.get(url, { responseType: "blob" });

  return response.data;
};

/**
 * Fetches and parses the config.json file for a model.
 * @param modelId - The model ID
 * @returns The parsed config object, or null if not found/invalid
 */
export const getModelConfig = async (modelId: string): Promise<IModelConfig | null> => {
    try {
        const path = `/files/model/${modelId}/${encodeURIComponent("config.json")}`;
        const blob = await downloadModelFile(path);
        const text = await blob.text();
        return JSON.parse(text) as IModelConfig;
    } catch {
        // Config file doesn't exist or is invalid JSON
        return null;
    }
};

/**
 * Extracts the job_type from config.json, validating against available job types from the API.
 * Defaults to 'standard' if not found, missing, or invalid.
 * @param modelId - The model ID
 * @param jobTypes - Optional pre-fetched job types. If not provided, will fetch from API.
 * @returns The job type from config.json or 'standard' as default
 */
export const getJobTypeFromConfig = async (
    modelId: string,
    jobTypes?: JobTypesResponse
): Promise<JobType> => {
    try {
        const availableJobTypes = jobTypes ?? await fetchJobTypes();
        const config = await getModelConfig(modelId);

        if (config && config.job_type && isValidJobType(availableJobTypes, config.job_type)) {
            return config.job_type;
        }

        return DEFAULT_JOB_TYPE;
    } catch {
        return DEFAULT_JOB_TYPE;
    }
};

/**
 * Result of resolving the model's `config.json` state for a poll tick.
 * `changed` is true when `config.json`'s upload status differs from
 * `previousStatus`, indicating the caller should update downstream refs
 * (`currentJobType`, `requiredFiles`) and the status tracker.
 */
export interface IResolvedConfigState {
    changed: boolean;
    configStatus: string | null;
    jobType: JobType;
    requiredFiles: string[];
}

/**
 * Decides whether `config.json` needs re-reading for a poll tick and — if so —
 * resolves the job type and the required files that follow from it.
 *
 * The model detail page polls every 5 s. `config.json` is immutable once
 * uploaded, so we only re-download it when its upload status transitions
 * (e.g. `null` → `SCANNING` → `COMPLETED`, or reset on delete).
 *
 * @param files - Files currently reported by the model API
 * @param previousStatus - Status observed on the previous tick (`null` if none)
 * @param jobTypes - Cached job type → required files map
 * @param modelId - Model ID, used to fetch `config.json` when status becomes COMPLETED
 */
export const resolveModelConfigState = async (
    files: { name: string; status: string }[],
    previousStatus: string | null,
    jobTypes: JobTypesResponse,
    modelId: string
): Promise<IResolvedConfigState> => {
    const configFile = files.find(f => f.name === "config.json");
    const configStatus = configFile?.status ?? null;

    if (configStatus === previousStatus) {
        return { changed: false, configStatus, jobType: DEFAULT_JOB_TYPE, requiredFiles: [] };
    }

    let jobType: JobType = DEFAULT_JOB_TYPE;
    if (configFile && configStatus === FileUploadStatus.COMPLETED) {
        jobType = await getJobTypeFromConfig(modelId, jobTypes);
    }

    return {
        changed: true,
        configStatus,
        jobType,
        requiredFiles: getRequiredFilesForJobType(jobTypes, jobType)
    };
};

export const deleteModelFile = async (url: string): Promise<string> => {
    const response = await _http.delete<string>(url);

    return response.data;
};

export const processScannedFile = async (url: string): Promise<string> => {
    const response = await _http.post<string>(url);

    return response.data;
};
