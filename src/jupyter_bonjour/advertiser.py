"""mDNS/Bonjour service advertisement for Jupyter servers."""

from __future__ import annotations

import logging
import re
import socket

from zeroconf import ServiceInfo, Zeroconf

logger = logging.getLogger(__name__)

SERVICE_TYPE = "_jupyter._tcp.local."
_TXT_VALUE_MAX_BYTES = 255
_DNS_LABEL_MAX_BYTES = 63
_CREDENTIAL_KEY_PATTERN = re.compile(r"^(token|password|secret|credential|api.?key)", re.IGNORECASE)


def strip_trailing_zeros(version: str) -> str:
    """Strip trailing '.0' segments from a version string.

    ``4.0.0`` → ``4``, ``4.3.0`` → ``4.3``, ``4.3.1`` → ``4.3.1``
    """
    while version.endswith(".0"):
        version = version[:-2]
    return version


def truncate_to_txt_limit(value: str, *, limit: int = _TXT_VALUE_MAX_BYTES) -> str:
    """Truncate a TXT record value to fit within the per-value byte limit.

    If truncation is needed, the value is cut and ``,...`` is appended so that
    consumers know the list is incomplete.
    """
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    suffix = b",..."
    truncated = encoded[: limit - len(suffix)]
    # Avoid splitting a multi-byte character by decoding with error handling
    return truncated.decode("utf-8", errors="ignore").rsplit(",", 1)[0] + ",..."


def truncate_service_name(name: str, *, limit: int = _DNS_LABEL_MAX_BYTES) -> str:
    """Truncate an mDNS service instance name to fit in a single DNS label.

    DNS labels are limited to 63 bytes.  If *name* exceeds that, it is
    truncated and an ellipsis (``…``) is appended, staying within *limit*.
    Multi-byte UTF-8 characters are never split.
    """
    encoded = name.encode("utf-8")
    if len(encoded) <= limit:
        return name
    suffix = "…".encode()  # 3 bytes
    truncated = encoded[: limit - len(suffix)]
    # Avoid splitting a multi-byte character
    result = truncated.decode("utf-8", errors="ignore") + "…"
    logger.warning("Service name truncated from %d to %d bytes: %r", len(encoded), len(result.encode("utf-8")), result)
    return result


def _validate_properties(properties: dict[str, str]) -> None:
    """Raise ``ValueError`` if any property key looks like a credential."""
    for key in properties:
        if _CREDENTIAL_KEY_PATTERN.match(key):
            msg = f"Refusing to advertise property {key!r}: looks like a credential"
            raise ValueError(msg)


class BonjourAdvertiser:
    """Manages the lifecycle of a single ``_jupyter._tcp`` mDNS service registration."""

    def __init__(
        self,
        port: int,
        *,
        service_name: str,
        base_url: str = "/",
        properties: dict[str, str],
        parsed_addresses: list[str],
    ) -> None:
        if port <= 0:
            msg = f"port must be positive, got {port}"
            raise ValueError(msg)
        if not parsed_addresses:
            msg = "parsed_addresses must be non-empty"
            raise ValueError(msg)
        _validate_properties(properties)

        self._port = port
        self._service_name = truncate_service_name(service_name)
        self._properties = dict(properties)
        self._parsed_addresses = list(parsed_addresses)

        hostname = socket.gethostname()
        # Avoid double .local suffix — gethostname() often returns "host.local" on macOS
        server = f"{hostname}." if hostname.endswith(".local") else f"{hostname}.local."
        fqdn = f"{self._service_name}.{SERVICE_TYPE}"

        self._info = ServiceInfo(
            SERVICE_TYPE,
            fqdn,
            port=port,
            properties=self._properties,
            server=server,
            parsed_addresses=self._parsed_addresses,
        )
        self._zeroconf: Zeroconf | None = None
        self._started = False

    @property
    def info(self) -> ServiceInfo:
        """The ``ServiceInfo`` being advertised (for inspection/testing)."""
        return self._info

    async def start(self) -> None:
        """Register the service on the network."""
        if self._started:
            return
        self._zeroconf = Zeroconf()
        await self._zeroconf.async_register_service(self._info, allow_name_change=True)
        self._started = True
        logger.info("Advertising %s on port %d", self._info.name, self._port)

    async def update_properties(self, new_properties: dict[str, str]) -> None:
        """Merge *new_properties* into the TXT record and push an update.

        Raises ``ValueError`` if any new key looks like a credential.
        Silently returns if the advertiser has not been started.
        """
        if not self._started or self._zeroconf is None:
            return
        _validate_properties(new_properties)
        self._properties.update(new_properties)
        self._info = ServiceInfo(
            SERVICE_TYPE,
            self._info.name,
            port=self._port,
            properties=self._properties,
            server=self._info.server,
            parsed_addresses=self._parsed_addresses,
        )
        await self._zeroconf.async_update_service(self._info)
        logger.info("Updated TXT records for %s", self._info.name)

    async def stop(self) -> None:
        """Unregister the service and close zeroconf.  Idempotent and exception-safe."""
        if not self._started or self._zeroconf is None:
            return
        self._started = False
        zc = self._zeroconf
        self._zeroconf = None
        try:
            await zc.async_unregister_service(self._info)
        except Exception:
            logger.debug("Error unregistering mDNS service (may be expected during shutdown)", exc_info=True)
        try:
            zc.close()
        except Exception:
            logger.debug("Error closing Zeroconf (may be expected during shutdown)", exc_info=True)
        logger.info("Stopped advertising %s", self._info.name)
