"""renderdoc-cli — AI-friendly command-line interface for .rdc analysis.

Uses the same BridgeManager + file IPC as the MCP server.
Requires a running RenderDoc instance with renderdoc_toolset_bridge extension loaded.

All commands dispatch through ``rdc_core.executor.Executor`` so that
preset merging, multi-step IPC, error wrapping and local operations
are handled identically to the MCP server.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from mcp_server.bridge.manager import BridgeManager
from mcp_server.config import settings

# Trigger operation registration
from rdc_core import operations as _ops  # noqa: F401
from rdc_core.executor import Executor

from .output import emit, emit_error


# ── Infrastructure ───────────────────────────────────────────────────

def _build_executor() -> Executor:
    """Create a BridgeManager + Executor pair from environment settings."""
    manager = BridgeManager(
        ipc_root_dir=settings.ipc_root_dir,
        host=settings.renderdoc_host,
        port=settings.renderdoc_port,
    )
    return Executor(manager)


# ── Command handlers ─────────────────────────────────────────────────
# Each handler receives (args, executor) and returns a dict result.

# -- Capture -----------------------------------------------------------

def cmd_status(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("get_capture_status", session=args.session)


def cmd_info(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("get_frame_summary", session=args.session)


def cmd_list_captures(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("list_captures", {"directory": args.directory}, session=args.session)


def cmd_open(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("open_capture", {"capture_path": args.path}, session=args.session)


# -- Draw calls --------------------------------------------------------

def cmd_draws(args: argparse.Namespace, exe: Executor) -> dict:
    params: dict[str, Any] = {"include_children": True}
    if args.only_actions:
        params["only_actions"] = True
    if args.flags:
        params["flags_filter"] = args.flags
    if args.marker:
        params["marker_filter"] = args.marker
    if args.exclude_markers:
        params["exclude_markers"] = args.exclude_markers
    if args.event_id_min is not None:
        params["event_id_min"] = args.event_id_min
    if args.event_id_max is not None:
        params["event_id_max"] = args.event_id_max
    if args.preset:
        params["preset"] = args.preset
    return exe.execute("get_draw_calls", params, session=args.session)


def cmd_summary(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("get_frame_summary", session=args.session)


def cmd_draw_detail(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("get_draw_call_details", {"event_id": args.event_id}, session=args.session)


def cmd_timings(args: argparse.Namespace, exe: Executor) -> dict:
    params: dict[str, Any] = {}
    if args.event_ids:
        params["event_ids"] = args.event_ids
    if args.marker:
        params["marker_filter"] = args.marker
    if args.exclude_markers:
        params["exclude_markers"] = args.exclude_markers
    if args.preset:
        params["preset"] = args.preset
    return exe.execute("get_action_timings", params, session=args.session)


# -- Pipeline ----------------------------------------------------------

def cmd_pipeline(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("get_pipeline_state", {"event_id": args.event_id}, session=args.session)


def cmd_pipelines(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("get_multiple_pipeline_states", {"event_ids": args.event_ids}, session=args.session)


def cmd_diff(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute(
        "compare_pipeline_states",
        {"base_event_id": args.base, "target_event_id": args.target},
        session=args.session,
    )

# -- Shader ------------------------------------------------------------

def cmd_shader_info(args: argparse.Namespace, exe: Executor) -> dict:
    params: dict[str, Any] = {"event_id": args.event_id, "stage": args.stage}
    if args.include_disassembly:
        params["include_disassembly"] = True
    if args.include_cbuffers:
        params["include_constant_buffers"] = True
    if args.include_resources:
        params["include_resources"] = True
    if args.disassembly_target:
        params["disassembly_target"] = args.disassembly_target
    return exe.execute("get_shader_info", params, session=args.session)


def cmd_shader_source(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute(
        "get_shader_source",
        {"event_id": args.event_id, "stage": args.stage},
        session=args.session,
    )


def cmd_edit_shader(args: argparse.Namespace, exe: Executor) -> dict:
    # Read source from file or stdin
    if args.source_file == "-":
        source_code = sys.stdin.read()
    else:
        with open(args.source_file, "r", encoding="utf-8") as f:
            source_code = f.read()
    params: dict[str, Any] = {
        "event_id": args.event_id,
        "stage": args.stage,
        "source_code": source_code,
    }
    if args.entry_point:
        params["entry_point"] = args.entry_point
    return exe.execute("edit_shader", params, session=args.session)


def cmd_revert_shader(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute(
        "revert_shader",
        {"event_id": args.event_id, "stage": args.stage},
        session=args.session,
    )





# -- Resource ----------------------------------------------------------

def cmd_buffer(args: argparse.Namespace, exe: Executor) -> dict:
    params: dict[str, Any] = {"resource_id": args.resource_id}
    if args.offset:
        params["offset"] = args.offset
    if args.length:
        params["length"] = args.length
    return exe.execute("get_buffer_contents", params, session=args.session)


def cmd_texture_info(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("get_texture_info", {"resource_id": args.resource_id}, session=args.session)


def cmd_texture_data(args: argparse.Namespace, exe: Executor) -> dict:
    params: dict[str, Any] = {
        "resource_id": args.resource_id,
        "mip": args.mip,
    }
    if args.output:
        params["output_path"] = args.output
    return exe.execute("get_texture_data", params, session=args.session)





def cmd_texture_thumb(args: argparse.Namespace, exe: Executor) -> dict:
    """Texture thumbnail - now delegates to save_texture_as_png with base64 output."""
    params: dict[str, Any] = {
        "resource_id": args.resource_id,
        "max_size": args.max_size,
    }
    if args.output:
        params["output_path"] = args.output
    return exe.execute("save_texture_as_png", params, session=args.session)


def cmd_texture_save(args: argparse.Namespace, exe: Executor) -> dict:
    params: dict[str, Any] = {
        "resource_id": args.resource_id,
        "output_path": args.output,
        "mip": args.mip,
        "max_size": 0,
    }
    if args.event_id is not None:
        params["event_id"] = args.event_id
    return exe.execute("save_texture_as_png", params, session=args.session)


def cmd_rt_thumb(args: argparse.Namespace, exe: Executor) -> dict:
    params: dict[str, Any] = {
        "event_id": args.event_id,
        "rtv_index": args.rtv_index,
        "max_size": args.max_size,
    }
    if args.depth:
        params["depth"] = True
    if args.output:
        params["output_path"] = args.output
    return exe.execute("get_render_target_thumbnail", params, session=args.session)


def cmd_rt_diff(args: argparse.Namespace, exe: Executor) -> dict:
    params: dict[str, Any] = {
        "event_id": args.event_id,
        "max_size": args.max_size,
    }
    if args.compare is not None:
        params["compare_event_id"] = args.compare
    if args.rtv_index != 0:
        params["rtv_index"] = args.rtv_index
    if args.depth:
        params["depth"] = True
    if args.threshold:
        params["threshold"] = args.threshold
    if args.output:
        params["output_path"] = args.output
    return exe.execute("get_render_target_diff", params, session=args.session)


# -- Debug / diagnostics ----------------------------------------------


def cmd_debug_pixel(args: argparse.Namespace, exe: Executor) -> dict:
    params: dict[str, Any] = {
        "event_id": args.event_id,
        "x": args.x,
        "y": args.y,
    }
    if args.sample is not None:
        params["sample"] = args.sample
    if args.primitive is not None:
        params["primitive"] = args.primitive
    return exe.execute("debug_pixel", params, session=args.session)


def cmd_debug_vertex(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute(
        "debug_vertex",
        {
            "event_id": args.event_id,
            "vtx_id": args.vtx_id,
            "instance": args.instance,
        },
        session=args.session,
    )


def cmd_debug_thread(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute(
        "debug_thread",
        {
            "event_id": args.event_id,
            "gx": args.gx,
            "gy": args.gy,
            "gz": args.gz,
            "tx": args.tx,
            "ty": args.ty,
            "tz": args.tz,
        },
        session=args.session,
    )


def cmd_pick_pixel(args: argparse.Namespace, exe: Executor) -> dict:
    params: dict[str, Any] = {
        "x": args.x,
        "y": args.y,
        "target": args.target,
    }
    if args.event_id is not None:
        params["event_id"] = args.event_id
    return exe.execute("pick_pixel", params, session=args.session)


def cmd_tex_stats(args: argparse.Namespace, exe: Executor) -> dict:
    params: dict[str, Any] = {
        "resource_id": args.resource_id,
        "mip": args.mip,
        "array_slice": args.slice,
        "histogram": bool(args.histogram),
    }
    if args.event_id is not None:
        params["event_id"] = args.event_id
    return exe.execute("tex_stats", params, session=args.session)


# -- VFS ---------------------------------------------------------------


def cmd_vfs_ls(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute(
        "vfs_ls",
        {
            "path": args.path,
            "long": bool(args.long),
        },
        session=args.session,
    )


def cmd_vfs_cat(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("vfs_cat", {"path": args.path}, session=args.session)


def cmd_vfs_tree(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute(
        "vfs_tree",
        {"path": args.path, "depth": args.depth},
        session=args.session,
    )


# -- Export ------------------------------------------------------------


def cmd_mesh(args: argparse.Namespace, exe: Executor) -> dict:
    params: dict[str, Any] = {"stage": args.stage}
    if args.event_id is not None:
        params["event_id"] = args.event_id
    return exe.execute("mesh_data", params, session=args.session)


def cmd_snapshot(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute(
        "snapshot_export",
        {"event_id": args.event_id, "output_dir": args.output_dir},
        session=args.session,
    )


# -- Capturefile-style -------------------------------------------------


def cmd_capture_sections(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("capture_sections", session=args.session)


def cmd_capture_section(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute(
        "capture_section_content",
        {"name": args.name},
        session=args.session,
    )


def cmd_capture_gpus(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("capture_gpus", session=args.session)


def cmd_capture_thumbnail(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute(
        "capture_thumbnail",
        {"max_size": args.max_size},
        session=args.session,
    )


def cmd_callstacks(args: argparse.Namespace, exe: Executor) -> dict:
    params: dict[str, Any] = {}
    if args.event_id is not None:
        params["event_id"] = args.event_id
    return exe.execute("callstack_resolve", params, session=args.session)



# -- Session -----------------------------------------------------------

def cmd_sessions(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("list_sessions")


def cmd_use(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("set_default_session", {"session_id": args.session_id})


def cmd_ping(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("ping_bridge", session=args.session)


def cmd_bridge_status(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("get_bridge_status", session=args.session)


# -- Local -------------------------------------------------------------

def cmd_presets(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("list_filter_presets")


def cmd_config(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("get_server_config")


def cmd_capabilities(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("get_capabilities")


def cmd_versions(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("list_renderdoc_versions")


def cmd_switch_version(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("switch_renderdoc_version", {"version": args.version})


def cmd_uninstall(args: argparse.Namespace, exe: Executor) -> dict:
    return exe.execute("uninstall_extension")


# ── Argument parser ──────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser with all subcommands."""
    p = argparse.ArgumentParser(
        prog="renderdoc-cli",
        description="renderdoc-cli — AI-friendly command-line interface for .rdc capture analysis",
    )
    p.add_argument("--session", "-s", default=None, help="Session ID (auto-selected when omitted)")
    p.add_argument("--format", "-f", default="json", choices=["json", "tsv"], help="Output format (default: json)")
    p.add_argument("--output", "-o", default=None, metavar="FILE", help="Write output to file instead of stdout")
    p.add_argument("--quiet", action="store_true", help="Suppress non-error stderr hints")


    sub = p.add_subparsers(dest="command", help="Available commands")

    # ── Capture ──────────────────────────────────────────────────
    sub.add_parser("status", help="Check if a capture is loaded")
    sub.add_parser("info", help="Detailed capture info (API, driver, GPU, stats)")

    ls = sub.add_parser("list-captures", help="List .rdc files in a directory")
    ls.add_argument("directory", help="Directory to search for .rdc files")

    op = sub.add_parser("open", help="Open a capture file")
    op.add_argument("path", help="Full path to .rdc file")

    # ── Draw calls ───────────────────────────────────────────────
    dr = sub.add_parser("draws", help="Get draw calls with optional filtering")
    dr.add_argument("--preset", "-p", help="Filter preset name (e.g. unity_game_rendering)")
    dr.add_argument("--only-actions", action="store_true", help="Only return actual rendering actions")
    dr.add_argument("--flags", nargs="*", help="Action flag filters (e.g. Drawcall Dispatch)")
    dr.add_argument("--marker", help="PushMarker 名称子串过滤（匹配 marker 名称，不匹配其子节点 action 名称）")

    dr.add_argument("--exclude-markers", nargs="*", help="Marker names to exclude")
    dr.add_argument("--event-id-min", type=int, default=None, help="Minimum event ID")
    dr.add_argument("--event-id-max", type=int, default=None, help="Maximum event ID")

    sub.add_parser("summary", help="Frame summary (draw counts, resource counts)")

    dd = sub.add_parser("draw-detail", help="Details for a single draw call")
    dd.add_argument("event_id", type=int, help="Event ID to inspect")

    tm = sub.add_parser("timings", help="GPU timing info for actions")
    tm.add_argument("--event-ids", type=int, nargs="*", help="Specific event IDs")
    tm.add_argument("--preset", "-p", help="Filter preset name")
    tm.add_argument("--marker", help="PushMarker 名称子串过滤（匹配 marker 名称，不匹配其子节点 action 名称）")

    tm.add_argument("--exclude-markers", nargs="*", help="Marker names to exclude")

    # ── Pipeline ─────────────────────────────────────────────────
    ps = sub.add_parser("pipeline", help="Full pipeline state at an event")
    ps.add_argument("event_id", type=int)

    pss = sub.add_parser("pipelines", help="Pipeline states for multiple events")
    pss.add_argument("event_ids", type=int, nargs="+")

    df = sub.add_parser("diff", help="Pipeline state diff between two events")
    df.add_argument("base", type=int, help="Base event ID")
    df.add_argument("target", type=int, help="Target event ID")

    # ── Shader ───────────────────────────────────────────────────
    si = sub.add_parser("shader-info", help="Shader metadata at event/stage")
    si.add_argument("event_id", type=int)
    si.add_argument("stage", help="Shader stage (vertex/pixel/compute/...)")
    si.add_argument("--include-disassembly", action="store_true")
    si.add_argument("--include-cbuffers", action="store_true", help="Include constant buffer values")
    si.add_argument("--include-resources", action="store_true", help="Include resource bindings")
    si.add_argument("--disassembly-target", help="Disassembly format (e.g. GLSL)")

    ss = sub.add_parser("shader-source", help="Get editable shader source code")
    ss.add_argument("event_id", type=int)
    ss.add_argument("stage", help="Shader stage")

    es = sub.add_parser("edit-shader", help="Replace shader source code")
    es.add_argument("event_id", type=int)
    es.add_argument("stage", help="Shader stage")
    es.add_argument("source_file", help="Path to source file (use '-' for stdin)")
    es.add_argument("--entry-point", help="Optional entry point override")

    rv = sub.add_parser("revert-shader", help="Revert edited shader to original")
    rv.add_argument("event_id", type=int)
    rv.add_argument("stage", help="Shader stage")



    # ── Resource ─────────────────────────────────────────────────
    bf = sub.add_parser("buffer", help="Read buffer contents")
    bf.add_argument("resource_id")
    bf.add_argument("--offset", type=int, default=0)
    bf.add_argument("--length", type=int, default=0)

    ti = sub.add_parser("texture-info", help="Texture metadata")
    ti.add_argument("resource_id")

    td = sub.add_parser("texture-data", help="Read texture pixel data")
    td.add_argument("resource_id")
    td.add_argument("--mip", type=int, default=0)
    td.add_argument("-o", "--output", default=None, metavar="FILE", dest="output", help="Save raw data to file")



    tt = sub.add_parser("texture-thumb", help="Get texture thumbnail PNG")
    tt.add_argument("resource_id")
    tt.add_argument("--max-size", type=int, default=256)
    tt.add_argument("-o", "--output", default=None, metavar="FILE", dest="output", help="Save PNG to file")

    ts = sub.add_parser("texture-save", help="Save texture as full-resolution PNG")
    ts.add_argument("resource_id")
    ts.add_argument("-o", "--output", required=True, dest="output", metavar="FILE", help="Output PNG path")
    ts.add_argument("--event-id", type=int, default=None, help="Replay to event before reading")
    ts.add_argument("--mip", type=int, default=0)

    rt = sub.add_parser("rt-thumb", help="Render target thumbnail at an event")
    rt.add_argument("event_id", type=int)
    rt.add_argument("--rtv-index", type=int, default=0, help="RTV index (default 0)")
    rt.add_argument("--depth", action="store_true", help="Read depth buffer instead")
    rt.add_argument("--max-size", type=int, default=256)
    rt.add_argument("-o", "--output", default=None, metavar="FILE", dest="output", help="Save PNG to file")

    rd = sub.add_parser("rt-diff", help="Pixel-level render target diff between events")
    rd.add_argument("event_id", type=int)
    rd.add_argument("--compare", type=int, default=None, help="Baseline event ID (auto if omitted)")
    rd.add_argument("--rtv-index", type=int, default=0)
    rd.add_argument("--depth", action="store_true")
    rd.add_argument("--threshold", type=int, default=0, help="Per-byte diff threshold (0-255)")
    rd.add_argument("--max-size", type=int, default=512)
    rd.add_argument("-o", "--output", default=None, metavar="FILE", dest="output", help="Save diff PNG to file")

    # ── Debug / diagnostics ──────────────────────────────────────
    dp = sub.add_parser("debug-pixel", help="Debug pixel shader at coordinate")
    dp.add_argument("event_id", type=int)
    dp.add_argument("x", type=int)
    dp.add_argument("y", type=int)
    dp.add_argument("--sample", type=int, default=None)
    dp.add_argument("--primitive", type=int, default=None)

    dv = sub.add_parser("debug-vertex", help="Debug vertex shader for one vertex")
    dv.add_argument("event_id", type=int)
    dv.add_argument("vtx_id", type=int)
    dv.add_argument("--instance", type=int, default=0)

    dt = sub.add_parser("debug-thread", help="Debug compute shader for one thread")
    dt.add_argument("event_id", type=int)
    dt.add_argument("gx", type=int)
    dt.add_argument("gy", type=int)
    dt.add_argument("gz", type=int)
    dt.add_argument("tx", type=int)
    dt.add_argument("ty", type=int)
    dt.add_argument("tz", type=int)

    pp = sub.add_parser("pick-pixel", help="Read one pixel value from render target")
    pp.add_argument("x", type=int)
    pp.add_argument("y", type=int)
    pp.add_argument("--event-id", type=int, default=None)
    pp.add_argument("--target", type=int, default=0)

    txs = sub.add_parser("tex-stats", help="Texture min/max and optional histogram")
    txs.add_argument("resource_id")
    txs.add_argument("--event-id", type=int, default=None)
    txs.add_argument("--mip", type=int, default=0)
    txs.add_argument("--slice", type=int, default=0)
    txs.add_argument("--histogram", action="store_true")

    # ── VFS ───────────────────────────────────────────────────────
    vls = sub.add_parser("vfs-ls", help="List semantic VFS nodes")
    vls.add_argument("path", nargs="?", default="/")
    vls.add_argument("-l", "--long", action="store_true")

    vcat = sub.add_parser("vfs-cat", help="Read semantic VFS leaf node")
    vcat.add_argument("path")

    vtree = sub.add_parser("vfs-tree", help="Display semantic VFS subtree")
    vtree.add_argument("path", nargs="?", default="/")
    vtree.add_argument("--depth", type=int, default=2)

    # ── Export ────────────────────────────────────────────────────
    mesh = sub.add_parser("mesh", help="Export post-transform mesh data")
    mesh.add_argument("event_id", type=int, nargs="?", default=None)
    mesh.add_argument("--stage", default="vs-out", choices=["vs-out", "gs-out"])

    snap = sub.add_parser("snapshot", help="Export event snapshot bundle")
    snap.add_argument("event_id", type=int)
    snap.add_argument("--output-dir", required=True)

    # ── Capturefile-style ─────────────────────────────────────────
    sub.add_parser("capture-sections", help="List capture structured sections")

    csec = sub.add_parser("capture-section", help="Read one capture section content")
    csec.add_argument("name")

    sub.add_parser("capture-gpus", help="List GPUs recorded in capture metadata")

    cthumb = sub.add_parser("capture-thumbnail", help="Get capture thumbnail as base64 PNG")
    cthumb.add_argument("--max-size", type=int, default=0)

    cstack = sub.add_parser("callstacks", help="Resolve CPU callstack for an event")
    cstack.add_argument("--event-id", type=int, default=None)



    # ── Session ──────────────────────────────────────────────────
    sub.add_parser("sessions", help="List active RenderDoc sessions")

    us = sub.add_parser("use", help="Set default session")
    us.add_argument("session_id", help="Session ID from 'sessions' command")

    sub.add_parser("ping", help="Ping bridge (measure latency)")
    sub.add_parser("bridge-status", help="Bridge diagnostics")

    # ── Local ────────────────────────────────────────────────────
    sub.add_parser("presets", help="List available filter presets")
    sub.add_parser("config", help="Show server/IPC configuration")
    sub.add_parser("capabilities", help="Show server capabilities and tool list")
    sub.add_parser("versions", help="List installed RenderDoc versions")

    sv = sub.add_parser("switch-version", help="Switch active RenderDoc version")
    sv.add_argument("version", help="Version string or installation path")

    sub.add_parser("uninstall", help="Uninstall renderdoc_toolset_bridge extension")

    return p


