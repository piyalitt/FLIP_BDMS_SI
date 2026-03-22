###############
Logging Stack
###############

FLIP uses a structured logging stack at each Trust site to collect, store and
visualise application logs. The stack consists of three layers:

1. **flip_logging** -- a shared Python library that emits structured JSON logs
   with PII redaction.
2. **Promtail + Loki** -- Docker-native log collection and storage with 30-day
   retention.
3. **Grafana** -- a web dashboard for querying and visualising logs.

.. contents:: On this page
   :local:
   :depth: 2

************
Architecture
************

.. code-block:: text

   ┌─────────────┐  ┌──────────────────┐  ┌─────────────┐
   │  trust-api   │  │  data-access-api  │  │  imaging-api │
   │  (JSON logs  │  │  (JSON logs       │  │  (JSON logs  │
   │   to stdout) │  │   to stdout)      │  │   to stdout) │
   └──────┬───────┘  └────────┬──────────┘  └──────┬───────┘
          │                   │                     │
          └───────────┬───────┘─────────────────────┘
                      ▼
              ┌───────────────┐
              │   Promtail    │  Scrapes Docker logs via socket
              │  (port 9080)  │  Parses JSON, extracts labels
              └───────┬───────┘
                      ▼
              ┌───────────────┐
              │     Loki      │  Stores logs with labels
              │  (port 3100)  │  30-day retention
              └───────┬───────┘
                      ▼
              ┌───────────────┐
              │    Grafana    │  Query & visualise
              │  (port 3000)  │
              └───────────────┘

Each FLIP API service writes single-line JSON to stdout. Docker captures this
output. Promtail discovers containers via the Docker socket, parses the JSON
and forwards the logs to Loki. Grafana queries Loki through a pre-provisioned
datasource.

*******************
Application Logging
*******************

Shared library: ``flip_logging``
================================

All trust-side APIs use the ``flip_logging`` library located at
``libs/flip_logging/``. The library provides:

- **JSONFormatter** -- serialises every log record as a single-line JSON object
  containing ``timestamp``, ``level``, ``api``, ``site``, ``logger``,
  ``message`` and any extra fields.
- **PIIRedactionFilter** -- defence-in-depth filter that redacts NHS numbers
  (10-digit sequences) and email addresses before they reach the log output.
- **LoggingMiddleware** -- FastAPI/Starlette middleware that generates a
  ``request_id`` (from the ``X-Request-ID`` header or a UUID), logs
  ``REQUEST_STARTED`` / ``REQUEST_COMPLETED`` / ``REQUEST_FAILED`` events and
  records ``method``, ``path``, ``status_code`` and ``duration_ms``.
- **request_context** -- a ``contextvars.ContextVar`` that carries per-request
  fields (e.g. ``request_id``) into every log emitted during that request.

Initialisation
--------------

Each API initialises logging in its ``utils/logger.py`` module using values
from the service's Pydantic ``Settings`` class:

.. code-block:: python

   from flip_logging import configure_logging, get_logger
   from trust_api.config import get_settings

   _settings = get_settings()

   configure_logging(
       api_name="trust-api",
       site=_settings.FLIP_SITE_NAME,
       level=_settings.LOG_LEVEL,
   )

   logger = get_logger(__name__)

The two relevant settings are:

.. list-table::
   :header-rows: 1

   * - Setting
     - Default
     - Description
   * - ``LOG_LEVEL``
     - ``INFO`` (``DEBUG`` for imaging-api)
     - Python log level (``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``,
       ``CRITICAL``).
   * - ``FLIP_SITE_NAME``
     - ``unknown``
     - Human-readable trust/site name included in every log line for
       multi-site identification.

These are set via environment variables or ``.env.*`` files and read through
each service's Pydantic ``Settings`` class.

Structured events
-----------------

The library defines named event constants in ``flip_logging.events`` for
consistent log tagging across services:

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Category
     - Events
   * - Project lifecycle
     - ``PROJECT_SUBMITTED``, ``PROJECT_APPROVED``, ``PROJECT_STAGED``,
       ``PROJECT_UNSTAGED``, ``PROJECT_DELETED``
   * - Data access
     - ``COHORT_QUERY_SUBMITTED``, ``COHORT_RESULTS_RECEIVED``
   * - Imaging pipeline
     - ``IMAGING_PROJECT_CREATED``, ``IMAGING_STUDIES_IMPORTED``,
       ``IMAGING_STUDIES_REIMPORTED``
   * - Training
     - ``TRAINING_INITIATED``, ``TRAINING_COMPLETED``, ``TRAINING_FAILED``
   * - Model management
     - ``MODEL_CREATED``, ``MODEL_DELETED``, ``MODEL_STATUS_UPDATED``
   * - Request lifecycle
     - ``REQUEST_STARTED``, ``REQUEST_COMPLETED``, ``REQUEST_FAILED``

Use events via the ``event`` extra field:

.. code-block:: python

   from flip_logging.events import PROJECT_APPROVED

   logger.info("Project approved", extra={"event": PROJECT_APPROVED, "project_id": pid})

Log output format
-----------------

Every log line is a JSON object:

