"""Jupyter Server extension that advertises the server via mDNS/Bonjour."""

from __future__ import annotations

import asyncio
import re
import socket
from typing import Any

import ifaddr
from jupyter_server.extension.application import ExtensionApp
from traitlets import Bool, Dict, Set, Unicode

from ._version import __version__
from .advertiser import (
    _DNS_LABEL_MAX_BYTES,
    BonjourAdvertiser,
    strip_trailing_zeros,
    truncate_to_txt_limit,
)

_STRIP_PREFIX = re.compile(r"^(?:jupyterlab[-_]|jupyter[-_])")


def _shorten_extension_name(name: str) -> str:
    """Strip common ``jupyter_`` / ``jupyterlab_`` prefixes for brevity.

    Only strips when there is a separator (``_`` or ``-``) after the prefix,
    so ``jupyterlab`` itself becomes ``lab`` (via the ``jupyter_`` branch)
    but ``jupytext`` is left alone (no separator after ``jupyter``).
    """
    # Special-case: "jupyterlab" itself -> "lab"
    if name == "jupyterlab":
        return "lab"
    return _STRIP_PREFIX.sub("", name)


def _format_extension_list(extensions: dict[str, str]) -> str:
    """Format ``{name: version, ...}`` as a comma-separated TXT-record value.

    Names are shortened and versions have trailing ``.0`` stripped.
    The result is truncated to fit within the 255-byte TXT value limit.
    """
    parts = [f"{_shorten_extension_name(n)}={strip_trailing_zeros(v)}" for n, v in sorted(extensions.items())]
    return truncate_to_txt_limit(",".join(parts))


def _detect_auth_type(serverapp: Any) -> str:
    """Return a short string describing the authentication method."""
    ip_cls = type(serverapp.identity_provider).__name__.lower()
    if "password" in ip_cls:
        return "password"
    if "token" in ip_cls:
        return "token"
    # The default IdentityProvider uses token auth
    if serverapp.identity_provider.token:
        return "token"
    return "none"


def _build_default_service_name(port: int) -> str:
    """Build a default mDNS service name that fits within the 63-byte DNS label limit.

    The format is ``Jupyter on {hostname}:{port}``.  When the hostname is too
    long the hostname portion is truncated (preserving the port, which is the
    most important disambiguator on multi-server machines).
    """
    hostname = socket.gethostname()
    suffix = f":{port}"
    prefix = "Jupyter on "
    budget = _DNS_LABEL_MAX_BYTES - len(prefix.encode("utf-8")) - len(suffix.encode("utf-8"))
    host_bytes = hostname.encode("utf-8")
    if len(host_bytes) > budget:
        ellipsis = "…".encode()  # 3 bytes
        host_bytes = host_bytes[: budget - len(ellipsis)]
        hostname = host_bytes.decode("utf-8", errors="ignore") + "…"
    return f"{prefix}{hostname}{suffix}"


def _resolve_addresses(server_ip: str, allowed_interfaces: set[str]) -> list[str]:
    """Return a list of IPv4 address strings to advertise.

    When the server binds to all interfaces (``""`` or ``"0.0.0.0"``), or to
    ``localhost``/``127.0.0.1``, we enumerate real interface addresses.
    For ``localhost`` we include ``127.0.0.1`` so local discovery still works.

    Only IPv4 addresses are returned — IPv6 link-local (``fe80::``) addresses
    cause problems with many mDNS implementations and are filtered out.
    """
    if server_ip in ("", "0.0.0.0", "localhost", "127.0.0.1"):
        addrs: list[str] = []
        for adapter in ifaddr.get_adapters():
            for ip in adapter.ips:
                # ifaddr returns str for IPv4, tuple for IPv6 — skip IPv6
                if not isinstance(ip.ip, str):
                    continue
                # Skip the entire 127.0.0.0/8 range — we add 127.0.0.1 explicitly below if needed
                if ip.ip.startswith("127."):
                    continue
                if allowed_interfaces and ip.ip not in allowed_interfaces:
                    continue
                addrs.append(ip.ip)
        # For localhost binding, include 127.0.0.1 for local service discovery
        if server_ip in ("localhost", "127.0.0.1"):
            addrs.insert(0, "127.0.0.1")
        return addrs

    # Specific IP given — use it directly (even if it's loopback)
    return [server_ip]


