# tribit-control

Control a **Tribit XSound Go** Bluetooth speaker from Linux without the
proprietary Tribit Android app. A single Python file, standard library only.

The protocol was reverse engineered from the decompiled Tribit Android app,
version 4.6.5.

## Tested hardware

| Model | Firmware |
|-------|----------|
| Tribit XSound Go | 24/8/5 v1.3.6 |

Other Tribit models use the same app and likely a similar protocol, but are
untested. Reports welcome.

## Requirements

- Linux with BlueZ (uses Python's `AF_BLUETOOTH` / RFCOMM sockets; not available on macOS/Windows)
- Python 3.8+
- The speaker paired and connected to your computer
- The Tribit phone app **disconnected**: the speaker accepts only one control connection at a time

## Usage

Find your speaker address with `bluetoothctl devices`, then either pass
`--mac` or set `TRIBIT_MAC`:

```sh
export TRIBIT_MAC=XX:XX:XX:XX:XX:XX
```

```sh
# Show everything
./tribit.py status
# battery:  100%
# eq:       xbass
# sleep:    off
# auto-off: off
# voice:    power=on pairing=on low_battery=on max_volume=on tws=on
# firmware: 24/8/5 v1.3.6

# EQ presets: xbass, audiobook, classical, rock, jazz
./tribit.py eq rock

# Custom EQ: 9 gains from -8 to 8 for 80Hz 150Hz 300Hz 600Hz 1.2kHz 2.5kHz 5kHz 9kHz 13kHz
./tribit.py eq custom 4 3 1 0 0 0 1 2 3

# Sleep timer (power off after H:MM), or disable it
./tribit.py sleep 1:30
./tribit.py sleep off

# Auto power-off when idle
./tribit.py autooff on

# Voice prompts: all on/off, or 5 flags (power pairing low_battery max_volume tws)
./tribit.py voice off
./tribit.py voice 1 1 1 1 0

# Turn the speaker off
./tribit.py poweroff
```

## Features

| Feature | Command | Tested |
|---------|---------|--------|
| Battery level | `status` | yes |
| Firmware version | `status` | yes |
| EQ presets | `eq <preset>` | yes |
| Custom 9-band EQ | `eq custom ...` | yes |
| Sleep timer | `sleep H:MM` / `sleep off` | yes |
| Auto power-off | `autooff on/off` | yes |
| Voice prompts | `voice ...` | yes |
| Power off | `poweroff` | yes |

`status` shows the configured sleep timer value, not the remaining time.

## Protocol

RFCOMM channel 10 (SDP service UUID `0cf12d31-fac3-4553-bd80-d6832e7b3119`).

Request:

```
08 EE 00 00 00 01 <cmd> <len lo> <len hi> <payload...> <checksum>
```

`len` is the total packet length (10 + payload length), `checksum` is the sum
of all previous bytes modulo 256. Replies have the same layout with the header
`09 FF 00 00 01 01`. Set commands are acknowledged with an empty-payload reply.

| Cmd | Meaning | Payload |
|-----|---------|---------|
| `0x01` | power off | none |
| `0x02` | get battery | reply: `[percent]` |
| `0x05` | get EQ | reply: `[mode, 9 gains]` |
| `0x06` | get firmware version | reply: `[y, m, d, major, minor, patch]` |
| `0x0B` | set sleep timer | `[hours, minutes]`, `FF FF` = off |
| `0x11` | get sleep/auto-off | reply: `[hours, minutes, auto_off]` |
| `0x82` | set EQ | `[mode, 9 gains]`, gains offset by +8 (0..16) |
| `0x8C` | set auto power-off | `[0/1]` |
| `0x90` | set voice prompts | 5 flags: power, pairing, low battery, max volume, TWS |
| `0x91` | get voice prompts | reply: same 5 flags |

EQ modes: 1 XBass, 2 Audiobook, 3 Classical, 4 Rock, 5 Jazz, 254 Custom.
Presets send zero gains.

## Troubleshooting

- `Connection refused`: the phone app is still connected to the speaker, or the speaker is off.
- `Device or resource busy`: the script retries automatically; the speaker needs a moment after the previous connection.

## License

MIT, see [LICENSE](LICENSE).

## Disclaimer

Not affiliated with or endorsed by Tribit. Use at your own risk.
