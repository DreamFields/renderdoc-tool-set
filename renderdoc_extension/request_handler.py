"""
Request Handler for RenderDoc renderdoc_toolset_bridge.
Routes incoming requests to appropriate facade methods.
"""



import traceback


class RequestHandler:
    """Handle incoming bridge requests."""

    def __init__(self, facade):
        self.facade = facade
        self._methods = {
            "ping": self._handle_ping,
            "get_capture_status": self._handle_get_capture_status,
            "get_draw_calls": self._handle_get_draw_calls,
            "get_frame_summary": self._handle_get_frame_summary,

            "get_draw_call_details": self._handle_get_draw_call_details,
            "get_action_timings": self._handle_get_action_timings,
            "get_shader_info": self._handle_get_shader_info,
            "get_buffer_contents": self._handle_get_buffer_contents,
            "get_texture_info": self._handle_get_texture_info,
            "get_texture_data": self._handle_get_texture_data,
            "get_pipeline_state": self._handle_get_pipeline_state,
            "get_multiple_pipeline_states": self._handle_get_multiple_pipeline_states,
            "compare_pipeline_states": self._handle_compare_pipeline_states,
            "list_captures": self._handle_list_captures,
            "open_capture": self._handle_open_capture,
            "get_shader_source": self._handle_get_shader_source,
            "edit_shader": self._handle_edit_shader,
            "revert_shader": self._handle_revert_shader,
            "get_frame_summary": self._handle_get_frame_summary,
            "save_texture_as_png": self._handle_save_texture_as_png,
            "get_render_target_thumbnail": self._handle_get_render_target_thumbnail,
            "get_render_target_diff": self._handle_get_render_target_diff,

            "debug_pixel": self._handle_debug_pixel,
            "debug_vertex": self._handle_debug_vertex,
            "debug_thread": self._handle_debug_thread,
            "pick_pixel": self._handle_pick_pixel,
            "tex_stats": self._handle_tex_stats,
            "vfs_ls": self._handle_vfs_ls,
            "vfs_cat": self._handle_vfs_cat,
            "vfs_tree": self._handle_vfs_tree,
            "mesh_data": self._handle_mesh_data,
            "snapshot_export": self._handle_snapshot_export,
            "capture_sections": self._handle_capture_sections,
            "capture_section_content": self._handle_capture_section_content,
            "capture_gpus": self._handle_capture_gpus,
            "capture_thumbnail": self._handle_capture_thumbnail,
            "callstack_resolve": self._handle_callstack_resolve,
        }

    def handle(self, request):
        """Handle a request and return a response payload."""
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        try:
            if method not in self._methods:
                return self._error_response(
                    request_id, -32601, "Method not found: %s" % method
                )

            result = self._methods[method](params)
            return {"id": request_id, "result": result}

        except ValueError as exc:
            return self._error_response(request_id, -32602, str(exc))
        except Exception as exc:
            traceback.print_exc()
            return self._error_response(request_id, -32000, str(exc))

    def _error_response(self, request_id, code, message):
        """Create a structured error response."""
        return {"id": request_id, "error": {"code": code, "message": message}}

    def _handle_ping(self, params):
        """Handle ping requests."""
        return {"status": "ok", "message": "pong"}

    def _handle_get_capture_status(self, params):
        return self.facade.get_capture_status()

    def _handle_get_draw_calls(self, params):
        return self.facade.get_draw_calls(
            include_children=params.get("include_children", True),
            marker_filter=params.get("marker_filter"),
            exclude_markers=params.get("exclude_markers"),
            event_id_min=params.get("event_id_min"),
            event_id_max=params.get("event_id_max"),
            only_actions=params.get("only_actions", False),
            flags_filter=params.get("flags_filter"),
        )

    def _handle_get_frame_summary(self, params):
        return self.facade.get_frame_summary()



    def _handle_get_draw_call_details(self, params):
        event_id = params.get("event_id")
        if event_id is None:
            raise ValueError("event_id is required")
        return self.facade.get_draw_call_details(int(event_id))

    def _handle_get_action_timings(self, params):
        return self.facade.get_action_timings(
            event_ids=params.get("event_ids"),
            marker_filter=params.get("marker_filter"),
            exclude_markers=params.get("exclude_markers"),
        )

    def _handle_get_shader_info(self, params):
        event_id = params.get("event_id")
        stage = params.get("stage")
        if event_id is None:
            raise ValueError("event_id is required")
        if stage is None:
            raise ValueError("stage is required")
        return self.facade.get_shader_info(
            int(event_id),
            stage,
            include_disassembly=bool(params.get("include_disassembly", False)),
            include_constant_buffers=bool(params.get("include_constant_buffers", False)),
            include_resources=bool(params.get("include_resources", False)),
            disassembly_target=params.get("disassembly_target"),
        )

    def _handle_get_buffer_contents(self, params):
        resource_id = params.get("resource_id")
        if resource_id is None:
            raise ValueError("resource_id is required")

        try:
            offset = int(params.get("offset", 0))
        except (TypeError, ValueError):
            raise ValueError("offset must be an integer >= 0")

        try:
            length = int(params.get("length", 0))
        except (TypeError, ValueError):
            raise ValueError("length must be an integer >= 0")

        if offset < 0:
            raise ValueError("offset must be >= 0")
        if length < 0:
            raise ValueError("length must be >= 0")

        return self.facade.get_buffer_contents(resource_id, offset, length)


    def _handle_get_texture_info(self, params):
        resource_id = params.get("resource_id")
        if resource_id is None:
            raise ValueError("resource_id is required")
        return self.facade.get_texture_info(resource_id)

    def _handle_get_texture_data(self, params):
        resource_id = params.get("resource_id")
        if resource_id is None:
            raise ValueError("resource_id is required")
        return self.facade.get_texture_data(
            resource_id,
            params.get("mip", 0),
            params.get("slice", 0),
            params.get("sample", 0),
            params.get("depth_slice"),
            params.get("output_path"),
        )

    def _handle_save_texture_as_png(self, params):
        resource_id = params.get("resource_id")
        if resource_id is None:
            raise ValueError("resource_id is required")
        output_path = params.get("output_path")
        event_id = params.get("event_id")
        mip = params.get("mip", 0)
        max_size = params.get("max_size", 0)
        return self.facade.save_texture_as_png(resource_id, output_path, event_id, int(mip), int(max_size))

    def _handle_get_pipeline_state(self, params):
        event_id = params.get("event_id")
        if event_id is None:
            raise ValueError("event_id is required")
        return self.facade.get_pipeline_state(int(event_id))

    def _handle_get_multiple_pipeline_states(self, params):
        event_ids = params.get("event_ids")
        if not event_ids:
            raise ValueError("event_ids is required")
        return self.facade.get_multiple_pipeline_states([int(event_id) for event_id in event_ids])

    def _handle_compare_pipeline_states(self, params):
        base_event_id = params.get("base_event_id")
        target_event_id = params.get("target_event_id")
        if base_event_id is None:
            raise ValueError("base_event_id is required")
        if target_event_id is None:
            raise ValueError("target_event_id is required")
        return self.facade.compare_pipeline_states(
            int(base_event_id), int(target_event_id)
        )

    def _handle_list_captures(self, params):
        directory = params.get("directory")
        if directory is None:
            raise ValueError("directory is required")
        return self.facade.list_captures(directory)

    def _handle_open_capture(self, params):
        capture_path = params.get("capture_path")
        if capture_path is None:
            raise ValueError("capture_path is required")
        return self.facade.open_capture(capture_path)

    def _handle_get_shader_source(self, params):
        event_id = params.get("event_id")
        stage = params.get("stage")
        if event_id is None:
            raise ValueError("event_id is required")
        if stage is None:
            raise ValueError("stage is required")
        return self.facade.get_shader_source(int(event_id), stage)

    def _handle_edit_shader(self, params):
        event_id = params.get("event_id")
        stage = params.get("stage")
        source_code = params.get("source_code")
        if event_id is None:
            raise ValueError("event_id is required")
        if stage is None:
            raise ValueError("stage is required")
        if source_code is None:
            raise ValueError("source_code is required")
        return self.facade.edit_shader(
            int(event_id),
            stage,
            source_code,
            params.get("entry_point"),
        )

    def _handle_revert_shader(self, params):
        event_id = params.get("event_id")
        stage = params.get("stage")
        if event_id is None:
            raise ValueError("event_id is required")
        if stage is None:
            raise ValueError("stage is required")
        return self.facade.revert_shader(int(event_id), stage)

    def _handle_get_render_target_thumbnail(self, params):
        event_id = params.get("event_id")
        if event_id is None:
            raise ValueError("event_id is required")
        rtv_index = params.get("rtv_index", 0)
        depth = params.get("depth", False)
        max_size = params.get("max_size", 256)
        output_path = params.get("output_path")
        return self.facade.get_render_target_thumbnail(
            int(event_id), int(rtv_index), bool(depth), int(max_size), output_path
        )

    def _handle_get_render_target_diff(self, params):
        event_id = params.get("event_id")
        if event_id is None:
            raise ValueError("event_id is required")
        compare_event_id = params.get("compare_event_id")
        if compare_event_id is not None:
            compare_event_id = int(compare_event_id)
        rtv_index = params.get("rtv_index", 0)
        depth = params.get("depth", False)
        threshold = params.get("threshold", 0)
        max_size = params.get("max_size", 512)
        output_path = params.get("output_path")
        try:
            return self.facade.get_render_target_diff(
                int(event_id), compare_event_id, int(rtv_index),
                bool(depth), int(threshold), int(max_size), output_path
            )
        except Exception as exc:
            actual_compare = compare_event_id if compare_event_id is not None else int(event_id) - 1
            raise type(exc)(
                "[get_render_target_diff] event_id=%s, compare_event_id=%s, "
                "rtv_index=%s, depth=%s, threshold=%s: %s"
                % (event_id, actual_compare, rtv_index, depth, threshold, str(exc))
            )

    def _handle_debug_pixel(self, params):
        event_id = params.get("event_id")
        if event_id is None:
            event_id = params.get("eid")
        if event_id is None:
            raise ValueError("event_id is required")
        x = params.get("x")
        y = params.get("y")
        if x is None or y is None:
            raise ValueError("x and y are required")
        return self.facade.debug_pixel(
            int(event_id), int(x), int(y),
            params.get("sample"), params.get("primitive")
        )

    def _handle_debug_vertex(self, params):
        event_id = params.get("event_id")
        if event_id is None:
            event_id = params.get("eid")
        if event_id is None:
            raise ValueError("event_id is required")
        vtx_id = params.get("vtx_id")
        if vtx_id is None:
            raise ValueError("vtx_id is required")
        instance = params.get("instance", 0)
        return self.facade.debug_vertex(int(event_id), int(vtx_id), int(instance))

    def _handle_debug_thread(self, params):
        event_id = params.get("event_id")
        if event_id is None:
            event_id = params.get("eid")
        if event_id is None:
            raise ValueError("event_id is required")
        for key in ("gx", "gy", "gz", "tx", "ty", "tz"):
            if params.get(key) is None:
                raise ValueError("%s is required" % key)
        return self.facade.debug_thread(
            int(event_id),
            int(params.get("gx")), int(params.get("gy")), int(params.get("gz")),
            int(params.get("tx")), int(params.get("ty")), int(params.get("tz")),
        )

    def _handle_pick_pixel(self, params):
        x = params.get("x")
        y = params.get("y")
        if x is None or y is None:
            raise ValueError("x and y are required")
        event_id = params.get("event_id")
        if event_id is None:
            event_id = params.get("eid")
        target = params.get("target", 0)
        return self.facade.pick_pixel(
            int(x), int(y),
            int(event_id) if event_id is not None else None,
            int(target),
        )

    def _handle_tex_stats(self, params):
        resource_id = params.get("resource_id")
        if resource_id is None:
            rid = params.get("id")
            if rid is not None:
                resource_id = "ResourceId::%s" % str(rid)
        if resource_id is None:
            raise ValueError("resource_id is required")
        mip = params.get("mip", 0)
        array_slice = params.get("slice", params.get("array_slice", 0))
        histogram = bool(params.get("histogram", False))
        event_id = params.get("event_id")
        if event_id is None:
            event_id = params.get("eid")
        return self.facade.tex_stats(
            str(resource_id), int(mip), int(array_slice), histogram,
            int(event_id) if event_id is not None else None,
        )

    def _handle_vfs_ls(self, params):
        path = params.get("path", "/")
        return self.facade.vfs_ls(path, bool(params.get("long", False)))

    def _handle_vfs_cat(self, params):
        path = params.get("path")
        if path is None:
            raise ValueError("path is required")
        return self.facade.vfs_cat(path)

    def _handle_vfs_tree(self, params):
        path = params.get("path", "/")
        depth = params.get("depth", 2)
        return self.facade.vfs_tree(path, int(depth))

    def _handle_mesh_data(self, params):
        event_id = params.get("event_id")
        if event_id is None:
            event_id = params.get("eid")
        stage = params.get("stage", "vs-out")
        return self.facade.mesh_data(
            int(event_id) if event_id is not None else None,
            stage,
        )

    def _handle_snapshot_export(self, params):
        event_id = params.get("event_id")
        if event_id is None:
            event_id = params.get("eid")
        if event_id is None:
            raise ValueError("event_id is required")
        output_dir = params.get("output_dir")
        if output_dir is None:
            raise ValueError("output_dir is required")
        return self.facade.snapshot_export(int(event_id), output_dir)

    def _handle_capture_sections(self, params):
        return self.facade.capture_sections()

    def _handle_capture_section_content(self, params):
        name = params.get("name")
        if name is None:
            raise ValueError("name is required")
        return self.facade.capture_section_content(name)

    def _handle_capture_gpus(self, params):
        return self.facade.capture_gpus()

    def _handle_capture_thumbnail(self, params):
        max_size = params.get("max_size", params.get("maxsize", 0))
        return self.facade.capture_thumbnail(int(max_size))

    def _handle_callstack_resolve(self, params):
        event_id = params.get("event_id")
        if event_id is None:
            event_id = params.get("eid")
        return self.facade.callstack_resolve(
            int(event_id) if event_id is not None else None
        )
