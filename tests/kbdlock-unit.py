#!/usr/bin/python3
"""KeyboardLock without a VT, for machines whose volume keys belong to the
console keymap (where the daemon itself refuses to lock). Run as root.

With a virtual keyboard and touchpad: lock() grabs the keyboard (another
reader gets nothing) and inhibits the touchpad; a lone volume press acts
once, after CHORD_SECONDS; both volume keys together unlock without acting;
auto-repeat acts; a new KeyboardLock (a restarted daemon) puts back the
touchpad a killed one left inhibited.
"""
import fcntl
import importlib.machinery
import importlib.util
import os
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
loader = importlib.machinery.SourceFileLoader(
    "daemon", os.path.join(HERE, "..", "tty-i3-keys"))
spec = importlib.util.spec_from_loader("daemon", loader)
d = importlib.util.module_from_spec(spec)
loader.exec_module(d)

vt = importlib.util.module_from_spec(importlib.util.spec_from_loader(
    "vt", importlib.machinery.SourceFileLoader(
        "vt", os.path.join(HERE, "vt-test.py"))))
os.environ.setdefault("SUDO_USER", "root")
vt.__spec__.loader.exec_module(vt)

E = struct.Struct("llHHi")


class NullBar:
    def __init__(self):
        self.messages = []

    def notify(self, text, level=None):
        self.messages.append(text)


def keyboard():
    fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
    fcntl.ioctl(fd, vt.UI_SET_EVBIT, 1)
    for k in (vt.KEY_A, vt.KEY_S, vt.KEY_LEFTMETA, vt.KEY_VOLUMEUP,
              vt.KEY_VOLUMEDOWN):
        fcntl.ioctl(fd, vt.UI_SET_KEYBIT, k)
    fcntl.ioctl(fd, vt.UI_DEV_SETUP, struct.pack(
        "4H80sI", 3, 1, 1, 1, b"kbdlock unit keyboard", 0))
    fcntl.ioctl(fd, vt.UI_DEV_CREATE)
    time.sleep(0.3)
    for dev in os.listdir("/sys/class/input"):
        name = f"/sys/class/input/{dev}/name"
        if dev.startswith("event") and open(
                f"/sys/class/input/{dev}/device/name").read().strip() \
                == "kbdlock unit keyboard":
            return fd, f"/dev/input/{dev}"
    raise RuntimeError("keyboard not found")


def main():
    active = subprocess.run(["systemctl", "is-active", "--quiet",
                             "tty-i3-keys"]).returncode == 0
    if active:      # it would act on the virtual keys too
        subprocess.run(["systemctl", "stop", "tty-i3-keys"], check=True)
    kb, path = keyboard()
    tp, tp_dev = vt.touchpad()
    inhibited = lambda: open(f"{tp_dev}/inhibited").read().strip()
    failures = 0
    try:
        ours = os.open(path, os.O_RDONLY | os.O_NONBLOCK)     # the daemon's fd
        other = os.open(path, os.O_RDONLY | os.O_NONBLOCK)    # e.g. the console
        bar, acted = NullBar(), []
        lock = d.KeyboardLock({vt.KEY_VOLUMEUP, vt.KEY_VOLUMEDOWN})
        fds = {ours: path}

        def drain(fd):
            try:
                return [E.unpack_from(b, i)[3:] for b in [os.read(fd, 4096)]
                        for i in range(0, len(b), E.size)
                        if E.unpack_from(b, i)[2] == 1]
            except BlockingIOError:
                return []

        lock.lock(fds, bar)
        vt.chord(kb, vt.KEY_A)
        failures += vt.check("locked: the other reader gets nothing, we do",
                             f"{drain(other)} {len(drain(ours)) > 0}".encode(),
                             b"[] True")
        failures += vt.check("locked: touchpad inhibited", inhibited().encode(),
                             b"1")

        held = set()

        def press(code, value):
            if value:
                held.add(code)
            else:
                held.discard(code)
            lock.volume_key(code, value, held, fds, bar, acted.append)

        press(vt.KEY_VOLUMEUP, 1)
        early = list(acted)
        time.sleep(d.CHORD_SECONDS + 0.05)
        lock.tick(acted.append)
        press(vt.KEY_VOLUMEUP, 0)
        failures += vt.check("lone volume press acts once, after the wait",
                             f"{early} {acted}".encode(), b"[] [115]")

        acted.clear()
        press(vt.KEY_VOLUMEDOWN, 1)
        press(vt.KEY_VOLUMEDOWN, 2)
        press(vt.KEY_VOLUMEDOWN, 2)
        press(vt.KEY_VOLUMEDOWN, 0)
        failures += vt.check("auto-repeat acts on every repeat",
                             str(acted).encode(), b"[114, 114, 114]")

        acted.clear()
        press(vt.KEY_VOLUMEDOWN, 1)
        press(vt.KEY_VOLUMEUP, 1)
        press(vt.KEY_VOLUMEUP, 2)
        press(vt.KEY_VOLUMEUP, 0)
        press(vt.KEY_VOLUMEDOWN, 0)
        time.sleep(d.CHORD_SECONDS + 0.05)
        lock.tick(acted.append)
        vt.chord(kb, vt.KEY_S)
        failures += vt.check("chord unlocks without acting; keys flow again",
                             f"{lock.locked} {acted} {inhibited()} "
                             f"{len(drain(other)) > 0}".encode(),
                             b"False [] 0 True")

        # A pair more than CHORD_SECONDS apart is no chord: the first acts.
        acted.clear()
        press(vt.KEY_VOLUMEDOWN, 1)
        time.sleep(d.CHORD_SECONDS + 0.05)
        lock.tick(acted.append)
        press(vt.KEY_VOLUMEUP, 1)
        press(vt.KEY_VOLUMEUP, 0)
        press(vt.KEY_VOLUMEDOWN, 0)
        failures += vt.check("a late pair is two volume steps, not a chord",
                             f"{lock.locked} {acted}".encode(),
                             b"False [114, 115]")

        # A keyboard without volume buttons cannot be locked: no way out.
        plain = os.open("/dev/null", os.O_RDONLY)
        lock.lock({plain: "/dev/null"}, bar)
        failures += vt.check("no volume buttons: lock refused",
                             f"{lock.locked} {inhibited()}".encode(), b"False 0")
        os.close(plain)

        # The volume-button keyboard unplugged while locked: unlocked.
        lock.lock(fds, bar)
        lock.forget(ours, {}, bar)
        failures += vt.check("volume keyboard gone while locked: unlocked",
                             f"{lock.locked} {inhibited()}".encode(), b"False 0")
        fcntl.ioctl(ours, d.EVIOCGRAB, 0)   # it did not really go away

        lock.lock(fds, bar)
        restarted = d.KeyboardLock({vt.KEY_VOLUMEUP, vt.KEY_VOLUMEDOWN})
        failures += vt.check("a restarted daemon puts back the touchpad",
                             f"{inhibited()} {os.path.exists(d.POINTERS_STATE)}"
                             .encode(), b"0 False")
        print("  bar:", bar.messages)
        os.close(ours)
        os.close(other)
    finally:
        fcntl.ioctl(kb, vt.UI_DEV_DESTROY)
        fcntl.ioctl(tp, vt.UI_DEV_DESTROY)
        if active:
            subprocess.run(["systemctl", "start", "tty-i3-keys"])
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
