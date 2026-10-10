# CallPerch Linux 1.3.0 — local test, October 10, 2026

This source test package includes the latest local Mac features adapted to Linux: callsign comparison with saved ratings and CSV export, improved QSL/plate previews, snapshot-age reminders, previous-callsign navigation that preserves the selected license record, accurate expiration/cancellation wording, loading feedback and cancellation, and acknowledgments. Existing watchlists, assignment timelines, themes and modal FCC sync are included.

FCC sync now downloads into a temporary subfolder of the CallPerch data directory, alongside the database. It no longer depends on a large `/tmp` or a TMPDIR override. Temporary downloads are removed after completion, cancellation or failure. The conservative 12 GiB free-space threshold remains; storage errors identify the actual folder.

## Start the test on Linux

Extract the ZIP or tar.gz with your file manager. Close your installed CallPerch app. Open a terminal in the extracted `CallPerch-Linux-1.3.0-test-20261010` folder.

On Debian/Ubuntu, install the source runtime and local audio tools once:

```sh
sudo apt install python3-venv pulseaudio-utils espeak-ng
```

Then launch:

```sh
bash scripts/run-linux-test.sh
```

The launcher creates `.venv` in this test folder and installs the pinned Qt dependency on first launch. Later launches reuse it. Python 3.10–3.13 is required for this runtime. To choose an installed Python explicitly, use `CALLPERCH_TEST_PYTHON=python3.12 bash scripts/run-linux-test.sh`.

If installing on a fresh system, also install the Qt desktop libraries listed in `scripts/build-linux.sh`. Your existing Debian installation of CallPerch should already have these libraries.

This does not replace the installed app. It reuses the same settings, watchlist, saved comparisons and FCC database under `$XDG_DATA_HOME/callperch`, or `~/.local/share/callperch`. No FCC database is included, and this test does not download another one unless you choose Sync FCC. Run one instance at a time. **Delete local data also deletes the shared database and settings.**

## Check before publication

- Search a callsign, open its details, and follow a previous-callsign link. Verify that the clicked license's dates/status remain selected.
- Check expiration/cancellation wording, the loading indicator and Cancel. Expand/collapse assignment timelines and reveal/hide addresses.
- Check the snapshot-age reminder if your existing snapshot is at least seven days old; dismiss it and reopen the app on the same day.
- Open Compare callsigns. Add manually, from the watchlist, and from details; verify duplicate checks and the ten-call limit.
- Try Balanced/CW/SSB priorities and personal ratings. A personal category enters the ranking only after every candidate is rated.
- Play CW at 5, 20 and 50 WPM, speak phonetics, stop audio, and close the window during playback. Check sound on your Linux desktop.
- View QSL/plate previews and initials matching. Check light/dark appearance at your normal window size.
- Save, reopen and delete a named comparison; export CSV. Restart the app and verify draft persistence.
- Open Acknowledgments and check the sidebar links.
- Sync FCC if desired. Confirm the modal progress window, cancellation and successful cleanup of `fcc-sync-*` folders in the data directory. A successful sync replaces the existing snapshot; failed/canceled imports preserve it.

## Automated checks and native packages

```sh
.venv/bin/python -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s linux -p 'test*.py' -v
```

To build an installable `.deb` on your Linux computer:

```sh
APP_VERSION=1.3.0 bash scripts/build-linux.sh
```

Outputs are under `dist/linux`. Native builds require Linux; this source test archive is not a binary installer. The contributor's AppImage PR has not been merged into this package.

The preparation checks run on macOS: 55 backend tests and 34 Qt/comparison tests passed. Offscreen checks do not establish Linux binary compatibility or audible playback. Native x86-64/ARM64 and real desktop tests remain necessary before release. The source and native build outputs are available through the public Linux repository.


## Spoken voice quality

Linux spoken phonetics uses a lightweight local eSpeak voice and may sound robotic. For an optional, more natural standalone voice, see [voice downloads and setup](VOICE-QUALITY.md). Downloaded Piper voices do not automatically change the app’s Speak phonetics button; that currently uses eSpeak.
