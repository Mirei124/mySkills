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
