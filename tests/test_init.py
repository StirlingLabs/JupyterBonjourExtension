"""Tests for the extension entry point."""

from __future__ import annotations

import jupyter_bonjour


def test_version_is_string():
    assert isinstance(jupyter_bonjour.__version__, str)
    assert jupyter_bonjour.__version__


def test_extension_points_structure():
    points = jupyter_bonjour._jupyter_server_extension_points()
    assert isinstance(points, list)
    assert len(points) == 1
    point = points[0]
    assert point["module"] == "jupyter_bonjour"
    assert "app" in point


def test_extension_points_app_is_extension_app():
    from jupyter_server.extension.application import ExtensionApp

    points = jupyter_bonjour._jupyter_server_extension_points()
    app_cls = points[0]["app"]
    assert issubclass(app_cls, ExtensionApp)
