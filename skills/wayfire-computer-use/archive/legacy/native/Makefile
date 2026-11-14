CC ?= cc
CFLAGS += -Wall -Wextra -O2 $(shell pkg-config --cflags wayland-client xkbcommon)
LDLIBS += $(shell pkg-config --libs wayland-client xkbcommon)
all: build/input-helper
build:
	mkdir -p build
build/pointer.h: protocols/wlr-virtual-pointer-unstable-v1.xml | build
	wayland-scanner client-header $< $@
build/pointer.c: protocols/wlr-virtual-pointer-unstable-v1.xml | build
	wayland-scanner private-code $< $@
build/keyboard.h: protocols/virtual-keyboard-unstable-v1.xml | build
	wayland-scanner client-header $< $@
build/keyboard.c: protocols/virtual-keyboard-unstable-v1.xml | build
	wayland-scanner private-code $< $@
build/input-helper: input.c build/pointer.h build/keyboard.h build/pointer.c build/keyboard.c
	$(CC) $(CFLAGS) -Ibuild input.c build/pointer.c build/keyboard.c $(LDLIBS) -o $@
clean:
	rm -rf build
.PHONY: all clean
