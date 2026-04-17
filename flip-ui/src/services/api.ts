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

import { fetchAuthSession } from 'aws-amplify/auth';
import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse } from "axios";

import { useAuthStore } from "@/store/auth";
import { NO_FORCED_SIGNOUT_PATHS } from "@/utils/auth";
import { Snackbar } from "@/utils/snackbar";

// Debounce the "Not Authorised" snackbar so a burst of parallel 401s
// (common when multiple SWRV hooks fail at the same token expiry) shows
// exactly one message, not one per request.
let lastNotAuthorisedAt = 0;
const NOT_AUTHORISED_COOLDOWN_MS = 5_000;

export interface IResponse<T> extends AxiosResponse<T> { }

export interface IGenericResponse { body: string }

export type IPaginatedResponse<T> = {
    page: number,
    pageSize: number,
    totalPages: number,
    totalRecords: number,
    data: T[]
}

class Http {
    private instance: AxiosInstance | null = null;

    private get http(): AxiosInstance {
        return this.instance != null ? this.instance : this.initHttp();
    }

    private initHttp() {
        const authStore = useAuthStore();
        const devMode = process.env.NODE_ENV === "development";

        if (devMode) {
            console.log("Initializing HTTP client in development mode");
        }

        const http = axios.create({
            baseURL: devMode ? process.env.VITE_AWS_BASE_URL : window.AWS_BASE_URL,
            timeout: 30_000,
            headers: {}
        });

        http.interceptors.request.use(
            async config => {
                if (config.headers && config.headers.Authorization === undefined) {
                    const session = await fetchAuthSession();
                    const token = session.tokens?.idToken?.toString();

                    if (token) {
                        config.headers.Authorization = "Bearer " + token;
                    }
                }
                return config;
            },
            error => {
                return Promise.reject(error);
            }
        );

        http.interceptors.response.use(
            (response) => response,
            function (error) {
                if (error.response?.status === 401) {
                    // Skip the forced sign-out entirely on mid-flow auth
                    // pages; the user hasn't completed their challenge
                    // chain and we'd throw away their progress.
                    const currentPath = window.location.pathname;
                    if (NO_FORCED_SIGNOUT_PATHS.has(currentPath)) {
                        return Promise.reject(error);
                    }

                    authStore.signOut();

                    const now = Date.now();
                    if (now - lastNotAuthorisedAt > NOT_AUTHORISED_COOLDOWN_MS) {
                        lastNotAuthorisedAt = now;
                        Snackbar.show({
                            type: "info",
                            title: "Not Authorised",
                            text: "You have been signed out. Please log back in."
                        });
                    }

                    return Promise.reject(error);
                }

                return Promise.reject(error);
            }
        );

        this.instance = http;

        return http;
    }

    get<T = unknown, R = IResponse<T>>(url: string, config?: AxiosRequestConfig): Promise<R> {
        return this.http.get<T, R>(url, config);
    }

    post<T = unknown, I = unknown, R = IResponse<T>>(
        url: string,
        data?: I,
        config?: AxiosRequestConfig
    ): Promise<R> {
        return this.http.post<I, R>(url, data, config);
    }

    put<T = unknown, I = unknown, R = IResponse<T>>(
        url: string,
        data?: I,
        config?: AxiosRequestConfig
    ): Promise<R> {
        return this.http.put<I, R>(url, data, config);
    }

    delete<T = unknown, R = IResponse<T>>(
        url: string,
        config?: AxiosRequestConfig
    ): Promise<R> {
        return this.http.delete<T, R>(url, config);
    }
}

export const _http = new Http();
