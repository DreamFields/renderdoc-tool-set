"""All RDC operations defined in one place.

This is the SINGLE SOURCE OF TRUTH — both MCP tools and CLI commands
are auto-generated from these definitions.  Adding a new operation only
requires adding an entry here (+ the Service implementation).
"""

from .registry import register, OperationParam

# ── Capture ──────────────────────────────────────────────────────────

register(
    "get_capture_status",
    description="Check if a capture is currently loaded in RenderDoc.",
    category="capture",
)

register(
    "get_frame_summary",
    description=(
        "Get a unified capture info and frame summary including API, filename, "
        "driver, action statistics (draw/dispatch/clear/copy/present/markers), "
        "top-level markers and resource counts."
    ),
    category="capture",
)

register(
    "list_captures",
    description="List all RenderDoc capture files (.rdc) in a directory.",
    params=[OperationParam("directory", str, help="Directory to search for .rdc files")],
    category="capture",
)

register(
    "open_capture",
    description="Open a RenderDoc capture file.",
    params=[OperationParam("capture_path", str, help="Full path to the .rdc file")],
    category="capture",
)

# ── Draw Calls ───────────────────────────────────────────────────────

register(
    "get_draw_calls",
    description="Get draw calls and actions with optional filtering and presets.",
    params=[
        OperationParam("include_children", bool, required=False, default=True),
        OperationParam(
            "marker_filter",
            str,
            required=False,
            help="Filter by PushMarker name substring (matches marker names, not child action names)",
        ),
        OperationParam("exclude_markers", list, required=False),

        OperationParam("event_id_min", int, required=False),
        OperationParam("event_id_max", int, required=False),
        OperationParam("only_actions", bool, required=False, default=False),
        OperationParam("flags_filter", list, required=False),
        OperationParam("preset", str, required=False, help="Filter preset name"),
    ],
    category="draw",
)

register(
    "get_draw_call_details",
    description="Get details for a single draw call or action.",
    params=[OperationParam("event_id", int, help="Event ID to inspect")],
    category="draw",
)

register(
    "get_action_timings",
    description="Get GPU timing information for actions with optional presets.",
    params=[
        OperationParam("event_ids", list, required=False, help="List of event IDs"),
        OperationParam(
            "marker_filter",
            str,
            required=False,
            help="Filter by PushMarker name substring (matches marker names, not child action names)",
        ),
        OperationParam("exclude_markers", list, required=False),

        OperationParam("preset", str, required=False, help="Filter preset name"),
    ],
    category="draw",
)

# ── Pipeline ─────────────────────────────────────────────────────────

register(
    "get_pipeline_state",
    description="Get the full graphics pipeline state at a specific event.",
    params=[OperationParam("event_id", int)],
    category="pipeline",
)

register(
    "get_multiple_pipeline_states",
    description="Get pipeline states for multiple events in one request.",
    params=[OperationParam("event_ids", list, help="List of event IDs")],
    category="pipeline",
)

register(
    "compare_pipeline_states",
    description="Compare pipeline states between two events and return a diff summary.",
    params=[
        OperationParam("base_event_id", int),
        OperationParam("target_event_id", int),
    ],
    category="pipeline",
)

# ── Shader ───────────────────────────────────────────────────────────

register(
    "get_shader_info",
    description=(
        "Get shader information for a specific stage at an event. "
        "Set include_* flags to True to fetch heavier data."
    ),
    params=[
        OperationParam("event_id", int),
        OperationParam("stage", str, help="vertex/hull/domain/geometry/pixel/compute"),
        OperationParam("include_disassembly", bool, required=False, default=False),
        OperationParam("include_constant_buffers", bool, required=False, default=False),
        OperationParam("include_resources", bool, required=False, default=False),
        OperationParam("disassembly_target", str, required=False),
    ],
    category="shader",
)

register(
    "get_shader_source",
    description="Get the editable source code for a shader.",
    params=[
        OperationParam("event_id", int),
        OperationParam("stage", str),
    ],
    category="shader",
)