class BonjourExtensionApp(ExtensionApp):
    """Advertise this Jupyter server on the local network via mDNS/Bonjour."""

    name = "jupyter_bonjour"

    enabled = Bool(
        default_value=True,
        help="Whether to advertise the server via mDNS.  Set to False to disable.",
    ).tag(config=True)

    service_name = Unicode(
        default_value="",
        help=(
            "Custom mDNS service name.  Leave empty to auto-generate from the hostname. "
            "Must be unique on the local network."
        ),
    ).tag(config=True)

    interfaces = Set(
        trait=Unicode(),
        default_value=set(),
        help="Restrict advertisement to these IP addresses.  Empty means all non-loopback interfaces.",
    ).tag(config=True)

    extra_properties = Dict(
        key_trait=Unicode(),
        value_trait=Unicode(),
        default_value={},
        help="Additional key-value pairs to include in TXT records.  Credential-like keys are rejected.",
    ).tag(config=True)

    _advertiser: BonjourAdvertiser | None = None

    def _build_properties(self, serverapp: Any) -> dict[str, str]:
        """Assemble the TXT record properties dict."""
        import jupyter_server

        props: dict[str, str] = {
            "version": jupyter_server.__version__,
            "base_url": serverapp.base_url,
            "auth": _detect_auth_type(serverapp),
            "bonjour_version": __version__,
        }

        # Detect frontends (jupyterlab, notebook, nbclassic) and format as ui
        extensions = serverapp.extension_manager.extensions
        ui_frontends: dict[str, str] = {}
        for frontend in ("jupyterlab", "notebook", "nbclassic"):
            if frontend in extensions and extensions[frontend].enabled:
                ui_frontends[frontend] = extensions[frontend].version or "?"
        if ui_frontends:
            props["ui"] = _format_extension_list(ui_frontends)

        # All enabled server extensions
        server_exts: dict[str, str] = {}
        for ext_name, ext_pkg in extensions.items():
            if ext_pkg.enabled:
                server_exts[ext_name] = ext_pkg.version or "?"
        if server_exts:
            props["srvxtn"] = _format_extension_list(server_exts)

        props.update(self.extra_properties)
        return props

    async def _enumerate_lab_extensions(self, serverapp: Any) -> None:
        """Background task: enumerate JupyterLab frontend extensions and update TXT records."""
        extensions = serverapp.extension_manager.extensions
        if "jupyterlab" not in extensions or not extensions["jupyterlab"].enabled:
            return

        try:
            from jupyterlab.commands import get_app_info  # type: ignore[import-untyped]
        except ImportError:
            self.log.debug("jupyterlab.commands not available; skipping lab extension enumeration")
            return

        loop = asyncio.get_running_loop()
        try:
            info = await loop.run_in_executor(None, get_app_info)
        except Exception:
            self.log.debug("Failed to enumerate JupyterLab extensions", exc_info=True)
            return

        lab_exts: dict[str, str] = {}
        for ext in getattr(info, "extensions", None) or []:
            name = getattr(ext, "name", None) or str(ext)
            version = getattr(ext, "version", None) or "?"
            lab_exts[name] = version

        if lab_exts and self._advertiser is not None:
            try:
                await self._advertiser.update_properties({"labxtn": _format_extension_list(lab_exts)})
            except Exception:
                self.log.debug("Failed to update TXT records with lab extensions", exc_info=True)

    async def _start_jupyter_server_extension(self, serverapp: Any) -> None:
        """Called after the event loop and HTTP server are running."""
        if not self.enabled:
            self.log.info("jupyter_bonjour: disabled by configuration")
            return

        addresses = _resolve_addresses(serverapp.ip, self.interfaces)
        if not addresses:
            self.log.warning("jupyter_bonjour: no advertisable addresses found; mDNS skipped")
            return

        service_name = self.service_name or _build_default_service_name(serverapp.port)
        properties = self._build_properties(serverapp)

        try:
            self._advertiser = BonjourAdvertiser(
                serverapp.port,
                service_name=service_name,
                base_url=serverapp.base_url,
                properties=properties,
                parsed_addresses=addresses,
            )
            await self._advertiser.start()
        except Exception:
            self.log.exception("jupyter_bonjour: failed to start mDNS advertisement")
            return

        # Fire-and-forget: enumerate lab extensions in the background
        asyncio.ensure_future(self._enumerate_lab_extensions(serverapp))

    async def stop_extension(self) -> None:
        """Called during server shutdown."""
        if self._advertiser is not None:
            await self._advertiser.stop()
            self._advertiser = None
