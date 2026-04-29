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
#

ifeq ($(PROD),true)
MAIN_ENV_FILE=../.env.production
else ifeq ($(PROD),stag)
MAIN_ENV_FILE=../.env.stag
else
MAIN_ENV_FILE=../.env.development
endif

$(info Using MAIN_ENV_FILE: $(MAIN_ENV_FILE))

# replace environment variables by the values from the .env files
ifneq ("$(wildcard $(MAIN_ENV_FILE))","")
include $(MAIN_ENV_FILE)
export $(shell sed 's/=.*//' $(MAIN_ENV_FILE))
endif

docker_command = docker compose -f ../deploy/compose.development.yml

unit_test:
	$(docker_command) run --rm --remove-orphans --name flip-ui-test flip-ui npm run test:unit:update
shell:
	$(docker_command) run --rm --remove-orphans --name flip-ui-shell flip-ui sh
npm-install:
	$(docker_command) run --rm --remove-orphans --name flip-ui-npm-install flip-ui npm install

# Cypress runs on the host (matching CI), not inside the dev container — Chrome
# needs to be available locally. Requires Node >=20.19 and `npm install` to have
# been run on the host.
e2e_test:
	@test -f .env.development || { \
		echo "ERROR: flip-ui/.env.development is missing." >&2; \
		echo "Cypress needs it for Vite + dotenv. See flip-ui/README.md → Testing → End-to-end tests for the dummy values to use locally." >&2; \
		exit 1; \
	}
	npm run test:ci

# Same as e2e_test but runs Cypress in the official cypress/included image
# instead of on the host. Useful on Linux without Xvfb / Chrome installed.
# The dev server still runs on the host (so it can hot-reload your local
# checkout) and the container reaches it via --network host.
e2e_test_docker:
	@test -f .env.development || { \
		echo "ERROR: flip-ui/.env.development is missing." >&2; \
		echo "Cypress needs it for Vite + dotenv. See flip-ui/README.md → Testing → End-to-end tests for the dummy values to use locally." >&2; \
		exit 1; \
	}
	npm run test:ci:docker