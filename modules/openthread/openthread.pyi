# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Make a board a Thread network node on its own 802.15.4 radio.

One board forms a Thread network and leads it; others join with its dataset
and attach as children or routers. Nodes talk over UDP inside the network.
It runs ESP-IDF's OpenThread in a task of its own, on the ESP32-S31.

The stack has no lwIP interface: UDP goes through OpenThread's own sockets
(`udp_open`, `udp_send`, `udp_recv`), so Thread never takes the board's
default route, addresses or DNS from Wi-Fi or Ethernet. No call waits for
the network: what arrives is queued until it's read.
"""

__revision__: str
"""Which source this firmware was built from, from `git describe`: a release
tag, or the nearest one and the commit. "unknown" when the build had no git."""

def start() -> None:
    """Start OpenThread on the board's 802.15.4 radio. Starting again does nothing.

    The network stays down until `up(True)`.

    Raises:
        OSError: the stack or the 802.15.4 radio couldn't start.
    """

def stop() -> None:
    """Leave the network and stop OpenThread. The dataset stays in flash."""

def dataset_new(name: str | None = None, *, channel: int | None = None, panid: int | None = None) -> bytes:
    """A new network's dataset as TLVs, with a random network key and IDs.

    It sets nothing: give it to `dataset` on this board and the others.

    Args:
        name: the network name, 1 to 16 bytes. Default: OpenThread's.
        channel: 11 to 26. Default: a random one.
        panid: 0 to 0xfffe. Default: a random one.
    """

def dataset(tlvs: bytes | None = None) -> bytes | None:
    """The active dataset as TLVs, or None; with *tlvs*, make that the active dataset.

    The active dataset is saved in flash and survives a reset. One being set
    needs at least a network key, a channel and a PAN ID; a node joining
    with only those gets the rest from the network once it's on.

    Raises:
        ValueError: *tlvs* isn't a usable dataset.
    """

def up(on: bool | None = None) -> bool | None:
    """Whether the Thread interface is up; with *on*, bring it up or down.

    Coming up forms the dataset's network, leading it, when no node of it is
    in range, and joins it otherwise.

    Raises:
        OSError: there's no dataset to come up on.
    """

def role() -> str:
    """``"disabled"``, ``"detached"``, ``"child"``, ``"router"`` or ``"leader"``."""

def info() -> dict[str, object]:
    """This node and its network: ``role``, ``name``, ``channel``, ``panid``,
    ``extpanid`` (hex), ``extaddr`` (hex), ``rloc16``, ``mleid`` (its
    mesh-local address) and ``partition``."""

def addresses() -> list[str]:
    """This node's IPv6 addresses on the Thread interface."""

def neighbors() -> list[tuple[str, int, int, bool]]:
    """The nodes this one hears directly, as ``(extaddr hex, rloc16, average RSSI, is_child)``."""

def discover() -> None:
    """Start looking for Thread networks on every channel, for a few seconds.

    It brings the IPv6 side up, which looking needs, and leaves it up.

    Raises:
        OSError: a search is already running, or the radio is busy.
    """

def discovered() -> list[tuple[str, str, int, int, int]] | None:
    """None while `discover` is looking, then what it found, as
    ``(name, extpanid hex, panid, channel, rssi)``."""

def udp_open(port: int) -> None:
    """Listen for UDP on *port*, and send from it. One socket at a time; opening again moves it."""

def udp_close() -> None:
    """Close the UDP socket and drop what was queued."""

def udp_send(addr: str, port: int, data: bytes) -> None:
    """Send *data*, 1024 bytes at most, to IPv6 *addr*.

    *addr* may be multicast: ``"ff03::1"`` reaches every node on the network.

    Raises:
        OSError: no socket is open, or the stack is out of buffers.
    """

def udp_recv() -> tuple[str, int, bytes] | None:
    """The oldest datagram that arrived, as ``(addr, port, data)``, or None, without waiting.

    Eight wait at most; the oldest is dropped when a ninth arrives, and data
    past 256 bytes is cut. `counts` says how often.
    """

def counts() -> tuple[int, int]:
    """``(dropped, truncated)``: datagrams lost because the queue was full, and cut to 256 bytes."""
