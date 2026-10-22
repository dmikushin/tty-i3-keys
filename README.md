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
| `Win+Escape` | lock all consoles, the counterpart of i3's `xsecurelock`: asks for the VT owner's password |
| `Win+O` | rotate the console a quarter turn clockwise (fbcon `rotate_all`), for convertible laptops; kept across reboots in `/var/lib/tty-i3-keys/rotation` |

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

## The lock

`Win+Escape` runs kbd's `vlock -a` as the owner of the VT, on a spare VT
(63 downwards, away from getty's autovt range) with that VT as its
controlling terminal, and switches to it: the locked screen is hidden and
the password asked is that user's (PAM service `vlock`), as with
`xsecurelock` under X.

- `vlock -a` puts its VT in `VT_PROCESS` mode and refuses every release
  request, so nothing switches away until it exits: not `Ctrl+Alt+Fn`, not
  `chvt`, not root's `VT_ACTIVATE`. X on another VT is covered too.
- It ignores `SIGINT`, `SIGQUIT`, `SIGTSTP`, `SIGTERM` and `SIGHUP`:
  `Ctrl+C`, `Ctrl+\`, `Ctrl+Z` do nothing. A wrong password keeps it locked.
- It runs in its own session, outside the daemon's process group, and the
  unit has `KillMode=process`: stopping or restarting the daemon leaves the
  lock in place. The new daemon adopts it from `/run/tty-i3-keys/lock.json`
  (pid and start time, so a reused pid is not mistaken for it).
- The spare VT stays root's; vlock reaches it only as its controlling
  terminal, so other processes of the user cannot open it.
- While locked, the daemon does nothing: no bar (it would show the user's
  status), no tmux, volume, brightness or lid actions.
- After the right password vlock exits; the daemon switches back to the VT
  that was locked and frees the spare VT.

What it does not protect against, as with `xsecurelock`: another process of
the same user (an ssh session, a cron job) can kill vlock and so unlock;
root can. `Ctrl+Alt+Del` still reboots through systemd (no session survives
that). Magic SysRq is what the kernel allows; on these laptops
`kernel.sysrq = 16`, i.e. only sync.

## Typing for the console's owner

A user process cannot inject input into a VT (TIOCSTI on a terminal that
is not its controlling one needs `CAP_SYS_ADMIN`). The daemon offers it on
`/run/tty-i3-keys-type.sock`: connect, send UTF-8 text, shut down the
sending side, read one line: `ok` (typed; an empty request only asks), `x`
(the VT in front is in graphics mode: X takes the text) or
`denied: <reason>`. It types only into the foreground VT, only if the
client's uid (`SO_PEERCRED`) owns it, never into a root-owned (login) VT
or while the console is locked, and stops if the VT is switched or changes
hands mid-text. [nerd-dictation](../nerd-dictation)'s `auto` input method
types the dictated text through it.

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

Switches to VT 12 for about a minute and a half and drives a virtual keyboard
through uinput. It checks that typing still works and that `Win+1` and the
media keys type nothing. It checks that holding Win shows the i3blocks bar
and releasing it restores the row byte-exact, keeping a program's redraw.
It also tests brightness, volume, mute and the `Win+Shift+S` lid toggle
with their messages at column 0, the row restore after a message, tmux
window switching on a real tmux, and keymap restore. The lock is tested
with a throwaway user created with a known password and deleted afterwards:
`Win+Escape` starts vlock as that user on a spare VT, `Ctrl+Alt+F1`, root's
`VT_ACTIVATE` and `Ctrl+C` do not get out, restarting the daemon does not
unlock, a wrong password keeps it locked, the right one unlocks and returns
to the VT. Volume, brightness and the lid state are put
back afterwards. The typing socket is tested too: the VT owner's text
arrives byte-exact, another user is refused, a VT in graphics mode answers
`x`; with `NERD_DICTATION_DRIVER` set to nerd-dictation's built
`console_type_driver`, its `auto` input method is checked the same way.
The real keyboards are grabbed while it runs (virtual uinput devices are
left alone), so typing does not disturb it. It refuses to start while the
console is locked or another VT test runs; run it under
`flock /tmp/vt12-test.lock` when other VT tests may run.
