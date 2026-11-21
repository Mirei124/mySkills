# GTK, Qt, Chromium and Electron element lookup

The private dual-output test places one disposable window on HEADLESS-2 at scale 1, requests verified focus, captures the window, queries a named accessible button, and clicks its output-local center using that observation. It retains before/after PNGs and the result JSON. Run with the repository Python interpreter using `tests/probe_rust_isolated.py --multi-output --toolkit-test` from this maintenance directory.

| Application and backend | Observed outcome |
|---|---|
| KDialog 26.08.3, Qt Wayland | The named push button resolved and the Yes dialog exited with status 0. |
| Zenity 4.2.2, GDK X11 on Xwayland 24.1.13 | The named confirm button resolved. A screenshot showed the button at the returned point and clicking it accepted the dialog (exit 0). |
| Chromium 158, Wayland app window | Clicking the accessible HTML button changed the same window's title as expected. |
| Electron 44, Wayland BrowserWindow | Clicking the accessible HTML button changed the same window's title as expected. |

The first browser runs had mapped windows but no browser application on the private AT-SPI registry. Lookup failed explicitly. Successful runs enabled IsEnabled on the isolated accessibility service, exported the private accessibility bus address, and requested complete renderer accessibility. Electron also called setAccessibilitySupportEnabled(true). The probe uses disposable profiles and memory-backed accessibility settings.

The earlier one-off report of an unresponsive Xwayland native dialog lacks the original application, window and dialog identity. The Zenity case did not reproduce it. These measurements establish one working Xwayland dialog and do not identify the cause of the historical failure. No Xwayland-specific coordinate correction was justified.

## Text delivery, drag selection and scroll distance

The same secondary-output harness checks the literal string `Test 😀𠀀 é 中文`, including the decomposed accent. KDialog and Xwayland Zenity entry dialogs return the accepted text on stdout. A Kitty Wayland window runs a Python line reader and uses Ctrl+Shift+V. Each returned UTF-8 line must match byte for byte. Chromium and Electron expose the input value in their window title, which must match exactly.

The browser drag test queries the accessible selection region, drags across a fixed monospace string and checks the browser's selected text. The scroll test sends both axes over scrollable content, waits for movement, then reads the settled CSS offsets. On Chromium 158 and Electron 44 the accumulated offsets after requests of 80, 160 and −80 per axis were (96,96), (288,288) and (192,192). These measurements apply to the fixture at scale 1.

In the Xwayland Zenity 4.2.2 file chooser with the C locale, the screenshot showed Cancel and OK. The accessible tree reported Grid View, Cancel and OK as buttons. Exact-name lookup for Open returned zero matches; lookup for OK returned one visible, sensitive button. Clicking its output-local center accepted the selection, and Zenity exited with status 0 and printed the exact path of the temporary probe-document.txt. Query the dialog's own button names when labels vary by application or locale. The earlier report about an unidentified dialog remains a separate deferred investigation.
