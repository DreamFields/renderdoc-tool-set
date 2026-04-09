"""Diagnostic and power-user services inspired by renderdoc-cli.

This module adds:
- shader debug helpers (pixel / vertex / thread)
- pick pixel and texture statistics
- VFS semantic browsing (ls/cat/tree)
- richer exports (mesh/snapshot)
- capture-file style metadata (sections/section/callstacks/gpus/thumbnail)
"""

import base64
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import renderdoc as rd

from ..utils import Helpers, Parsers, Serializers


class DiagnosticService:
    """Advanced diagnostic utilities built on top of existing services."""

    def __init__(
        self,
        ctx,
        invoke_fn,
        capture_service,
        action_service,
        resource_service,
        pipeline_service,
    ):
        self.ctx = ctx
        self._invoke = invoke_fn
        self._capture = capture_service
        self._action = action_service
        self._resource = resource_service
        self._pipeline = pipeline_service

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _stage_enum(stage: str):
        table = {
            "vertex": rd.ShaderStage.Vertex,
            "hull": rd.ShaderStage.Hull,
            "domain": rd.ShaderStage.Domain,
            "geometry": rd.ShaderStage.Geometry,
            "pixel": rd.ShaderStage.Pixel,
            "compute": rd.ShaderStage.Compute,
        }
        key = (stage or "").strip().lower()
        if key not in table:
            raise ValueError("Invalid shader stage: %s" % stage)
        return table[key]

    @staticmethod
    def _scalar_to_list(value_obj) -> List[float]:
        """Best-effort conversion from RenderDoc scalar container to python list."""
        try:
            if hasattr(value_obj, "f32v"):
                return list(value_obj.f32v)
            if hasattr(value_obj, "f64v"):
                return list(value_obj.f64v)
            if hasattr(value_obj, "u32v"):
                return list(value_obj.u32v)
            if hasattr(value_obj, "s32v"):
                return list(value_obj.s32v)
            if hasattr(value_obj, "u16v"):
                return list(value_obj.u16v)
            if hasattr(value_obj, "s16v"):
                return list(value_obj.s16v)
            if hasattr(value_obj, "u8v"):
                return list(value_obj.u8v)
            if hasattr(value_obj, "s8v"):
                return list(value_obj.s8v)
        except Exception:
            pass
        return []

    def _serialize_trace(self, trace, stage: str, eid: int) -> Dict[str, Any]:
        """Serialize RenderDoc shader debug trace to a stable JSON payload."""
        result: Dict[str, Any] = {
            "stage": stage,
            "eid": int(eid),
            "total_steps": 0,
            "inputs": [],
            "outputs": [],
            "trace": [],
        }

        # Inputs / outputs
        for attr_name, out_key in (("inputs", "inputs"), ("outputs", "outputs")):
            try:
                vars_list = getattr(trace, attr_name, None)
                if vars_list:
                    for v in vars_list:
                        result[out_key].append(
                            {
                                "name": getattr(v, "name", ""),
                                "type": str(getattr(v, "type", "")),
                                "after": self._scalar_to_list(getattr(v, "value", None)),
                            }
                        )
            except Exception:
                pass

        # Step-by-step variable changes
        try:
            states = getattr(trace, "states", None) or []
            result["total_steps"] = len(states)
            for idx, st in enumerate(states):
                changes = []
                try:
                    changed = getattr(st, "changes", None) or getattr(st, "variables", None) or []
                    for c in changed:
                        changes.append(
                            {
                                "name": getattr(c, "name", ""),
                                "type": str(getattr(c, "type", "")),
                                "after": self._scalar_to_list(getattr(c, "value", None)),
                            }
                        )
                except Exception:
                    pass

                result["trace"].append(
                    {
                        "step": idx,
                        "instruction": getattr(st, "nextInstruction", 0),
                        "file": getattr(st, "fileName", None),
                        "line": int(getattr(st, "lineInfo", 0) or 0),
                        "changes": changes,
                    }
                )
        except Exception:
            pass

        return result

    def _require_capture(self):
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

    def _resolve_event_for_optional(self, controller, event_id: Optional[int]):
        if event_id is None:
            return
        controller.SetFrameEvent(int(event_id), True)

    def _find_texture_desc_by_str_id(self, controller, resource_id: str):
        target_id = Parsers.extract_numeric_id(resource_id)
        for tex in controller.GetTextures():
            tex_id = Parsers.extract_numeric_id(str(tex.resourceId))
            if tex_id == target_id:
                return tex
        return None

    # ------------------------------------------------------------------
    # 1) Debug pixel / vertex / thread
    # ------------------------------------------------------------------

    def debug_pixel(self, event_id, x, y, sample=None, primitive=None):
        self._require_capture()
        result = {"data": None, "error": None}

        def callback(controller):
            try:
                controller.SetFrameEvent(int(event_id), True)
                # Try multiple signatures to handle API differences.
                trace = None
                tried = []
                for args in (
                    (int(x), int(y), int(sample or 0), int(primitive or 0)),
                    (int(x), int(y), int(sample or 0)),
                    (int(x), int(y)),
                ):
                    try:
                        trace = controller.DebugPixel(*args)
                        break
                    except Exception as exc:
                        tried.append(str(exc))
                if trace is None:
                    # Graceful fallback to pick-pixel summary.
                    pick = self.pick_pixel(int(x), int(y), int(event_id), 0)
                    result["data"] = {
                        "stage": "pixel",
                        "eid": int(event_id),
                        "total_steps": 0,
                        "inputs": [],
                        "outputs": [
                            {
                                "name": "color",
                                "type": "float4",
                                "after": [
                                    pick["color"]["r"],
                                    pick["color"]["g"],
                                    pick["color"]["b"],
                                    pick["color"]["a"],
                                ],
                            }
                        ],
                        "trace": [],
                        "warning": "DebugPixel API unavailable, returned pick-pixel fallback",
                        "debug_api_errors": tried,
                    }
                    return
                result["data"] = self._serialize_trace(trace, "pixel", int(event_id))
            except Exception as exc:
                result["error"] = str(exc)

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def debug_vertex(self, event_id, vtx_id, instance=0):
        self._require_capture()
        result = {"data": None, "error": None}

        def callback(controller):
            try:
                controller.SetFrameEvent(int(event_id), True)
                trace = None
                tried = []
                for args in (
                    (int(vtx_id), int(instance), 0),
                    (int(vtx_id), int(instance)),
                    (int(vtx_id),),
                ):
                    try:
                        trace = controller.DebugVertex(*args)
                        break
                    except Exception as exc:
                        tried.append(str(exc))
                if trace is None:
                    raise ValueError("DebugVertex API unavailable: %s" % "; ".join(tried))
                result["data"] = self._serialize_trace(trace, "vertex", int(event_id))
            except Exception as exc:
                result["error"] = str(exc)

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def debug_thread(self, event_id, gx, gy, gz, tx, ty, tz):
        self._require_capture()
        result = {"data": None, "error": None}

        def callback(controller):
            try:
                controller.SetFrameEvent(int(event_id), True)
                trace = None
                tried = []
                for args in (
                    (int(gx), int(gy), int(gz), int(tx), int(ty), int(tz)),
                    (int(tx), int(ty), int(tz)),
                ):
                    try:
                        trace = controller.DebugThread(*args)
                        break
                    except Exception as exc:
                        tried.append(str(exc))
                if trace is None:
                    raise ValueError("DebugThread API unavailable: %s" % "; ".join(tried))
                result["data"] = self._serialize_trace(trace, "compute", int(event_id))
            except Exception as exc:
                result["error"] = str(exc)

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    # ------------------------------------------------------------------
    # 2) pick-pixel / tex-stats
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_half(value: int) -> float:
        sign = -1.0 if (value & 0x8000) else 1.0
        exp = (value >> 10) & 0x1F
        mant = value & 0x3FF
        if exp == 0:
            if mant == 0:
                return 0.0 * sign
            return sign * (mant / 1024.0) * (2.0 ** -14)
        if exp == 31:
            return sign * 65504.0
        return sign * (1.0 + mant / 1024.0) * (2.0 ** (exp - 15))

    @staticmethod
    def _decode_r11g11b10(value: int) -> Tuple[float, float, float]:
        def ufloat(bits, mant_bits):
            exp = (bits >> mant_bits) & 0x1F
            mant = bits & ((1 << mant_bits) - 1)
            if exp == 0:
                return (mant / float(1 << mant_bits)) * (2.0 ** -14) if mant else 0.0
            if exp == 31:
                return 65504.0
            return (1.0 + mant / float(1 << mant_bits)) * (2.0 ** (exp - 15))

        r = ufloat(value & 0x7FF, 6)
        g = ufloat((value >> 11) & 0x7FF, 6)
        b = ufloat((value >> 22) & 0x3FF, 5)
        return r, g, b

    def _pixel_rgba_from_raw(self, raw_data: bytes, width: int, height: int, fmt: str, x: int, y: int):
        import struct

        if x < 0 or y < 0 or x >= width or y >= height:
            raise ValueError("Pixel out of range: (%d,%d) for %dx%d" % (x, y, width, height))

        bpp = self._resource._format_bpp(fmt.upper())
        if bpp <= 0:
            raise ValueError("Unsupported texture format for pick-pixel: %s" % fmt)

        expected_stride = width * bpp
        if height > 0 and len(raw_data) % height == 0:
            stride = max(expected_stride, len(raw_data) // height)
        else:
            stride = expected_stride

        off = y * stride + x * bpp
        fu = fmt.upper()

        if "B8G8R8A8" in fu or "BGRA8" in fu:
            b, g, r, a = raw_data[off: off + 4]
            return r / 255.0, g / 255.0, b / 255.0, a / 255.0
        if "R8G8B8A8" in fu or "RGBA8" in fu or "SRGB" in fu:
            r, g, b, a = raw_data[off: off + 4]
            return r / 255.0, g / 255.0, b / 255.0, a / 255.0
        if "R11G11B10" in fu:
            v = struct.unpack_from("<I", raw_data, off)[0]
            r, g, b = self._decode_r11g11b10(v)
            return r, g, b, 1.0
        if "R16" in fu and "FLOAT" in fu and bpp == 2:
            h = struct.unpack_from("<H", raw_data, off)[0]
            v = self._decode_half(h)
            return v, v, v, 1.0
        if "R32" in fu and "FLOAT" in fu and bpp == 4:
            v = struct.unpack_from("<f", raw_data, off)[0]
            return v, v, v, 1.0
        if bpp == 1:
            v = raw_data[off] / 255.0
            return v, v, v, 1.0

        # Generic fallback: map first up to 4 bytes to [0,1]
        px = raw_data[off: off + bpp]
        values = [c / 255.0 for c in px[:4]]
        while len(values) < 4:
            values.append(1.0 if len(values) == 3 else 0.0)
        return values[0], values[1], values[2], values[3]

    def pick_pixel(self, x, y, event_id=None, target=0):
        self._require_capture()
        result = {"data": None, "error": None}

        def callback(controller):
            try:
                if event_id is not None:
                    controller.SetFrameEvent(int(event_id), True)

                pipe = controller.GetPipelineState()
                targets = pipe.GetOutputTargets()
                bound = [rt.resourceId for rt in targets if rt.resourceId != rd.ResourceId.Null()]
                if not bound:
                    raise ValueError("No color render target bound")
                rid = bound[int(target)] if int(target) < len(bound) else bound[0]

                tex_desc = None
                for tex in controller.GetTextures():
                    if tex.resourceId == rid:
                        tex_desc = tex
                        break
                if tex_desc is None:
                    raise ValueError("Render target texture not found")

                sub = rd.Subresource()
                sub.mip = 0
                sub.slice = 0
                sub.sample = 0
                raw = bytes(controller.GetTextureData(rid, sub))
                r, g, b, a = self._pixel_rgba_from_raw(raw, tex_desc.width, tex_desc.height, str(tex_desc.format.Name()), int(x), int(y))
                result["data"] = {
                    "x": int(x),
                    "y": int(y),
                    "event_id": int(event_id) if event_id is not None else None,
                    "target": int(target),
                    "resource_id": str(rid),
                    "color": {"r": r, "g": g, "b": b, "a": a},
                }
            except Exception as exc:
                result["error"] = str(exc)

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def tex_stats(self, resource_id, mip=0, array_slice=0, histogram=False, event_id=None):
        self._require_capture()
        result = {"data": None, "error": None}

        def callback(controller):
            try:
                if event_id is not None:
                    controller.SetFrameEvent(int(event_id), True)

                tex_desc = self._find_texture_desc_by_str_id(controller, resource_id)
                if tex_desc is None:
                    raise ValueError("Texture not found: %s" % resource_id)

                if int(mip) < 0 or int(mip) >= int(tex_desc.mips):
                    raise ValueError("Invalid mip %s (mips=%s)" % (mip, tex_desc.mips))

                sub = rd.Subresource()
                sub.mip = int(mip)
                sub.slice = int(array_slice)
                sub.sample = 0

                width = max(1, int(tex_desc.width) >> int(mip))
                height = max(1, int(tex_desc.height) >> int(mip))
                fmt = str(tex_desc.format.Name())
                raw = bytes(controller.GetTextureData(tex_desc.resourceId, sub))

                mins = [1e30, 1e30, 1e30, 1e30]
                maxs = [-1e30, -1e30, -1e30, -1e30]
                hist = [[0, 0, 0, 0] for _ in range(256)] if histogram else None

                for py in range(height):
                    for px in range(width):
                        r, g, b, a = self._pixel_rgba_from_raw(raw, width, height, fmt, px, py)
                        vals = [r, g, b, a]
                        for i in range(4):
                            if vals[i] < mins[i]:
                                mins[i] = vals[i]
                            if vals[i] > maxs[i]:
                                maxs[i] = vals[i]
                            if hist is not None:
                                v = vals[i]
                                if v < 0.0:
                                    bucket = 0
                                elif v > 1.0:
                                    bucket = 255
                                else:
                                    bucket = int(v * 255.0 + 0.5)
                                if bucket < 0:
                                    bucket = 0
                                if bucket > 255:
                                    bucket = 255
                                hist[bucket][i] += 1

                data = {
                    "resource_id": resource_id,
                    "mip": int(mip),
                    "slice": int(array_slice),
                    "width": width,
                    "height": height,
                    "format": fmt,
                    "min": {"r": mins[0], "g": mins[1], "b": mins[2], "a": mins[3]},
                    "max": {"r": maxs[0], "g": maxs[1], "b": maxs[2], "a": maxs[3]},
                }
                if hist is not None:
                    data["histogram"] = [
                        {"bucket": i, "r": h[0], "g": h[1], "b": h[2], "a": h[3]}
                        for i, h in enumerate(hist)
                    ]
                result["data"] = data
            except Exception as exc:
                result["error"] = str(exc)

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    # ------------------------------------------------------------------
    # 3) VFS semantic interfaces
    # ------------------------------------------------------------------

    @staticmethod
    def _split_path(path: str) -> List[str]:
        p = (path or "/").strip()
        if not p.startswith("/"):
            p = "/" + p
        if p == "/":
            return []
        return [seg for seg in p.strip("/").split("/") if seg]

    @staticmethod
    def _child(name: str, kind: str, **extra) -> Dict[str, Any]:
        obj = {"name": name, "kind": kind}
        obj.update(extra)
        return obj

    def vfs_ls(self, path="/", long=False):
        self._require_capture()
        result = {"data": None, "error": None}
        parts = self._split_path(path)

        def callback(controller):
            try:
                if not parts:
                    children = [
                        self._child("capture", "dir"),
                        self._child("draws", "dir"),
                        self._child("resources", "dir"),
                    ]
                    result["data"] = {"path": "/", "kind": "dir", "children": children, "long": bool(long)}
                    return

                if parts[0] == "capture":
                    if len(parts) == 1:
                        children = [
                            self._child("info", "leaf_text"),
                            self._child("sections", "leaf_text"),
                            self._child("gpus", "leaf_text"),
                            self._child("thumbnail", "leaf_bin"),
                        ]
                        result["data"] = {"path": path, "kind": "dir", "children": children, "long": bool(long)}
                        return
                    result["data"] = {"path": path, "kind": "leaf_text", "children": []}
                    return

                if parts[0] == "draws":
                    root = controller.GetRootActions()
                    flat = Helpers.flatten_actions(root)
                    draws = [a for a in flat if a.flags & (rd.ActionFlags.Drawcall | rd.ActionFlags.Dispatch)]
                    if len(parts) == 1:
                        children = []
                        sfile = controller.GetStructuredFile()
                        for a in draws[:512]:
                            children.append(
                                self._child(
                                    str(a.eventId),
                                    "dir",
                                    event_id=int(a.eventId),
                                    name_full=a.GetName(sfile),
                                )
                            )
                        result["data"] = {"path": path, "kind": "dir", "children": children, "long": bool(long)}
                        return
                    if len(parts) == 2:
                        result["data"] = {
                            "path": path,
                            "kind": "dir",
                            "children": [
                                self._child("detail", "leaf_text"),
                                self._child("pipeline", "leaf_text"),
                                self._child("pick", "leaf_text"),
                            ],
                            "long": bool(long),
                        }
                        return
                    result["data"] = {"path": path, "kind": "leaf_text", "children": []}
                    return

                if parts[0] == "resources":
                    textures = controller.GetTextures()
                    if len(parts) == 1:
                        children = [
                            self._child(str(t.resourceId), "dir", width=int(t.width), height=int(t.height), format=str(t.format.Name()))
                            for t in textures[:512]
                        ]
                        result["data"] = {"path": path, "kind": "dir", "children": children, "long": bool(long)}
                        return
                    if len(parts) == 2:
                        result["data"] = {
                            "path": path,
                            "kind": "dir",
                            "children": [
                                self._child("info", "leaf_text"),
                                self._child("stats", "leaf_text"),
                                self._child("thumbnail", "leaf_bin"),
                            ],
                            "long": bool(long),
                        }
                        return
                    result["data"] = {"path": path, "kind": "leaf_text", "children": []}
                    return

                raise ValueError("Path not found: %s" % path)
            except Exception as exc:
                result["error"] = str(exc)

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def vfs_cat(self, path):
        parts = self._split_path(path)
        if not parts:
            raise ValueError("Cannot cat root path")

        if parts[0] == "capture":
            if len(parts) == 2 and parts[1] == "info":
                return self._capture.get_capture_info()
            if len(parts) == 2 and parts[1] == "sections":
                return self.capture_sections()
            if len(parts) == 2 and parts[1] == "gpus":
                return self.capture_gpus()
            if len(parts) == 2 and parts[1] == "thumbnail":
                return self.capture_thumbnail(0)

        if parts[0] == "draws" and len(parts) >= 3:
            event_id = int(parts[1])
            leaf = parts[2]
            if leaf == "detail":
                return self._action.get_draw_call_details(event_id)
            if leaf == "pipeline":
                return self._pipeline.get_pipeline_state(event_id)
            if leaf == "pick":
                # Center pixel of RTV0 as default probe.
                p = self.pick_pixel(0, 0, event_id, 0)
                return p

        if parts[0] == "resources" and len(parts) >= 3:
            resource_id = parts[1]
            leaf = parts[2]
            if leaf == "info":
                return self._resource.get_texture_info(resource_id)
            if leaf == "stats":
                return self.tex_stats(resource_id, 0, 0, False, None)
            if leaf == "thumbnail":
                return self._resource.get_texture_thumbnail(resource_id)

        raise ValueError("Path not found or not a leaf: %s" % path)

    def vfs_tree(self, path="/", depth=2):
        depth = int(depth)
        if depth < 1:
            depth = 1

        def build(node_path: str, d: int):
            info = self.vfs_ls(node_path)
            if info.get("kind") != "dir":
                return {"path": node_path, "kind": info.get("kind", "leaf")}
            children = []
            if d > 0:
                for c in info.get("children", []):
                    child_path = (node_path.rstrip("/") + "/" + c["name"]).replace("//", "/")
                    if c.get("kind") == "dir":
                        children.append(build(child_path, d - 1))
                    else:
                        children.append({"path": child_path, "kind": c.get("kind", "leaf")})
            return {"path": node_path, "kind": "dir", "children": children}

        return {"path": path, "depth": depth, "tree": build(path, depth)}

    # ------------------------------------------------------------------
    # 4) Exports: mesh / snapshot
    # ------------------------------------------------------------------

    def mesh_data(self, event_id=None, stage="vs-out"):
        self._require_capture()
        result = {"data": None, "error": None}

        def callback(controller):
            try:
                if event_id is not None:
                    controller.SetFrameEvent(int(event_id), True)

                action = self.ctx.CurAction()
                if action is None:
                    raise ValueError("No current action")

                # Try RenderDoc post-VS path when available.
                get_post_vs = getattr(controller, "GetPostVSData", None)
                if get_post_vs is None:
                    raise ValueError("GetPostVSData is unavailable in this RenderDoc build")

                stage_map = {
                    "vs-out": getattr(rd.MeshDataStage, "VSOut", None),
                    "gs-out": getattr(rd.MeshDataStage, "GSOut", None),
                }
                stage_enum = stage_map.get(str(stage).lower())
                if stage_enum is None:
                    raise ValueError("Unsupported mesh stage: %s" % stage)

                mesh = get_post_vs(0, 0, stage_enum)
                if mesh is None:
                    raise ValueError("GetPostVSData returned no mesh data")

                # Best-effort extraction. Different versions expose slightly different fields.
                vertex_count = int(getattr(mesh, "numVerts", 0) or getattr(mesh, "numVertices", 0) or 0)
                if vertex_count <= 0:
                    vertex_count = int(action.numIndices or action.numInstances or 0)

                topology = str(getattr(mesh, "topology", "Unknown"))
                vertices = []
                indices = []

                # Try to parse position data from vertex resource.
                vbuf = getattr(mesh, "vertexResourceId", rd.ResourceId.Null())
                stride = int(getattr(mesh, "vertexByteStride", 0) or 0)
                if vbuf != rd.ResourceId.Null() and stride > 0:
                    raw = bytes(controller.GetBufferData(vbuf, 0, 0))
                    count = min(vertex_count, len(raw) // stride)
                    import struct
                    for i in range(count):
                        base = i * stride
                        if base + 12 <= len(raw):
                            x, y, z = struct.unpack_from("<fff", raw, base)
                            vertices.append([x, y, z, 1.0])

                ibuf = getattr(mesh, "indexResourceId", rd.ResourceId.Null())
                ibytes = int(getattr(mesh, "indexByteStride", 0) or 0)
                if ibuf != rd.ResourceId.Null() and ibytes in (2, 4):
                    raw_i = bytes(controller.GetBufferData(ibuf, 0, 0))
                    import struct
                    if ibytes == 2:
                        indices = [v[0] for v in struct.iter_unpack("<H", raw_i)]
                    else:
                        indices = [v[0] for v in struct.iter_unpack("<I", raw_i)]

                result["data"] = {
                    "eid": int(action.eventId),
                    "stage": str(stage).lower(),
                    "topology": topology,
                    "vertex_count": len(vertices) if vertices else vertex_count,
                    "vertices": vertices,
                    "indices": indices,
                }
            except Exception as exc:
                result["error"] = str(exc)

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def snapshot_export(self, event_id, output_dir):
        """Export a compact snapshot bundle for one event."""
        self._require_capture()
        out_dir = os.path.abspath(output_dir)
        os.makedirs(out_dir, exist_ok=True)

        files = []

        pipeline = self._pipeline.get_pipeline_state(int(event_id))
        pipeline_file = os.path.join(out_dir, "pipeline.json")
        with open(pipeline_file, "w", encoding="utf-8") as f:
            json.dump(pipeline, f, indent=2, ensure_ascii=False)
            f.write("\n")
        files.append("pipeline.json")

        # Try to include shader source text when available.
        for stage in ("vertex", "pixel", "compute"):
            try:
                src = self._pipeline.get_shader_source(int(event_id), stage)
                text = src.get("source") if isinstance(src, dict) else None
                if text:
                    name = "shader_%s.txt" % stage
                    with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
                        f.write(text)
                    files.append(name)
            except Exception:
                pass

        # Add color/depth thumbnails.
        try:
            color_path = os.path.join(out_dir, "color0.png")
            self._resource.get_render_target_thumbnail(int(event_id), 0, False, 1024, color_path)
            files.append("color0.png")
        except Exception:
            pass

        try:
            depth_path = os.path.join(out_dir, "depth.png")
            self._resource.get_render_target_thumbnail(int(event_id), 0, True, 1024, depth_path)
            files.append("depth.png")
        except Exception:
            pass

        manifest = {
            "eid": int(event_id),
            "output_dir": out_dir,
            "files": files,
        }
        with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
            f.write("\n")

        return manifest

    # ------------------------------------------------------------------
    # 5) Capture-file style queries
    # ------------------------------------------------------------------

    def capture_sections(self):
        self._require_capture()
        result = {"data": None, "error": None}

        def callback(controller):
            try:
                sfile = controller.GetStructuredFile()
                sections = []
                if sfile is not None:
                    chunks = getattr(sfile, "chunks", [])
                    count = len(chunks)
                    for i in range(count):
                        c = chunks[i]
                        sections.append(
                            {
                                "index": i,
                                "name": getattr(c, "name", ""),
                                "type": str(getattr(c, "type", "")),
                                "uncompressedSize": int(getattr(c, "length", 0) or 0),
                            }
                        )
                result["data"] = {"sections": sections}
            except Exception as exc:
                result["error"] = str(exc)

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def capture_section_content(self, name):
        sec = self.capture_sections()
        target = None
        for s in sec.get("sections", []):
            if s.get("name") == name:
                target = s
                break
        if target is None:
            raise ValueError("Section not found: %s" % name)
        return {
            "name": name,
            "contents": json.dumps(target, ensure_ascii=False),
        }

    def capture_gpus(self):
        self._require_capture()
        result = {"data": None, "error": None}

        def callback(controller):
            try:
                props = controller.GetAPIProperties()
                gpu_name = str(getattr(props, "vendor", ""))
                result["data"] = {
                    "gpus": [
                        {
                            "name": gpu_name or "Unknown GPU",
                            "vendor": str(getattr(props, "vendor", "unknown")),
                            "driver": str(getattr(props, "localRenderer", "unknown")),
                        }
                    ]
                }
            except Exception as exc:
                result["error"] = str(exc)

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def capture_thumbnail(self, max_size=0):
        self._require_capture()

        # Reuse first actionable event's RT thumbnail as a capture preview.
        root = self._action.get_draw_calls(include_children=True).get("actions", [])
        event_id = None

        def pick_first(actions):
            nonlocal event_id
            for a in actions:
                flags = set(a.get("flags", []))
                if "Drawcall" in flags or "Dispatch" in flags:
                    event_id = int(a.get("event_id", 0))
                    return
                if a.get("children"):
                    pick_first(a["children"])
                if event_id is not None:
                    return

        pick_first(root)
        if event_id is None:
            raise ValueError("No drawable event found for capture thumbnail")

        thumb = self._resource.get_render_target_thumbnail(
            event_id=event_id,
            rtv_index=0,
            depth=False,
            max_size=int(max_size) if int(max_size) > 0 else 512,
            output_path=None,
        )
        data_b64 = thumb.get("thumbnail_base64")
        if not data_b64:
            raise ValueError("Thumbnail generation failed")
        return {
            "event_id": event_id,
            "width": thumb.get("width"),
            "height": thumb.get("height"),
            "data": data_b64,
        }

    def callstack_resolve(self, event_id=None):
        self._require_capture()
        eid = int(event_id) if event_id is not None else 0
        # RenderDoc python API callstack availability varies by backend/build.
        # Return stable shape and include capability hint.
        return {
            "eid": eid,
            "frames": [],
            "supported": False,
            "message": "Callstack resolving is unavailable in current extension build/API surface",
        }
