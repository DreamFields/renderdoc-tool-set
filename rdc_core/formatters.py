"""Formatting helpers for auto-generating MCP tool signatures and CLI args.

These utilities convert ``Operation`` / ``OperationParam`` metadata into
the Python type annotations and argparse arguments needed by the MCP
server and the CLI, respectively.
"""

from __future__ import annotations

from typing import Any

from .registry import Operation, OperationParam


# Python type → annotation string mapping for MCP tool signatures
_TYPE_MAP: dict[type, str] = {
    str: "str",
    int: "int",
    float: "float",
    bool: "bool",
    list: "list",
}


def param_python_type(param: OperationParam) -> type:
    """Return the Python type for a parameter, wrapped as Optional if not required."""
    return param.type


def build_mcp_description(op: Operation) -> str:
    """Build a full MCP tool description string including warnings."""
    parts = [op.description]
    if op.warning:
        parts.append("\nWARNING: " + op.warning)
    if op.needs_session:
        parts.append("\nArgs:\n    session: Optional session ID. Auto-selected when omitted.")
    return "\n".join(parts)
