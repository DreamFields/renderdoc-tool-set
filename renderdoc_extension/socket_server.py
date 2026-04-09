"""
File-based IPC server for RenderDoc renderdoc_toolset_bridge.
Uses file polling since RenderDoc's Python doesn't have socket or QtNetwork modules.

Multi-session support
---------------------
Each ``MCPBridgeServer`` instance operates on its own IPC sub-directory so that
multiple RenderDoc processes can coexist.  The per-instance paths are derived
from :mod:`renderdoc_extension.settings` which creates a ``session_<pid>``
sub-directory by default.
"""



import datetime
import json
import os
import traceback
import importlib
import threading


_QTCORE_CANDIDATES = [
    "PySide2.QtCore",
    "PySide6.QtCore",
    "PyQt5.QtCore",
    "PyQt6.QtCore",
    "PySide.QtCore",
]


_qt_object_cls = None
_qt_timer_cls = None
for _module_name in _QTCORE_CANDIDATES:
    try:
        _qtcore = importlib.import_module(_module_name)
        _qt_object_cls = _qtcore.QObject
        _qt_timer_cls = _qtcore.QTimer
        break
    except ImportError:
        pass

_HAS_QT_TIMER = _qt_object_cls is not None and _qt_timer_cls is not None

from . import settings


class MCPBridgeServer(object):
    """File-based IPC server for bridge communication.

    Parameters
    ----------
    host, port : str, int
        Legacy fields kept for status reporting.
    handler : RequestHandler
        Delegates actual request execution.
    version : str
        RenderDoc version string written into status.
    ipc_dir : str or None
        Per-instance IPC directory.  Defaults to ``settings.IPC_DIR``.
    session_id : str or None
        Human-readable session identifier.  Defaults to ``settings.SESSION_ID``.
    parent : object
        Unused, kept for Qt-style compatibility.
    """

    def __init__(self, host, port, handler, version="",
                 ipc_dir=None, session_id=None, parent=None):
        self.host = host
        self.port = port
        self.handler = handler
        self.version = version

        # Per-instance IPC paths
        self._ipc_dir = ipc_dir or settings.IPC_DIR
        self._session_id = session_id or settings.SESSION_ID
        self._request_file = os.path.join(self._ipc_dir, settings.REQUEST_FILE_NAME)
        self._response_file = os.path.join(self._ipc_dir, settings.RESPONSE_FILE_NAME)
        self._lock_file = os.path.join(self._ipc_dir, settings.LOCK_FILE_NAME)
        self._status_file = os.path.join(self._ipc_dir, settings.STATUS_FILE_NAME)
        self._poll_interval_ms = settings.POLL_INTERVAL_MS

        self._timer = None
        self._poll_thread = None
        self._thread_stop = None
        self._running = False
        self._requests_served = 0
        self._last_error = None
        self._last_request_id = None
        self._last_request_method = None
        self._started_at = None

        # Ensure the root IPC dir exists as well as the session sub-dir.
        if not os.path.exists(self._ipc_dir):
            os.makedirs(self._ipc_dir)

    # -- public properties ---------------------------------------------------

    @property
    def ipc_dir(self):
        return self._ipc_dir

    @property
    def session_id(self):
        return self._session_id

    def start(self):
        """Start the polling server."""
        self._running = True
        self._started_at = self._now_iso()
        self._cleanup_transient_files()
        self._write_status()

        if _HAS_QT_TIMER:
            qt_timer_cls = _qt_timer_cls
            if qt_timer_cls is None:
                raise RuntimeError("Qt timer backend is marked available but class is missing")
            self._timer = qt_timer_cls()
            self._timer.timeout.connect(self._poll_request)
            self._timer.start(self._poll_interval_ms)
            print("[renderdoc_toolset_bridge] Polling backend: Qt QTimer")
        else:
            self._thread_stop = threading.Event()
            self._poll_thread = threading.Thread(
                target=self._thread_poll_loop,
                name="MCPBridgePollLoop",
            )
            self._poll_thread.daemon = True
            self._poll_thread.start()
            print("[renderdoc_toolset_bridge] Polling backend: Python thread fallback")

        print("[renderdoc_toolset_bridge] File-based IPC server started")
        print("[renderdoc_toolset_bridge] Session: %s" % self._session_id)
        print("[renderdoc_toolset_bridge] IPC directory: %s" % self._ipc_dir)
        return True

    def stop(self):
        """Stop the polling server and clean up the session directory."""
        self._running = False

        if self._timer:
            self._timer.stop()
            self._timer = None

        if self._thread_stop:
            self._thread_stop.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=1.0)
        self._poll_thread = None
        self._thread_stop = None

        self._cleanup_transient_files()

        # Write a final "stopped" status then remove the entire session dir.
        self._write_status()
        self._cleanup_session_dir()

        print("[renderdoc_toolset_bridge] Server stopped (session %s)" % self._session_id)

    def _cleanup_session_dir(self):
        """Remove the session sub-directory (best-effort).

        Called on clean shutdown so the MCP server doesn't need to
        garbage-collect stale directories.
        """
        import shutil
        try:
            shutil.rmtree(self._ipc_dir)
        except Exception:
            # Directory may be locked or partially removed — not critical.
            pass

    def is_running(self):
        """Return whether the server is active."""
        return self._running

    def _thread_poll_loop(self):
        """Fallback polling loop when Qt timer is unavailable."""
        interval_sec = max(0.01, float(self._poll_interval_ms) / 1000.0)
        while self._running and self._thread_stop and not self._thread_stop.is_set():
            self._poll_request()
            _ = self._thread_stop.wait(interval_sec)

    def _cleanup_transient_files(self):
        """Remove request/response synchronization files."""
        for file_path in [self._request_file, self._response_file, self._lock_file]:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass

    def _poll_request(self):
        """Check for an incoming request."""
        if not self._running:
            return

        if not os.path.exists(self._request_file):
            return

        if os.path.exists(self._lock_file):
            return

        try:
            with open(self._request_file, "r", encoding="utf-8") as request_handle:
                request = json.load(request_handle)

            os.remove(self._request_file)

            self._last_request_id = request.get("id")
            self._last_request_method = request.get("method")
            self._last_error = None
            self._write_status()

            try:
                response = self.handler.handle(request)
                self._requests_served += 1
            except Exception as exc:
                traceback.print_exc()
                self._last_error = str(exc)
                response = {
                    "id": request.get("id"),
                    "error": {"code": -32603, "message": str(exc)},
                }

            with open(self._response_file, "w", encoding="utf-8") as response_handle:
                json.dump(response, response_handle)

            self._write_status()

        except Exception as exc:
            self._last_error = str(exc)
            self._write_status()
            print("[renderdoc_toolset_bridge] Error processing request: %s" % str(exc))
            traceback.print_exc()

    def _write_status(self):
        """Persist a lightweight runtime status snapshot."""
        payload = {
            "running": self._running,
            "session_id": self._session_id,
            "pid": os.getpid(),
            "host": self.host,
            "port": self.port,
            "version": self.version,
            "ipc_dir": self._ipc_dir,
            "poll_interval_ms": self._poll_interval_ms,
            "started_at": self._started_at,
            "updated_at": self._now_iso(),
            "requests_served": self._requests_served,
            "last_request_id": self._last_request_id,
            "last_request_method": self._last_request_method,
            "last_error": self._last_error,
        }
        with open(self._status_file, "w", encoding="utf-8") as status_handle:
            json.dump(payload, status_handle)

    def _now_iso(self):
        """Return the current UTC timestamp as an ISO string."""
        return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
