"""
Service classes for RenderDoc operations.
"""

from .capture_manager import CaptureManager
from .action_service import ActionService
from .resource_service import ResourceService
from .pipeline_service import PipelineService

# NOTE:
# Diagnostic service is optional to keep extension loading resilient when
# users have a stale/partial installation in RenderDoc's extension folder.
try:
    from .diagnostic_service import DiagnosticService
except Exception as e:
    import os
    import traceback
    log_path = os.path.join(os.path.dirname(__file__), "..", "diagnostic_import_error.log")
    try:
        with open(log_path, "w") as f:
            f.write("DiagnosticService import failed:\n")
            f.write(str(e) + "\n\n")
            traceback.print_exc(file=f)
    except:
        pass
    DiagnosticService = None


__all__ = [
    "CaptureManager",
    "ActionService",
    "ResourceService",
    "PipelineService",
    "DiagnosticService",
]

