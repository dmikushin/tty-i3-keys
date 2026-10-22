#!/usr/bin/python3
"""End-to-end test of tty-i3-keys on a real VT. Run as root (sudo), from the
account whose tmux, PipeWire and lid toggle script are tested ($SUDO_USER).

Briefly switches to a spare VT, drives a virtual keyboard through uinput and
checks:
  1. typing: plain digits, Shift, Ctrl and the Cyrillic lock still type; Win+1
     and the handled media keys type nothing; keys the console keymap toggle
     file maps on purpose (Fn+Left/Right on the 3a5000) still type theirs;
  2. brightness keys change /sys/class/backlight (restored afterwards);
  3. a real tmux on that VT: Win+2, Win+3, Win+1 select those windows;
  4. volume and mute keys change the user's PipeWire volume (restored), and
     the level is shown in tmux;
  5. Win+Shift+S toggles the lid-switch inhibitor, twice = back as it was;
  6. the console keymap is restored when the daemon stops.
Then switches back to the original VT and restarts the installed service.
"""
import fcntl
import glob
import os
import pwd
import struct
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DAEMON = os.path.join(HERE, "..", "tty-i3-keys")
VT = 12
TTY = f"/dev/tty{VT}"
USER = pwd.getpwnam(os.environ["SUDO_USER"])

EV_SYN, EV_KEY = 0, 1
KEY_1, KEY_2, KEY_3, KEY_A, KEY_Q, KEY_S = 2, 3, 4, 30, 16, 31
KEY_LEFTCTRL, KEY_LEFTSHIFT, KEY_CAPSLOCK, KEY_LEFTMETA = 29, 42, 58, 125
KEY_MUTE, KEY_VOLUMEDOWN, KEY_VOLUMEUP = 113, 114, 115
KEY_BRIGHTNESSDOWN, KEY_BRIGHTNESSUP = 224, 225
KEYS = (KEY_1, KEY_2, KEY_3, KEY_A, KEY_Q, KEY_S, KEY_LEFTCTRL,
        KEY_LEFTSHIFT, KEY_CAPSLOCK, KEY_LEFTMETA, KEY_MUTE, KEY_VOLUMEDOWN,
        KEY_VOLUMEUP, KEY_BRIGHTNESSDOWN, KEY_BRIGHTNESSUP)
UI_SET_EVBIT, UI_SET_KEYBIT = 0x40045564, 0x40045565
UI_DEV_SETUP, UI_DEV_CREATE, UI_DEV_DESTROY = 0x405C5503, 0x5501, 0x5502
EVENT = struct.Struct("llHHi")
SERVICES = ("tty-i3-keys", "tty-lid-toggle-hotkey")
# Console strings of the keysyms the 3a5000 toggle map gives 114/115.
TOGGLE_OUTPUT = {KEY_VOLUMEDOWN: b"\033[1~", KEY_VOLUMEUP: b"\033[4~"}

READER = r"""
import os, sys, tty, time, select
out, seconds = sys.argv[1], float(sys.argv[2])
fd = sys.stdin.fileno()
tty.setraw(fd)
os.write(1, b"\033[H\033[2Jtty-i3-keys test: the keyboard is grabbed for 15 s\r\n")
got = b""
end = time.time() + seconds
while time.time() < end:
    if select.select([fd], [], [], 0.05)[0]:
        got += os.read(fd, 1024)
open(out, "wb").write(got)
"""