register(
    "edit_shader",
    description="Compile new shader source code and replace the original.",
    params=[
        OperationParam("event_id", int),
        OperationParam("stage", str),
        OperationParam("source_code", str),
        OperationParam("entry_point", str, required=False),
    ],
    category="shader",
)

register(
    "revert_shader",
    description="Revert a previously edited shader back to original.",
    params=[
        OperationParam("event_id", int),
        OperationParam("stage", str),
    ],
    category="shader",
)



# ── Resource ─────────────────────────────────────────────────────────

register(
    "get_buffer_contents",
    description="Read the contents of a buffer resource.",
    params=[
        OperationParam("resource_id", str),
        OperationParam("offset", int, required=False, default=0),
        OperationParam("length", int, required=False, default=0),
    ],
    category="resource",
)

register(
    "get_texture_info",
    description="Get metadata about a texture resource.",
    params=[OperationParam("resource_id", str)],
    category="resource",
)

register(
    "get_texture_data",
    description="Read the pixel data of a texture resource.",
    params=[
        OperationParam("resource_id", str),
        OperationParam("mip", int, required=False, default=0),
        OperationParam("slice", int, required=False, default=0),
        OperationParam("sample", int, required=False, default=0),
        OperationParam("depth_slice", int, required=False),
        OperationParam("output_path", str, required=False),
    ],
    category="resource",
)

register(
    "save_texture_as_png",
    description=(
        "Save a texture as a PNG file or return base64 thumbnail. "
        "Unifies get_texture_thumbnail + save_texture_as_png. "
        "If output_path is omitted, returns base64-encoded thumbnail."
    ),
    params=[
        OperationParam("resource_id", str),
        OperationParam("output_path", str, required=False,
                       help="File path to save to (returns base64 if omitted)"),
        OperationParam("event_id", int, required=False),
        OperationParam("mip", int, required=False, default=0),
        OperationParam("max_size", int, required=False, default=0,
                       help="Max width/height (0 = original resolution)"),
    ],
    category="resource",
)

register(
    "get_render_target_thumbnail",
    description="Get a PNG thumbnail of a render target at a specific event.",
    params=[
        OperationParam("event_id", int),
        OperationParam("rtv_index", int, required=False, default=0),
        OperationParam("depth", bool, required=False, default=False),
        OperationParam("max_size", int, required=False, default=256),
        OperationParam("output_path", str, required=False),
    ],
    category="resource",
)

register(
    "get_render_target_diff",
    description="Get pixel-level render target diff between two events.",
    params=[
        OperationParam("event_id", int),
        OperationParam("compare_event_id", int, required=False),
        OperationParam("rtv_index", int, required=False, default=0),
        OperationParam("depth", bool, required=False, default=False),
        OperationParam("threshold", int, required=False, default=0),
        OperationParam("max_size", int, required=False, default=512),
        OperationParam("output_path", str, required=False),
    ],
    category="resource",
)

# ── Diagnostics / Debug ──────────────────────────────────────────────

register(
    "debug_pixel",
    description="Debug pixel shader execution trace at a specific screen coordinate.",
    params=[
        OperationParam("event_id", int),
        OperationParam("x", int),
        OperationParam("y", int),
        OperationParam("sample", int, required=False),
        OperationParam("primitive", int, required=False),
    ],
    category="debug",
)

register(
    "debug_vertex",
    description="Debug vertex shader execution trace for one vertex.",
    params=[
        OperationParam("event_id", int),
        OperationParam("vtx_id", int),
        OperationParam("instance", int, required=False, default=0),
    ],
    category="debug",
)

register(
    "debug_thread",
    description="Debug compute shader execution trace for one thread.",
    params=[
        OperationParam("event_id", int),
        OperationParam("gx", int),
        OperationParam("gy", int),
        OperationParam("gz", int),
        OperationParam("tx", int),
        OperationParam("ty", int),
        OperationParam("tz", int),
    ],
    category="debug",
)

