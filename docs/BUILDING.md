# CallPerch for Linux — release preparation

The Qt desktop port uses the same FCC SQLite engine and supports search, applications/history, exact-address matches, phonetic/CW weights, available/coming date and CW sorting, region/format filters, watchlist, native FCC sync/ZIP import, attribution, and the coffee link. Queries and imports run in a separate process so the UI remains responsive.

## Desktop interface

The Linux interface follows the Mac layout with persistent section navigation, context-sensitive filters applied only when Search / Refresh is pressed, readable license summaries and a separate callsign inspector. PySide6 is pinned to 6.8.3 for older x86-64 processors, including the Core 2 Duo; Qt 6.11 binaries require SSE4.2 and POPCNT.

Choose **System**, **Light** or **Dark** using the sidebar Appearance selector. The choice is saved; System follows Qt’s desktop color-scheme notifications (when provided by the Linux desktop). Callsign details show CW dot/dash notation with spaces between letters; result tooltips show the same notation.

## Run from source

Python 3.10+ and a graphical desktop are required. On Debian/Ubuntu, install `python3-venv`, `curl`, `libnotify-bin`, and the Qt platform libraries listed in the generated Debian package's dependencies. Qt/PySide dependencies are isolated in a virtual environment.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r linux/requirements.txt
.venv/bin/python linux/callperch.py
```

Linux preferences and database live under `$XDG_DATA_HOME/callperch`, defaulting to `~/.local/share/callperch`. The source checkout can read `data/fcc.sqlite` until a user snapshot exists. Frozen Linux packages start empty; use Sync FCC or import the two weekly ZIP archives. Full imports require several GB and take several minutes.

## Build native packages

Run on Linux; PyInstaller cannot produce Linux binaries on macOS. The intended baseline is Ubuntu 24.04+ on x86-64 or ARM64.

```sh
./scripts/build-linux.sh
./scripts/build-deb.sh
```

Alternatively, the AppImage can be built separately once the PyInstaller bundle is present:

```sh
./scripts/build-linux.sh
./scripts/build-appimage.sh
```

Outputs: a portable application folder, `.tar.gz`, AppImage, checksums, and `.deb` when `dpkg-deb` is available. Python and Qt are included. curl and desktop system libraries are installed dependencies. Do not move the executable away from its `_internal` directory. No FCC snapshot is included in these Linux binary packages by default.

The manual `release-candidates` GitHub workflow (or the Linux-only `linux-candidates` workflow) builds on separate Ubuntu x86-64 and ARM64 runners, runs synthetic-data UI tests, and verifies the frozen GUI can start offscreen. Native build workflows run on GitHub-hosted Ubuntu runners. Real desktop/notification tests are still required on each architecture. Debian installation and Wayland/X11 behavior have not yet been verified here.

## One-day reminders

While the app is open, it checks reminders at launch, on watchlist changes, and hourly. Notifications require `notify-send` and a running desktop notification service. The popup includes an Open FCC ULS action. Actual action support depends on the desktop notification server and must be tested on the release target.

For reminders with the app closed, after installing the Debian package:

```sh
mkdir -p ~/.config/systemd/user
cp /opt/callperch/systemd/callperch-reminders.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now callperch-reminders.timer
```

The timer runs hourly from 9 AM to 11 PM in your session's local timezone and catches up after login. It reads the local database and current watchlist; it does not download FCC data. Dates are estimates. An active user session and functioning notification service are required. Disable the app's reminder checkbox or disable the timer to stop reminders.

Portable tar users must update the service's ExecStart to their actual executable path before installing the units. App installation does not enable background work automatically. The timers and desktop notification actions are prepared but have not been exercised on an actual Linux desktop.

## Licensing and publication

The package keeps Qt as replaceable shared libraries and copies available dependency license notices. Review LGPL obligations and matching source/offer requirements for the exact Qt libraries before public distribution. Verify all bundled-component notices and vulnerabilities. CallPerch Linux code is licensed under MIT; third-party components retain their own licenses. See LICENSE and THIRD_PARTY.md.

The macOS-hosted offscreen test is useful for Qt behavior but is not proof of Linux binary compatibility. Use [PyInstaller's platform guidance](https://pyinstaller.org/en/stable/) and [Qt's deployment documentation](https://doc.qt.io/qtforpython-6/deployment/index.html).

Version 1.2.1 adds read-only schema-2 queries, precomputed CW sorting, bounded ZIP parsing, disk checks, a helper watchdog and Cancel, full-address display opt-in, local data deletion and the canonical bundled privacy policy. Downloads run through a bounded curl process in the GUI; the old backend sync command is removed. Native Linux packages still require a Linux build and desktop testing.

## Assignment history in version 1.2.3

Callsign details now show **Repeated callsign switching** with an FRN-linked assignment timeline, cancellation dates, return counts, and returns before ordinary release estimates. Click a timeline callsign to inspect it. The shared detector requires at least two returns across four or more assignments and excludes clubs/trustees. Names and addresses are not used to link holders. A flag does not establish intent, misconduct or confirmed former-holder eligibility.

For testing, search **N4BD** and **KV4M** after **Sync FCC** completes. Each should show the historical switching pattern for the same individual FRN. If using an older database, Sync FCC first to import holder identities. Missing FRNs and incomplete histories are reported without treating them as evidence of no switching. The interface was tested by the user before publication.

Version 1.2.3 shows FCC sync and ZIP import in a modal progress window, with live stage text, an indeterminate progress indicator, and Cancel Sync. Other app controls are blocked during the operation. Completion, cancellation and failure stay visible until Done is clicked. No percentage or time estimate is invented during indexing.

Linux 1.2.3 starts assignment timelines collapsed. Click **Assignment timeline · Expand** to show dates and callsign links, then **Collapse** to hide them. Each holder expands independently; selecting another callsign resets the timelines.
