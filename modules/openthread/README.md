# openthread — a Thread network node on the ESP32-S31

`import openthread` makes a board a node of a Thread network, on the chip's
own IEEE 802.15.4 radio. One board forms a network and leads it; others join
with its dataset and attach as children or routers, and the nodes talk over
UDP inside the network. It runs ESP-IDF's OpenThread in a task of its own.

```python
import openthread

openthread.start()
openthread.dataset(openthread.dataset_new("garden", channel=25))
openthread.up(True)                       # forms the network: "detached", then "leader"
print(openthread.role(), openthread.info()["extpanid"])
print(openthread.dataset().hex())         # give this to the boards that join

openthread.udp_open(4242)
openthread.udp_send("ff03::1", 4242, b"hello")   # every node on the network
print(openthread.udp_recv())             # ("fd..", 4242, b"..") or None
```

A board that joins sets the same dataset (or just the network key, channel
and PAN ID; it gets the rest from the network once it's on) and calls
`up(True)`. `discover()` and `discovered()` find networks in range by name.
The full API is in [`openthread.pyi`](openthread.pyi). On top of it,
OmniPython's `threadnet` lists Thread networks as `endpointkit` endpoints,
so a picker can form and join them.

It's opt-in: `--modules all` leaves it out, so name it.

```
./build_mp.py --port esp32 --board ESP32_GENERIC_S31 --variant LCD_4_3C \
    --flash 16MB --modules all,openthread
```

[`sdkconfig.esp32s31`](sdkconfig.esp32s31) turns on the radio and OpenThread
as a full Thread device, so a board can lead or route. The stack's heap and
message buffers live in PSRAM. The module builds only for the S31 so far.

## What it doesn't do

The stack has no lwIP interface. UDP goes through OpenThread's own sockets,
so `socket` can't reach a Thread address, and Thread never takes the board's
default route, addresses or DNS from Wi-Fi or Ethernet. There's no border
router: nodes reach each other, not the internet. Commissioning (a joiner
with a passphrase) isn't built in; a node joins with the dataset or the
network key.

Wi-Fi, Bluetooth and Thread share the chip's 2.4 GHz radio time, which
ESP-IDF's coexistence scheduler divides between them. Pick a Thread
channel away from your Wi-Fi's: 25 and 26 sit above Wi-Fi channels 1, 6
and 11.
