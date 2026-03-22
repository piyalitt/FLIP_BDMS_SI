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

import json
import logging
import re
from contextvars import ContextVar
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Per-request context
# ---------------------------------------------------------------------------

# Holds a dict of fields (request_id, user_id, etc.) that get merged into
# every log record emitted during that request.
request_context: ContextVar[dict | None] = ContextVar("request_context", default=None)

# ---------------------------------------------------------------------------
# PII redaction
# ---------------------------------------------------------------------------

# NHS number: 10 consecutive digits (with optional spaces in groups of 3-3-4)
_NHS_NUMBER_PATTERN = re.compile(r"\b\d{3}\s?\d{3}\s?\d{4}\b")

# Email address
_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

_REDACTED = "[REDACTED]"


def _redact(text: str) -> str:
    """Replace potential PII patterns in a string."""
    text = _NHS_NUMBER_PATTERN.sub(_REDACTED, text)
    text = _EMAIL_PATTERN.sub(_REDACTED, text)
    return text


class PIIRedactionFilter(logging.Filter):
    """Defence-in-depth filter that redacts potential PII from log messages.

    Developers should never log patient data, but this filter catches
    accidental inclusion of NHS numbers and email addresses.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg and isinstance(record.msg, str):
            record.msg = _redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _redact(str(v)) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(_redact(str(a)) if isinstance(a, str) else a for a in record.args)
        return True


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------

# Fields from LogRecord that we handle explicitly or want to exclude from extras
_BUILTIN_ATTRS = frozenset({
    "args", "created", "exc_info", "exc_text", "filename", "funcName",
    "levelname", "levelno", "lineno", "message", "module", "msecs", "msg",
    "name", "pathname", "process", "processName", "relativeCreated",
    "stack_info", "thread", "threadName", "taskName",
})


class JSONFormatter(logging.Formatter):
    """Outputs log records as single-line JSON objects."""

    def __init__(self, api_name: str, site: str) -> None:
        super().__init__()
        self.api_name = api_name
        self.site = site

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "api": self.api_name,
            "site": self.site,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Merge request-scoped context
        ctx = request_context.get()
        if ctx:
            entry.update(ctx)

        # Merge extra fields passed via logger.info("msg", extra={...})
        for key, val in record.__dict__.items():
            if key not in _BUILTIN_ATTRS and key not in entry:
                entry[key] = val

        if record.exc_info and record.exc_info[1] is not None:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, default=str)
