"""
RenderDoc Bridge Client
Communicates with the RenderDoc extension via file-based IPC.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from ..config import settings


class RenderDocBridgeError(Exception):
    """Error communicating with the RenderDoc bridge."""

    pass


class RenderDocBridge:
    """Client for communicating with the RenderDoc extension via file-based IPC."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 19876,
        ipc_dir: str | None = None,
        timeout: float | None = None,
        poll_interval: float | None = None,
        response_ready_delay: float | None = None,
    ):
        self.host = host
        self.port = port
        self.ipc_dir = ipc_dir or settings.ipc_dir
        self.timeout = (
            settings.request_timeout_seconds if timeout is None else float(timeout)
        )
        self.poll_interval = (
            settings.response_poll_interval_seconds
            if poll_interval is None
            else float(poll_interval)
        )
        self.response_ready_delay = (
            settings.response_ready_delay_seconds
            if response_ready_delay is None
            else float(response_ready_delay)
        )

        self.request_file = os.path.join(self.ipc_dir, settings.request_file_name)
        self.response_file = os.path.join(self.ipc_dir, settings.response_file_name)
        self.lock_file = os.path.join(self.ipc_dir, settings.lock_file_name)
        self.status_file = os.path.join(self.ipc_dir, settings.status_file_name)

    def ping(self) -> dict[str, Any]:
        """Measure bridge round-trip latency."""
        started_at = time.time()
        result = self.call("ping")
        result["latency_ms"] = round((time.time() - started_at) * 1000.0, 3)
        return result

    def get_status(self) -> dict[str, Any]:
        """Return a diagnostic snapshot without issuing a bridge request."""
        status: dict[str, Any] = {
            "bridge_reachable": False,
            "ipc_dir": self.ipc_dir,
            "request_file": self.request_file,
            "response_file": self.response_file,
            "lock_file": self.lock_file,
            "status_file": self.status_file,
            "request_timeout_seconds": self.timeout,
            "response_poll_interval_seconds": self.poll_interval,
            "response_ready_delay_seconds": self.response_ready_delay,
            "ipc_dir_exists": os.path.exists(self.ipc_dir),
            "status_file_exists": os.path.exists(self.status_file),
        }

        if not os.path.exists(self.status_file):
            return status

        try:
            extension_status = self._read_json(self.status_file)
            status["extension_status"] = extension_status
            status["bridge_reachable"] = bool(extension_status.get("running", False))
        except Exception as exc:
            status["status_read_error"] = str(exc)

        return status

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Call a method on the RenderDoc extension."""
        if not os.path.exists(self.ipc_dir):
            raise RenderDocBridgeError(
                "Cannot connect to RenderDoc renderdoc_toolset_bridge at %s:%s. "
                "Make sure RenderDoc is running with the renderdoc_toolset_bridge extension loaded."
                % (self.host, self.port)
            )

        request = {
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params or {},
        }

        try:
            if os.path.exists(self.response_file):
                os.remove(self.response_file)

            with open(self.lock_file, "w", encoding="utf-8") as lock_handle:
                lock_handle.write("lock")

            with open(self.request_file, "w", encoding="utf-8") as request_handle:
                json.dump(request, request_handle)

            os.remove(self.lock_file)

            start_time = time.time()
            while True:
                if os.path.exists(self.response_file):
                    time.sleep(self.response_ready_delay)
                    response = self._read_json(self.response_file)
                    os.remove(self.response_file)

                    if "error" in response:
                        error = response["error"]
                        raise RenderDocBridgeError(
                            "[%s] %s" % (error["code"], error["message"])
                        )

                    return response.get("result")

                if time.time() - start_time > self.timeout:
                    raise RenderDocBridgeError("Request timed out")

                time.sleep(self.poll_interval)

        except RenderDocBridgeError:
            raise
        except Exception as exc:
            raise RenderDocBridgeError("Communication error: %s" % exc)

    def _read_json(self, file_path: str) -> dict[str, Any]:
        """Read and decode a JSON file."""
        with open(file_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
