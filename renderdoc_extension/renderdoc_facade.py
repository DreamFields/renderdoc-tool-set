"""
RenderDoc API Facade.
Provides thread-safe access to RenderDoc's ReplayController and CaptureContext.
"""



from .services import (
    CaptureManager,
    ActionService,
    ResourceService,
    PipelineService,
    DiagnosticService,
)



class RenderDocFacade:
    """Facade that delegates RenderDoc work to specialized services."""

    def __init__(self, ctx):
        self.ctx = ctx
        self._capture = CaptureManager(ctx, self._invoke)
        self._action = ActionService(ctx, self._invoke)
        self._resource = ResourceService(ctx, self._invoke)

        self._pipeline = PipelineService(ctx, self._invoke)
        self._diag = None
        if DiagnosticService is not None:
            self._diag = DiagnosticService(
                ctx,
                self._invoke,
                self._capture,
                self._action,
                self._resource,
                self._pipeline,
            )


    def _invoke(self, callback):
        """Invoke a callback on the replay thread."""
        self.ctx.Replay().BlockInvoke(callback)

    def get_capture_status(self):
        return self._capture.get_capture_status()

    def list_captures(self, directory):
        return self._capture.list_captures(directory)

    def open_capture(self, capture_path):
        return self._capture.open_capture(capture_path)

    def get_draw_calls(
        self,
        include_children=True,
        marker_filter=None,
        exclude_markers=None,
        event_id_min=None,
        event_id_max=None,
        only_actions=False,
        flags_filter=None,
    ):
        return self._action.get_draw_calls(
            include_children=include_children,
            marker_filter=marker_filter,
            exclude_markers=exclude_markers,
            event_id_min=event_id_min,
            event_id_max=event_id_max,
            only_actions=only_actions,
            flags_filter=flags_filter,
        )

    def get_frame_summary(self):
        return self._action.get_frame_summary()

    def get_draw_call_details(self, event_id):
        return self._action.get_draw_call_details(event_id)

    def get_action_timings(self, event_ids=None, marker_filter=None, exclude_markers=None):
        return self._action.get_action_timings(
            event_ids=event_ids,
            marker_filter=marker_filter,
            exclude_markers=exclude_markers,
        )



    def get_buffer_contents(self, resource_id, offset=0, length=0):
        return self._resource.get_buffer_contents(resource_id, offset, length)

    def get_texture_info(self, resource_id):
        return self._resource.get_texture_info(resource_id)

    def get_texture_data(self, resource_id, mip=0, slice=0, sample=0,
                         depth_slice=None, output_path=None):
        return self._resource.get_texture_data(
            resource_id, mip, slice, sample, depth_slice, output_path)

    def save_texture_as_png(self, resource_id, output_path, event_id=None, mip=0,
                              max_size=0):
        return self._resource.save_texture_as_png(
            resource_id, output_path, event_id, mip, max_size)

    def get_shader_info(self, event_id, stage, include_disassembly=False,
                        include_constant_buffers=False, include_resources=False,
                        disassembly_target=None):
        return self._pipeline.get_shader_info(
            event_id, stage,
            include_disassembly=include_disassembly,
            include_constant_buffers=include_constant_buffers,
            include_resources=include_resources,
            disassembly_target=disassembly_target,
        )

    def get_pipeline_state(self, event_id):
        return self._pipeline.get_pipeline_state(event_id)

    def get_multiple_pipeline_states(self, event_ids):
        return self._pipeline.get_multiple_pipeline_states(event_ids)

    def compare_pipeline_states(self, base_event_id, target_event_id):
        return self._pipeline.compare_pipeline_states(base_event_id, target_event_id)

    def get_shader_source(self, event_id, stage):
        return self._pipeline.get_shader_source(event_id, stage)

    def edit_shader(self, event_id, stage, source_code, entry_point=None):
        return self._pipeline.edit_shader(event_id, stage, source_code, entry_point)

    def revert_shader(self, event_id, stage):
        return self._pipeline.revert_shader(event_id, stage)

    # ------------------------------------------------------------------ #
    #  New features                                                       #
    # ------------------------------------------------------------------ #

    def get_render_target_thumbnail(self, event_id, rtv_index=0, depth=False,
                                     max_size=256, output_path=None):
        return self._resource.get_render_target_thumbnail(
            event_id, rtv_index, depth, max_size, output_path)

    def get_render_target_diff(self, event_id, compare_event_id=None,
                                rtv_index=0, depth=False, threshold=0,
                                max_size=512, output_path=None):
        return self._resource.get_render_target_diff(
            event_id, compare_event_id, rtv_index, depth,
            threshold, max_size, output_path)

    # ------------------------------------------------------------------ #
    #  Diagnostic + power-user features                                  #
    # ------------------------------------------------------------------ #

    def _require_diag(self):
        if self._diag is None:
            raise ValueError(
                "DiagnosticService is unavailable in current extension install. "
                "Please reinstall extension (python scripts/install_extension.py sync)."
            )
        return self._diag

    def debug_pixel(self, event_id, x, y, sample=None, primitive=None):
        return self._require_diag().debug_pixel(event_id, x, y, sample, primitive)


    def debug_vertex(self, event_id, vtx_id, instance=0):
        return self._require_diag().debug_vertex(event_id, vtx_id, instance)

    def debug_thread(self, event_id, gx, gy, gz, tx, ty, tz):
        return self._require_diag().debug_thread(event_id, gx, gy, gz, tx, ty, tz)

    def pick_pixel(self, x, y, event_id=None, target=0):
        return self._require_diag().pick_pixel(x, y, event_id, target)

    def tex_stats(self, resource_id, mip=0, array_slice=0, histogram=False, event_id=None):
        return self._require_diag().tex_stats(resource_id, mip, array_slice, histogram, event_id)

    def vfs_ls(self, path="/", long=False):
        return self._require_diag().vfs_ls(path, long)

    def vfs_cat(self, path):
        return self._require_diag().vfs_cat(path)

    def vfs_tree(self, path="/", depth=2):
        return self._require_diag().vfs_tree(path, depth)

    def mesh_data(self, event_id=None, stage="vs-out"):
        return self._require_diag().mesh_data(event_id, stage)

    def snapshot_export(self, event_id, output_dir):
        return self._require_diag().snapshot_export(event_id, output_dir)

    def capture_sections(self):
        return self._require_diag().capture_sections()

    def capture_section_content(self, name):
        return self._require_diag().capture_section_content(name)

    def capture_gpus(self):
        return self._require_diag().capture_gpus()

    def capture_thumbnail(self, max_size=0):
        return self._require_diag().capture_thumbnail(max_size)

    def callstack_resolve(self, event_id=None):
        return self._require_diag().callstack_resolve(event_id)

