"""Jupyter Server extension for mDNS/Bonjour service discovery."""

from __future__ import annotations

from typing import Any

from ._version import __version__

__all__ = ["__version__", "_jupyter_server_extension_points"]


def _jupyter_server_extension_points() -> list[dict[str, Any]]:
    from .app import BonjourExtensionApp

    return [{"module": "jupyter_bonjour", "app": BonjourExtensionApp}]
