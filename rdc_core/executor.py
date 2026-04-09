"""Shared executor that both MCP server and CLI use to invoke operations.

This module encapsulates all special-case handling (local ops, preset
merging, multi-step IPC) so that callers only need to call
``executor.execute(name, params)``.
"""

from __future__ import annotations

import base64
import glob
import os
import shutil
import traceback
from pathlib import Path
from typing import Any

from mcp_server.bridge.manager import BridgeManager
from mcp_server.config import settings
from mcp_server.presets import list_presets, merge_filters

from .registry import get_operation, list_operations

# Operations resolved locally without IPC
_LOCAL_OPS = {"list_sessions", "set_default_session", "ping_bridge", "get_bridge_status"}

# Operations that support preset merging
_PRESET_OPS = {"get_draw_calls", "get_action_timings"}

# Operations requiring multi-step IPC logic
_MULTI_STEP_OPS = {"get_render_target_thumbnail"}

# Operations needing structured error wrapping
_ERROR_WRAP_OPS = {"get_render_target_diff"}


class Executor:
    """Execute registered operations through BridgeManager.

    This is the single call-path used by both MCP tools and CLI commands.
    """

    def __init__(self, manager: BridgeManager):
        self.manager = manager

    def execute(
        self,
        operation_name: str,
        params: dict[str, Any] | None = None,
        session: str | None = None,
    ) -> dict[str, Any]:
        """Execute an operation by name."""
        params = dict(params or {})
        op = get_operation(operation_name)
        if op is None:
            raise ValueError("Unknown operation: %s" % operation_name)

        # ── Local operations (no IPC) ────────────────────────────
        if operation_name == "list_sessions":
            return self.manager.list_sessions()

        if operation_name == "set_default_session":
            self.manager.set_default_session(params["session_id"])
            return {
                "success": True,
                "default_session": params["session_id"],
                "message": (
                    "Default session set to '%s'. All subsequent calls "
                    "without an explicit session parameter will use this session."
                    % params["session_id"]
                ),
            }

        if operation_name == "ping_bridge":
            return self.manager.get_bridge(session).ping()

        if operation_name == "get_bridge_status":
            return self.manager.get_bridge(session).get_status()

        if operation_name == "list_filter_presets":
            presets = list_presets()
            return {"count": len(presets), "presets": presets}

        if operation_name == "get_server_config":
            presets = list_presets()
            return {
                "settings": settings.to_dict(),
                "preset_names": sorted(presets.keys()),
            }

        if operation_name == "get_capabilities":
            return self._get_capabilities()

        if operation_name == "list_renderdoc_versions":
            return self._list_renderdoc_versions()

        if operation_name == "switch_renderdoc_version":
            return self._switch_renderdoc_version(params["version"])

        if operation_name == "uninstall_extension":
            return self._uninstall_extension()

        # ── Multi-step: get_render_target_thumbnail ──────────────
        if operation_name == "get_render_target_thumbnail":
            return self._render_target_thumbnail(params, session)

        # ── Error-wrapped: get_render_target_diff ────────────────
        if operation_name == "get_render_target_diff":
            return self._render_target_diff(params, session)

        # ── Preset-aware operations ──────────────────────────────
        preset_meta = None
        if operation_name in _PRESET_OPS:
            preset_name = params.pop("preset", None)
            if preset_name is not None:
                params, preset_meta = merge_filters(params, preset_name)

        # ── Standard IPC call ────────────────────────────────────
        result = self.manager.call(
            operation_name, params or None, session=session,
        )

        # Attach preset metadata if applicable
        if preset_meta is not None:
            result["applied_preset"] = preset_meta
            result["request_params"] = params
            if session is not None:
                result["session"] = session

        return result

    # ── Private helpers ──────────────────────────────────────────

    def _get_capabilities(self) -> dict[str, Any]:
        """Return server capabilities summary."""
        presets = list_presets()
        tools = [op.name for op in list_operations()]
        return {
            "server_name": "RenderDoc Tools MCP Server",
            "version": "1.0.0",
            "tool_count": len(tools),
            "tools": tools,
            "preset_names": sorted(presets.keys()),
            "settings": settings.to_dict(),
            "multi_session": True,
        }

    @staticmethod
    def _list_renderdoc_versions() -> dict[str, Any]:
        """Scan common install paths for RenderDoc versions."""
        search_paths: list[str] = []
        if os.name == "nt":
            for base in [
                os.environ.get("ProgramFiles", r"C:\Program Files"),
                os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                os.path.expanduser("~"),
            ]:
                if base:
                    search_paths.append(os.path.join(base, "RenderDoc*"))
        else:
            search_paths.extend([
                "/usr/local/share/renderdoc*",
                "/opt/renderdoc*",
                os.path.expanduser("~/renderdoc*"),
            ])

        versions = []
        for pattern in search_paths:
            for path in glob.glob(pattern):
                if os.path.isdir(path):
                    info: dict[str, Any] = {
                        "path": path,
                        "name": os.path.basename(path),
                    }
                    for fname in [
                        "renderdoccmd.exe", "renderdoccmd",
                        "qrenderdoc.exe", "qrenderdoc",
                    ]:
                        exe = os.path.join(path, fname)
                        if os.path.isfile(exe):
                            info["executable"] = exe
                            break
                    versions.append(info)

        return {
            "count": len(versions),
            "versions": versions,
            "note": (
                "Use switch_renderdoc_version to change the active version. "
                "A server restart is required after switching."
            ),
        }

    @staticmethod
    def _switch_renderdoc_version(version: str) -> dict[str, Any]:
        """Set RENDERDOC_VERSION env var."""
        os.environ["RENDERDOC_VERSION"] = version
        return {
            "success": True,
            "version": version,
            "message": (
                "RENDERDOC_VERSION set to '%s'. Please restart the MCP server "
                "for the change to take effect." % version
            ),
        }

    @staticmethod
    def _uninstall_extension() -> dict[str, Any]:
        """Uninstall renderdoc extension directories used by this project."""
        project_root = Path(__file__).resolve().parent.parent
        scripts_dir = project_root / "scripts"
        if str(scripts_dir) not in os.sys.path:
            os.sys.path.insert(0, str(scripts_dir))

        try:
            from install_extension import get_extension_dirs  # type: ignore
        except Exception as exc:
            return {
                "success": False,
                "error": "Failed to load extension installer: %s" % str(exc),
            }

        removed: list[str] = []
        missing: list[str] = []

        try:
            for ext_dir in get_extension_dirs():
                dest = ext_dir / "renderdoc_toolset_bridge"
                if dest.exists():
                    shutil.rmtree(dest)
                    removed.append(str(dest))
                else:
                    missing.append(str(dest))
        except Exception as exc:
            return {
                "success": False,
                "error": "Failed to uninstall extension: %s" % str(exc),
                "removed": removed,
                "missing": missing,
            }

        return {
            "success": True,
            "removed": removed,
            "missing": missing,
            "removed_count": len(removed),
            "message": (
                "Extension uninstalled."
                if removed
                else "No installed extension directory was found."
            ),
        }

    def _render_target_thumbnail(
        self, params: dict[str, Any], session: str | None,
    ) -> dict[str, Any]:
        """Multi-step IPC: resolve RT resource then fetch thumbnail."""
        event_id = params["event_id"]
        rtv_index = params.get("rtv_index", 0)
        depth = params.get("depth", False)
        max_size = params.get("max_size", 256)
        output_path = params.get("output_path")

        def _is_null_resource_id(resource_id: Any) -> bool:
            if resource_id is None:
                return True
            rid_text = str(resource_id).strip()
            return rid_text in {
                "",
                "0",
                "ResourceId::0",
                "ResourceId::Null()",
                "ResourceId()",
                "Null",
            }

        # Step 1: get draw call details to find RT resource_id
        details = self.manager.call(
            "get_draw_call_details", {"event_id": event_id}, session=session,
        )

        resource_id = None
        actual_index = rtv_index
        if depth:
            depth_output = details.get("depth_output")
            if _is_null_resource_id(depth_output):
                raise ValueError(
                    "No depth attachment bound at event %d. "
                    "Try depth=False or choose an earlier event where depth is available."
                    % event_id
                )
            resource_id = depth_output
            actual_index = -1
        else:
            outputs = details.get("outputs", [])
            if rtv_index < len(outputs):
                resource_id = outputs[rtv_index].get("resource_id")
            elif outputs:
                resource_id = outputs[0].get("resource_id")
                actual_index = 0

        if _is_null_resource_id(resource_id):
            kind = "depth attachment" if depth else "render target (index %d)" % rtv_index
            raise ValueError("No %s found at event %d" % (kind, event_id))


        # Step 2: get texture thumbnail (unified save_texture_as_png)
        thumb_params: dict[str, Any] = {
            "resource_id": resource_id,
            "max_size": max_size,
        }
        if output_path is not None:
            thumb_params["output_path"] = output_path

        result = self.manager.call(
            "save_texture_as_png", thumb_params, session=session,
        )

        # Fallback: server-side save if extension returned base64
        if (
            output_path is not None
            and "thumbnail_base64" in result
            and "output_path" not in result
        ):
            png_bytes = base64.b64decode(result["thumbnail_base64"])
            with open(output_path, "wb") as f:
                f.write(png_bytes)
            result["output_path"] = output_path
            result["saved"] = True
            del result["thumbnail_base64"]

        result["event_id"] = event_id
        result["rtv_index"] = actual_index
        result["depth"] = depth
        return result

    def _render_target_diff(
        self, params: dict[str, Any], session: str | None,
    ) -> dict[str, Any]:
        """IPC call with structured error wrapping."""
        event_id = params.get("event_id")
        output_path = params.get("output_path")
        compare_event_id = params.get("compare_event_id")
        actual_compare = (
            compare_event_id
            if compare_event_id is not None
            else "auto (previous draw call)"
        )

        try:
            result = self.manager.call(
                "get_render_target_diff", params or None, session=session,
            )
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "traceback": traceback.format_exc(),
                "debug_info": {
                    "tool": "get_render_target_diff",
                    "event_id": event_id,
                    "compare_event_id": actual_compare,
                    "rtv_index": params.get("rtv_index", 0),
                    "depth": params.get("depth", False),
                    "threshold": params.get("threshold", 0),
                    "max_size": params.get("max_size", 512),
                    "output_path": output_path,
                    "session": session,
                },
                "hint": (
                    "Common causes: (1) No capture loaded in RenderDoc, "
                    "(2) Invalid event_id — use get_draw_calls to find valid IDs, "
                    "(3) No render target bound at the specified event, "
                    "(4) RenderDoc bridge not running or timed out, "
                    "(5) compare_event_id resolved to: %s" % actual_compare
                ),
            }

        # Fallback: server-side save if extension returned base64
        try:
            if (
                output_path is not None
                and "diff_base64" in result
                and "output_path" not in result
            ):
                png_bytes = base64.b64decode(result["diff_base64"])
                with open(output_path, "wb") as f:
                    f.write(png_bytes)
                result["output_path"] = output_path
                result["saved"] = True
                del result["diff_base64"]
        except Exception as exc:
            result["save_warning"] = (
                "Diff computed successfully but failed to save PNG to '%s': %s"
                % (output_path, str(exc))
            )

        result["success"] = True
        return result
