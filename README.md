# tty-i3-keys

i3 hotkeys on the Linux text console. On a text VT nothing listens for the
i3 chords; this daemon reads the keyboards through evdev and, while the
foreground VT is in text mode (not X), acts for the user who owns that VT:

| keys | action |
|---|---|
| `Win` held | the i3 bar's status line on the bottom row, like i3's `mode hide` bar with `modifier Mod4` |
| `Win+1` .. `Win+9`, `Win+0` | select tmux window 1 .. 9, 10 in the session attached to the VT, like i3 workspaces |
| `Win+Shift+S` | toggle suspend on lid close, by the same `~/.config/i3/toggle-lid-suspend.sh` as i3 (shared state with X) |
| volume up / down, mute | `pamixer -ui 3`, `pamixer -ud 3`, `pamixer -t` as in the i3 config, in the user's PipeWire session |
| brightness up / down | `brightnessctl set +5%` / `5%-` as in the i3 config (never down to 0) |

Feedback appears in the same bar for 2.5 seconds, with the message at the
left and the status at the right: the lid state, the volume and brightness
level, and errors (no tmux window 7, no tmux on this console). Nothing is
written into the tty, which would corrupt full-screen programs, and nothing
depends on tmux. Levels have colors: info normal, warning yellow, error red.

How it works:

- The bar's content is the user's own `i3blocks`, the `status_command` of
  their i3 bar. It runs persistently as the user (with no `DISPLAY`), and its
  i3bar JSON stream is drawn into the screen memory through `/dev/vcsaN`, over
  whatever program is on the VT, without moving the cursor or sending the
  program anything. Text is mapped to the console font's glyphs. A small table
  substitutes the icons the user's scripts emit (the battery block's
  charging bolt `U+F0E7` becomes `↑`, or `+` if the font lacks it). Missing
  characters get a compatibility form (`℃` -> `°C`). Anything else the font
  lacks, such as the other icons, is dropped together with its spacing. Colors map to the console palette. When the bar
  goes away, a cell is put back only if it still shows the bar and the
  program has not written there. The `/dev/vcsuN` text shadow, which only
  program output changes, catches writes of identical cells. If the screen
  scrolled meanwhile, the bar is found where it moved to. After a VT resize
  the row is left as it is.

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
- tmux, pamixer, i3blocks and the lid script run as the owner of the VT,
  with that user's groups, never as root. Their run time and output are
  bounded. On a root-owned (login) VT only brightness acts, and it shows its
  message without a status.

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

Switches to VT 12 for about a minute and drives a virtual keyboard
through uinput. It checks that typing still works and that `Win+1` and the
media keys type nothing. It checks that holding Win shows the i3blocks bar
and releasing it restores the row byte-exact, keeping a program's redraw.
It also tests brightness, volume, mute and the `Win+Shift+S` lid toggle
with their messages at column 0, the row restore after a message, tmux
window switching on a real tmux, and keymap restore. Volume, brightness and the lid state are put
back afterwards. The real keyboards are grabbed while it runs, so typing
does not disturb it.
