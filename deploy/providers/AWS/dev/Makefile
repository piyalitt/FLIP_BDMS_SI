# Copyright (c) 2026 Guy's and St Thomas' NHS Foundation Trust & King's College London
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Dev-account Terraform root: Cognito + SES only.
#
# Shares the same env file as the local Docker Compose dev stack
# (../../../.env.development) so developers only maintain one set of
# credentials. The variables we need — AWS_PROFILE, AWS_REGION,
# SES_VERIFIED_EMAIL, ADMIN_USER_PASSWORD — already live there.
# Cognito admin/researcher emails are usually set in .env.development as
# well for seeding the local stack; reuse them here.

ENV_FILE := ../../../../.env.development

ifneq ("$(wildcard $(ENV_FILE))","")
include $(ENV_FILE)
export $(shell sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1/p' $(ENV_FILE))
endif

ifndef AWS_PROFILE
$(error AWS_PROFILE is not set. Add it to $(ENV_FILE))
endif

# Safety guard: refuse to run against the prod or stag account by accident.
# The prod/stag profiles are hard-coded in the parent Makefile's guard; the
# same account numbers are rejected here.
ifeq ($(AWS_PROFILE),FlipDeveloperAccess-046651569599)
$(error AWS_PROFILE is the PROD account — refuse to run dev-stack commands against prod)
endif
ifeq ($(AWS_PROFILE),FlipDeveloperAccess-080369786334)
$(error AWS_PROFILE is the STAG account — refuse to run dev-stack commands against stag)
endif

# Backend bucket for dev state. Set DEV_STATE_BUCKET in .env.development
# if dev uses its own state bucket; otherwise fall back to the shared
# STATE_BUCKET (must be reachable from the dev AWS profile).
DEV_STATE_BUCKET ?= $(STATE_BUCKET)
ifndef DEV_STATE_BUCKET
$(error Set DEV_STATE_BUCKET (or STATE_BUCKET) in $(ENV_FILE))
endif

# Terraform variables picked up via the TF_VAR_ env var convention.
# Seed the admin email from SES_VERIFIED_EMAIL by default — in dev that's
# usually the developer's own mailbox, which is what you want for
# receiving the Cognito invite. Override by setting
# flip_cognito_admin_email in .env.development.
TF_VAR_flip_cognito_admin_email ?= $(SES_VERIFIED_EMAIL)

export TF_VAR_AWS_REGION ?= $(AWS_REGION)
export TF_VAR_flip_user_pool_name ?= flip-user-pool-dev
export TF_VAR_flip_cognito_client ?= flip-cognito-client-dev
export TF_VAR_sign_in_hostname ?= localhost
export TF_VAR_flip_cognito_admin_email
export TF_VAR_flip_cognito_researcher_email ?= $(flip_cognito_researcher_email)
export TF_VAR_ADMIN_USER_PASSWORD := $(ADMIN_USER_PASSWORD)
export TF_VAR_SES_VERIFIED_EMAIL := $(SES_VERIFIED_EMAIL)

BACKEND_CONFIG := \
	-backend-config="bucket=$(DEV_STATE_BUCKET)" \
	-backend-config="region=$(AWS_REGION)"

.PHONY: init plan apply destroy validate status fmt help

help:
	@echo "Dev-account Terraform targets (Cognito + SES only):"
	@echo "  make init      - terraform init (first run, or after changing backend config)"
	@echo "  make validate  - terraform validate"
	@echo "  make fmt       - terraform fmt -recursive on this dir + shared modules"
	@echo "  make plan      - terraform plan"
	@echo "  make apply     - terraform apply"
	@echo "  make destroy   - terraform destroy (refused while prevent_destroy is set)"
	@echo "  make status    - terraform state list"
	@echo ""
	@echo "Env: loaded from $(ENV_FILE)"
	@echo "First-time setup for an already-existing dev Cognito pool: see README.md."

init:
	terraform init $(BACKEND_CONFIG) -reconfigure

validate:
	terraform validate

fmt:
	terraform fmt -recursive .
	terraform fmt -recursive ../modules/cognito
	terraform fmt -recursive ../modules/ses

plan:
	terraform plan

apply:
	terraform apply

destroy:
	terraform destroy

status:
	terraform state list
