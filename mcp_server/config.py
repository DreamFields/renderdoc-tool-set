"""Configuration for the enhanced RenderDoc MCP server.

Multi-session support
---------------------
``ipc_root_dir`` points to the parent directory that contains per-session
sub-folders (e.g. ``session_<pid>``).  ``ipc_dir`` is kept for backward
compatibility and points to ``ipc_root_dir`` itself — single-session tools
that only need one bridge still work as before.
"""

from __future__ import annotations

import os
import tempfile


class Settings:
    """Server settings loaded from environment variables."""

    def __init__(self):
        default_ipc_root = os.path.join(tempfile.gettempdir(), "renderdoc_mcp")

        self.renderdoc_host = os.environ.get("RENDERDOC_MCP_HOST", "127.0.0.1")
        self.renderdoc_port = int(os.environ.get("RENDERDOC_MCP_PORT", "19876"))

        # Root IPC directory that contains per-session sub-directories.
        self.ipc_root_dir = os.environ.get("RENDERDOC_MCP_IPC_DIR", default_ipc_root)

        # Legacy alias — kept so that RenderDocBridge can still be pointed at a
        # single directory when used outside the multi-session manager.
        self.ipc_dir = self.ipc_root_dir

        self.request_timeout_seconds = float(
            os.environ.get("RENDERDOC_MCP_TIMEOUT", "120")
        )
        self.response_poll_interval_seconds = float(
            os.environ.get("RENDERDOC_MCP_RESPONSE_POLL", "0.05")
        )
        self.response_ready_delay_seconds = float(
            os.environ.get("RENDERDOC_MCP_RESPONSE_DELAY", "0.01")
        )
        self.extension_poll_interval_ms = int(
            os.environ.get("RENDERDOC_MCP_EXTENSION_POLL_MS", "100")
        )

        self.request_file_name = os.environ.get(
            "RENDERDOC_MCP_REQUEST_FILE", "request.json"
        )
        self.response_file_name = os.environ.get(
            "RENDERDOC_MCP_RESPONSE_FILE", "response.json"
        )
        self.lock_file_name = os.environ.get("RENDERDOC_MCP_LOCK_FILE", "lock")
        self.status_file_name = os.environ.get(
            "RENDERDOC_MCP_STATUS_FILE", "status.json"
        )

    @property
    def request_file(self) -> str:
        return os.path.join(self.ipc_dir, self.request_file_name)

    @property
    def response_file(self) -> str:
        return os.path.join(self.ipc_dir, self.response_file_name)

    @property
    def lock_file(self) -> str:
        return os.path.join(self.ipc_dir, self.lock_file_name)

    @property
    def status_file(self) -> str:
        return os.path.join(self.ipc_dir, self.status_file_name)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable snapshot of current settings."""
        return {
            "renderdoc_host": self.renderdoc_host,
            "renderdoc_port": self.renderdoc_port,
            "ipc_root_dir": self.ipc_root_dir,
            "ipc_dir": self.ipc_dir,
            "request_timeout_seconds": self.request_timeout_seconds,
            "response_poll_interval_seconds": self.response_poll_interval_seconds,
            "response_ready_delay_seconds": self.response_ready_delay_seconds,
            "extension_poll_interval_ms": self.extension_poll_interval_ms,
            "request_file": self.request_file,
            "response_file": self.response_file,
            "lock_file": self.lock_file,
            "status_file": self.status_file,
        }


settings = Settings()
