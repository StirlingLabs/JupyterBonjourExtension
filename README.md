# jupyter-bonjour

A Jupyter Server extension that advertises running servers on the local network
via mDNS/Bonjour (zeroconf) service discovery.

Install it, and every Jupyter server on your LAN becomes discoverable — no
configuration required. Other machines can find servers automatically using any
Bonjour/Avahi/mDNS client.

## What gets advertised

Each server registers a `_jupyter._tcp.local.` service with the following
metadata in its DNS TXT record:

| Key | Example | Description |
|-----|---------|-------------|
| `version` | `2.14` | Jupyter Server version |
| `auth` | `token` | Authentication method (`token`, `password`, or `none`) |
| `base_url` | `/` | Server base URL |
| `bonjour_version` | `0.1` | This extension's version |
| `ui` | `lab=4.3,notebook=7.2` | Enabled UI frontends |
| `srvxtn` | `git=0.50,collaboration=0.9` | Enabled server extensions |
| `labxtn` | `@jupyterlab/toc=6.0` | JupyterLab frontend extensions |

Extension names are shortened for brevity (`jupyter_server_` and `jupyterlab_`
prefixes are stripped), and version strings are compacted (`4.0.0` becomes `4`).

Credential-like keys (`token`, `password`, `secret`, `api_key`) are always
rejected to prevent accidental leakage onto the network.

## Installation

```
pip install jupyter-bonjour
```

The extension is auto-enabled on install. Just start Jupyter as usual:

```
jupyter lab
```

Your server is now discoverable on the local network.

## Configuration

All settings are optional. Add them to `jupyter_server_config.py` if needed:

```python
c.BonjourExtensionApp.enabled = True                  # set False to disable
c.BonjourExtensionApp.service_name = "My Lab Server"   # custom mDNS name
c.BonjourExtensionApp.interfaces = {"192.168.1.100"}   # restrict to specific IPs
c.BonjourExtensionApp.extra_properties = {              # custom TXT record entries
    "room": "301",
    "owner": "rj",
}
```

By default the service name is `Jupyter on <hostname>:<port>` and all
non-loopback interfaces are advertised.

## Discovering servers

### Command line

On macOS:

```
dns-sd -B _jupyter._tcp local.
```

On Linux (with Avahi):

```
avahi-browse -r _jupyter._tcp
```

### Python

```python
from zeroconf import ServiceBrowser, Zeroconf

def on_service_state_change(zeroconf, service_type, name, state_change):
    if state_change.name == "Added":
        info = zeroconf.get_service_info(service_type, name)
        if info:
            addrs = [addr for addr in info.parsed_addresses()]
            port = info.port
            props = {k.decode(): v.decode() for k, v in info.properties.items()}
            print(f"{name} @ {addrs[0]}:{port}  auth={props.get('auth')}")

zc = Zeroconf()
browser = ServiceBrowser(zc, "_jupyter._tcp.local.", handlers=[on_service_state_change])
input("Listening... press Enter to exit\n")
zc.close()
```

## Use cases

- **Labs and classrooms** — students and instructors can discover each other's
  servers without exchanging URLs
- **Headless machines** — find a Jupyter server running on a Raspberry Pi or
  remote workstation without remembering its IP
- **Multi-server setups** — see all Jupyter instances on the network at a glance
- **Custom tooling** — build dashboards or launchers that auto-discover Jupyter
  services

## Requirements

- Python 3.10+
- Jupyter Server 2.0+

## License

BSD-3-Clause
