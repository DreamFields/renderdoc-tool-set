"""
RenderDoc renderdoc_toolset_bridge Extension.
Provides file-based bridge services for external MCP clients.

Multi-session support: each RenderDoc process creates its own IPC sub-directory
so that multiple instances can coexist.
"""



from . import renderdoc_facade
from . import request_handler
from . import settings
from . import socket_server

_context = None
_server = None
_version = ""

try:
    import qrenderdoc as qrd

    _has_qrenderdoc = True
except ImportError:
    _has_qrenderdoc = False



def register(version, ctx):
    """Called when the extension is loaded by RenderDoc."""
    global _context, _server, _version
    _version = version
    _context = ctx

    facade = renderdoc_facade.RenderDocFacade(ctx)
    handler = request_handler.RequestHandler(facade)

    _server = socket_server.MCPBridgeServer(
        host="127.0.0.1",
        port=19876,
        handler=handler,
        version=version,
        ipc_dir=settings.IPC_DIR,
        session_id=settings.SESSION_ID,
    )
    _server.start()

    if _has_qrenderdoc:
        try:
            ctx.Extensions().RegisterWindowMenu(
                qrd.WindowMenu.Tools, ["renderdoc_toolset_bridge", "Status"], _show_status
            )
        except Exception as exc:
            print("[renderdoc_toolset_bridge] Could not register menu: %s" % str(exc))

    print("[renderdoc_toolset_bridge] Extension loaded (RenderDoc %s)" % version)
    print("[renderdoc_toolset_bridge] Session: %s" % settings.SESSION_ID)
    print("[renderdoc_toolset_bridge] IPC directory: %s" % settings.IPC_DIR)



def unregister():
    """Called when the extension is unloaded."""
    global _server
    if _server:
        _server.stop()
        _server = None
    print("[renderdoc_toolset_bridge] Extension unloaded")



def _show_status(ctx, data):
    """Show a basic bridge status dialog."""
    if _server and _server.is_running():
        ctx.Extensions().MessageDialog(
            "renderdoc_toolset_bridge is running.\n"
            "Session: %s\n"
            "IPC: %s\n"
            "Poll: %sms"
            % (settings.SESSION_ID, settings.IPC_DIR, settings.POLL_INTERVAL_MS),
            "renderdoc_toolset_bridge Status",
        )
    else:
        ctx.Extensions().ErrorDialog("renderdoc_toolset_bridge is not running", "renderdoc_toolset_bridge Status")
