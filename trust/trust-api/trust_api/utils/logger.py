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

import os

from flip_logging import configure_logging, get_logger

configure_logging(
    api_name="trust-api",
    site=os.getenv("FLIP_SITE_NAME", "unknown"),
    level=os.getenv("LOG_LEVEL", "INFO"),
)

logger = get_logger(__name__)
