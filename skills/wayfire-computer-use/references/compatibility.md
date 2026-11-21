# Tested scope

The Rust runtime has passed private Wayfire dual-output capture/input, explicit output selection, session cleanup, launcher detachment, window listing/focus, cancellation and service-loss regressions. Current-desktop checks covered eDP-1 and HEADLESS-8 at normal orientation and scale 1, GTK, Dolphin (Qt), Chromium, Typora (Electron), and a full-screen game. One game control session lasted about 31 minutes; this is not a general long-duration reliability guarantee.

Selected input outputs with scaling or rotation remain unsupported. Simulated transformed-output geometry checks do not establish correct input mapping. Topology changes invalidate coordinates and require a fresh session. External Portal/slurp fixes were needed in the tested environment; a different installation may still exhibit those upstream failures.

ASCII, Chinese and BMP symbols were tested with experimental keymap settling delays. Native key mode rejects non-BMP text before input. Do not infer universal IME, toolkit or game support. Explicit clipboard paste delivered supplementary Unicode in GTK, Qt, Xwayland Zenity, Chromium, Electron and Kitty. The Kitty test used Ctrl+Shift+V and compared the bytes read from its terminal with the expected UTF-8 line. Chromium and Electron also reported the selected substring after a pointer drag.

Recovery checks included Portal replacement, PipeWire loss, output removal, lock-screen capture and suspend/resume in the tested environment. The owner monitors logind LockedHint. A private logind test verified cancellation during active typing. The earlier completed-lock screenshot test verified capture content on the development desktop. A fresh session after recovery still requires a new screenshot before input. See [diagnostics](troubleshooting.md).
