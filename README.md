# tty-i3-keys

i3 hotkeys on the Linux text console. On a text VT nothing listens for the
i3 chords; this daemon reads the keyboards through evdev and, while the
foreground VT is in text mode (not X), acts for the user who owns that VT:

| keys | action |
|---|---|
| `Win+1` .. `Win+9`, `Win+0` | select tmux window 1 .. 9, 10 in the session attached to the VT, like i3 workspaces |
| `Win+Shift+S` | toggle suspend on lid close, by the same `~/.config/i3/toggle-lid-suspend.sh` as i3 (shared state with X) |
| volume up / down, mute | `pamixer -ui 3`, `pamixer -ud 3`, `pamixer -t` as in the i3 config, in the user's PipeWire session |
| brightness up / down | `brightnessctl set +5%` / `5%-` as in the i3 config (never down to 0) |

Volume and brightness show the new level in tmux (`display-message`) when a
tmux client is attached to the VT. Nothing is written into the tty, which
would corrupt full-screen programs.

How it works:

- The kernel console has no Super modifier, so `Win+1` would also type `1`.
  The daemon makes both Win keys the kernel's `ShiftL` modifier in the
  console keymap. The keymap has no tables for `ShiftL` combinations, so the
  kernel types nothing for `Win+key` (arrows excepted: the kernel sends them
  with the modifier encoded). If the keymap does use `ShiftL`, the Win keys
  are left alone. The handled media keys become holes,
  so they do not also type `F13`/`F14`/`Help`. The original entries are
  restored when the daemon stops and re-applied if the keymap is reloaded.
- Keys that the `KEYMAP_TOGGLE` file of `/etc/vconsole.conf` maps on purpose
  are left to the console. On a laptop whose `Fn+Left/Right` arrive as
  volume keys and are mapped to Home/End there, they stay Home/End.
- tmux, pamixer and the lid script run as the owner of the VT, never as
  root. Nothing is done for a root-owned (login) VT, except brightness.

## Install

```sh
sudo make install
```

Installs `/usr/local/bin/tty-i3-keys`, enables `tty-i3-keys.service`, and
installs a polkit rule that lets `wheel` users block lid-switch handling
from outside their session (the daemon runs the lid script for them).

## Test

```sh
sudo make test
```

Switches to VT 12 for about 15 seconds and drives a virtual keyboard
through uinput. It checks that typing still works and that `Win+1` and the
media keys type nothing, then tests brightness, tmux window switching on a
real tmux, volume and mute with the tmux message, the `Win+Shift+S`
toggle, and keymap restore. Volume, brightness and the lid state are put
back afterwards. The real keyboards are grabbed while it runs, so typing
does not disturb it.
