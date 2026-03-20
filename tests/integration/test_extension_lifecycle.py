"""Integration tests: verify the extension loads and runs inside a real Jupyter Server."""

from __future__ import annotations

from jupyter_bonjour.advertiser import BonjourAdvertiser
from jupyter_bonjour.app import BonjourExtensionApp

from .conftest import _get_extension_app

# ---------------------------------------------------------------------------
# Extension loading (no _post_start needed)
# ---------------------------------------------------------------------------


class TestExtensionLoading:
    def test_extension_is_loaded(self, jp_serverapp):
        extensions = jp_serverapp.extension_manager.extensions
        assert "jupyter_bonjour" in extensions
        assert extensions["jupyter_bonjour"].enabled

    def test_extension_app_is_correct_type(self, jp_serverapp):
        ext_app = _get_extension_app(jp_serverapp)
        assert isinstance(ext_app, BonjourExtensionApp)

    def test_extension_has_serverapp_reference(self, jp_serverapp):
        ext_app = _get_extension_app(jp_serverapp)
        assert ext_app.serverapp is jp_serverapp


# ---------------------------------------------------------------------------
# Extension start (requires _post_start / start_all_extensions)
# ---------------------------------------------------------------------------


class TestExtensionStart:
    def test_start_creates_advertiser(self, started_serverapp, _always_mock_zeroconf):
        ext_app = _get_extension_app(started_serverapp)
        assert ext_app._advertiser is not None
        assert isinstance(ext_app._advertiser, BonjourAdvertiser)

        zc = _always_mock_zeroconf._instance
        zc.async_register_service.assert_awaited_once()

    def test_start_builds_expected_properties(self, started_serverapp):
        ext_app = _get_extension_app(started_serverapp)
        assert ext_app._advertiser is not None

        props = ext_app._advertiser.info.properties
        # Properties are bytes in ServiceInfo
        assert b"version" in props
        assert b"base_url" in props
        assert b"auth" in props
        assert b"bonjour_version" in props

    def test_start_service_name_contains_port(self, started_serverapp):
        ext_app = _get_extension_app(started_serverapp)
        assert ext_app._advertiser is not None

        service_name = ext_app._advertiser.info.name
        port_str = str(started_serverapp.port)
        assert port_str in service_name

    def test_base_url_matches_serverapp(self, started_serverapp):
        ext_app = _get_extension_app(started_serverapp)
        assert ext_app._advertiser is not None

        props = ext_app._advertiser.info.properties
        assert props[b"base_url"] == started_serverapp.base_url.encode()


# ---------------------------------------------------------------------------
# Extension stop
# ---------------------------------------------------------------------------


class TestExtensionStop:
    async def test_stop_cleans_up_advertiser(self, started_serverapp, _always_mock_zeroconf):
        ext_app = _get_extension_app(started_serverapp)
        assert ext_app._advertiser is not None

        await ext_app.stop_extension()

        assert ext_app._advertiser is None
        zc = _always_mock_zeroconf._instance
        zc.async_unregister_service.assert_awaited_once()

    async def test_stop_before_start_is_safe(self, jp_serverapp):
        ext_app = _get_extension_app(jp_serverapp)
        assert ext_app._advertiser is None

        # Should not raise
        await ext_app.stop_extension()
        assert ext_app._advertiser is None
