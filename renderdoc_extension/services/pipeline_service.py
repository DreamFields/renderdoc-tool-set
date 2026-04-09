"""
Pipeline state service for RenderDoc.
"""



import renderdoc as rd

from ..utils import Helpers, Parsers, Serializers


class PipelineService:
    """Pipeline state service."""

    def __init__(self, ctx, invoke_fn):
        self.ctx = ctx
        self._invoke = invoke_fn

    def get_shader_info(self, event_id, stage, include_disassembly=False,
                        include_constant_buffers=False, include_resources=False,
                        disassembly_target=None):
        """Get shader information for a specific stage.

        By default only lightweight metadata is returned (resource_id, entry_point,
        available_targets).  Set the ``include_*`` flags to ``True`` to fetch the
        heavier sections (disassembly text, constant buffer values, resource
        bindings).  This avoids exceeding MCP response-size limits.

        Args:
            disassembly_target: When ``include_disassembly`` is True, use this to
                pick a specific target (e.g. ``"GLSL"``).  If the requested target
                is not found, an error is returned instead of falling back to
                another target.  When *None* (default) the first available target
                is used.
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"shader": None, "error": None}

        def callback(controller):
            controller.SetFrameEvent(event_id, True)

            pipe = controller.GetPipelineState()
            stage_enum = Parsers.parse_stage(stage)

            shader = pipe.GetShader(stage_enum)
            if shader == rd.ResourceId.Null():
                result["error"] = "No %s shader bound" % stage
                return

            entry = pipe.GetShaderEntryPoint(stage_enum)
            reflection = pipe.GetShaderReflection(stage_enum)

            shader_info = {
                "event_id": event_id,
                "resource_id": str(shader),
                "entry_point": entry,
                "stage": stage,
            }

            # Determine the correct pipeline object based on shader stage
            if stage_enum == rd.ShaderStage.Compute:
                pipeline_obj = pipe.GetComputePipelineObject()
            else:
                pipeline_obj = pipe.GetGraphicsPipelineObject()

            # Always list available disassembly targets (lightweight)
            try:
                targets = controller.GetDisassemblyTargets(True)
                if targets:
                    shader_info["available_targets"] = list(targets)
            except Exception:
                pass

            # Optionally include full disassembly text
            if include_disassembly:
                try:
                    targets = controller.GetDisassemblyTargets(True)
                    if not targets:
                        shader_info["disassembly_error"] = (
                            "No disassembly targets available. "
                            "RenderDoc may lack the required disassembly plugin."
                        )
                    else:
                        if disassembly_target is not None:
                            # User requested a specific target – look for it
                            matched = None
                            for t in targets:
                                if disassembly_target.upper() in t.upper():
                                    matched = t
                                    break
                            if matched is None:
                                shader_info["disassembly_error"] = (
                                    "Requested target '%s' not found. "
                                    "Available: %s" % (disassembly_target, list(targets))
                                )
                            else:
                                try:
                                    shader_info["disassembly"] = controller.DisassembleShader(
                                        pipeline_obj, reflection, matched
                                    )
                                    shader_info["disassembly_target"] = matched
                                except Exception as inner_exc:
                                    shader_info["disassembly_error"] = (
                                        "Disassembly with target '%s' failed: %s"
                                        % (matched, str(inner_exc))
                                    )
                        else:
                            # No preference – try each target until one succeeds
                            disasm_ok = False
                            last_err = None
                            for target in targets:
                                try:
                                    shader_info["disassembly"] = controller.DisassembleShader(
                                        pipeline_obj, reflection, target
                                    )
                                    shader_info["disassembly_target"] = target
                                    disasm_ok = True
                                    break
                                except Exception as inner_exc:
                                    last_err = str(inner_exc)
                            if not disasm_ok:
                                shader_info["disassembly_error"] = (
                                    "All disassembly targets failed. Last error: %s" % last_err
                                )
                except Exception as exc:
                    shader_info["disassembly_error"] = "GetDisassemblyTargets failed: %s" % str(exc)

            if reflection:
                # Optionally include constant buffer values
                if include_constant_buffers:
                    shader_info["constant_buffers"] = self._get_cbuffer_info(
                        controller, pipe, reflection, stage_enum, pipeline_obj
                    )

                # Optionally include resource bindings (with runtime details)
                if include_resources:
                    shader_info["resources"] = self._get_resource_bindings(
                        controller, pipe, stage_enum, reflection
                    )

            result["shader"] = shader_info

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["shader"]

    def get_pipeline_state(self, event_id):
        """Get the full pipeline state at an event."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"pipeline": None, "error": None}

        def callback(controller):
            result["pipeline"] = self._capture_pipeline_state(controller, event_id)

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["pipeline"]

    def get_multiple_pipeline_states(self, event_ids):
        """Get the pipeline state for multiple event IDs."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        if not event_ids:
            raise ValueError("event_ids must not be empty")

        normalized_event_ids = self._normalize_event_ids(event_ids)
        result = {"payload": None}

        def callback(controller):
            states = {}
            for event_id in normalized_event_ids:
                states[str(event_id)] = self._capture_pipeline_state(controller, event_id)
            result["payload"] = {
                "count": len(normalized_event_ids),
                "event_ids": normalized_event_ids,
                "states": states,
            }

        self._invoke(callback)
        return result["payload"]

    def compare_pipeline_states(self, base_event_id, target_event_id):
        """Compare pipeline state between two events."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"comparison": None}

        def callback(controller):
            base_state = self._capture_pipeline_state(controller, base_event_id)
            target_state = self._capture_pipeline_state(controller, target_event_id)
            result["comparison"] = self._build_pipeline_comparison(
                base_state, target_state
            )

        self._invoke(callback)
        return result["comparison"]

    def _normalize_event_ids(self, event_ids):
        """Normalize event IDs while preserving order."""
        normalized = []
        seen = set()
        for event_id in event_ids:
            numeric_id = int(event_id)
            if numeric_id in seen:
                continue
            normalized.append(numeric_id)
            seen.add(numeric_id)
        return normalized

    def _capture_pipeline_state(self, controller, event_id):
        """Capture a serialized pipeline snapshot for one event."""
        controller.SetFrameEvent(event_id, True)
        action = self.ctx.GetAction(event_id)
        if not action:
            raise ValueError("No action at event %d" % event_id)

        structured_file = controller.GetStructuredFile()
        pipe = controller.GetPipelineState()
        api = controller.GetAPIProperties().pipelineType

        pipeline_info = {
            "event_id": event_id,
            "action_id": action.actionId,
            "action_name": action.GetName(structured_file),
            "api": str(api),
        }

        # Build resource caches once — O(T+B) up front, then O(1) per lookup
        tex_cache = {}
        try:
            for tex in controller.GetTextures():
                tex_cache[tex.resourceId] = tex
        except Exception:
            pass

        buf_cache = {}
        try:
            for buf in controller.GetBuffers():
                buf_cache[buf.resourceId] = buf
        except Exception:
            pass

        stages = {}
        for stage in Helpers.get_all_shader_stages():
            shader = pipe.GetShader(stage)
            if shader == rd.ResourceId.Null():
                continue

            stage_name = self._stage_to_name(stage)
            reflection = pipe.GetShaderReflection(stage)
            stage_info = {
                "stage": stage_name,
                "resource_id": str(shader),
                "entry_point": pipe.GetShaderEntryPoint(stage),
                "resources": self._get_stage_resources(
                    controller, pipe, stage, reflection, tex_cache, buf_cache
                ),
                "uavs": self._get_stage_uavs(
                    controller, pipe, stage, reflection, tex_cache, buf_cache
                ),
                "samplers": self._get_stage_samplers(pipe, stage, reflection),
                "constant_buffers": self._get_stage_cbuffers(
                    controller, pipe, stage, reflection
                ),
            }
            stages[stage_name] = stage_info

        pipeline_info["shaders"] = stages
        pipeline_info["active_stages"] = sorted(stages.keys())

        try:
            vp_scissor = pipe.GetViewportScissor()
            if vp_scissor:
                pipeline_info["viewports"] = [
                    {
                        "x": viewport.x,
                        "y": viewport.y,
                        "width": viewport.width,
                        "height": viewport.height,
                        "min_depth": viewport.minDepth,
                        "max_depth": viewport.maxDepth,
                    }
                    for viewport in vp_scissor.viewports
                ]
        except Exception:
            pass

        try:
            om = pipe.GetOutputMerger()
            if om:
                render_targets = []
                for index, render_target in enumerate(om.renderTargets):
                    if render_target.resourceId == rd.ResourceId.Null():
                        continue
                    rt_info = {"index": index, "resource_id": str(render_target.resourceId)}
                    rt_info.update(
                        self._get_resource_details_cached(
                            render_target.resourceId, tex_cache, buf_cache
                        )
                    )
                    render_targets.append(rt_info)
                pipeline_info["render_targets"] = render_targets

                if om.depthTarget.resourceId != rd.ResourceId.Null():
                    depth_target = {"resource_id": str(om.depthTarget.resourceId)}
                    depth_target.update(
                        self._get_resource_details_cached(
                            om.depthTarget.resourceId, tex_cache, buf_cache
                        )
                    )
                    pipeline_info["depth_target"] = depth_target
        except Exception:
            pass

        # --- Input Assembly / Vertex Input ---
        try:
            topology = pipe.GetPrimitiveTopology()
            pipeline_info["input_assembly"] = {"topology": str(topology)}
        except Exception:
            # Fallback to legacy GetIAState for older RenderDoc versions
            try:
                ia = pipe.GetIAState()
                if ia:
                    pipeline_info["input_assembly"] = {"topology": str(ia.topology)}
            except Exception:
                pass

        # Collect per-VB-slot metadata from vertex attributes:
        #   - which slots are referenced
        #   - per_instance flag
        #   - binding names (attribute names that reference each VB slot)
        referenced_vb_slots = set()
        vb_instance_map = {}   # slot -> bool (per-instance)
        vb_binding_names = {}  # slot -> list[str] (attribute names)
        try:
            attrs = pipe.GetVertexInputs()
            for attr in attrs:
                if attr.used:
                    slot = attr.vertexBuffer
                    referenced_vb_slots.add(slot)
                    vb_instance_map[slot] = attr.perInstance
                    vb_binding_names.setdefault(slot, []).append(attr.name)
        except Exception:
            pass

        # Vertex Buffers — include ALL bound VBs, mark whether referenced
        try:
            vbuffers = pipe.GetVBuffers()
            vb_list = []
            for idx, vb in enumerate(vbuffers):
                if vb.resourceId == rd.ResourceId.Null():
                    continue
                is_referenced = idx in referenced_vb_slots
                is_instance = vb_instance_map.get(idx, False)
                vb_info = {
                    "index": idx,
                    "resource_id": str(vb.resourceId),
                    "referenced_by_attribute": is_referenced,
                    "rate": "Instance" if is_instance else "Vertex",
                    "byte_offset": vb.byteOffset,
                    "byte_stride": vb.byteStride,
                }
                # Binding names: which vertex attributes reference this VB slot
                names = vb_binding_names.get(idx, [])
                if names:
                    vb_info["binding_names"] = names
                # Enrich with resource name
                try:
                    name = self.ctx.GetResourceName(vb.resourceId)
                    if name:
                        vb_info["resource_name"] = name
                except Exception:
                    pass
                # Enrich with buffer byte length and byte range from cache
                buf_desc = buf_cache.get(vb.resourceId)
                if buf_desc is not None:
                    vb_info["byte_length"] = buf_desc.length
                    # Byte Range: [byte_offset, byte_offset + byte_length)
                    # This matches RenderDoc GUI's "Byte Range" column
                    vb_info["byte_range"] = [vb.byteOffset, vb.byteOffset + buf_desc.length]
                vb_list.append(vb_info)
            if vb_list:
                pipeline_info["vertex_buffers"] = vb_list
        except Exception:
            pass

        # Index Buffer
        try:
            ib = pipe.GetIBuffer()
            if ib and ib.resourceId != rd.ResourceId.Null():
                ib_info = {
                    "resource_id": str(ib.resourceId),
                    "byte_offset": ib.byteOffset,
                    "byte_stride": ib.byteStride,
                }
                try:
                    name = self.ctx.GetResourceName(ib.resourceId)
                    if name:
                        ib_info["resource_name"] = name
                except Exception:
                    pass
                buf_desc = buf_cache.get(ib.resourceId)
                if buf_desc is not None:
                    ib_info["byte_length"] = buf_desc.length
                # Derive index format from stride
                stride_to_format = {2: "R16_UINT", 4: "R32_UINT"}
                ib_info["format"] = stride_to_format.get(
                    ib.byteStride, "UNKNOWN (stride=%d)" % ib.byteStride
                )
                pipeline_info["index_buffer"] = ib_info
        except Exception:
            pass

        # Vertex Input Attributes (Input Layout)
        try:
            attrs = pipe.GetVertexInputs()
            attr_list = []
            for attr in attrs:
                if not attr.used:
                    continue
                attr_info = {
                    "name": attr.name,
                    "vertex_buffer": attr.vertexBuffer,
                    "byte_offset": attr.byteOffset,
                    "format": str(attr.format.Name()) if hasattr(attr.format, 'Name') else str(attr.format),
                    "per_instance": attr.perInstance,
                    "instance_rate": attr.instanceRate,
                }
                if attr.genericEnabled:
                    attr_info["generic_enabled"] = True
                attr_list.append(attr_info)
            if attr_list:
                pipeline_info["vertex_attributes"] = attr_list
        except Exception:
            pass

        return pipeline_info

    def _build_pipeline_comparison(self, base_state, target_state):
        """Build a concise diff between two pipeline snapshots."""
        shader_changes = []
        resource_changes = {}

        stage_names = sorted(
            set(base_state.get("shaders", {}).keys())
            | set(target_state.get("shaders", {}).keys())
        )
        for stage_name in stage_names:
            base_stage = base_state.get("shaders", {}).get(stage_name)
            target_stage = target_state.get("shaders", {}).get(stage_name)

            base_shader = self._shader_signature(base_stage)
            target_shader = self._shader_signature(target_stage)
            if base_shader != target_shader:
                shader_changes.append(
                    {
                        "stage": stage_name,
                        "base": base_shader,
                        "target": target_shader,
                    }
                )

            stage_diff = {}
            for field_name in ("resources", "uavs", "samplers", "constant_buffers"):
                changes = self._compare_binding_lists(
                    base_stage.get(field_name, []) if base_stage else [],
                    target_stage.get(field_name, []) if target_stage else [],
                    key_field="slot",
                )
                if changes:
                    stage_diff[field_name] = changes

            if stage_diff:
                resource_changes[stage_name] = stage_diff

        render_target_changes = self._compare_binding_lists(
            base_state.get("render_targets", []),
            target_state.get("render_targets", []),
            key_field="index",
        )
        depth_target_changed = base_state.get("depth_target") != target_state.get(
            "depth_target"
        )
        input_assembly_changed = base_state.get("input_assembly") != target_state.get(
            "input_assembly"
        )
        viewport_changed = base_state.get("viewports") != target_state.get("viewports")

        same_pipeline = not any(
            [
                shader_changes,
                resource_changes,
                render_target_changes,
                depth_target_changed,
                input_assembly_changed,
                viewport_changed,
            ]
        )

        return {
            "base_event": {
                "event_id": base_state["event_id"],
                "action_name": base_state.get("action_name"),
            },
            "target_event": {
                "event_id": target_state["event_id"],
                "action_name": target_state.get("action_name"),
            },
            "same_pipeline": same_pipeline,
            "shader_changes": shader_changes,
            "resource_changes": resource_changes,
            "render_target_changes": render_target_changes,
            "depth_target_changed": depth_target_changed,
            "depth_target_base": self._compact_binding_item(base_state.get("depth_target")),
            "depth_target_target": self._compact_binding_item(target_state.get("depth_target")),
            "input_assembly_changed": input_assembly_changed,
            "input_assembly_base": base_state.get("input_assembly"),
            "input_assembly_target": target_state.get("input_assembly"),
            "viewport_changed": viewport_changed,
            "viewports_base": base_state.get("viewports", []),
            "viewports_target": target_state.get("viewports", []),
        }

    def _shader_signature(self, stage_info):
        """Return a compact shader signature for comparisons."""
        if not stage_info:
            return None
        return {
            "resource_id": stage_info.get("resource_id"),
            "entry_point": stage_info.get("entry_point"),
        }

    def _compare_binding_lists(self, base_items, target_items, key_field="slot"):
        """Compare two binding collections by slot or index."""
        base_map = self._index_binding_items(base_items, key_field)
        target_map = self._index_binding_items(target_items, key_field)
        binding_keys = sorted(set(base_map.keys()) | set(target_map.keys()))

        changes = []
        for binding_key in binding_keys:
            base_item = self._compact_binding_item(base_map.get(binding_key))
            target_item = self._compact_binding_item(target_map.get(binding_key))
            if base_item != target_item:
                changes.append(
                    {
                        key_field: binding_key,
                        "base": base_item,
                        "target": target_item,
                    }
                )
        return changes

    def _index_binding_items(self, items, key_field):
        """Create a keyed view of binding collections."""
        indexed = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            if key_field not in item:
                continue
            indexed[str(item[key_field])] = item
        return indexed

    def _compact_binding_item(self, item):
        """Trim large binding structures to the fields that matter for diffs."""
        if item is None:
            return None
        if not isinstance(item, dict):
            return item

        preferred_keys = [
            "index",
            "slot",
            "name",
            "resource_id",
            "resource_name",
            "type",
            "entry_point",
            "byte_size",
            "variable_count",
            "length",
            "format",
            "dimension",
            "filter",
            "address_u",
            "address_v",
            "address_w",
            "first_mip",
            "num_mips",
            "first_slice",
            "num_slices",
            "first_element",
            "num_elements",
        ]
        compact = {}
        for key in preferred_keys:
            if key in item:
                compact[key] = item[key]
        return compact or item

    def _stage_to_name(self, stage):
        """Convert a RenderDoc shader stage enum to a stable string."""
        stage_map = {
            rd.ShaderStage.Vertex: "vertex",
            rd.ShaderStage.Hull: "hull",
            rd.ShaderStage.Domain: "domain",
            rd.ShaderStage.Geometry: "geometry",
            rd.ShaderStage.Pixel: "pixel",
            rd.ShaderStage.Compute: "compute",
        }
        return stage_map.get(stage, str(stage))

    @staticmethod
    def _get_bind_number(res):
        """Get the bind number from a shader resource, handling API differences.

        Always returns an int, converting Bindpoint objects as needed.
        """
        raw = None
        if hasattr(res, 'fixedBindNumber'):
            raw = res.fixedBindNumber
        elif hasattr(res, 'bindPoint'):
            raw = res.bindPoint
        elif hasattr(res, 'fixedBindSetOrSpace'):
            raw = res.fixedBindSetOrSpace
        else:
            return 0
        return PipelineService._bindpoint_to_int(raw)

    @staticmethod
    def _bindpoint_to_int(bp):
        """Convert a RenderDoc Bindpoint object to an integer slot number.

        RenderDoc 1.25 uses ``Bindpoint`` objects (with ``.bind`` attribute)
        instead of plain integers for binding indices.  This helper safely
        converts either form to an int.
        """
        if isinstance(bp, int):
            return bp
        # Bindpoint object — prefer .bind, fall back to .set then int()
        if hasattr(bp, 'bind'):
            return bp.bind
        if hasattr(bp, 'set'):
            return bp.set
        try:
            return int(bp)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _flatten_bound_resources(bound_list):
        """Flatten BoundResourceArray objects into (slot, descriptor) tuples.

        RenderDoc 1.25 returns BoundResourceArray objects from
        GetReadOnlyResources / GetReadWriteResources / GetSamplers.
        Each BoundResourceArray has a ``bindPoint`` and a ``resources`` list
        of BoundResource items (each with ``.resourceId``, ``.firstMip``, etc.).

        Older versions return flat lists where each item already has
        ``.access.index`` and ``.descriptor``.

        This helper normalises both into a flat list of dicts with:
            slot, resource_id, firstMip, numMips, firstSlice, numSlices
        """
        results = []
        for item in bound_list:
            # --- New-style: BoundResourceArray (1.25+) ---
            if hasattr(item, 'resources') and hasattr(item, 'bindPoint'):
                slot = PipelineService._bindpoint_to_int(item.bindPoint)
                for bound in item.resources:
                    res_id = None
                    if hasattr(bound, 'resourceId'):
                        res_id = bound.resourceId
                    elif hasattr(bound, 'resource'):
                        res_id = bound.resource

                    entry = {
                        "slot": slot,
                        "resource_id": res_id,
                        "firstMip": getattr(bound, 'firstMip', 0),
                        "numMips": getattr(bound, 'numMips', 1),
                        "firstSlice": getattr(bound, 'firstSlice', 0),
                        "numSlices": getattr(bound, 'numSlices', 1),
                    }
                    results.append(entry)
            # --- Old-style: flat BoundResource with .access / .descriptor ---
            elif hasattr(item, 'access') and hasattr(item, 'descriptor'):
                desc = item.descriptor
                res_id = getattr(desc, 'resource', None) or getattr(desc, 'resourceId', None)
                entry = {
                    "slot": item.access.index,
                    "resource_id": res_id,
                    "firstMip": getattr(desc, 'firstMip', 0),
                    "numMips": getattr(desc, 'numMips', 1),
                    "firstSlice": getattr(desc, 'firstSlice', 0),
                    "numSlices": getattr(desc, 'numSlices', 1),
                }
                results.append(entry)
            else:
                # Unknown format — skip
                pass
        return results

    @staticmethod
    def _flatten_bound_samplers(sampler_list):
        """Flatten BoundResourceArray sampler objects into (slot, descriptor) tuples.

        Similar to _flatten_bound_resources but for sampler bindings.
        """
        results = []
        for item in sampler_list:
            # --- New-style: BoundResourceArray ---
            if hasattr(item, 'resources') and hasattr(item, 'bindPoint'):
                slot = PipelineService._bindpoint_to_int(item.bindPoint)
                for bound in item.resources:
                    results.append({"slot": slot, "bound": bound})
            # --- Old-style ---
            elif hasattr(item, 'access') and hasattr(item, 'descriptor'):
                results.append({
                    "slot": item.access.index,
                    "bound": item.descriptor,
                })
            else:
                pass
        return results

    def _get_stage_resources(self, controller, pipe, stage, reflection,
                             tex_cache=None, buf_cache=None):
        """Get shader resource views for a stage."""
        resources = []
        try:
            srvs = pipe.GetReadOnlyResources(stage, False)
            name_map = {}
            if reflection:
                for res in reflection.readOnlyResources:
                    name_map[self._get_bind_number(res)] = res.name

            for entry in self._flatten_bound_resources(srvs):
                res_id = entry["resource_id"]
                if res_id is None or res_id == rd.ResourceId.Null():
                    continue

                slot = entry["slot"]
                resource_info = {
                    "slot": slot,
                    "name": name_map.get(slot, ""),
                    "resource_id": str(res_id),
                }
                if tex_cache is not None and buf_cache is not None:
                    resource_info.update(
                        self._get_resource_details_cached(
                            res_id, tex_cache, buf_cache
                        )
                    )
                else:
                    resource_info.update(
                        self._get_resource_details(controller, res_id)
                    )
                resource_info["first_mip"] = entry["firstMip"]
                resource_info["num_mips"] = entry["numMips"]
                resource_info["first_slice"] = entry["firstSlice"]
                resource_info["num_slices"] = entry["numSlices"]
                resources.append(resource_info)
        except Exception as exc:
            resources.append({"error": str(exc)})
        return resources

    def _get_stage_uavs(self, controller, pipe, stage, reflection,
                        tex_cache=None, buf_cache=None):
        """Get unordered access views for a stage."""
        uavs = []
        try:
            uav_list = pipe.GetReadWriteResources(stage, False)
            name_map = {}
            if reflection:
                for res in reflection.readWriteResources:
                    name_map[self._get_bind_number(res)] = res.name

            for entry in self._flatten_bound_resources(uav_list):
                res_id = entry["resource_id"]
                if res_id is None or res_id == rd.ResourceId.Null():
                    continue

                slot = entry["slot"]
                uav_info = {
                    "slot": slot,
                    "name": name_map.get(slot, ""),
                    "resource_id": str(res_id),
                }
                if tex_cache is not None and buf_cache is not None:
                    uav_info.update(
                        self._get_resource_details_cached(
                            res_id, tex_cache, buf_cache
                        )
                    )
                else:
                    uav_info.update(
                        self._get_resource_details(controller, res_id)
                    )
                uav_info["first_element"] = entry["firstMip"]
                uav_info["num_elements"] = entry["numMips"]
                uavs.append(uav_info)
        except Exception as exc:
            uavs.append({"error": str(exc)})
        return uavs

    def _get_stage_samplers(self, pipe, stage, reflection):
        """Get samplers for a stage."""
        samplers = []
        try:
            # GetSamplers API differs across RenderDoc versions
            try:
                sampler_list = pipe.GetSamplers(stage, False)
            except TypeError:
                sampler_list = pipe.GetSamplers(stage)
            name_map = {}
            if reflection:
                for sampler in reflection.samplers:
                    name_map[self._get_bind_number(sampler)] = sampler.name

            for entry in self._flatten_bound_samplers(sampler_list):
                slot = entry["slot"]
                desc = entry["bound"]
                sampler_info = {
                    "slot": slot,
                    "name": name_map.get(slot, ""),
                }

                try:
                    sampler_info["address_u"] = str(desc.addressU)
                    sampler_info["address_v"] = str(desc.addressV)
                    sampler_info["address_w"] = str(desc.addressW)
                except AttributeError:
                    pass

                try:
                    sampler_info["filter"] = str(desc.filter)
                except AttributeError:
                    pass

                try:
                    sampler_info["max_anisotropy"] = desc.maxAnisotropy
                except AttributeError:
                    pass

                try:
                    sampler_info["min_lod"] = desc.minLOD
                    sampler_info["max_lod"] = desc.maxLOD
                    sampler_info["mip_lod_bias"] = desc.mipLODBias
                except AttributeError:
                    pass

                try:
                    sampler_info["border_color"] = [
                        desc.borderColor[0],
                        desc.borderColor[1],
                        desc.borderColor[2],
                        desc.borderColor[3],
                    ]
                except (AttributeError, TypeError):
                    pass

                try:
                    sampler_info["compare_function"] = str(desc.compareFunction)
                except AttributeError:
                    pass

                samplers.append(sampler_info)
        except Exception as exc:
            samplers.append({"error": str(exc)})
        return samplers

    def _get_stage_cbuffers(self, controller, pipe, stage, reflection):
        """Get constant buffers for a stage from shader reflection."""
        cbuffers = []
        try:
            if not reflection:
                return cbuffers

            for constant_block in reflection.constantBlocks:
                raw_bp = (
                    constant_block.bindPoint
                    if hasattr(constant_block, "bindPoint")
                    else self._get_bind_number(constant_block)
                )
                slot = self._bindpoint_to_int(raw_bp)
                cbuffer_info = {
                    "slot": slot,
                    "name": constant_block.name,
                    "byte_size": constant_block.byteSize,
                    "variable_count": len(constant_block.variables)
                    if constant_block.variables
                    else 0,
                    "variables": [],
                }
                if constant_block.variables:
                    for variable in constant_block.variables:
                        cbuffer_info["variables"].append(
                            {
                                "name": variable.name,
                                "byte_offset": variable.byteOffset,
                                "type": str(variable.type.name)
                                if variable.type
                                else "",
                            }
                        )
                cbuffers.append(cbuffer_info)
        except Exception as exc:
            cbuffers.append({"error": str(exc)})
        return cbuffers

    def _get_resource_details(self, controller, resource_id):
        """Get details about a resource."""
        details = {}

        try:
            resource_name = self.ctx.GetResourceName(resource_id)
            if resource_name:
                details["resource_name"] = resource_name
        except Exception:
            pass

        for texture in controller.GetTextures():
            if texture.resourceId == resource_id:
                details["type"] = "texture"
                details["width"] = texture.width
                details["height"] = texture.height
                details["depth"] = texture.depth
                details["array_size"] = texture.arraysize
                details["mip_levels"] = texture.mips
                details["format"] = str(texture.format.Name())
                details["dimension"] = str(texture.type)
                details["msaa_samples"] = texture.msSamp
                return details

        for buffer in controller.GetBuffers():
            if buffer.resourceId == resource_id:
                details["type"] = "buffer"
                details["length"] = buffer.length
                return details

        return details

    def _get_cbuffer_info(self, controller, pipe, reflection, stage, pipeline_obj=None):
        """Get constant buffer information and values."""
        if pipeline_obj is None:
            if stage == rd.ShaderStage.Compute:
                pipeline_obj = pipe.GetComputePipelineObject()
            else:
                pipeline_obj = pipe.GetGraphicsPipelineObject()
        cbuffers = []
        for index, cbuffer in enumerate(reflection.constantBlocks):
            cbuffer_info = {
                "name": cbuffer.name,
                "slot": index,
                "size": cbuffer.byteSize,
                "variables": [],
            }

            try:
                binding = pipe.GetConstantBuffer(stage, index, 0)
                if binding.resourceId != rd.ResourceId.Null():
                    variables = controller.GetCBufferVariableContents(
                        pipeline_obj,
                        reflection.resourceId,
                        stage,
                        reflection.entryPoint,
                        index,
                        binding.resourceId,
                        binding.byteOffset,
                        binding.byteSize,
                    )
                    cbuffer_info["variables"] = Serializers.serialize_variables(variables)
            except Exception as exc:
                cbuffer_info["error"] = str(exc)

            cbuffers.append(cbuffer_info)
        return cbuffers

    def _get_resource_bindings(self, controller, pipe, stage, reflection):
        """Get shader resource bindings with runtime details.

        Merges reflection metadata (name, type) with runtime binding data
        (resource_id, texture/buffer properties) from the pipeline state.

        Args:
            controller: The replay controller.
            pipe: The pipeline state object.
            stage: The shader stage enum.
            reflection: The shader reflection object.

        Returns:
            List of resource binding dicts with full details.
        """
        resources = []

        # Build lookup caches for resource details (avoids O(N) per resource)
        tex_cache = {}
        try:
            for tex in controller.GetTextures():
                tex_cache[tex.resourceId] = tex
        except Exception:
            pass

        buf_cache = {}
        try:
            for buf in controller.GetBuffers():
                buf_cache[buf.resourceId] = buf
        except Exception:
            pass

        # --- Read-only resources (SRVs) ---
        try:
            ro_name_map = {}
            ro_type_map = {}
            if reflection:
                for res in reflection.readOnlyResources:
                    bind_num = self._get_bind_number(res)
                    ro_name_map[bind_num] = res.name
                    ro_type_map[bind_num] = str(res.resType)

            srvs = pipe.GetReadOnlyResources(stage, False)
            for flat in self._flatten_bound_resources(srvs):
                slot = flat["slot"]
                res_id = flat["resource_id"]
                entry = {
                    "slot": slot,
                    "name": ro_name_map.get(slot, ""),
                    "type": ro_type_map.get(slot, ""),
                    "access": "ReadOnly",
                }

                if res_id is not None and res_id != rd.ResourceId.Null():
                    entry["resource_id"] = str(res_id)
                    entry.update(
                        self._get_resource_details_cached(
                            res_id, tex_cache, buf_cache
                        )
                    )
                    entry["first_mip"] = flat["firstMip"]
                    entry["num_mips"] = flat["numMips"]
                    entry["first_slice"] = flat["firstSlice"]
                    entry["num_slices"] = flat["numSlices"]

                resources.append(entry)
        except Exception as exc:
            resources.append({"error": "ReadOnly: %s" % str(exc)})

        # --- Read-write resources (UAVs) ---
        try:
            rw_name_map = {}
            rw_type_map = {}
            if reflection:
                for res in reflection.readWriteResources:
                    bind_num = self._get_bind_number(res)
                    rw_name_map[bind_num] = res.name
                    rw_type_map[bind_num] = str(res.resType)

            uavs = pipe.GetReadWriteResources(stage, False)
            for flat in self._flatten_bound_resources(uavs):
                slot = flat["slot"]
                res_id = flat["resource_id"]
                entry = {
                    "slot": slot,
                    "name": rw_name_map.get(slot, ""),
                    "type": rw_type_map.get(slot, ""),
                    "access": "ReadWrite",
                }

                if res_id is not None and res_id != rd.ResourceId.Null():
                    entry["resource_id"] = str(res_id)
                    entry.update(
                        self._get_resource_details_cached(
                            res_id, tex_cache, buf_cache
                        )
                    )
                    entry["first_element"] = flat["firstMip"]
                    entry["num_elements"] = flat["numMips"]

                resources.append(entry)
        except Exception as exc:
            resources.append({"error": "ReadWrite: %s" % str(exc)})

        return resources

    def _get_resource_details_cached(self, resource_id, tex_cache, buf_cache):
        """Get resource details using pre-built caches (O(1) lookup).

        Args:
            resource_id: The resource ID to look up.
            tex_cache: Dict mapping ResourceId -> texture descriptor.
            buf_cache: Dict mapping ResourceId -> buffer descriptor.

        Returns:
            Dict with resource properties (type, dimensions, format, etc.).
        """
        details = {}

        try:
            resource_name = self.ctx.GetResourceName(resource_id)
            if resource_name:
                details["resource_name"] = resource_name
        except Exception:
            pass

        texture = tex_cache.get(resource_id)
        if texture is not None:
            details["type"] = "texture"
            details["width"] = texture.width
            details["height"] = texture.height
            details["depth"] = texture.depth
            details["array_size"] = texture.arraysize
            details["mip_levels"] = texture.mips
            details["format"] = str(texture.format.Name())
            details["dimension"] = str(texture.type)
            details["msaa_samples"] = texture.msSamp
            return details

        buffer = buf_cache.get(resource_id)
        if buffer is not None:
            details["type"] = "buffer"
            details["length"] = buffer.length
            return details

        return details



    # ------------------------------------------------------------------ #
    #  Shader editing helpers                                             #
    # ------------------------------------------------------------------ #

    # Track replacements so we can revert them later.
    # Key: original ResourceId (int), Value: replacement ResourceId (int)
    _replacements = {}

    def get_shader_source(self, event_id, stage):
        """Get the editable source code for a shader at the given event/stage.

        The method prioritises GLSL source over other representations so that
        callers get human-readable shader code by default.

        Returns a dict with:
          - event_id, stage, resource_id, entry_point
          - encoding: the ShaderEncoding name (e.g. "GLSL", "HLSL")
          - source: the source text (from debug info or disassembly)
          - source_files: list of {filename, source} from debug info (if available)
          - raw_encoding: encoding of rawBytes in reflection
          - editable: whether the source can be compiled back
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"shader": None, "error": None}

        def callback(controller):
            controller.SetFrameEvent(event_id, True)

            pipe = controller.GetPipelineState()
            stage_enum = Parsers.parse_stage(stage)

            shader = pipe.GetShader(stage_enum)
            if shader == rd.ResourceId.Null():
                result["error"] = "No %s shader bound" % stage
                return

            entry = pipe.GetShaderEntryPoint(stage_enum)
            reflection = pipe.GetShaderReflection(stage_enum)

            info = {
                "event_id": event_id,
                "stage": stage,
                "resource_id": str(shader),
                "entry_point": entry,
                "source": None,
                "source_files": [],
                "encoding": None,
                "raw_encoding": None,
                "editable": False,
            }

            # 1. Try to get source from debug info (embedded original source)
            if reflection and reflection.debugInfo:
                debug = reflection.debugInfo
                if debug.files:
                    for src_file in debug.files:
                        info["source_files"].append({
                            "filename": src_file.filename,
                            "source": src_file.contents,
                        })
                    # Use the first file as the main source
                    info["source"] = debug.files[0].contents
                    info["editable"] = True

            # 2. Get the raw encoding
            if reflection:
                try:
                    info["raw_encoding"] = str(reflection.encoding)
                except Exception:
                    pass

            # 3. If no source from debug info, try disassembly targets
            #    Prioritise GLSL target so the caller gets readable code.
            if info["source"] is None:
                if stage_enum == rd.ShaderStage.Compute:
                    pipeline_obj = pipe.GetComputePipelineObject()
                else:
                    pipeline_obj = pipe.GetGraphicsPipelineObject()

                try:
                    targets = controller.GetDisassemblyTargets(True)
                    if targets and reflection:
                        # Sort targets so that GLSL-like ones come first
                        def _glsl_priority(t):
                            upper = t.upper()
                            if "GLSL" in upper:
                                return 0
                            if "HLSL" in upper:
                                return 1
                            return 2

                        sorted_targets = sorted(targets, key=_glsl_priority)
                        for target in sorted_targets:
                            try:
                                disasm = controller.DisassembleShader(
                                    pipeline_obj, reflection, target
                                )
                                info["source"] = disasm
                                info["encoding"] = target
                                # Disassembly is generally editable for GLSL
                                if "GLSL" in target.upper():
                                    info["editable"] = True
                                break
                            except Exception:
                                pass
                except Exception:
                    pass

            # 4. Determine the encoding for compilation
            if info["encoding"] is None and reflection:
                try:
                    enc = reflection.encoding
                    info["encoding"] = str(enc)
                except Exception:
                    pass

            result["shader"] = info

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["shader"]

    def edit_shader(self, event_id, stage, source_code, entry_point=None):
        """Compile new shader source and replace the original shader.

        Args:
            event_id: The event ID where the shader is bound.
            stage: Shader stage (vertex, pixel, etc.).
            source_code: The new shader source code (text string).
            entry_point: Optional override for entry point name.

        Returns a dict with:
          - success: bool
          - original_id: the original shader resource id
          - replacement_id: the new compiled shader resource id (if success)
          - errors: compilation errors/warnings (if any)
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"data": None, "error": None}

        def callback(controller):
            controller.SetFrameEvent(event_id, True)

            pipe = controller.GetPipelineState()
            stage_enum = Parsers.parse_stage(stage)

            shader = pipe.GetShader(stage_enum)
            if shader == rd.ResourceId.Null():
                result["error"] = "No %s shader bound" % stage
                return

            reflection = pipe.GetShaderReflection(stage_enum)
            actual_entry = entry_point or pipe.GetShaderEntryPoint(stage_enum)

            # Determine the source encoding for compilation
            source_encoding = rd.ShaderEncoding.Unknown
            if reflection:
                enc = reflection.encoding
                # Map raw encoding to a source-level encoding
                if enc == rd.ShaderEncoding.GLSL:
                    source_encoding = rd.ShaderEncoding.GLSL
                elif enc == rd.ShaderEncoding.HLSL:
                    source_encoding = rd.ShaderEncoding.HLSL
                elif enc == rd.ShaderEncoding.SPIRV or enc == rd.ShaderEncoding.OpenGLSPIRV:
                    # For SPIR-V shaders, try GLSL as input encoding
                    source_encoding = rd.ShaderEncoding.GLSL
                elif enc == rd.ShaderEncoding.DXBC or enc == rd.ShaderEncoding.DXIL:
                    source_encoding = rd.ShaderEncoding.HLSL
                else:
                    source_encoding = rd.ShaderEncoding.GLSL

            # Get compile flags from the original shader if available
            compile_flags = rd.ShaderCompileFlags()
            if reflection and reflection.debugInfo:
                try:
                    compile_flags = reflection.debugInfo.compileFlags
                except Exception:
                    pass

            # Build the replacement shader
            source_bytes = source_code.encode("utf-8")
            new_id, errors = controller.BuildTargetShader(
                actual_entry,
                source_encoding,
                source_bytes,
                compile_flags,
                stage_enum,
            )

            if new_id == rd.ResourceId.Null():
                result["data"] = {
                    "success": False,
                    "original_id": str(shader),
                    "replacement_id": None,
                    "errors": errors,
                }
                return

            # If there was a previous replacement for this shader, free it
            orig_id_int = shader.id if hasattr(shader, "id") else int(str(shader).split("::")[-1])
            if orig_id_int in PipelineService._replacements:
                try:
                    old_replacement = rd.ResourceId()
                    old_replacement.id = PipelineService._replacements[orig_id_int]
                    controller.FreeTargetResource(old_replacement)
                except Exception:
                    pass

            # Apply the replacement
            controller.ReplaceResource(shader, new_id)
            PipelineService._replacements[orig_id_int] = new_id.id if hasattr(new_id, "id") else int(str(new_id).split("::")[-1])

            result["data"] = {
                "success": True,
                "original_id": str(shader),
                "replacement_id": str(new_id),
                "errors": errors if errors else None,
            }

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def revert_shader(self, event_id, stage):
        """Revert a previously edited shader back to the original.

        Args:
            event_id: The event ID where the shader is bound.
            stage: Shader stage (vertex, pixel, etc.).

        Returns a dict indicating success and which shader was reverted.
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"data": None, "error": None}

        def callback(controller):
            controller.SetFrameEvent(event_id, True)

            pipe = controller.GetPipelineState()
            stage_enum = Parsers.parse_stage(stage)

            shader = pipe.GetShader(stage_enum)
            if shader == rd.ResourceId.Null():
                result["error"] = "No %s shader bound" % stage
                return

            orig_id_int = shader.id if hasattr(shader, "id") else int(str(shader).split("::")[-1])

            if orig_id_int not in PipelineService._replacements:
                result["data"] = {
                    "success": False,
                    "resource_id": str(shader),
                    "message": "No active replacement found for this shader",
                }
                return

            # Remove the replacement
            controller.RemoveReplacement(shader)

            # Free the replacement resource
            try:
                replacement = rd.ResourceId()
                replacement.id = PipelineService._replacements[orig_id_int]
                controller.FreeTargetResource(replacement)
            except Exception:
                pass

            del PipelineService._replacements[orig_id_int]

            result["data"] = {
                "success": True,
                "resource_id": str(shader),
                "message": "Shader reverted to original",
            }

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]