# ── Dispatch table ───────────────────────────────────────────────────

_DISPATCH: dict[str, callable] = {
    # Capture
    "status": cmd_status,
    "info": cmd_info,
    "list-captures": cmd_list_captures,
    "open": cmd_open,
    # Draw calls
    "draws": cmd_draws,
    "summary": cmd_summary,
    "draw-detail": cmd_draw_detail,
    "timings": cmd_timings,
    # Pipeline
    "pipeline": cmd_pipeline,
    "pipelines": cmd_pipelines,
    "diff": cmd_diff,
    # Shader
    "shader-info": cmd_shader_info,
    "shader-source": cmd_shader_source,
    "edit-shader": cmd_edit_shader,
    "revert-shader": cmd_revert_shader,

    # Resource
    "buffer": cmd_buffer,
    "texture-info": cmd_texture_info,
    "texture-data": cmd_texture_data,

    "texture-thumb": cmd_texture_thumb,
    "texture-save": cmd_texture_save,
    "rt-thumb": cmd_rt_thumb,
    "rt-diff": cmd_rt_diff,

    # Debug / diagnostics
    "debug-pixel": cmd_debug_pixel,
    "debug-vertex": cmd_debug_vertex,
    "debug-thread": cmd_debug_thread,
    "pick-pixel": cmd_pick_pixel,
    "tex-stats": cmd_tex_stats,

    # VFS
    "vfs-ls": cmd_vfs_ls,
    "vfs-cat": cmd_vfs_cat,
    "vfs-tree": cmd_vfs_tree,

    # Export
    "mesh": cmd_mesh,
    "snapshot": cmd_snapshot,

    # Capturefile-style
    "capture-sections": cmd_capture_sections,
    "capture-section": cmd_capture_section,
    "capture-gpus": cmd_capture_gpus,
    "capture-thumbnail": cmd_capture_thumbnail,
    "callstacks": cmd_callstacks,

    # Session
    "sessions": cmd_sessions,
    "use": cmd_use,
    "ping": cmd_ping,
    "bridge-status": cmd_bridge_status,
    # Local
    "presets": cmd_presets,
    "config": cmd_config,
    "capabilities": cmd_capabilities,
    "versions": cmd_versions,
    "switch-version": cmd_switch_version,
    "uninstall": cmd_uninstall,
}


# ── Entry point ──────────────────────────────────────────────────────

def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    handler = _DISPATCH.get(args.command)
    if handler is None:
        emit_error("Unknown command: %s" % args.command, command=args.command)
        sys.exit(1)

    exe = _build_executor()

    try:
        result = handler(args, exe)
        # Use top-level --output if subcommand didn't override
        output_file = getattr(args, "output", None) or None
        emit(result, fmt=args.format, file=output_file, quiet=bool(args.quiet))

    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        emit_error(str(exc), command=args.command)
        sys.exit(1)


if __name__ == "__main__":
    main()
