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

# Event name constants for structured logging across FLIP trust services.
# Use these as the "event" field in log extra dicts, e.g.:
#   logger.info("Project staged", extra={"event": events.PROJECT_STAGED, ...})

# Project lifecycle
PROJECT_SUBMITTED = "project.submitted"
PROJECT_APPROVED = "project.approved"
PROJECT_STAGED = "project.staged"
PROJECT_UNSTAGED = "project.unstaged"
PROJECT_DELETED = "project.deleted"

# Cohort / data access
COHORT_QUERY_SUBMITTED = "cohort.query_submitted"
COHORT_RESULTS_RECEIVED = "cohort.results_received"

# Imaging pipeline
IMAGING_PROJECT_CREATED = "imaging.project_created"
IMAGING_STUDIES_IMPORTED = "imaging.studies_imported"
IMAGING_STUDIES_REIMPORTED = "imaging.studies_reimported"

# Federated learning / training
TRAINING_INITIATED = "training.initiated"
TRAINING_COMPLETED = "training.completed"
TRAINING_FAILED = "training.failed"

# Model management
MODEL_CREATED = "model.created"
MODEL_DELETED = "model.deleted"
MODEL_STATUS_UPDATED = "model.status_updated"

# Request lifecycle (used by middleware)
REQUEST_STARTED = "request.started"
REQUEST_COMPLETED = "request.completed"
REQUEST_FAILED = "request.failed"
