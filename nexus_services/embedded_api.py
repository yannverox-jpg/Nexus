"""Run the private operational API inside the Streamlit service process."""

from __future__ import annotations

import atexit
import os
import threading
import time
from typing import List, Optional

_server = None
_thread: Optional[threading.Thread] = None
_lock = threading.Lock()
_errors: List[BaseException] = []


def _run_server(server) -> None:
    try:
        server.run()
    except BaseException as exc:
        _errors.append(exc)


def _shutdown_server() -> None:
    if _server is not None:
        _server.should_exit = True
    if _thread is not None and _thread.is_alive():
        _thread.join(timeout=10)


def ensure_operational_api(timeout: float = 30.0) -> None:
    """Start the private Nexus API once, bound to loopback, and await startup."""
    global _server, _thread

    with _lock:
        if _server is not None and _thread is not None:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline and _thread.is_alive() and not _server.started:
                time.sleep(0.1)
            if _server.started and _thread.is_alive():
                return
            error = _errors[-1] if _errors else None
            raise RuntimeError("The private Nexus API is not running") from error
        port = int(os.getenv("NEXUS_API_PORT", "8000"))
        import uvicorn
        from .operational_api import app

        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level=os.getenv("NEXUS_API_LOG_LEVEL", "warning"),
            access_log=False,
            lifespan="on",
        )
        _server = uvicorn.Server(config)
        _thread = threading.Thread(
            target=_run_server,
            args=(_server,),
            name="nexus-private-api",
            daemon=True,
        )
        _thread.start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if _server.started and _thread.is_alive():
                atexit.register(_shutdown_server)
                return
            if not _thread.is_alive():
                error = _errors[-1] if _errors else None
                raise RuntimeError("The private Nexus API stopped during startup") from error
            time.sleep(0.1)
        _server.should_exit = True
        raise RuntimeError(f"The private Nexus API did not start within {timeout:g} seconds")