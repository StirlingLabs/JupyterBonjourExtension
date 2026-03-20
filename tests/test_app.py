"""Tests for BonjourExtensionApp."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jupyter_bonjour.app import (
    BonjourExtensionApp,
    _detect_auth_type,
    _format_extension_list,
    _resolve_addresses,
    _shorten_extension_name,
)

# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestShortenExtensionName:
    def test_jupyter_prefix(self):
        assert _shorten_extension_name("jupyter_server") == "server"

    def test_jupyterlab_prefix(self):
        assert _shorten_extension_name("jupyterlab_git") == "git"

    def test_jupyter_collaboration(self):
        assert _shorten_extension_name("jupyter_collaboration") == "collaboration"

    def test_no_prefix(self):
        assert _shorten_extension_name("jupytext") == "jupytext"

    def test_nbclassic(self):
        assert _shorten_extension_name("nbclassic") == "nbclassic"


class TestFormatExtensionList:
    def test_basic(self):
        result = _format_extension_list({"jupyterlab": "4.0.0", "jupytext": "1.16.0"})
        # jupyterlab -> lab, jupytext stays (no jupyter_ prefix), versions stripped
        assert "lab=4" in result
        assert "jupytext=1.16" in result

    def test_sorted(self):
        result = _format_extension_list({"z_ext": "1.0.0", "a_ext": "2.0.0"})
        parts = result.split(",")
        assert parts[0].startswith("a_ext=")


class TestResolveAddresses:
    def test_localhost_includes_loopback(self):
        addrs = _resolve_addresses("localhost", set())
        assert "127.0.0.1" in addrs

    def test_127_includes_loopback(self):
        addrs = _resolve_addresses("127.0.0.1", set())
        assert "127.0.0.1" in addrs

    def test_ipv6_loopback_returned_directly(self):
        # ::1 is treated as a specific IP and returned as-is
        assert _resolve_addresses("::1", set()) == ["::1"]

    def test_specific_ip(self):
        assert _resolve_addresses("192.168.1.5", set()) == ["192.168.1.5"]

    def test_specific_ip_ignores_filter(self):
        # When a specific IP is given, the interfaces filter doesn't apply
        assert _resolve_addresses("192.168.1.5", {"10.0.0.1"}) == ["192.168.1.5"]

    def test_wildcard_returns_ipv4_only(self):
        addrs = _resolve_addresses("0.0.0.0", set())
        for addr in addrs:
            # All addresses should be IPv4 (no colons)
            assert ":" not in addr

    def test_empty_string_same_as_wildcard(self):
        addrs = _resolve_addresses("", set())
        for addr in addrs:
            assert ":" not in addr


class TestDetectAuthType:
    def _make_serverapp(self, *, provider_class_name: str = "IdentityProvider", token: str = ""):
        from unittest.mock import MagicMock

        serverapp = MagicMock()
        type(serverapp.identity_provider).__name__ = provider_class_name
        serverapp.identity_provider.token = token
        return serverapp

    def test_token_auth(self):
        app = self._make_serverapp(token="abc123")
        assert _detect_auth_type(app) == "token"

    def test_no_auth(self):
        app = self._make_serverapp(token="")
        assert _detect_auth_type(app) == "none"

    def test_password_provider(self):
        app = self._make_serverapp(provider_class_name="PasswordIdentityProvider", token="")
        assert _detect_auth_type(app) == "password"


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_mock_extension(*, enabled: bool = True, version: str = "1.0.0"):
    """Create a mock extension package for serverapp.extension_manager."""
    ext = MagicMock()
    ext.enabled = enabled
    ext.version = version
    return ext


def _make_mock_serverapp(
    *,
    ip: str = "127.0.0.1",
    port: int = 8888,
    base_url: str = "/",
    token: str = "abc123",
    provider_class_name: str = "IdentityProvider",
    extensions: dict[str, MagicMock] | None = None,
):
    """Create a mock ServerApp for unit testing."""
    serverapp = MagicMock()
    serverapp.ip = ip
    serverapp.port = port
    serverapp.base_url = base_url
    type(serverapp.identity_provider).__name__ = provider_class_name
    serverapp.identity_provider.token = token
    serverapp.extension_manager.extensions = extensions or {}
    return serverapp


# ---------------------------------------------------------------------------
# _build_properties tests
# ---------------------------------------------------------------------------


class TestBuildProperties:
    def _make_app(self, **kwargs):
        app = BonjourExtensionApp()
        for k, v in kwargs.items():
            setattr(app, k, v)
        return app

    def test_minimal(self):
        serverapp = _make_mock_serverapp(extensions={})
        app = self._make_app()
        props = app._build_properties(serverapp)

        assert "version" in props
        assert props["base_url"] == "/"
        assert props["auth"] == "token"
        assert "bonjour_version" in props
        assert "ui" not in props
        assert "srvxtn" not in props

    def test_with_ui_frontends(self):
        extensions = {"jupyterlab": _make_mock_extension(version="4.0.0")}
        serverapp = _make_mock_serverapp(extensions=extensions)
        app = self._make_app()
        props = app._build_properties(serverapp)

        assert "ui" in props
        assert "lab=4" in props["ui"]

    def test_with_server_extensions(self):
        extensions = {
            "jupytext": _make_mock_extension(version="1.16.0"),
            "jupyter_bonjour": _make_mock_extension(version="0.1.0"),
        }
        serverapp = _make_mock_serverapp(extensions=extensions)
        app = self._make_app()
        props = app._build_properties(serverapp)

        assert "srvxtn" in props
        assert "jupytext=1.16" in props["srvxtn"]
        assert "bonjour=0.1" in props["srvxtn"]

    def test_with_extra_properties(self):
        serverapp = _make_mock_serverapp(extensions={})
        app = self._make_app(extra_properties={"custom_key": "custom_val"})
        props = app._build_properties(serverapp)

        assert props["custom_key"] == "custom_val"

    def test_disabled_extensions_excluded(self):
        extensions = {
            "jupyterlab": _make_mock_extension(enabled=False, version="4.0.0"),
            "jupytext": _make_mock_extension(enabled=True, version="1.16.0"),
        }
        serverapp = _make_mock_serverapp(extensions=extensions)
        app = self._make_app()
        props = app._build_properties(serverapp)

        # jupyterlab disabled → not in ui
        assert "ui" not in props
        # jupytext enabled → in srvxtn
        assert "srvxtn" in props
        assert "jupytext" in props["srvxtn"]


# ---------------------------------------------------------------------------
# _enumerate_lab_extensions tests
# ---------------------------------------------------------------------------


class TestEnumerateLabExtensions:
    def _make_app(self):
        return BonjourExtensionApp()

    @pytest.mark.asyncio
    async def test_skips_when_no_jupyterlab(self):
        app = self._make_app()
        app._advertiser = MagicMock()
        app._advertiser.update_properties = AsyncMock()
        serverapp = _make_mock_serverapp(extensions={})

        await app._enumerate_lab_extensions(serverapp)

        app._advertiser.update_properties.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_when_jupyterlab_disabled(self):
        app = self._make_app()
        app._advertiser = MagicMock()
        app._advertiser.update_properties = AsyncMock()
        extensions = {"jupyterlab": _make_mock_extension(enabled=False)}
        serverapp = _make_mock_serverapp(extensions=extensions)

        await app._enumerate_lab_extensions(serverapp)

        app._advertiser.update_properties.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_when_import_fails(self):
        app = self._make_app()
        app._advertiser = MagicMock()
        app._advertiser.update_properties = AsyncMock()
        extensions = {"jupyterlab": _make_mock_extension()}
        serverapp = _make_mock_serverapp(extensions=extensions)

        with patch.dict("sys.modules", {"jupyterlab": None, "jupyterlab.commands": None}):
            await app._enumerate_lab_extensions(serverapp)

        app._advertiser.update_properties.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_updates_properties_on_success(self):
        app = self._make_app()
        app._advertiser = MagicMock()
        app._advertiser.update_properties = AsyncMock()
        extensions = {"jupyterlab": _make_mock_extension()}
        serverapp = _make_mock_serverapp(extensions=extensions)

        mock_ext = MagicMock()
        mock_ext.name = "my-lab-ext"
        mock_ext.version = "2.0.0"
        mock_info = MagicMock()
        mock_info.extensions = [mock_ext]

        mock_commands = MagicMock()
        mock_commands.get_app_info = MagicMock(return_value=mock_info)
        with patch.dict("sys.modules", {"jupyterlab": MagicMock(), "jupyterlab.commands": mock_commands}):
            await app._enumerate_lab_extensions(serverapp)

        app._advertiser.update_properties.assert_awaited_once()
        call_args = app._advertiser.update_properties.call_args[0][0]
        assert "labxtn" in call_args

    @pytest.mark.asyncio
    async def test_handles_get_app_info_failure(self):
        app = self._make_app()
        app._advertiser = MagicMock()
        app._advertiser.update_properties = AsyncMock()
        extensions = {"jupyterlab": _make_mock_extension()}
        serverapp = _make_mock_serverapp(extensions=extensions)

        # Mock the import and make get_app_info raise
        mock_commands = MagicMock()
        mock_commands.get_app_info = MagicMock(side_effect=RuntimeError("boom"))
        with patch.dict("sys.modules", {"jupyterlab": MagicMock(), "jupyterlab.commands": mock_commands}):
            await app._enumerate_lab_extensions(serverapp)

        app._advertiser.update_properties.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_when_no_advertiser(self):
        app = self._make_app()
        app._advertiser = None
        extensions = {"jupyterlab": _make_mock_extension()}
        serverapp = _make_mock_serverapp(extensions=extensions)

        mock_ext = MagicMock()
        mock_ext.name = "some-ext"
        mock_ext.version = "1.0.0"
        mock_info = MagicMock()
        mock_info.extensions = [mock_ext]

        mock_commands = MagicMock()
        mock_commands.get_app_info = MagicMock(return_value=mock_info)
        with patch.dict("sys.modules", {"jupyterlab": MagicMock(), "jupyterlab.commands": mock_commands}):
            # Should not raise even though _advertiser is None
            await app._enumerate_lab_extensions(serverapp)


# ---------------------------------------------------------------------------
# _start_jupyter_server_extension tests
# ---------------------------------------------------------------------------


class TestStartJupyterServerExtension:
    @pytest.mark.asyncio
    async def test_disabled(self, mock_zeroconf):
        app = BonjourExtensionApp()
        app.enabled = False
        serverapp = _make_mock_serverapp()

        await app._start_jupyter_server_extension(serverapp)

        assert app._advertiser is None

    @pytest.mark.asyncio
    async def test_no_addresses(self, mock_zeroconf):
        app = BonjourExtensionApp()
        serverapp = _make_mock_serverapp()

        with patch("jupyter_bonjour.app._resolve_addresses", return_value=[]):
            await app._start_jupyter_server_extension(serverapp)

        assert app._advertiser is None

    @pytest.mark.asyncio
    async def test_normal_start(self, mock_zeroconf):
        app = BonjourExtensionApp()
        serverapp = _make_mock_serverapp(extensions={})

        with patch("jupyter_bonjour.app._resolve_addresses", return_value=["192.168.1.1"]):
            await app._start_jupyter_server_extension(serverapp)

        assert app._advertiser is not None
        zc = mock_zeroconf._instance
        zc.async_register_service.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_in_start(self, mock_zeroconf):
        app = BonjourExtensionApp()
        serverapp = _make_mock_serverapp(extensions={})

        mock_zeroconf._instance.async_register_service = AsyncMock(side_effect=OSError("network down"))
        with patch("jupyter_bonjour.app._resolve_addresses", return_value=["192.168.1.1"]):
            await app._start_jupyter_server_extension(serverapp)

        # Exception caught; advertiser creation attempted but start failed
        # The advertiser is assigned before start() is called, so it may be non-None
        # but the important thing is that no exception propagated


# ---------------------------------------------------------------------------
# stop_extension tests
# ---------------------------------------------------------------------------


class TestStopExtension:
    @pytest.mark.asyncio
    async def test_stop_no_advertiser(self):
        app = BonjourExtensionApp()
        app._advertiser = None

        # Should not raise
        await app.stop_extension()
        assert app._advertiser is None

    @pytest.mark.asyncio
    async def test_stop_calls_advertiser_stop(self):
        app = BonjourExtensionApp()
        mock_adv = AsyncMock()
        app._advertiser = mock_adv

        await app.stop_extension()

        mock_adv.stop.assert_awaited_once()
        assert app._advertiser is None
