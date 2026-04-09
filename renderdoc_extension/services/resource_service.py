"""
Resource information service for RenderDoc.
"""

import base64

import renderdoc as rd

from ..utils import Parsers, Helpers


class ResourceService:
    """Resource information service"""

    def __init__(self, ctx, invoke_fn):
        self.ctx = ctx
        self._invoke = invoke_fn

    def _find_texture_by_id(self, controller, resource_id):
        """Find texture by resource ID."""
        target_id = Parsers.extract_numeric_id(resource_id)
        for tex in controller.GetTextures():
            tex_id_str = str(tex.resourceId)
            tex_id = Parsers.extract_numeric_id(tex_id_str)
            if tex_id == target_id:
                return tex
        return None

    def get_buffer_contents(self, resource_id, offset=0, length=0):
        """Get buffer data."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"data": None, "error": None}

        def callback(controller):
            # Parse resource ID
            try:
                rid = Parsers.parse_resource_id(resource_id)
            except Exception as exc:
                result["error"] = (
                    "Invalid resource_id '%s'. Expected formats like 'ResourceId::1234'. "
                    "Parse error: %s" % (resource_id, str(exc))
                )
                return

            # Find buffer (robust across API wrappers: compare numeric IDs)
            buf_desc = None
            target_num = Parsers.extract_numeric_id(str(resource_id))
            for buf in controller.GetBuffers():
                try:
                    buf_num = Parsers.extract_numeric_id(str(buf.resourceId))
                except Exception:
                    continue
                if buf_num == target_num:
                    buf_desc = buf
                    rid = buf.resourceId
                    break

            if not buf_desc:
                result["error"] = (
                    "Buffer not found for resource_id '%s'. "
                    "Verify the resource belongs to a buffer in current capture."
                    % resource_id
                )
                return

            total_size = int(buf_desc.length)
            req_offset = int(offset)
            req_length = int(length)

            if req_offset < 0:
                result["error"] = "offset must be >= 0, got %d" % req_offset
                return
            if req_length < 0:
                result["error"] = "length must be >= 0, got %d" % req_length
                return
            if req_offset > total_size:
                result["error"] = (
                    "offset out of range: offset=%d > buffer_size=%d "
                    "(resource_id=%s)" % (req_offset, total_size, resource_id)
                )
                return

            remaining = total_size - req_offset
            actual_length = remaining if req_length == 0 else req_length

            if actual_length > remaining:
                result["error"] = (
                    "Requested range exceeds buffer size: offset=%d, length=%d, "
                    "buffer_size=%d, max_readable=%d (resource_id=%s)"
                    % (req_offset, req_length, total_size, remaining, resource_id)
                )
                return

            try:
                data = controller.GetBufferData(rid, req_offset, actual_length)
            except Exception as exc:
                result["error"] = (
                    "Failed to read buffer data: resource_id=%s, offset=%d, length=%d. "
                    "RenderDoc error: %s"
                    % (resource_id, req_offset, actual_length, str(exc))
                )
                return

            result["data"] = {
                "resource_id": resource_id,
                "length": len(data),
                "total_size": total_size,
                "offset": req_offset,
                "requested_length": req_length,
                "content_base64": base64.b64encode(data).decode("ascii"),
            }

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]


    def get_texture_info(self, resource_id):
        """Get texture metadata"""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"texture": None, "error": None}

        def callback(controller):
            try:
                tex_desc = self._find_texture_by_id(controller, resource_id)

                if not tex_desc:
                    result["error"] = "Texture not found: %s" % resource_id
                    return

                result["texture"] = {
                    "resource_id": resource_id,
                    "width": tex_desc.width,
                    "height": tex_desc.height,
                    "depth": tex_desc.depth,
                    "array_size": tex_desc.arraysize,
                    "mip_levels": tex_desc.mips,
                    "format": str(tex_desc.format.Name()),
                    "dimension": str(tex_desc.type),
                    "msaa_samples": tex_desc.msSamp,
                    "byte_size": tex_desc.byteSize,
                }
            except Exception as e:
                import traceback
                result["error"] = "Error: %s\n%s" % (str(e), traceback.format_exc())

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["texture"]



    def get_texture_thumbnail(self, resource_id, max_size=256, output_path=None):
        """Get a PNG thumbnail of a texture.

        Uses GetTextureData + pure-Python PNG encoder with format-aware
        pixel decoding for correct color output on all texture formats.

        Args:
            resource_id: The texture resource ID string.
            max_size: Maximum width/height of the thumbnail (default 256).
            output_path: If provided, save PNG to this path instead of base64.

        Returns:
            dict with resource_id, width, height, format, and either
            output_path (file saved) or thumbnail_base64 (PNG bytes).
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"data": None, "error": None}

        def callback(controller):
            tex_desc = self._find_texture_by_id(controller, resource_id)
            if not tex_desc:
                result["error"] = "Texture not found: %s" % resource_id
                return

            sub = rd.Subresource()
            sub.mip = 0
            sub.slice = 0
            sub.sample = 0

            try:
                data = controller.GetTextureData(tex_desc.resourceId, sub)
            except Exception as e:
                result["error"] = "Failed to get texture data: %s" % str(e)
                return

            width = tex_desc.width
            height = tex_desc.height
            fmt = str(tex_desc.format.Name())

            png_bytes = self._raw_to_png_bytes(data, width, height, fmt, max_size)

            info = {
                "resource_id": resource_id,
                "width": width,
                "height": height,
                "format": fmt,
                "max_size": max_size,
            }

            if output_path:
                try:
                    with open(output_path, "wb") as f:
                        f.write(png_bytes)
                    info["output_path"] = output_path
                    info["saved"] = True
                except Exception as e:
                    result["error"] = "Failed to save thumbnail: %s" % str(e)
                    return
            else:
                info["thumbnail_base64"] = base64.b64encode(png_bytes).decode("ascii")

            result["data"] = info

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def get_render_target_thumbnail(self, event_id, rtv_index=0, depth=False,
                                     max_size=256, output_path=None):
        """Get a PNG thumbnail of a render target at a specific event.

        Uses two BlockInvoke calls:
        1. Lightweight: SetFrameEvent + GetPipelineState to find the RT id
        2. Delegates to get_texture_thumbnail for pixel read + PNG encoding

        Args:
            event_id: The event ID to capture the render target from.
            rtv_index: Which RenderTargetView to read (default 0).
            depth: If True, read the depth buffer instead of a color RTV.
            max_size: Maximum width/height of the thumbnail (default 256).
            output_path: If provided, save PNG to this path.

        Returns:
            dict with event_id, resource_id, width, height, format, rtv_index,
            and either output_path or thumbnail_base64.
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        # Step 1: find the RT resource_id (lightweight, no GetTextures)
        rt_info = {"resource_id": None, "actual_index": rtv_index, "error": None}

        def find_rt(controller):
            controller.SetFrameEvent(int(event_id), True)
            pipe = controller.GetPipelineState()
            try:
                if depth:
                    dt = pipe.GetDepthTarget()
                    if dt.resourceId != rd.ResourceId.Null():
                        rt_info["resource_id"] = str(dt.resourceId)
                        rt_info["actual_index"] = -1
                else:
                    targets = pipe.GetOutputTargets()
                    bound_rts = []
                    for rt in targets:
                        if rt.resourceId != rd.ResourceId.Null():
                            bound_rts.append(str(rt.resourceId))
                    if rtv_index < len(bound_rts):
                        rt_info["resource_id"] = bound_rts[rtv_index]
                    elif bound_rts:
                        rt_info["resource_id"] = bound_rts[0]
                        rt_info["actual_index"] = 0
            except Exception as e:
                import traceback
                rt_info["error"] = "GetOutputTargets() raised: %s\n%s" % (str(e), traceback.format_exc())
                return

            if rt_info["resource_id"] is None:
                kind = "depth target" if depth else "render target (index %d)" % rtv_index
                rt_info["error"] = "No %s bound at event %d" % (kind, event_id)

        self._invoke(find_rt)

        if rt_info["error"]:
            raise ValueError(rt_info["error"])

        # Step 2: reuse get_texture_thumbnail (its own BlockInvoke)
        result = self.get_texture_thumbnail(
            rt_info["resource_id"], max_size, output_path
        )

        # Enrich with render-target metadata
        result["event_id"] = event_id
        result["rtv_index"] = rt_info["actual_index"]
        result["depth"] = depth
        return result

    @staticmethod
    def _format_bpp(fmt_upper):
        """Return bytes-per-pixel for known texture formats (uppercase name).

        Returns 0 for unrecognised formats so the caller can fall back.
        """
        # 1 byte per pixel
        if "R8_" in fmt_upper or fmt_upper == "R8" or fmt_upper.startswith("R8_"):
            return 1
        # 2 bytes per pixel
        if ("R16" in fmt_upper and "G16" not in fmt_upper):
            return 2
        if "R8G8" in fmt_upper and "B8" not in fmt_upper:
            return 2
        # 4 bytes per pixel
        if "R11G11B10" in fmt_upper:
            return 4
        if "R10G10B10A2" in fmt_upper or "B10G10R10A2" in fmt_upper:
            return 4
        if "R8G8B8A8" in fmt_upper or "B8G8R8A8" in fmt_upper:
            return 4
        if "RGBA8" in fmt_upper or "BGRA8" in fmt_upper:
            return 4
        if "SRGB" in fmt_upper and "16" not in fmt_upper and "32" not in fmt_upper:
            return 4
        if "D24" in fmt_upper:
            return 4
        if "R32_" in fmt_upper or fmt_upper == "R32" or "R32_FLOAT" in fmt_upper:
            return 4
        if "R16G16_" in fmt_upper or "R16G16B16A16" not in fmt_upper and "R16G16" in fmt_upper:
            return 4
        if "D32" in fmt_upper and "S8" not in fmt_upper:
            return 4
        # 8 bytes per pixel
        if "R16G16B16A16" in fmt_upper:
            return 8
        if "R32G32" in fmt_upper and "B32" not in fmt_upper:
            return 8
        if "D32_FLOAT_S8" in fmt_upper or ("D32" in fmt_upper and "S8" in fmt_upper):
            return 8
        # 12 bytes per pixel
        if "R32G32B32_" in fmt_upper and "A32" not in fmt_upper:
            return 12
        # 16 bytes per pixel
        if "R32G32B32A32" in fmt_upper:
            return 16
        # BC compressed — not really pixel-addressable; return 0 so the caller
        # falls back to the data-size heuristic.
        if fmt_upper.startswith("BC"):
            return 0
        return 0

    def _raw_to_png_bytes(self, raw_data, width, height, fmt, max_size):
        """Convert raw texture data to minimal PNG bytes.

        Optimized: only decodes pixels needed for the output size.
        Uses Reinhard tone mapping for HDR formats (R11G11B10, float formats).
        Supports R11G11B10_FLOAT, RGBA8, BGRA8, R16F, R16G16B16A16F, R32F,
        R32G32B32A32F, D24S8, R8, and falls back to gray for unknown formats.
        """
        import struct
        import zlib

        # Ensure raw_data is bytes (RenderDoc may return a custom buffer type)
        if not isinstance(raw_data, (bytes, bytearray)):
            raw_data = bytes(raw_data)

        fmt_upper = fmt.upper()
        total_pixels = width * height

        # Determine bytes-per-pixel from the format name, NOT from data size.
        # RenderDoc's GetTextureData may return rows with padding (row pitch
        # != width * bpp), so dividing total bytes by total pixels gives a
        # wrong bpp when there is per-row alignment padding.
        bpp = self._format_bpp(fmt_upper)
        if bpp == 0:
            # Fallback: guess from data size (legacy path)
            bpp = len(raw_data) // total_pixels if total_pixels > 0 else 0

        # Compute output dimensions
        out_w, out_h = width, height
        if max_size > 0 and (width > max_size or height > max_size):
            scale = min(max_size / float(width), max_size / float(height))
            out_w = max(1, int(width * scale))
            out_h = max(1, int(height * scale))

        # Pre-compute sampling map
        src_ys = [int(y * height / out_h) for y in range(out_h)]
        src_xs = [int(x * width / out_w) for x in range(out_w)]

        # Determine format decoder type
        is_r11g11b10 = bpp == 4 and "R11G11B10" in fmt_upper
        is_d24 = bpp == 4 and "D24" in fmt_upper
        is_rgba8 = (bpp == 4 and not is_r11g11b10 and not is_d24
                    and ("RGBA" in fmt_upper or "SRGB" in fmt_upper)
                    and "FLOAT" not in fmt_upper)
        is_bgra8 = bpp == 4 and "BGRA" in fmt_upper and "FLOAT" not in fmt_upper
        is_r16f = bpp == 2 and "FLOAT" in fmt_upper
        is_rgba16f = bpp == 8 and "16" in fmt_upper and "FLOAT" in fmt_upper
        is_rgba32f = bpp == 16 and "32" in fmt_upper and "FLOAT" in fmt_upper
        is_r8 = bpp == 1
        # Whether tone mapping is needed (HDR float formats)
        is_hdr = is_r11g11b10 or is_r16f or is_rgba16f or is_rgba32f

        # Pre-compiled struct unpackers
        _unpack_I = struct.Struct("<I").unpack_from
        _unpack_H = struct.Struct("<H").unpack_from
        _unpack_4H = struct.Struct("<HHHH").unpack_from
        _unpack_4f = struct.Struct("<ffff").unpack_from

        # Reinhard tone mapping: HDR linear -> [0,1] sRGB
        # tone(x) = x / (1 + x), then gamma correct with pow(x, 1/2.2)
        # Pre-build a lookup table for speed (256 entries covering 0..16 range)
        if is_hdr:
            _tm_steps = 4096
            _tm_max = 64.0  # max HDR value we handle
            _tm_lut = bytearray(_tm_steps)
            for i in range(_tm_steps):
                v = (i / float(_tm_steps - 1)) * _tm_max
                # Reinhard
                mapped = v / (1.0 + v)
                # Gamma 2.2
                if mapped > 0.0:
                    mapped = mapped ** (1.0 / 2.2)
                iv = int(mapped * 255.0 + 0.5)
                _tm_lut[i] = min(255, max(0, iv))
            _tm_scale = float(_tm_steps - 1) / _tm_max

            def _tone(fval):
                """Tone map a float HDR value to 0-255 byte."""
                if fval <= 0.0:
                    return 0
                if fval >= _tm_max:
                    return 255
                return _tm_lut[int(fval * _tm_scale)]
        else:
            def _tone(fval):
                v = int(fval * 255.0 + 0.5)
                if v < 0:
                    return 0
                if v > 255:
                    return 255
                return v

        # Build rows - only decode sampled pixels
        rows = []
        raw = raw_data

        # Compute actual row stride (row pitch) from data size.
        # RenderDoc may pad each row to a 256-byte or other alignment boundary.
        # expected = width * bpp (no padding). If data is larger, derive the
        # real stride by dividing total data length by height.
        expected_stride = width * bpp
        if height > 0 and len(raw_data) > 0:
            actual_stride = len(raw_data) // height
            # Sanity check: actual stride should be >= expected and a whole number
            if actual_stride >= expected_stride and (len(raw_data) % height) == 0:
                stride = actual_stride
            else:
                stride = expected_stride
        else:
            stride = expected_stride

        for oy in range(out_h):
            sy = src_ys[oy]
            row_off = sy * stride
            buf = bytearray(1 + out_w * 4)
            # buf[0] = 0 already (PNG filter None)
            wi = 1

            for ox in range(out_w):
                sx = src_xs[ox]
                off = row_off + sx * bpp

                if is_r11g11b10:
                    val = _unpack_I(raw, off)[0]
                    # R: bits 0-10 (11-bit unsigned float: 5e6m)
                    r_bits = val & 0x7FF
                    r_e = (r_bits >> 6) & 0x1F
                    r_m = r_bits & 0x3F
                    if r_e == 0:
                        rf = (r_m / 64.0) * (2.0 ** -14) if r_m else 0.0
                    elif r_e == 31:
                        rf = 65504.0
                    else:
                        rf = (1.0 + r_m / 64.0) * (2.0 ** (r_e - 15))
                    # G: bits 11-21 (11-bit)
                    g_bits = (val >> 11) & 0x7FF
                    g_e = (g_bits >> 6) & 0x1F
                    g_m = g_bits & 0x3F
                    if g_e == 0:
                        gf = (g_m / 64.0) * (2.0 ** -14) if g_m else 0.0
                    elif g_e == 31:
                        gf = 65504.0
                    else:
                        gf = (1.0 + g_m / 64.0) * (2.0 ** (g_e - 15))
                    # B: bits 22-31 (10-bit: 5e5m)
                    b_bits = (val >> 22) & 0x3FF
                    b_e = (b_bits >> 5) & 0x1F
                    b_m = b_bits & 0x1F
                    if b_e == 0:
                        bf = (b_m / 32.0) * (2.0 ** -14) if b_m else 0.0
                    elif b_e == 31:
                        bf = 65504.0
                    else:
                        bf = (1.0 + b_m / 32.0) * (2.0 ** (b_e - 15))
                    buf[wi] = _tone(rf)
                    buf[wi + 1] = _tone(gf)
                    buf[wi + 2] = _tone(bf)
                    buf[wi + 3] = 255

                elif is_rgba8:
                    buf[wi] = raw[off]
                    buf[wi + 1] = raw[off + 1]
                    buf[wi + 2] = raw[off + 2]
                    buf[wi + 3] = raw[off + 3]

                elif is_bgra8:
                    buf[wi] = raw[off + 2]
                    buf[wi + 1] = raw[off + 1]
                    buf[wi + 2] = raw[off]
                    buf[wi + 3] = raw[off + 3]

                elif is_d24:
                    d24 = _unpack_I(raw, off)[0] & 0x00FFFFFF
                    v = int(d24 * 1.5259021896696422e-05 + 0.5)
                    if v > 255:
                        v = 255
                    buf[wi] = v
                    buf[wi + 1] = v
                    buf[wi + 2] = v
                    buf[wi + 3] = 255

                elif is_r16f:
                    h = _unpack_H(raw, off)[0]
                    e = (h >> 10) & 0x1F
                    m = h & 0x3FF
                    if e == 0:
                        fv = (m / 1024.0) * (2.0 ** -14) if m else 0.0
                    elif e == 31:
                        fv = 65504.0
                    else:
                        fv = (1.0 + m / 1024.0) * (2.0 ** (e - 15))
                    if h & 0x8000:
                        fv = -fv
                    v = _tone(fv)
                    buf[wi] = v
                    buf[wi + 1] = v
                    buf[wi + 2] = v
                    buf[wi + 3] = 255

                elif is_rgba16f:
                    rh, gh, bh, ah = _unpack_4H(raw, off)
                    for i, h in enumerate((rh, gh, bh, ah)):
                        e = (h >> 10) & 0x1F
                        m = h & 0x3FF
                        if e == 0:
                            fv = (m / 1024.0) * (2.0 ** -14) if m else 0.0
                        elif e == 31:
                            fv = 65504.0
                        else:
                            fv = (1.0 + m / 1024.0) * (2.0 ** (e - 15))
                        if h & 0x8000:
                            fv = -fv
                        if i == 3:
                            # Alpha: just linear clamp, no tone map
                            v = int(fv * 255.0 + 0.5)
                            buf[wi + i] = min(255, max(0, v))
                        else:
                            buf[wi + i] = _tone(fv)

                elif is_rgba32f:
                    rf, gf, bf, af = _unpack_4f(raw, off)
                    buf[wi] = _tone(rf)
                    buf[wi + 1] = _tone(gf)
                    buf[wi + 2] = _tone(bf)
                    av = int(af * 255.0 + 0.5)
                    buf[wi + 3] = min(255, max(0, av))

                elif is_r8:
                    v = raw[off]
                    buf[wi] = v
                    buf[wi + 1] = v
                    buf[wi + 2] = v
                    buf[wi + 3] = 255

                else:
                    buf[wi] = 128
                    buf[wi + 1] = 128
                    buf[wi + 2] = 128
                    buf[wi + 3] = 255

                wi += 4

            rows.append(bytes(buf))

        raw_png_data = b"".join(rows)

        # Build minimal PNG file
        def _png_chunk(chunk_type, data):
            chunk = chunk_type + data
            crc = struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
            return struct.pack(">I", len(data)) + chunk + crc

        signature = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", out_w, out_h, 8, 6, 0, 0, 0)
        ihdr = _png_chunk(b"IHDR", ihdr_data)
        compressed = zlib.compress(raw_png_data)
        idat = _png_chunk(b"IDAT", compressed)
        iend = _png_chunk(b"IEND", b"")

        return signature + ihdr + idat + iend

    def get_texture_data(self, resource_id, mip=0, slice=0, sample=0,
                         depth_slice=None, output_path=None):
        """Get texture pixel data.

        If output_path is provided, saves raw data to a binary file instead
        of returning base64 (avoids JSON bloat for large textures).

        Args:
            resource_id: The texture resource ID string.
            mip: Mip level (default 0).
            slice: Array slice (default 0).
            sample: MSAA sample (default 0).
            depth_slice: For 3D textures, a specific depth slice.
            output_path: If provided, save raw bytes to this file.
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"data": None, "error": None}

        def callback(controller):
            tex_desc = self._find_texture_by_id(controller, resource_id)

            if not tex_desc:
                result["error"] = "Texture not found: %s" % resource_id
                return

            # Validate mip level
            if mip < 0 or mip >= tex_desc.mips:
                result["error"] = "Invalid mip level %d (texture has %d mips)" % (
                    mip,
                    tex_desc.mips,
                )
                return

            # Validate slice for array/cube textures
            max_slices = tex_desc.arraysize
            if tex_desc.cubemap:
                max_slices = tex_desc.arraysize * 6
            if slice < 0 or (max_slices > 1 and slice >= max_slices):
                result["error"] = "Invalid slice %d (texture has %d slices)" % (
                    slice,
                    max_slices,
                )
                return

            # Validate sample for MSAA
            if sample < 0 or (tex_desc.msSamp > 1 and sample >= tex_desc.msSamp):
                result["error"] = "Invalid sample %d (texture has %d samples)" % (
                    sample,
                    tex_desc.msSamp,
                )
                return

            # Calculate dimensions at this mip level
            mip_width = max(1, tex_desc.width >> mip)
            mip_height = max(1, tex_desc.height >> mip)
            mip_depth = max(1, tex_desc.depth >> mip)

            # Validate depth_slice for 3D textures
            is_3d = tex_desc.depth > 1
            if depth_slice is not None:
                if not is_3d:
                    result["error"] = "depth_slice can only be used with 3D textures"
                    return
                if depth_slice < 0 or depth_slice >= mip_depth:
                    result["error"] = "Invalid depth_slice %d (texture has %d depth at mip %d)" % (
                        depth_slice,
                        mip_depth,
                        mip,
                    )
                    return

            # Create subresource specification
            sub = rd.Subresource()
            sub.mip = mip
            sub.slice = slice
            sub.sample = sample

            # Get texture data
            try:
                data = controller.GetTextureData(tex_desc.resourceId, sub)
            except Exception as e:
                result["error"] = "Failed to get texture data: %s" % str(e)
                return

            # Extract depth slice for 3D textures if requested
            output_depth = mip_depth
            if is_3d and depth_slice is not None:
                total_size = len(data)
                bytes_per_slice = total_size // mip_depth
                slice_start = depth_slice * bytes_per_slice
                slice_end = slice_start + bytes_per_slice
                data = data[slice_start:slice_end]
                output_depth = 1

            info = {
                "resource_id": resource_id,
                "width": mip_width,
                "height": mip_height,
                "depth": output_depth,
                "mip": mip,
                "slice": slice,
                "sample": sample,
                "depth_slice": depth_slice,
                "format": str(tex_desc.format.Name()),
                "dimension": str(tex_desc.type),
                "is_3d": is_3d,
                "total_depth": mip_depth if is_3d else 1,
                "data_length": len(data),
            }

            if output_path:
                try:
                    with open(output_path, "wb") as f:
                        f.write(bytes(data))
                    info["output_path"] = output_path
                    info["saved"] = True
                except Exception as e:
                    result["error"] = "Failed to save data: %s" % str(e)
                    return
            else:
                info["content_base64"] = base64.b64encode(bytes(data)).decode("ascii")

            result["data"] = info

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def get_render_target_diff(self, event_id, compare_event_id=None,
                               rtv_index=0, depth=False, threshold=0,
                               max_size=512, output_path=None):
        """Get pixel-level render target diff between two events.

        Replays to *compare_event_id* (baseline) and *event_id* (target),
        reads the same bound RT, computes per-pixel difference, and returns
        a magenta diff-mask image plus statistics.

        Args:
            event_id: Target event ID (the current draw call).
            compare_event_id: Baseline event ID.  When None, automatically
                finds the previous draw call / dispatch / clear in the
                action tree (not simply event_id - 1).
            rtv_index: Which color RTV to compare (default 0).
            depth: If True, compare the depth buffer instead of a color RTV.
            threshold: Per-byte diff threshold (0-255). Pixels with all
                       channel diffs <= threshold are treated as unchanged.
            max_size: Maximum width/height of the diff mask (default 512).
            output_path: Optional file path to save the diff mask PNG.

        Returns:
            dict with event_id, compare_event_id, resource_id,
            changed_pixels, total_pixels, change_percentage,
            bounding_box, and either output_path or diff_base64.
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        event_id = int(event_id)
        if compare_event_id is not None:
            compare_event_id = int(compare_event_id)
        # NOTE: when compare_event_id is None, we resolve it inside the
        # callback by walking the action tree to find the previous draw call.

        result = {"data": None, "error": None}

        def callback(controller):
            import struct
            import traceback as _tb

            nonlocal compare_event_id

            # --- Step 0: resolve compare_event_id if not provided ---
            if compare_event_id is None:
                try:
                    root_actions = controller.GetRootActions()
                    all_actions = Helpers.flatten_actions(root_actions)
                    # Filter to actual draw/dispatch/clear/copy actions
                    # (anything that may write to a render target)
                    draw_actions = [
                        a for a in all_actions
                        if a.flags & (
                            rd.ActionFlags.Drawcall
                            | rd.ActionFlags.Dispatch
                            | rd.ActionFlags.Clear
                            | rd.ActionFlags.Copy
                            | rd.ActionFlags.Resolve
                        )
                    ]
                    # Find the target event's index, then pick the one before it
                    prev_eid = None
                    for i, a in enumerate(draw_actions):
                        if a.eventId == event_id:
                            if i > 0:
                                prev_eid = draw_actions[i - 1].eventId
                            break
                        elif a.eventId > event_id:
                            # event_id is between two actions; use the one before
                            if i > 0:
                                prev_eid = draw_actions[i - 1].eventId
                            break

                    if prev_eid is not None:
                        compare_event_id = prev_eid
                    else:
                        # Fallback: use event_id - 1 (best effort)
                        compare_event_id = event_id - 1
                except Exception as e:
                    # If action tree traversal fails, fall back gracefully
                    compare_event_id = event_id - 1

            # --- Step 1: replay to *target* event and find the bound RT ---
            try:
                controller.SetFrameEvent(event_id, True)
            except Exception as e:
                result["error"] = (
                    "[Step1-Replay] Failed to replay to target event %d: %s\n%s"
                    % (event_id, str(e), _tb.format_exc())
                )
                return

            try:
                pipe = controller.GetPipelineState()
            except Exception as e:
                result["error"] = (
                    "[Step1-Pipeline] Failed to get pipeline state at event %d: %s\n%s"
                    % (event_id, str(e), _tb.format_exc())
                )
                return

            rt_resource_id = None
            om_error = None
            try:
                if depth:
                    dt = pipe.GetDepthTarget()
                    if dt.resourceId != rd.ResourceId.Null():
                        rt_resource_id = dt.resourceId
                else:
                    targets = pipe.GetOutputTargets()
                    bound_rts = []
                    for rt in targets:
                        if rt.resourceId != rd.ResourceId.Null():
                            bound_rts.append(rt.resourceId)
                    if rtv_index < len(bound_rts):
                        rt_resource_id = bound_rts[rtv_index]
                    elif bound_rts:
                        rt_resource_id = bound_rts[0]
            except Exception as e:
                om_error = "GetOutputTargets() raised: %s\n%s" % (str(e), _tb.format_exc())

            if rt_resource_id is None:
                kind = "depth target" if depth else "render target (index %d)" % rtv_index
                extra = (" (OM error: %s)" % om_error) if om_error else ""
                result["error"] = (
                    "[Step1-FindRT] No %s bound at event %d%s" % (kind, event_id, extra)
                )
                return

            # Find texture descriptor for dimensions / format
            tex_desc = None
            for tex in controller.GetTextures():
                if tex.resourceId == rt_resource_id:
                    tex_desc = tex
                    break
            if tex_desc is None:
                result["error"] = (
                    "[Step1-TexDesc] Texture descriptor not found for RT %s at event %d"
                    % (str(rt_resource_id), event_id)
                )
                return

            width = tex_desc.width
            height = tex_desc.height
            fmt = str(tex_desc.format.Name())
            total_pixels = width * height

            sub = rd.Subresource()
            sub.mip = 0
            sub.slice = 0
            sub.sample = 0

            # --- Step 2: read RT at target event ---
            try:
                data_after = bytes(controller.GetTextureData(rt_resource_id, sub))
            except Exception as e:
                result["error"] = (
                    "[Step2-ReadAfter] Failed to read RT %s at event %d "
                    "(fmt=%s, %dx%d): %s\n%s"
                    % (str(rt_resource_id), event_id, fmt, width, height,
                       str(e), _tb.format_exc())
                )
                return

            # --- Step 3: replay to baseline event and read RT ---
            try:
                controller.SetFrameEvent(compare_event_id, True)
            except Exception as e:
                result["error"] = (
                    "[Step3-Replay] Failed to replay to baseline event %d: %s\n%s"
                    % (compare_event_id, str(e), _tb.format_exc())
                )
                return

            try:
                data_before = bytes(controller.GetTextureData(rt_resource_id, sub))
            except Exception as e:
                result["error"] = (
                    "[Step3-ReadBefore] Failed to read RT %s at event %d "
                    "(fmt=%s, %dx%d): %s\n%s"
                    % (str(rt_resource_id), compare_event_id, fmt, width, height,
                       str(e), _tb.format_exc())
                )
                return

            # Restore replay cursor to the target event
            try:
                controller.SetFrameEvent(event_id, True)
            except Exception:
                pass  # Best-effort restore, don't fail the whole operation

            # --- Step 4: compute per-pixel diff ---
            if len(data_before) != len(data_after) or len(data_before) == 0:
                result["error"] = (
                    "[Step4-Validate] RT data size mismatch or empty "
                    "(before=%d bytes, after=%d bytes, fmt=%s, %dx%d, RT=%s)"
                    % (len(data_before), len(data_after), fmt, width, height,
                       str(rt_resource_id))
                )
                return

            bpp = ResourceService._format_bpp(fmt.upper())
            if bpp == 0:
                bpp = len(data_before) // total_pixels if total_pixels > 0 else 0
            if bpp == 0:
                result["error"] = (
                    "[Step4-BPP] Cannot determine bytes-per-pixel "
                    "(data=%d bytes, pixels=%d, fmt=%s, %dx%d)"
                    % (len(data_before), total_pixels, fmt, width, height)
                )
                return

            # Compute actual row stride (row pitch) — data may have row padding
            expected_stride = width * bpp
            if height > 0 and len(data_before) > 0:
                actual_stride = len(data_before) // height
                if actual_stride >= expected_stride and (len(data_before) % height) == 0:
                    diff_stride = actual_stride
                else:
                    diff_stride = expected_stride
            else:
                diff_stride = expected_stride

            # Build a 1-bit mask: changed[y*width+x] = True if pixel differs
            # Also track bounding box
            changed_count = 0
            min_x, min_y, max_x, max_y = width, height, 0, 0
            # For performance, compare in chunks of bpp
            changed_mask = bytearray(total_pixels)  # 0 = unchanged, 1 = changed

            thr = int(threshold)
            for py in range(height):
                row_off = py * diff_stride
                for px in range(width):
                    off = row_off + px * bpp
                    pixel_changed = False
                    for b in range(bpp):
                        d = abs(data_after[off + b] - data_before[off + b])
                        if d > thr:
                            pixel_changed = True
                            break
                    if pixel_changed:
                        idx = py * width + px
                        changed_mask[idx] = 1
                        changed_count += 1
                        if px < min_x:
                            min_x = px
                        if px > max_x:
                            max_x = px
                        if py < min_y:
                            min_y = py
                        if py > max_y:
                            max_y = py

            # Normalise bounding box when nothing changed
            if changed_count == 0:
                min_x = min_y = max_x = max_y = 0

            change_pct = round(changed_count / float(total_pixels) * 100.0, 4) if total_pixels else 0.0

            # --- Step 5: build diff-mask PNG (magenta for changed pixels) ---
            # Output dimensions (may be down-scaled)
            out_w, out_h = width, height
            if max_size > 0 and (width > max_size or height > max_size):
                scale = min(max_size / float(width), max_size / float(height))
                out_w = max(1, int(width * scale))
                out_h = max(1, int(height * scale))

            src_ys = [int(y * height / out_h) for y in range(out_h)]
            src_xs = [int(x * width / out_w) for x in range(out_w)]

            import zlib
            rows = []
            for oy in range(out_h):
                sy = src_ys[oy]
                row_off = sy * width
                buf = bytearray(1 + out_w * 4)
                # buf[0] = 0  (PNG filter None) — already zero
                wi = 1
                for ox in range(out_w):
                    sx = src_xs[ox]
                    if changed_mask[row_off + sx]:
                        # Magenta highlight
                        buf[wi] = 255
                        buf[wi + 1] = 0
                        buf[wi + 2] = 255
                        buf[wi + 3] = 255
                    else:
                        # Transparent black
                        buf[wi] = 0
                        buf[wi + 1] = 0
                        buf[wi + 2] = 0
                        buf[wi + 3] = 0
                    wi += 4
                rows.append(bytes(buf))

            raw_png = b"".join(rows)

            def _png_chunk(ctype, cdata):
                chunk = ctype + cdata
                crc = struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
                return struct.pack(">I", len(cdata)) + chunk + crc

            sig = b"\x89PNG\r\n\x1a\n"
            ihdr = _png_chunk(b"IHDR", struct.pack(">IIBBBBB", out_w, out_h, 8, 6, 0, 0, 0))
            idat = _png_chunk(b"IDAT", zlib.compress(raw_png))
            iend = _png_chunk(b"IEND", b"")
            png_bytes = sig + ihdr + idat + iend

            info = {
                "event_id": event_id,
                "compare_event_id": compare_event_id,
                "resource_id": str(rt_resource_id),
                "width": width,
                "height": height,
                "format": fmt,
                "total_pixels": total_pixels,
                "changed_pixels": changed_count,
                "change_percentage": change_pct,
                "threshold": thr,
                "bounding_box": {
                    "min_x": min_x,
                    "min_y": min_y,
                    "max_x": max_x,
                    "max_y": max_y,
                },
            }

            if output_path:
                try:
                    with open(output_path, "wb") as f:
                        f.write(png_bytes)
                    info["output_path"] = output_path
                    info["saved"] = True
                except Exception as e:
                    result["error"] = (
                        "[Step5-Save] Failed to save diff mask to '%s': %s\n%s"
                        % (output_path, str(e), _tb.format_exc())
                    )
                    return
            else:
                info["diff_base64"] = base64.b64encode(png_bytes).decode("ascii")

            result["data"] = info

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def save_texture_as_png(self, resource_id, output_path, event_id=None, mip=0,
                              max_size=0):
        """Save a texture as a PNG file (or return base64 if output_path omitted).

        Uses GetTextureData + format-aware pixel decoding (with HDR tone
        mapping) to produce a correct PNG regardless of texture format.

        This is the unified texture-to-PNG tool that covers both:
        - Full-resolution export (max_size=0, default)
        - Thumbnail/preview mode (max_size > 0, e.g. 256)

        Args:
            resource_id: The texture resource ID string.
            output_path: File path to save the PNG to. If None, returns base64.
            event_id: Optional event ID to replay to first.
            mip: Mip level to read (default 0).
            max_size: Maximum width/height (0 = original resolution).

        Returns:
            dict with resource_id, width, height, format, mip, and either
            output_path (file saved), thumbnail_base64 (if no output_path),
            or both (file saved + metadata).
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"data": None, "error": None}

        def callback(controller):
            if event_id is not None:
                controller.SetFrameEvent(int(event_id), True)

            tex_desc = self._find_texture_by_id(controller, resource_id)
            if not tex_desc:
                result["error"] = "Texture not found: %s" % resource_id
                return

            sub = rd.Subresource()
            sub.mip = mip
            sub.slice = 0
            sub.sample = 0

            try:
                data = controller.GetTextureData(tex_desc.resourceId, sub)
            except Exception as e:
                result["error"] = "Failed to get texture data: %s" % str(e)
                return

            width = max(1, tex_desc.width >> mip)
            height = max(1, tex_desc.height >> mip)
            fmt = str(tex_desc.format.Name())

            png_bytes = self._raw_to_png_bytes(data, width, height, fmt, max_size)

            info = {
                "resource_id": resource_id,
                "width": width,
                "height": height,
                "format": fmt,
                "mip": mip,
                "max_size": max_size,
            }

            if output_path:
                try:
                    with open(output_path, "wb") as f:
                        f.write(png_bytes)
                    info["output_path"] = output_path
                    info["saved"] = True
                    info["file_size"] = len(png_bytes)
                except Exception as e:
                    result["error"] = "Failed to save PNG: %s" % str(e)
                    return
            else:
                info["thumbnail_base64"] = base64.b64encode(png_bytes).decode("ascii")

            result["data"] = info

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]
