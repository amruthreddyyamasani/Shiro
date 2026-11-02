"""Validation tests for the action-safe visual-understanding schema."""

from __future__ import annotations

import json

import pytest

from shiro.visual import NormalizedBounds, parse_visual_response, visual_description


def _payload(**overrides):
    payload = {
        "schema_version": "shiro.visual.v1",
        "screen_width": 1920,
        "screen_height": 1080,
        "active_window": None,
        "targets": [
            {
                "id": "target_1",
                "label": "Save button",
                "role": "button",
                "bounds": {"x": 0.8, "y": 0.1, "width": 0.1, "height": 0.05},
                "confidence": 0.94,
                "visible_text": "Save",
                "interactable": True,
                "uncertainties": [],
            }
        ],
        "visible_text": ["Save"],
        "uncertainties": [],
    }
    payload.update(overrides)
    return payload


def test_visual_response_is_validated_and_dimensions_are_preserved():
    visual = parse_visual_response(
        json.dumps(_payload()),
        screen_width=1920,
        screen_height=1080,
        active_window={
            "title": "Untitled - Notepad",
            "process_name": "notepad.exe",
            "is_visible": True,
            "is_foreground": True,
            "bounding_rectangle": {"left": 0, "top": 0, "right": 1200, "bottom": 800},
        },
    )
    assert visual.targets[0].bounds == NormalizedBounds(
        x=0.8, y=0.1, width=0.1, height=0.05
    )
    assert visual.active_window is not None
    assert visual.active_window.process_name == "notepad.exe"
    assert "Save button" in visual_description(visual)


def test_visual_response_rejects_prose():
    with pytest.raises(ValueError, match="non-JSON"):
        parse_visual_response(
            "The screen contains a Save button.",
            screen_width=1920,
            screen_height=1080,
        )


def test_visual_response_rejects_stale_dimensions():
    with pytest.raises(ValueError, match="dimensions"):
        parse_visual_response(
            json.dumps(_payload(screen_width=1280)),
            screen_width=1920,
            screen_height=1080,
        )


def test_visual_response_rejects_out_of_bounds_target():
    invalid = _payload(
        targets=[
            {
                "id": "target_1",
                "label": "Invalid",
                "role": "button",
                "bounds": {"x": 0.95, "y": 0.1, "width": 0.1, "height": 0.1},
                "confidence": 0.9,
                "visible_text": "",
                "interactable": True,
                "uncertainties": [],
            }
        ]
    )
    with pytest.raises(ValueError, match="inside the screenshot"):
        parse_visual_response(
            json.dumps(invalid),
            screen_width=1920,
            screen_height=1080,
        )
