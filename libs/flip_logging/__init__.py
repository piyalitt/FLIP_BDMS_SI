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

from flip_logging.formatter import JSONFormatter
from flip_logging.context import request_context
from flip_logging.middleware import LoggingMiddleware
from flip_logging.filters import PIIRedactionFilter

import logging
import sys

_configured = False


def configure_logging(
    api_name: str,
    site: str = "unknown",
    level: str = "INFO",
) -> None:
    """Configure structured JSON logging for a FLIP API service.

    Args:
        api_name: The name of the API (e.g. "trust-api", "imaging-api").
        site: The site/trust name (e.g. "trustA"). Set via FLIP_SITE_NAME env var.
        level: Log level string (e.g. "DEBUG", "INFO"). Set via LOG_LEVEL env var.
    """
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter(api_name=api_name, site=site))
    handler.addFilter(PIIRedactionFilter())

    root.handlers.clear()
    root.addHandler(handler)

    # Suppress noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a logger with the given name."""
    return logging.getLogger(name)


__all__ = [
    "configure_logging",
    "get_logger",
    "JSONFormatter",
    "LoggingMiddleware",
    "PIIRedactionFilter",
    "request_context",
]
