"""Shared fixtures for jupyter_bonjour tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest_plugins = ["pytest_jupyter.jupyter_server"]


@pytest.fixture
def mock_zeroconf():
    """Patch ``zeroconf.Zeroconf`` so no real network traffic occurs.

    Yields the mock *class* — instantiation returns a mock with async helpers.
    """
    zc_instance = MagicMock()
    zc_instance.async_register_service = AsyncMock()
    zc_instance.async_unregister_service = AsyncMock()
    zc_instance.async_update_service = AsyncMock()
    zc_instance.close = MagicMock()

    with patch("jupyter_bonjour.advertiser.Zeroconf", return_value=zc_instance) as zc_cls:
        zc_cls._instance = zc_instance
        yield zc_cls
