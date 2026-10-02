#!/usr/bin/env python3
"""Control a Tribit XSound Go speaker over Bluetooth, without the Tribit app.

Set the speaker address with --mac or the TRIBIT_MAC environment variable.
Disconnect the Tribit phone app first: the speaker accepts one controller at a time.
"""
import argparse
import os
import socket
import time

RFCOMM_CHANNEL = 10
TIMEOUT = 1.5  # seconds to wait for a reply

# Command ids (byte 6 of a packet)
CMD_POWER_OFF = 1
CMD_BATTERY = 2
CMD_GET_EQ = 5
CMD_VERSION = 6
CMD_SET_SLEEP = 11
CMD_GET_SLEEP = 17  # reply: [hour, minute, auto_off]
CMD_SET_EQ = 0x82
CMD_SET_AUTO_OFF = 140
CMD_SET_VOICE = 144
CMD_GET_VOICE = 145

EQ_PRESETS = {"xbass": 1, "audiobook": 2, "classical": 3, "rock": 4, "jazz": 5}
EQ_CUSTOM = 254
EQ_BANDS = ["80Hz", "150Hz", "300Hz", "600Hz", "1.2kHz", "2.5kHz", "5kHz", "9kHz", "13kHz"]
EQ_RANGE = range(-8, 9)  # gain is sent offset by +8, i.e. 0..16
SLEEP_OFF = 255
VOICE_PROMPTS = ["power", "pairing", "low_battery", "max_volume", "tws"]


def packet(cmd, payload=()):
    """08 EE 00 00 00 01 <cmd> <len lo> <len hi> <payload...> <checksum>.

    len is the whole packet length; checksum is the sum of all previous bytes.
    """
    length = 10 + len(payload)
    body = bytes([0x08, 0xEE, 0, 0, 0, 1, cmd, length & 0xFF, length >> 8, *payload])
    return body + bytes([sum(body) & 0xFF])


class Speaker:
    def __init__(self, mac):
        # The speaker refuses (EBUSY) for a moment after a previous session closes.
        for attempt in range(5):
            self.sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            self.sock.settimeout(TIMEOUT)
            try:
                self.sock.connect((mac, RFCOMM_CHANNEL))
                break
            except OSError:
                self.sock.close()
                if attempt == 4:
                    raise
                time.sleep(1)
        time.sleep(0.5)  # a command sent right after connecting can be dropped

    def close(self):
        time.sleep(0.3)  # let the speaker apply the last command before hanging up
        self.sock.close()

    def request(self, cmd, payload=()):
        """Send a command and return the payload of its reply (b"" if none)."""
        self.sock.send(packet(cmd, payload))
        buf = b""
        try:
            while True:
                buf += self.sock.recv(1024)
                # Replies look like requests (09 FF ... header); split them by length field.
                while len(buf) >= 9:
                    length = buf[7] | buf[8] << 8
                    if length == 0 or len(buf) < length:
                        break
                    frame, buf = buf[:length], buf[length:]
                    if frame[6] == cmd:
                        return frame[9:-1]
        except (TimeoutError, ConnectionResetError):  # reset: speaker powered off
            return b""

    def status(self):
        eq = self.request(CMD_GET_EQ)
        hour, minute, auto_off = self.request(CMD_GET_SLEEP)[:3]
        voice = self.request(CMD_GET_VOICE)[:5]
        v = self.request(CMD_VERSION)

        names = {mode: name for name, mode in EQ_PRESETS.items()}
        if eq[0] == EQ_CUSTOM:
            eq_text = "custom " + " ".join(f"{b}:{g - 8:+d}" for b, g in zip(EQ_BANDS, eq[1:]))
        else:
            eq_text = names.get(eq[0], f"unknown ({eq[0]})")

        print(f"battery:  {self.request(CMD_BATTERY)[0]}%")
        print(f"eq:       {eq_text}")
        print(f"sleep:    {'off' if hour == SLEEP_OFF else f'{hour}:{minute:02}'}")
        print(f"auto-off: {'on' if auto_off else 'off'}")
        print("voice:    " + " ".join(f"{n}={'on' if x else 'off'}" for n, x in zip(VOICE_PROMPTS, voice)))
        print("firmware: %d/%d/%d v%d.%d.%d" % tuple(v[:6]))

    def set_eq_preset(self, name):
        self.request(CMD_SET_EQ, [EQ_PRESETS[name]] + [0] * 9)

    def set_eq_custom(self, gains):
        self.request(CMD_SET_EQ, [EQ_CUSTOM] + [g + 8 for g in gains])

    def set_sleep(self, hours, minutes):
        if hours * 60 + minutes <= 0:  # same as the app: 0:00 means off
            hours = minutes = SLEEP_OFF
        self.request(CMD_SET_SLEEP, [hours, minutes])

    def set_auto_off(self, on):
        self.request(CMD_SET_AUTO_OFF, [int(on)])

    def set_voice(self, flags):
        self.request(CMD_SET_VOICE, [int(f) for f in flags])

    def power_off(self):
        self.request(CMD_POWER_OFF)


