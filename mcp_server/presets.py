"""Reusable filter presets for common RenderDoc analysis workflows."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_PRESETS: dict[str, dict[str, Any]] = {
    "unity_game_rendering": {
        "name": "unity_game_rendering",
        "summary": "Focus on Camera.Render while excluding Unity editor UI noise.",
        "filters": {
            "marker_filter": "Camera.Render",
            "exclude_markers": [
                "GUI.Repaint",
                "UIR.DrawChain",
                "GUITexture.Draw",
                "UGUI.Rendering.RenderOverlays",
                "PlayerEndOfFrame",
                "EditorLoop",
            ],
        },
    },
    "unity_ui_rendering": {
        "name": "unity_ui_rendering",
        "summary": "Focus on Unity UI passes and editor overlays.",
        "filters": {
            "exclude_markers": ["Camera.Render"],
            "marker_filter": "UI",
        },
    },
    "unity_shadow_debug": {
        "name": "unity_shadow_debug",
        "summary": "Focus on shadow map generation and shadow-related passes.",
        "filters": {
            "marker_filter": "Shadow",
            "only_actions": True,
            "flags_filter": ["Drawcall", "Dispatch"],
        },
    },
    "dispatch_only": {
        "name": "dispatch_only",
        "summary": "Return only dispatch actions for compute analysis.",
        "filters": {
            "only_actions": True,
            "flags_filter": ["Dispatch"],
        },
    },
}


def list_presets() -> dict[str, dict[str, Any]]:
    """Return all available presets."""
    return deepcopy(_PRESETS)



def get_preset(name: str | None) -> dict[str, Any] | None:
    """Return a single preset definition by name."""
    if name is None:
        return None
    preset = _PRESETS.get(name)
    if preset is None:
        raise ValueError(
            "Unknown preset '%s'. Available presets: %s"
            % (name, ", ".join(sorted(_PRESETS.keys())))
        )
    return deepcopy(preset)



def merge_filters(base_params: dict[str, Any], preset_name: str | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Merge caller parameters with an optional preset."""
    params = dict(base_params)
    preset = get_preset(preset_name)
    if preset is None:
        return params, None

    merged = deepcopy(preset["filters"])
    for key, value in params.items():
        merged[key] = value

    return merged, {
        "name": preset["name"],
        "summary": preset["summary"],
        "filters": deepcopy(preset["filters"]),
    }