register(
    "pick_pixel",
    description="Read a single pixel value from the active render target.",
    params=[
        OperationParam("x", int),
        OperationParam("y", int),
        OperationParam("event_id", int, required=False),
        OperationParam("target", int, required=False, default=0),
    ],
    category="debug",
)

register(
    "tex_stats",
    description="Compute min/max statistics (and optional histogram) for a texture.",
    params=[
        OperationParam("resource_id", str),
        OperationParam("mip", int, required=False, default=0),
        OperationParam("array_slice", int, required=False, default=0),
        OperationParam("histogram", bool, required=False, default=False),
        OperationParam("event_id", int, required=False),
    ],
    category="debug",
)

# ── VFS semantic browsing ────────────────────────────────────────────

register(
    "vfs_ls",
    description="List VFS nodes under a semantic GPU-state path.",
    params=[
        OperationParam("path", str, required=False, default="/"),
        OperationParam("long", bool, required=False, default=False),
    ],
    category="vfs",
)

register(
    "vfs_cat",
    description="Read a VFS leaf node content.",
    params=[OperationParam("path", str)],
    category="vfs",
)

register(
    "vfs_tree",
    description="Read a VFS subtree for semantic navigation.",
    params=[
        OperationParam("path", str, required=False, default="/"),
        OperationParam("depth", int, required=False, default=2),
    ],
    category="vfs",
)

# ── Export / Capturefile-inspired utilities ─────────────────────────

register(
    "mesh_data",
    description="Export post-transform mesh data for an event.",
    params=[
        OperationParam("event_id", int, required=False),
        OperationParam("stage", str, required=False, default="vs-out"),
    ],
    category="export",
)

register(
    "snapshot_export",
    description="Export a compact per-event snapshot bundle to a directory.",
    params=[
        OperationParam("event_id", int),
        OperationParam("output_dir", str),
    ],
    category="export",
)

register(
    "capture_sections",
    description="List embedded structured sections of the loaded capture.",
    category="capture",
)

register(
    "capture_section_content",
    description="Read one capture section metadata/content by section name.",
    params=[OperationParam("name", str)],
    category="capture",
)

register(
    "capture_gpus",
    description="List GPU information recorded with the capture.",
    category="capture",
)

register(
    "capture_thumbnail",
    description="Get capture thumbnail image as base64 PNG.",
    params=[OperationParam("max_size", int, required=False, default=0)],
    category="capture",
)

register(
    "callstack_resolve",
    description="Resolve CPU callstack for an event (if available).",
    params=[OperationParam("event_id", int, required=False)],
    category="capture",
)


# ── Session (local, no IPC) ─────────────────────────────────────────

register(
    "list_sessions",
    description="Discover all active RenderDoc sessions.",
    category="session",
    needs_session=False,
)

register(
    "set_default_session",
    description="Pin a default session for subsequent calls.",
    params=[OperationParam("session_id", str)],
    category="session",
    needs_session=False,
)

register(
    "ping_bridge",
    description="Measure round-trip latency to the RenderDoc bridge.",
    category="session",
)

register(
    "get_bridge_status",
    description="Read bridge diagnostics from the shared IPC status file.",
    category="session",
)

# ── Local-only tools (no IPC, handled entirely by server/CLI) ───────

register(
    "list_filter_presets",
    description="List all built-in filter presets for draw call and timing analysis.",
    category="local",
    needs_session=False,
)

register(
    "get_server_config",
    description="Return the current MCP server and IPC configuration.",
    category="local",
    needs_session=False,
)

register(
    "get_capabilities",
    description="Get server capabilities including available tools, version and configuration.",
    category="local",
    needs_session=False,
)

register(
    "list_renderdoc_versions",
    description="List installed RenderDoc versions.",
    category="local",
    needs_session=False,
)

register(
    "switch_renderdoc_version",
    description="Switch the active RenderDoc version. Requires server restart.",
    params=[OperationParam("version", str, help="Version string or installation path")],
    category="local",
    needs_session=False,
)

register(
    "uninstall_extension",
    description="Uninstall renderdoc_toolset_bridge extension from RenderDoc extension directories.",
    category="local",
    needs_session=False,
)
