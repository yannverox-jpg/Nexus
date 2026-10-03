import logging
import json
import time
import uuid
from typing import Dict, Any

class JSONCorrelationLogger:
    """
    Logger structuré JSON avec génération automatique d'un Correlation ID par tâche.
    """
    def __init__(self, name: str = "NEXUS_AUDIT"):
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def log(self, level: str, message: str, correlation_id: str = None, extra: Dict[str, Any] = None):
        cid = correlation_id or f"corr_{uuid.uuid4().hex[:8]}"
        payload = {
            "timestamp": time.time(),
            "level": level.upper(),
            "correlation_id": cid,
            "message": message,
            "extra": extra or {}
        }
        log_line = json.dumps(payload)
        if level.upper() == "ERROR" or level.upper() == "CRITICAL":
            self.logger.error(log_line)
        elif level.upper() == "WARNING":
            self.logger.warning(log_line)
        else:
            self.logger.info(log_line)

logger = JSONCorrelationLogger()
