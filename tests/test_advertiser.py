"""Unit tests for BonjourAdvertiser."""

from __future__ import annotations

import pytest

from jupyter_bonjour.advertiser import (
    SERVICE_TYPE,
    BonjourAdvertiser,
    strip_trailing_zeros,
    truncate_service_name,
    truncate_to_txt_limit,
)

# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestStripTrailingZeros:
    def test_all_zeros(self):
        assert strip_trailing_zeros("4.0.0") == "4"

    def test_one_trailing(self):
        assert strip_trailing_zeros("4.3.0") == "4.3"

    def test_no_trailing(self):
        assert strip_trailing_zeros("4.3.1") == "4.3.1"

    def test_single_zero(self):
        assert strip_trailing_zeros("0") == "0"

    def test_ten(self):
        # "10" should not be stripped (does not end with ".0")
        assert strip_trailing_zeros("10") == "10"

    def test_version_10_0(self):
        assert strip_trailing_zeros("10.0") == "10"


class TestTruncateServiceName:
    def test_short_name_unchanged(self):
        assert truncate_service_name("Jupyter on myhost:8888") == "Jupyter on myhost:8888"

    def test_exact_63_bytes_unchanged(self):
        name = "a" * 63
        assert truncate_service_name(name) == name

    def test_long_name_truncated(self):
        # Simulate a CI runner with a very long hostname
        name = "Jupyter on sat12-dp154-b97b8b80-e27c-4f46-8aa9-789adc17c79a-CED78C8A7BC6.local:49230"
        result = truncate_service_name(name)
        assert len(result.encode("utf-8")) <= 63
        assert result.endswith("…")

    def test_multibyte_not_split(self):
        # Fill up to the boundary with multi-byte chars (each é is 2 bytes)
        name = "é" * 32  # 64 bytes > 63
        result = truncate_service_name(name)
        assert len(result.encode("utf-8")) <= 63
        assert result.endswith("…")
        # Should decode cleanly (no partial chars)
        result.encode("utf-8").decode("utf-8")

    def test_constructor_truncates_long_name(self):
        long_name = "Jupyter on " + "x" * 80 + ":8888"
        adv = BonjourAdvertiser(
            8888,
            service_name=long_name,
            properties={},
            parsed_addresses=["192.168.1.1"],
        )
        assert len(adv._service_name.encode("utf-8")) <= 63


class TestTruncateToTxtLimit:
    def test_short_string_unchanged(self):
        assert truncate_to_txt_limit("abc") == "abc"

    def test_exact_limit(self):
        s = "a" * 255
        assert truncate_to_txt_limit(s) == s

    def test_truncated(self):
        # A long comma-separated list gets truncated with ,...
        s = ",".join(f"ext{i}=1.0" for i in range(100))
        result = truncate_to_txt_limit(s)
        assert result.endswith(",...")
        assert len(result.encode("utf-8")) <= 255


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


