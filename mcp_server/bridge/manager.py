"""
Multi-session bridge manager.

Scans the IPC root directory for active session sub-directories and maintains
a ``session_id → RenderDocBridge`` mapping.  Provides helpers used by the MCP
tool layer to route requests to the correct RenderDoc instance.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from typing import Any

from .client import RenderDocBridge, RenderDocBridgeError
from ..config import settings


class BridgeManager:
    """Manage multiple RenderDocBridge instances (one per session).

    Auto-discovery
    --------------
    ``discover()`` scans ``ipc_root_dir`` for sub-directories that contain a
    ``status.json`` with ``"running": true``.  Each discovered directory is
    wrapped in a ``RenderDocBridge`` and keyed by its ``session_id`` field
    (falling back to the directory name).

    Default session
    ---------------
    When only one session is active, it is used automatically.  If multiple
    sessions are active the caller must either pass ``session=...`` or call
    ``set_default_session()`` first.
    """

    def __init__(
        self,
        ipc_root_dir: str | None = None,
        host: str | None = None,
        port: int | None = None,
    ):
        self._ipc_root = ipc_root_dir or settings.ipc_root_dir
        self._host = host or settings.renderdoc_host
        self._port = port or settings.renderdoc_port

        # session_id → RenderDocBridge
        self._bridges: dict[str, RenderDocBridge] = {}
        # session_id → last status dict
        self._status_cache: dict[str, dict[str, Any]] = {}

        self._default_session: str | None = None

    # -- discovery -----------------------------------------------------------

    def discover(self) -> dict[str, dict[str, Any]]:
        """Scan the IPC root for active sessions.

        Returns a dict of ``{session_id: status_dict}`` for every *running*
        session found.  Also updates internal bridge instances.

        Sessions whose owning process (PID) no longer exists are treated as
        stale: their IPC directory is removed and they are not included in the
        result.
        """
        found: dict[str, dict[str, Any]] = {}

        if not os.path.isdir(self._ipc_root):
            self._bridges.clear()
            self._status_cache.clear()
            return found

        for entry in os.listdir(self._ipc_root):
            sub_dir = os.path.join(self._ipc_root, entry)
            if not os.path.isdir(sub_dir):
                continue

            status_file = os.path.join(sub_dir, settings.status_file_name)
            if not os.path.isfile(status_file):
                continue

            try:
                with open(status_file, "r", encoding="utf-8") as fh:
                    status = json.load(fh)
            except Exception:
                continue

            if not status.get("running", False):
                # Explicitly stopped session — clean up the directory.
                self._cleanup_session_dir(sub_dir)
                continue

            # Verify the owning process is still alive.
            pid = status.get("pid")
            if pid is not None and not self._is_pid_alive(pid):
                # Process exited without a clean shutdown — garbage-collect.
                self._cleanup_session_dir(sub_dir)
                continue

            session_id = status.get("session_id", entry)
            found[session_id] = status

            # Create or update the bridge instance for this session.
            if session_id not in self._bridges:
                self._bridges[session_id] = RenderDocBridge(
                    host=self._host,
                    port=self._port,
                    ipc_dir=sub_dir,
                )
            self._status_cache[session_id] = status

        # Prune stale bridges that are no longer discovered.
        stale = set(self._bridges.keys()) - set(found.keys())
        for sid in stale:
            del self._bridges[sid]
            self._status_cache.pop(sid, None)

        # If the default session is stale, clear it.
        if self._default_session and self._default_session not in self._bridges:
            self._default_session = None

        return found

    # -- internal helpers ----------------------------------------------------

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        """Check whether a process with *pid* is still running.

        Works on both Windows and POSIX without external dependencies.
        """
        if os.name == "nt":
            # Windows: use kernel32.OpenProcess; returns 0 / NULL on failure.
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return exit_code.value == STILL_ACTIVE
                return False
            finally:
                kernel32.CloseHandle(handle)
        else:
            # POSIX: signal 0 doesn't actually send a signal but checks
            # whether we *could* signal the process.
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return False
            except PermissionError:
                # Process exists but we don't own it — still alive.
                return True
            return True

    @staticmethod
    def _cleanup_session_dir(path: str) -> None:
        """Remove a stale session directory (best-effort)."""
        try:
            shutil.rmtree(path)
        except Exception:
            pass

    # -- session routing -----------------------------------------------------

    def get_bridge(self, session: str | None = None) -> RenderDocBridge:
        """Return the bridge for *session*.

        Resolution order:

        1. If *session* is given, look it up directly.
        2. If a default session is set, use it.
        3. If exactly one session is active, use it automatically.
        4. Otherwise raise an error with helpful guidance.
        """
        # Always refresh discovery to catch newly launched / stopped instances.
        self.discover()

        if session:
            if session in self._bridges:
                return self._bridges[session]
            raise RenderDocBridgeError(
                "Session '%s' not found.  Active sessions: %s"
                % (session, list(self._bridges.keys()))
            )

        if self._default_session and self._default_session in self._bridges:
            return self._bridges[self._default_session]

        if len(self._bridges) == 1:
            return next(iter(self._bridges.values()))

        if len(self._bridges) == 0:
            raise RenderDocBridgeError(
                "No active RenderDoc sessions found.  "
                "Make sure RenderDoc is running with the renderdoc_toolset_bridge extension loaded.  "
                "IPC root: %s" % self._ipc_root
            )

        raise RenderDocBridgeError(
            "Multiple active sessions found: %s.  "
            "Please specify session=<id> or call set_default_session() first."
            % list(self._bridges.keys())
        )

    def set_default_session(self, session_id: str) -> None:
        """Pin a default session so that tools without an explicit session
        parameter are routed to the right instance."""
        self.discover()
        if session_id not in self._bridges:
            raise RenderDocBridgeError(
                "Cannot set default: session '%s' not found.  Active: %s"
                % (session_id, list(self._bridges.keys()))
            )
        self._default_session = session_id

    def get_default_session(self) -> str | None:
        return self._default_session

    # -- convenience ---------------------------------------------------------

    def list_sessions(self) -> dict[str, Any]:
        """Return a summary suitable for the ``list_sessions`` MCP tool."""
        active = self.discover()
        sessions = []
        for sid, status in active.items():
            sessions.append({
                "session_id": sid,
                "pid": status.get("pid"),
                "version": status.get("version"),
                "ipc_dir": status.get("ipc_dir"),
                "started_at": status.get("started_at"),
                "updated_at": status.get("updated_at"),
                "requests_served": status.get("requests_served"),
                "is_default": sid == self._default_session,
            })
        return {
            "count": len(sessions),
            "sessions": sessions,
            "default_session": self._default_session,
            "ipc_root_dir": self._ipc_root,
        }

    def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        session: str | None = None,
    ) -> Any:
        """Route a bridge call to the correct session."""
        bridge = self.get_bridge(session)
        return bridge.call(method, params)
