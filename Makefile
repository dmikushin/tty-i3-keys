PREFIX ?= /usr/local
UNITDIR ?= /etc/systemd/system
POLKITDIR ?= /etc/polkit-1/rules.d

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
