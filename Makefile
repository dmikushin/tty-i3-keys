PREFIX ?= /usr/local
UNITDIR ?= /etc/systemd/system
POLKITDIR ?= /etc/polkit-1/rules.d
UDEVDIR ?= /etc/udev/rules.d

install:
	install -Dm755 tty-i3-keys $(DESTDIR)$(PREFIX)/bin/tty-i3-keys
	install -Dm644 tty-i3-keys.service $(DESTDIR)$(UNITDIR)/tty-i3-keys.service
	install -Dm644 50-lid-switch-inhibit.rules $(DESTDIR)$(POLKITDIR)/50-lid-switch-inhibit.rules
	# tty-i3-keys replaces the Win+Shift+S-only daemon it grew out of.
	-systemctl disable --now tty-lid-toggle-hotkey.service 2>/dev/null
	rm -f $(DESTDIR)$(PREFIX)/bin/tty-lid-toggle-hotkey $(DESTDIR)$(UNITDIR)/tty-lid-toggle-hotkey.service
	systemctl daemon-reload
	systemctl enable tty-i3-keys.service
	systemctl restart tty-i3-keys.service

uninstall:
	systemctl disable --now tty-i3-keys.service
	rm -f $(DESTDIR)$(PREFIX)/bin/tty-i3-keys $(DESTDIR)$(UNITDIR)/tty-i3-keys.service \
		$(DESTDIR)$(POLKITDIR)/50-lid-switch-inhibit.rules
	systemctl daemon-reload

test:
	python3 tests/vt-test.py

.PHONY: install uninstall test

# Laptops whose touchpad sits on Synaptics RMI4 (ThinkPads; the TrackPoint is
# passed through it): switch both off while the lid is closed, where the lid
# presses on them. Hardware-specific, so a separate target.
install-lid-pointer:
	install -Dm755 lid-inhibit-pointer $(DESTDIR)$(PREFIX)/bin/lid-inhibit-pointer
	install -Dm644 lid-inhibit-pointer.service $(DESTDIR)$(UNITDIR)/lid-inhibit-pointer.service
	install -Dm644 90-lid-inhibit-pointer.rules $(DESTDIR)$(UDEVDIR)/90-lid-inhibit-pointer.rules
	udevadm control --reload
	systemctl daemon-reload
	systemctl enable lid-inhibit-pointer.service
	systemctl restart lid-inhibit-pointer.service

uninstall-lid-pointer:
	systemctl disable --now lid-inhibit-pointer.service
	rm -f $(DESTDIR)$(PREFIX)/bin/lid-inhibit-pointer $(DESTDIR)$(UNITDIR)/lid-inhibit-pointer.service \
		$(DESTDIR)$(UDEVDIR)/90-lid-inhibit-pointer.rules
	udevadm control --reload
	systemctl daemon-reload