.. code-block:: json

   {
     "timestamp": "2025-06-15T10:23:45.123456Z",
     "level": "INFO",
     "api": "trust-api",
     "site": "gstt",
     "logger": "trust_api.routers.cohort",
     "message": "Project approved",
     "event": "PROJECT_APPROVED",
     "project_id": "abc-123",
     "request_id": "d4e5f6a7-..."
   }

*************************
Infrastructure Components
*************************

Promtail
========

Promtail discovers containers via the Docker socket and scrapes their stdout
logs. Configuration is at ``trust/promtail-config.yml``.

Key behaviours:

- Discovers containers every 5 seconds.
- Extracts Docker labels as log labels: ``container``, ``service``,
  ``project``.
- Parses JSON log lines and promotes ``level``, ``api``, ``event`` and
  ``request_id`` to Loki labels for efficient querying.

Loki
====

Loki is the log storage backend. Configuration is at
``trust/loki/loki-config.yml``.

Key settings:

.. list-table::
   :header-rows: 1

   * - Setting
     - Value
   * - Retention period
     - 720 hours (30 days)
   * - Schema version
     - v13 (TSDB)
   * - Storage backend
     - Local filesystem
   * - Index rotation
     - 24 hours
   * - Compaction interval
     - 10 minutes

Grafana
=======

Grafana provides the web UI for log exploration. It is pre-provisioned with a
Loki datasource (``trust/grafana/provisioning/datasources/loki.yml``) so no
manual configuration is required on first start.

Default credentials and port:

- **URL**: ``http://<trust-host>:3000``
- **Admin password**: set via ``GRAFANA_ADMIN_PASSWORD`` environment variable

*************
Configuration
*************

Environment variables
=====================

The following environment variables control the logging stack. Set them in the
appropriate ``.env.*`` file or pass them directly in the Docker Compose
override.

.. list-table::
   :header-rows: 1

   * - Variable
     - Service
     - Description
   * - ``LOG_LEVEL``
     - All APIs
     - Python log level (default ``INFO``, imaging-api defaults to ``DEBUG``)
   * - ``FLIP_SITE_NAME``
     - All APIs
     - Site identifier included in every log line
   * - ``GRAFANA_PORT``
     - Grafana
     - Host port for the Grafana UI (default ``3000``)
   * - ``GRAFANA_ADMIN_PASSWORD``
     - Grafana
     - Admin password for Grafana
   * - ``LOKI_PORT``
     - Loki
     - Host port for the Loki API (default ``3100``)

Docker Compose services
=======================

The logging infrastructure is defined in the trust-level Docker Compose files:

- ``trust/compose_trust.development.yml`` -- development overrides with
  configurable ports
- ``trust/compose_trust.production.yml`` -- production settings with persistent
  volumes and automatic restart

Three services are added:

1. **loki** (``grafana/loki:3.4.0``) -- log storage
2. **promtail** (``grafana/promtail:3.4.0``) -- log collector (depends on
   loki)
3. **grafana** (``grafana/grafana:11.5.0``) -- dashboard (depends on loki)

In production, persistent volumes are mounted at:

- ``/opt/flip/volumes/loki`` -- Loki data
- ``/opt/flip/volumes/grafana`` -- Grafana data and configuration

**************************
Operations & Querying Logs
**************************

Accessing Grafana
=================

1. Open ``http://<trust-host>:3000`` in a browser.
2. Log in with the admin credentials.
3. Navigate to **Explore** and select the **Loki** datasource.

Example LogQL queries
=====================

All logs from a specific API:

.. code-block:: text

   {api="trust-api"}

Errors only:

.. code-block:: text

   {level="ERROR"}

Logs for a specific event:

.. code-block:: text

   {event="TRAINING_FAILED"}

Full-text search within a service:

.. code-block:: text

   {api="data-access-api"} |= "timeout"

Correlate logs by request ID:

.. code-block:: text

   {api=~"trust-api|data-access-api|imaging-api"} |= "d4e5f6a7-..."

PII redaction
=============

The ``PIIRedactionFilter`` automatically redacts:

- **NHS numbers** -- any sequence of 10 consecutive digits (with optional
  spaces) is replaced with ``[NHS_NUMBER_REDACTED]``.
- **Email addresses** -- patterns matching ``user@domain`` are replaced with
  ``[EMAIL_REDACTED]``.

This is a defence-in-depth measure. Application code should avoid logging PII
in the first place.

***************
Troubleshooting
***************

Logs not appearing in Grafana
=============================

1. Check that the API containers are running: ``docker compose ps``.
2. Check Promtail can reach Loki: ``docker compose logs promtail``.
3. Verify Promtail has access to the Docker socket
   (``/var/run/docker.sock`` must be mounted).
4. Check Loki is healthy: ``curl http://localhost:3100/ready``.

High disk usage from Loki
=========================

Loki retains logs for 30 days. If disk space is a concern:

- Reduce ``retention_period`` in ``trust/loki/loki-config.yml``.
- Check that the compactor is running (``compaction_interval: 10m``).
- Monitor the ``/opt/flip/volumes/loki`` directory size.

Changing log level at runtime
=============================

``LOG_LEVEL`` is read at service startup. To change the level, update the
environment variable and restart the affected container:

.. code-block:: bash

   docker compose restart trust-api
