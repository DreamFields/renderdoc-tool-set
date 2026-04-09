"""Output formatting for renderdoc-cli."""

from __future__ import annotations

import json
import sys
from typing import Any


# Keys that typically hold the main list in a result dict
_LIST_KEYS = (
    "actions", "textures", "shaders", "captures", "sessions",
    "matches", "timings", "states",
)


def format_output(data: Any, fmt: str = "json") -> str:
    """Format result data as a string."""
    if fmt == "tsv":
        return _to_tsv(data)
    return json.dumps(data, indent=2, ensure_ascii=False)


def emit(
    data: Any,
    fmt: str = "json",
    file: str | None = None,
    quiet: bool = False,
) -> None:
    """Format and write result data to stdout or a file.

    Special case: if *data* is a dict containing ``saved == True``, the
    binary payload (e.g. PNG) was already written by the RenderDoc
    extension side via its own ``output_path``.  In that case we **skip**
    writing JSON to *file* so the binary content is not overwritten.
    Instead the JSON metadata goes to stdout so the caller can still
    inspect the result.

    Args:
        data: Result payload.
        fmt: Output format.
        file: Optional output file path.
        quiet: If True, suppress non-error stderr hints.
    """

    # Detect extension-side file saves that must not be overwritten
    _already_saved = isinstance(data, dict) and data.get("saved") is True

    text = format_output(data, fmt)
    if file and not _already_saved:
        with open(file, "w", encoding="utf-8") as f:
            f.write(text)
            f.write("\n")
    else:
        # Always print to stdout; when file was already saved we still
        # want the caller to see the metadata.
        print(text)
        if file and _already_saved and not quiet:
            # Hint that the binary is in the file, not JSON
            print(
                "[Binary saved to %s — file contains PNG/data, not JSON]"
                % file,
                file=sys.stderr,
            )



def emit_error(message: str, command: str | None = None) -> None:
    """Write a structured error to stderr."""
    err = {"error": message}
    if command:
        err["command"] = command
    print(json.dumps(err, indent=2, ensure_ascii=False), file=sys.stderr)


# ── TSV helpers ──────────────────────────────────────────────────────

def _to_tsv(data: Any) -> str:
    """Convert dict/list to TSV for piping."""
    if isinstance(data, dict):
        for key in _LIST_KEYS:
            if key in data and isinstance(data[key], list):
                return _list_to_tsv(data[key])
        # Flat key-value pairs
        lines = []
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            lines.append("%s\t%s" % (k, v))
        return "\n".join(lines)
    if isinstance(data, list):
        return _list_to_tsv(data)
    return str(data)


def _list_to_tsv(items: list) -> str:
    """Convert a list of dicts to TSV with header row."""
    if not items:
        return ""
    if not isinstance(items[0], dict):
        return "\n".join(str(i) for i in items)
    keys = list(items[0].keys())
    lines = ["\t".join(keys)]
    for item in items:
        vals = []
        for k in keys:
            v = item.get(k, "")
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            vals.append(str(v))
        lines.append("\t".join(vals))
    return "\n".join(lines)
