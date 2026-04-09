"""
RenderDoc MCP Server.
FastMCP server providing access to RenderDoc capture data.

All MCP tools are auto-generated from the ``rdc_core.operations`` registry.
This eliminates the need to manually define 35+ ``@mcp.tool`` functions —
adding a new operation only requires an entry in ``rdc_core/operations.py``
(plus the Service implementation on the RenderDoc extension side).

Multi-session support
---------------------
All tools accept an optional ``session`` parameter.  When omitted the
``BridgeManager`` auto-selects:

* If exactly one RenderDoc instance is running → use it (backward compatible).
* If a default session has been pinned via ``set_default_session`` → use it.
* Otherwise → return an error listing available sessions.
"""

from __future__ import annotations

from typing import Any, Optional

from fastmcp import FastMCP

from .bridge.manager import BridgeManager
from .config import settings

# Import rdc_core — triggers registration of all operations
from rdc_core import operations as _operations_module  # noqa: F401
from rdc_core.registry import list_operations, Operation, OperationParam
from rdc_core.executor import Executor
from rdc_core.formatters import build_mcp_description

mcp = FastMCP(name="RenderDoc Tools MCP Server")
manager = BridgeManager(
    ipc_root_dir=settings.ipc_root_dir,
    host=settings.renderdoc_host,
    port=settings.renderdoc_port,
)
executor = Executor(manager)


# ------------------------------------------------------------------ #
#  Python type mapping for dynamic signature construction             #
# ------------------------------------------------------------------ #

_PARAM_TYPE_MAP: dict[type, str] = {
    str: "str",
    int: "int",
    float: "float",
    bool: "bool",
    list: "list",
}


def _python_type_str(param: OperationParam) -> str:
    """Return the type annotation string for a parameter."""
    base = _PARAM_TYPE_MAP.get(param.type, "Any")
    if not param.required and param.default is None and param.type is not bool:
        return "Optional[%s]" % base
    return base


def _default_repr(value: Any) -> str:
    """Return the repr() of a default value."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, str):
        return repr(value)
    return repr(value)


def _make_tool_function(op: Operation) -> callable:
    """Dynamically create a tool function for the given operation.

    We use ``exec()`` to build a real Python function with proper parameter
    declarations that Pydantic / FastMCP can introspect.  This avoids
    ``**kwargs`` which breaks Pydantic schema generation.
    """
    # Build function parameter list
    param_parts: list[str] = []
    for p in op.params:
        type_str = _python_type_str(p)
        if p.required:
            param_parts.append("%s: %s" % (p.name, type_str))
        else:
            param_parts.append(
                "%s: %s = %s" % (p.name, type_str, _default_repr(p.default))
            )

    # Append session parameter for session-aware operations
    if op.needs_session:
        param_parts.append("session: Optional[str] = None")

    params_str = ", ".join(param_parts)

    func_code = (
        "def {name}({params}) -> dict:\n"
        '    """{doc}"""\n'
        "    _kwargs = {{}}\n"
    ).format(
        name=op.name,
        params=params_str,
        doc=build_mcp_description(op).replace('"""', '\\"\\"\\"'),
    )

    # Add parameter assignment lines
    for p in op.params:
        if p.required:
            func_code += "    _kwargs[%r] = %s\n" % (p.name, p.name)
        else:
            # Only include optional params if they differ from None / default
            if p.default is None:
                func_code += (
                    "    if %s is not None:\n"
                    "        _kwargs[%r] = %s\n"
                ) % (p.name, p.name, p.name)
            else:
                # Always include params that have non-None defaults
                func_code += "    _kwargs[%r] = %s\n" % (p.name, p.name)

    # Call the executor
    if op.needs_session:
        func_code += "    return _executor_.execute(%r, _kwargs or None, session=session)\n" % op.name
    else:
        func_code += "    return _executor_.execute(%r, _kwargs or None)\n" % op.name

    # Execute in a namespace that includes the necessary imports
    namespace: dict[str, Any] = {
        "Optional": Optional,
        "Any": Any,
        "_executor_": executor,
    }
    exec(func_code, namespace)  # noqa: S102
    fn = namespace[op.name]

    return fn


def _auto_register_tools() -> None:
    """Register all operations from the rdc_core registry as MCP tools."""
    for op in list_operations():
        fn = _make_tool_function(op)
        mcp.tool(fn)


# Perform registration at module load time
_auto_register_tools()


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
