# Copyright (c) Guy's and St Thomas' NHS Foundation Trust & King's College London
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


from pydantic import BaseModel


class ISiteBanner(BaseModel):
    message: str
    link: str | None = None
    enabled: bool


class ISiteDetails(BaseModel):
    deploymentMode: bool
    banner: ISiteBanner | None = None
    # Cap on automatic reimport retries for failed studies. Sourced from
    # Settings.MAX_REIMPORT_COUNT (env-driven) rather than the DB — the
    # backend enforces the cap via the SQL query in
    # get_reimport_queries_service, so exposing the same number here lets
    # the UI's status display and the backend's enforcement agree without
    # a duplicate frontend env var. Optional because the PUT endpoint
    # only updates banner/deploymentMode (maxReimportCount is not DB
    # state to mutate) — GET always populates it.
    maxReimportCount: int | None = None
