"""Shared IPC settings for the RenderDoc extension runtime.

Multi-session support
---------------------
Each RenderDoc process creates its own IPC sub-directory under the root IPC
directory so that multiple instances can coexist without file collisions.

Layout::

    %TEMP%/renderdoc_mcp/           <-- IPC_ROOT_DIR
        session_<pid>/              <-- IPC_DIR (per-process)
            request.json
            response.json
            lock
            status.json

For backward compatibility the environment variable ``RENDERDOC_MCP_IPC_DIR``
still works: when set it is treated as the *root* and a per-process sub-folder
is created beneath it.  If the user explicitly sets
``RENDERDOC_MCP_SESSION_DIR`` the extension uses that directory *as-is* with
no automatic sub-folder creation (useful for manual multi-instance setups).
"""



import os
import tempfile


DEFAULT_IPC_ROOT = os.path.join(tempfile.gettempdir(), "renderdoc_mcp")
IPC_ROOT_DIR = os.environ.get("RENDERDOC_MCP_IPC_DIR", DEFAULT_IPC_ROOT)

# Allow the user to pin an exact session directory (no auto-subfolder).
_explicit_session_dir = os.environ.get("RENDERDOC_MCP_SESSION_DIR", "")

if _explicit_session_dir:
    IPC_DIR = _explicit_session_dir
else:
    IPC_DIR = os.path.join(IPC_ROOT_DIR, "session_%d" % os.getpid())

REQUEST_FILE_NAME = os.environ.get("RENDERDOC_MCP_REQUEST_FILE", "request.json")
RESPONSE_FILE_NAME = os.environ.get("RENDERDOC_MCP_RESPONSE_FILE", "response.json")
LOCK_FILE_NAME = os.environ.get("RENDERDOC_MCP_LOCK_FILE", "lock")
STATUS_FILE_NAME = os.environ.get("RENDERDOC_MCP_STATUS_FILE", "status.json")

REQUEST_FILE = os.path.join(IPC_DIR, REQUEST_FILE_NAME)
RESPONSE_FILE = os.path.join(IPC_DIR, RESPONSE_FILE_NAME)
LOCK_FILE = os.path.join(IPC_DIR, LOCK_FILE_NAME)
STATUS_FILE = os.path.join(IPC_DIR, STATUS_FILE_NAME)

POLL_INTERVAL_MS = int(os.environ.get("RENDERDOC_MCP_EXTENSION_POLL_MS", "100"))

# Session identity tag — written into status.json so the MCP server can
# distinguish sessions.  Defaults to ``session_<pid>``.
SESSION_ID = os.environ.get(
    "RENDERDOC_MCP_SESSION_ID",
    os.path.basename(IPC_DIR),
)
