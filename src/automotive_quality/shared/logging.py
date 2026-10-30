from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level.upper(), format="%(message)s")


def log_event(logger: logging.Logger, event: str, **context: Any) -> None:
    logger.info(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **context}, default=str))