def on_off(text):
    if text not in ("on", "off"):
        raise argparse.ArgumentTypeError("expected on or off")
    return text == "on"


def gain(text):
    value = int(text)
    if value not in EQ_RANGE:
        raise argparse.ArgumentTypeError("gain must be between -8 and 8")
    return value


def sleep_time(text):
    if text == "off":
        return 0, 0
    try:
        hours, minutes = map(int, text.split(":"))
    except ValueError:
        raise argparse.ArgumentTypeError("expected H:MM or off")
    if not (0 <= hours < 24 and 0 <= minutes < 60):
        raise argparse.ArgumentTypeError("expected H:MM or off")
    return hours, minutes


def voice_flags(values):
    if values in (["on"], ["off"]):
        return [values[0] == "on"] * 5
    if len(values) == 5 and all(v in ("0", "1") for v in values):
        return [v == "1" for v in values]
    raise SystemExit("voice: expected on, off, or 5 values of 0/1 (" + " ".join(VOICE_PROMPTS) + ")")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mac", default=os.environ.get("TRIBIT_MAC"), help="speaker Bluetooth address")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="show battery, EQ, sleep timer, auto-off, voice prompts, firmware")
    eq = sub.add_parser("eq", help="set an EQ preset or custom curve")
    eq.add_argument("preset", choices=[*EQ_PRESETS, "custom"])
    eq.add_argument("gains", nargs="*", type=gain, help="9 gains (-8..8) for custom: " + " ".join(EQ_BANDS))
    sleep = sub.add_parser("sleep", help="sleep timer, H:MM or off")
    sleep.add_argument("time", type=sleep_time)
    auto = sub.add_parser("autooff", help="auto power-off when idle")
    auto.add_argument("state", type=on_off)
    voice = sub.add_parser("voice", help="voice prompts: on, off, or 5 flags " + " ".join(VOICE_PROMPTS))
    voice.add_argument("values", nargs="+")
    sub.add_parser("poweroff", help="turn the speaker off")

    args = parser.parse_args()
    if not args.mac:
        parser.error("speaker address required: --mac XX:XX:XX:XX:XX:XX or TRIBIT_MAC")
    if args.command == "eq" and (len(args.gains) != 9 if args.preset == "custom" else args.gains):
        parser.error("eq custom needs exactly 9 gains; presets take none")
    flags = voice_flags(args.values) if args.command == "voice" else None

    speaker = Speaker(args.mac)
    try:
        if args.command == "status":
            speaker.status()
        elif args.command == "eq" and args.preset == "custom":
            speaker.set_eq_custom(args.gains)
        elif args.command == "eq":
            speaker.set_eq_preset(args.preset)
        elif args.command == "sleep":
            speaker.set_sleep(*args.time)
        elif args.command == "autooff":
            speaker.set_auto_off(args.state)
        elif args.command == "voice":
            speaker.set_voice(flags)
        elif args.command == "poweroff":
            speaker.power_off()
    finally:
        speaker.close()


if __name__ == "__main__":
    main()
