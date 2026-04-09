"""
Capture management service for RenderDoc.
"""

import renderdoc as rd


class CaptureManager:
    """Capture management service"""

    def __init__(self, ctx, invoke_fn):
        self.ctx = ctx
        self._invoke = invoke_fn

    def get_capture_status(self):
        """Check if a capture is loaded and get API info"""
        if not self.ctx.IsCaptureLoaded():
            return {"loaded": False}

        result = {"loaded": True, "api": None, "filename": None}

        try:
            result["filename"] = self.ctx.GetCaptureFilename()
        except Exception:
            pass

        # Get API type via replay
        def callback(controller):
            try:
                props = controller.GetAPIProperties()
                result["api"] = str(props.pipelineType)
            except Exception:
                pass

        self._invoke(callback)
        return result

    def get_capture_info(self):
        """Get detailed capture information including driver, GPU, draw count etc."""
        if not self.ctx.IsCaptureLoaded():
            return {"loaded": False}

        result = {
            "loaded": True,
            "api": None,
            "filename": None,
            "driver": None,
            "gpu": None,
            "statistics": {},
        }

        try:
            result["filename"] = self.ctx.GetCaptureFilename()
        except Exception:
            pass

        def callback(controller):
            try:
                props = controller.GetAPIProperties()
                result["api"] = str(props.pipelineType)
            except Exception:
                pass

            # Try to get driver/GPU info from structured data
            try:
                sfile = controller.GetStructuredFile()
                if sfile:
                    # Iterate through chunks for driver info
                    for i in range(sfile.chunks.count):
                        chunk = sfile.chunks[i]
                        chunk_name = chunk.name if hasattr(chunk, 'name') else ''
                        if 'driver' in chunk_name.lower() or 'init' in chunk_name.lower():
                            result["driver"] = chunk_name
                            break
            except Exception:
                pass

            # Count actions
            try:
                root_actions = controller.GetRootActions()
                stats = {"draw_calls": 0, "dispatches": 0, "total_actions": 0}

                def count_all(actions):
                    for action in actions:
                        stats["total_actions"] += 1
                        if action.flags & rd.ActionFlags.Drawcall:
                            stats["draw_calls"] += 1
                        if action.flags & rd.ActionFlags.Dispatch:
                            stats["dispatches"] += 1
                        if action.children:
                            count_all(action.children)

                count_all(root_actions)
                result["statistics"] = stats
            except Exception:
                pass

            # Resource counts
            try:
                result["statistics"]["texture_count"] = len(controller.GetTextures())
                result["statistics"]["buffer_count"] = len(controller.GetBuffers())
            except Exception:
                pass

        self._invoke(callback)
        return result

    def list_captures(self, directory):
        """
        List all .rdc files in the specified directory.

        Args:
            directory: Directory path to search

        Returns:
            dict with 'captures' list containing file info
        """
        import os
        import datetime

        # Validate directory exists
        if not os.path.isdir(directory):
            raise ValueError("Directory not found: %s" % directory)

        captures = []

        try:
            for filename in os.listdir(directory):
                if filename.lower().endswith(".rdc"):
                    filepath = os.path.join(directory, filename)
                    if os.path.isfile(filepath):
                        stat = os.stat(filepath)
                        # Format timestamp as ISO 8601
                        mtime = datetime.datetime.fromtimestamp(stat.st_mtime)
                        captures.append({
                            "filename": filename,
                            "path": filepath,
                            "size_bytes": stat.st_size,
                            "modified_time": mtime.isoformat(),
                        })
        except Exception as e:
            raise ValueError("Failed to list directory: %s" % str(e))

        # Sort by modified time (newest first)
        captures.sort(key=lambda x: x["modified_time"], reverse=True)

        return {
            "directory": directory,
            "count": len(captures),
            "captures": captures,
        }

    def open_capture(self, capture_path):
        """
        Open a capture file in RenderDoc.

        Args:
            capture_path: Full path to the .rdc file

        Returns:
            dict with success status and capture info
        """
        import os

        # Validate file exists
        if not os.path.isfile(capture_path):
            raise ValueError("Capture file not found: %s" % capture_path)

        # Validate extension
        if not capture_path.lower().endswith(".rdc"):
            raise ValueError("Invalid file type. Expected .rdc file: %s" % capture_path)

        # Create ReplayOptions with defaults
        opts = rd.ReplayOptions()

        # Open the capture
        # LoadCapture will automatically close any existing capture
        try:
            self.ctx.LoadCapture(
                capture_path,   # captureFile
                opts,           # ReplayOptions
                capture_path,   # origFilename (same as capture path)
                False,          # temporary (False = permanent load)
                True,           # local (True = local file)
            )
        except Exception as e:
            raise ValueError("Failed to open capture: %s" % str(e))

        # Verify the capture was loaded
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("Failed to load capture (unknown error)")

        # Get capture info
        result = {
            "success": True,
            "capture_path": capture_path,
            "filename": os.path.basename(capture_path),
        }

        # Get API type if possible (may require replay thread)
        try:
            api_result = {"api": None}

            def callback(controller):
                try:
                    props = controller.GetAPIProperties()
                    api_result["api"] = str(props.pipelineType)
                except Exception:
                    pass

            self._invoke(callback)
            if api_result["api"]:
                result["api"] = api_result["api"]
        except Exception:
            pass

        return result
