"""Integration test fixtures using pytest-jupyter's real Jupyter Server."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def jp_server_config(jp_server_config):
    """Enable the jupyter_bonjour extension in the test server."""
    jp_server_config["ServerApp"]["jpserver_extensions"]["jupyter_bonjour"] = True
    return jp_server_config


@pytest.fixture(autouse=True)
def _always_mock_zeroconf():
    """Patch ``zeroconf.Zeroconf`` so no real mDNS traffic occurs during integration tests."""
    zc_instance = MagicMock()
    zc_instance.async_register_service = AsyncMock()
    zc_instance.async_unregister_service = AsyncMock()
    zc_instance.async_update_service = AsyncMock()
    zc_instance.close = MagicMock()

    with patch("jupyter_bonjour.advertiser.Zeroconf", return_value=zc_instance) as zc_cls:
        zc_cls._instance = zc_instance
        yield zc_cls


@pytest.fixture
def started_serverapp(jp_serverapp, jp_asyncio_loop):
    """A serverapp where extension start hooks have been triggered.

    pytest-jupyter calls ``start_app()`` but not ``start_ioloop()``, so
    ``_post_start`` (which calls ``start_all_extensions``) never fires.
    This fixture manually triggers that step.
    """
    jp_asyncio_loop.run_until_complete(jp_serverapp.extension_manager.start_all_extensions())
    return jp_serverapp


def _get_extension_app(serverapp):
    """Retrieve the BonjourExtensionApp instance from a running serverapp."""
    ext = serverapp.extension_manager.extensions["jupyter_bonjour"]
    point = ext.extension_points["jupyter_bonjour"]
    return point.app
