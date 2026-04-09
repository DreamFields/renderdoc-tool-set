"""Operation registry — single source of truth for all RDC operations.

Both MCP tools and CLI commands are auto-generated from these definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class OperationParam:
    """Describes a single parameter for an operation."""

    name: str
    type: type
    required: bool = True
    default: Any = None
    help: str = ""


@dataclass
class Operation:
    """Describes a registered operation."""

    name: str                           # IPC method name (e.g. "get_pipeline_state")
    description: str                    # Human-readable description (used by MCP + CLI --help)
    params: list[OperationParam] = field(default_factory=list)
    category: str = "general"           # Grouping: capture, draw, pipeline, shader, resource, session
    needs_session: bool = True          # Whether to add optional session param
    warning: str | None = None          # Warning text (e.g. "may freeze on large captures")


# Global registry
_OPERATIONS: dict[str, Operation] = {}


def register(
    name: str,
    *,
    description: str,
    params: list[OperationParam] | None = None,
    category: str = "general",
    needs_session: bool = True,
    warning: str | None = None,
) -> Operation:
    """Register an operation in the global registry."""
    op = Operation(
        name=name,
        description=description,
        params=params or [],
        category=category,
        needs_session=needs_session,
        warning=warning,
    )
    _OPERATIONS[name] = op
    return op


def get_operation(name: str) -> Operation | None:
    """Return a registered operation by name, or None if not found."""
    return _OPERATIONS.get(name)


def list_operations(category: str | None = None) -> list[Operation]:
    """Return all registered operations, optionally filtered by category."""
    ops = list(_OPERATIONS.values())
    if category:
        ops = [o for o in ops if o.category == category]
    return sorted(ops, key=lambda o: (o.category, o.name))


def list_categories() -> list[str]:
    """Return sorted list of distinct category names."""
    return sorted({op.category for op in _OPERATIONS.values()})