def grab_keyboards():
    """Grab the real keyboards for the test, so what the person at the
    machine types does not mix into the VT under test. The grabs end when
    the fds close, at the latest when this process exits."""
    fds = []
    for path in glob.glob("/dev/input/event*"):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            bits = bytearray(96)
            fcntl.ioctl(fd, 0x80604521, bits)       # EVIOCGBIT(EV_KEY, 96)
            if bits[KEY_A // 8] >> (KEY_A % 8) & 1:
                fcntl.ioctl(fd, 0x40044590, 1)      # EVIOCGRAB
                fds.append(fd)
            else:
                os.close(fd)
        except OSError:
            pass
    return fds


def uinput():
    fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
    fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
    for k in KEYS:
        fcntl.ioctl(fd, UI_SET_KEYBIT, k)
    fcntl.ioctl(fd, UI_DEV_SETUP, struct.pack("4H80sI", 3, 1, 1, 1,
                                              b"tty-i3-keys test keyboard", 0))
    fcntl.ioctl(fd, UI_DEV_CREATE)
    return fd


def emit(fd, code, value):
    os.write(fd, EVENT.pack(0, 0, EV_KEY, code, value))
    os.write(fd, EVENT.pack(0, 0, EV_SYN, 0, 0))
    time.sleep(0.08)


def chord(kb, *keys):
    for k in keys:
        emit(kb, k, 1)
    for k in reversed(keys):
        emit(kb, k, 0)


def as_user(*argv):
    return subprocess.run(
        argv, user=USER.pw_uid, group=USER.pw_gid,
        env={"HOME": USER.pw_dir, "PATH": "/usr/local/bin:/usr/bin",
             "XDG_RUNTIME_DIR": f"/run/user/{USER.pw_uid}"},
        capture_output=True, text=True).stdout.strip()


def keymap_entries():
    fd = os.open("/dev/tty0", os.O_RDONLY | os.O_NOCTTY)
    out = []
    for table in range(256):
        for key in (0, 125, 126, 113, 114, 115, 224, 225):
            buf = bytearray(struct.pack("BBH", table, key, 0))
            fcntl.ioctl(fd, 0x4B46, buf)        # KDGKBENT
            out.append(struct.unpack("BBH", buf)[2])
    os.close(fd)
    return out


def toggle_keys():
    """Keycodes of the KEYMAP_TOGGLE file, as the daemon reads them."""
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("daemon", DAEMON)
    spec = importlib.util.spec_from_loader("daemon", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.console_toggle_keys()


def run_reader(seconds, actions):
    out = tempfile.mktemp()
    script = tempfile.mktemp(suffix=".py")
    open(script, "w").write(READER)
    subprocess.run(["openvt", "-c", str(VT), "-f", "--", "python3", script,
                    out, str(seconds)], check=True)
    subprocess.run(["chvt", str(VT)], check=True)
    time.sleep(0.5)
    actions()
    while not os.path.exists(out):
        time.sleep(0.1)
    time.sleep(0.1)
    return open(out, "rb").read()


def check(name, got, expected):
    ok = got == expected
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if not ok:
        print(f"  expected {expected!r}\n  got      {got!r}")
    return 0 if ok else 1


def backlight():
    path = sorted(glob.glob("/sys/class/backlight/*/brightness"))[0]
    return path, int(open(path).read())


def inhibited():
    return "i3-lid-toggle" in subprocess.run(
        ["systemd-inhibit", "--list", "--no-pager"],
        capture_output=True, text=True).stdout


def main():
    original_vt = open("/sys/class/tty/tty0/active").read().strip()[3:]
    active = [s for s in SERVICES if subprocess.run(
        ["systemctl", "is-active", "--quiet", s]).returncode == 0]
    for s in active:
        subprocess.run(["systemctl", "stop", s], check=True)
    keymap_before = keymap_entries()
    reserved = toggle_keys()
    bl_path, bl_before = backlight()
    vol_before = as_user("pamixer", "--get-volume")
    mute_before = as_user("pamixer", "--get-mute")
    inhibited_before = inhibited()
    grabbed = grab_keyboards()
    kb = uinput()
    time.sleep(0.3)
    daemon = subprocess.Popen([sys.executable, DAEMON])
    time.sleep(0.8)
    failures = 0
    tmux = ["tmux", "-L", "tty-i3-keys-test"]
    try:
        # 1. Typing on a root-owned VT (no user: volume does nothing there).
        def typing():
            chord(kb, KEY_1)
            chord(kb, KEY_LEFTMETA, KEY_1)
            chord(kb, KEY_LEFTSHIFT, KEY_1)
            chord(kb, KEY_LEFTCTRL, KEY_A)
            chord(kb, KEY_CAPSLOCK)                 # Cyrillic lock
            chord(kb, KEY_Q)
            chord(kb, KEY_CAPSLOCK)
            chord(kb, KEY_Q)
            for key in (KEY_MUTE, KEY_VOLUMEDOWN, KEY_VOLUMEUP):
                chord(kb, key)
            chord(kb, KEY_2)

        got = run_reader(3.0, typing)
        expected = b"1!\x01" + "й".encode() + b"q"
        expected += b"".join(TOGGLE_OUTPUT[k] for k in
                             (KEY_VOLUMEDOWN, KEY_VOLUMEUP) if k in reserved)
        expected += b"2"
        failures += check("typing; Win+1 and media keys type nothing", got,
                          expected)

        # 2. Brightness (acts on any VT).
        def bright():
            chord(kb, KEY_BRIGHTNESSDOWN)
            time.sleep(0.3)
            bright.down = backlight()[1]
            chord(kb, KEY_BRIGHTNESSUP)
            time.sleep(0.3)
            bright.up = backlight()[1]

        run_reader(1.5, bright)
        failures += check("brightness down then up",
                          str(bright.down < bl_before and bright.up > bright.down
                              ).encode(), b"True")

        # 3-5. A user's tmux on the VT.
        conf = tempfile.mktemp()
        open(conf, "w").write("set -g base-index 1\n")
        os.chmod(conf, 0o644)
        subprocess.run(["openvt", "-c", str(VT), "-f", "--", "sh", "-c",
                        f'chown {USER.pw_uid} {TTY}; TERM=linux exec runuser '
                        f'-u {USER.pw_name} -- {" ".join(tmux)} -f {conf} '
                        'new-session "sleep 60"'], check=True)
        subprocess.run(["chvt", str(VT)], check=True)
        time.sleep(1.5)
        for _ in range(2):
            as_user(*tmux, "new-window", "-d", "sleep 60")
        index = lambda: as_user(*tmux, "display", "-p", "#{window_index}")
        seen = []
        for key in (KEY_2, KEY_3, KEY_1):
            chord(kb, KEY_LEFTMETA, key)
            time.sleep(0.4)
            seen.append(index())
        failures += check("Win+2, Win+3, Win+1 select tmux windows",
                          " ".join(seen).encode(), b"2 3 1")

        as_user("pamixer", "--set-volume", "50")
        if KEY_VOLUMEUP not in reserved:
            chord(kb, KEY_VOLUMEUP)
            time.sleep(0.5)
            failures += check("volume up by 3",
                              as_user("pamixer", "--get-volume").encode(),
                              b"53")
        chord(kb, KEY_MUTE)
        time.sleep(0.5)
        failures += check("mute toggles",
                          as_user("pamixer", "--get-mute").encode(),
                          b"false" if mute_before == "true" else b"true")
        chord(kb, KEY_MUTE)
        time.sleep(0.5)
        messages = as_user(*tmux, "show-messages", "-t", TTY)
        failures += check("volume shown in tmux",
                          str("Volume:" in messages).encode(), b"True")

        states = []
        for _ in range(2):
            chord(kb, KEY_LEFTMETA, KEY_LEFTSHIFT, KEY_S)
            time.sleep(1.0)
            states.append(inhibited())
        failures += check("Win+Shift+S toggles the inhibitor and back",
                          str(states).encode(),
                          str([not inhibited_before, inhibited_before]).encode())
    finally:
        as_user(*tmux, "kill-server")
        daemon.terminate()
        daemon.wait()
        failures += check("keymap restored on stop",
                          str(keymap_entries() == keymap_before).encode(),
                          b"True")
        with open(bl_path, "w") as f:
            f.write(str(bl_before))
        if vol_before:
            as_user("pamixer", "--set-volume", vol_before)
        if mute_before and as_user("pamixer", "--get-mute") != mute_before:
            as_user("pamixer", "-t")
        subprocess.run(["chvt", original_vt])
        fcntl.ioctl(kb, UI_DEV_DESTROY)
        for fd in grabbed:
            os.close(fd)
        for s in active:
            subprocess.run(["systemctl", "start", s])
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