class TestBonjourAdvertiserInit:
    def test_rejects_zero_port(self):
        with pytest.raises(ValueError, match="port must be positive"):
            BonjourAdvertiser(0, service_name="test", properties={}, parsed_addresses=["192.168.1.1"])

    def test_rejects_negative_port(self):
        with pytest.raises(ValueError, match="port must be positive"):
            BonjourAdvertiser(-1, service_name="test", properties={}, parsed_addresses=["192.168.1.1"])

    def test_rejects_empty_addresses(self):
        with pytest.raises(ValueError, match="parsed_addresses must be non-empty"):
            BonjourAdvertiser(8888, service_name="test", properties={}, parsed_addresses=[])

    @pytest.mark.parametrize(
        "key", ["token", "Token", "password", "PASSWORD", "secret_key", "api_key", "apiKey", "credential"]
    )
    def test_rejects_credential_properties(self, key: str):
        with pytest.raises(ValueError, match="looks like a credential"):
            BonjourAdvertiser(
                8888,
                service_name="test",
                properties={key: "bad"},
                parsed_addresses=["192.168.1.1"],
            )

    def test_accepts_safe_properties(self):
        adv = BonjourAdvertiser(
            8888,
            service_name="test",
            properties={"version": "1.0", "ui": "lab=4"},
            parsed_addresses=["192.168.1.1"],
        )
        assert adv.info.port == 8888

    def test_service_info_type(self):
        adv = BonjourAdvertiser(
            8888,
            service_name="MyServer",
            properties={"version": "2.0"},
            parsed_addresses=["10.0.0.1"],
        )
        assert adv.info.type == SERVICE_TYPE
        assert adv.info.name == f"MyServer.{SERVICE_TYPE}"
        assert adv.info.port == 8888


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestBonjourAdvertiserLifecycle:
    @pytest.mark.asyncio
    async def test_start_registers_service(self, mock_zeroconf):
        adv = BonjourAdvertiser(
            8888,
            service_name="test",
            properties={"version": "1"},
            parsed_addresses=["192.168.1.1"],
        )
        await adv.start()
        zc = mock_zeroconf._instance
        zc.async_register_service.assert_awaited_once_with(adv.info, allow_name_change=True)

    @pytest.mark.asyncio
    async def test_stop_unregisters_and_closes(self, mock_zeroconf):
        adv = BonjourAdvertiser(
            8888,
            service_name="test",
            properties={"version": "1"},
            parsed_addresses=["192.168.1.1"],
        )
        await adv.start()
        await adv.stop()
        zc = mock_zeroconf._instance
        zc.async_unregister_service.assert_awaited_once()
        zc.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self, mock_zeroconf):
        adv = BonjourAdvertiser(
            8888,
            service_name="test",
            properties={"version": "1"},
            parsed_addresses=["192.168.1.1"],
        )
        await adv.start()
        await adv.stop()
        await adv.stop()  # should not raise
        zc = mock_zeroconf._instance
        # Only called once despite two stop() calls
        zc.async_unregister_service.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self, mock_zeroconf):
        adv = BonjourAdvertiser(
            8888,
            service_name="test",
            properties={"version": "1"},
            parsed_addresses=["192.168.1.1"],
        )
        await adv.start()
        await adv.start()  # should not raise or re-register
        zc = mock_zeroconf._instance
        zc.async_register_service.assert_awaited_once()


# ---------------------------------------------------------------------------
# Property updates
# ---------------------------------------------------------------------------


class TestBonjourAdvertiserUpdate:
    @pytest.mark.asyncio
    async def test_update_properties(self, mock_zeroconf):
        adv = BonjourAdvertiser(
            8888,
            service_name="test",
            properties={"version": "1"},
            parsed_addresses=["192.168.1.1"],
        )
        await adv.start()
        await adv.update_properties({"labxtn": "foo=1.2"})
        zc = mock_zeroconf._instance
        zc.async_update_service.assert_awaited_once()
        # New info should contain both old and new properties
        assert adv.info.properties[b"version"] == b"1"
        assert adv.info.properties[b"labxtn"] == b"foo=1.2"

    @pytest.mark.asyncio
    async def test_update_rejects_credentials(self, mock_zeroconf):
        adv = BonjourAdvertiser(
            8888,
            service_name="test",
            properties={"version": "1"},
            parsed_addresses=["192.168.1.1"],
        )
        await adv.start()
        with pytest.raises(ValueError, match="looks like a credential"):
            await adv.update_properties({"token": "bad"})

    @pytest.mark.asyncio
    async def test_update_before_start_is_noop(self, mock_zeroconf):
        adv = BonjourAdvertiser(
            8888,
            service_name="test",
            properties={"version": "1"},
            parsed_addresses=["192.168.1.1"],
        )
        # Should silently return, not raise
        await adv.update_properties({"labxtn": "foo=1"})
        zc = mock_zeroconf._instance
        zc.async_update_service.assert_not_awaited()
