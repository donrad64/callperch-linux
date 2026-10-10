# CallPerch for Linux

[![CI](https://github.com/donrad64/callperch-linux/actions/workflows/ci.yml/badge.svg)](https://github.com/donrad64/callperch-linux/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A Qt desktop application for researching public FCC amateur-radio licenses, applications, callsign assignments, and estimated availability. Created by Arash Manafirad (KR4GOJ). This repository contains the Linux application and its shared Python FCC engine. The current source version is Linux 1.3.0.

[Download installers](https://github.com/donrad64/callperch-support/releases/latest) · [Support](https://donrad64.github.io/callperch/) · [Privacy](https://donrad64.github.io/callperch/privacy.html)

## Features

- Search licensees and callsigns; inspect license/application history.
- Explore estimated availability, region/format filters, and CW/phonetic weights.
- Maintain a watchlist and local estimated-date reminders.
- Sync FCC weekly archives or import ZIPs, with a modal progress window and cancellation.
- Inspect exact public mailing-address matches; full addresses are hidden by default.
- Expand FRN-linked assignment timelines, with smaller orange release-estimate notes.
- Choose System, Light, or Dark appearance.
- Compare ten callsigns with adjustable priorities, personal ratings, local audio, QSL/plate previews, saved comparisons and CSV export.
- See snapshot-age reminders, previous-callsign records and clear loading/cancellation feedback.

Assignment-history summaries describe patterns in the available public records. They do not establish intent, improper conduct, rule violations, former-holder eligibility, entitlement to a callsign, or an application outcome. Missing records, changed FRNs, and weekly snapshot timing affect results. Estimated availability is not an FCC decision. Verify relevant records directly with the FCC. CallPerch is independent and is not affiliated with the FCC.

## Install

For Ubuntu 24.04+, download the `.deb` matching your architecture (amd64 for Intel/AMD or arm64 for ARM) from [Linux releases](https://github.com/donrad64/callperch-support/releases/latest). Close CallPerch, then install it, for example:

```sh
sudo apt install ./CallPerch-1.2.3-amd64.deb
callperch
```

Portable archives are also available. Keep the executable and `_internal` directory together. Verify downloads against the release's `SHA256SUMS.txt`.

## Run from source

Python 3.10–3.13 and a graphical Linux desktop are required. Ubuntu 24.04 is the build baseline. On Debian/Ubuntu:

```sh
sudo apt install python3-venv pulseaudio-utils espeak-ng curl libnotify-bin xdg-utils libegl1 libopengl0 libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0
git clone https://github.com/donrad64/callperch-linux.git
cd callperch-linux
python3 -m venv .venv
.venv/bin/python -m pip install -r linux/requirements.txt
.venv/bin/python linux/callperch.py
```

Choose **Sync FCC** or import both `l_amat.zip` and `a_amat.zip`. No FCC data is included in the repository or Linux packages. Downloads are large; imports need at least 12 GiB free and can take several minutes. A failed or canceled import preserves the previous snapshot.

Both installed and source versions use `$XDG_DATA_HOME/callperch`, defaulting to `~/.local/share/callperch`. They share the database and settings. Close other instances before syncing. Older snapshots need Sync FCC for assignment-history identity fields.

## Troubleshooting: temporary folder space during FCC sync

**Linux 1.3.0 fixes this issue:** sync downloads use a temporary folder beside the local FCC database and are cleaned up afterward. No TMPDIR override is needed. The 12 GiB check applies to available space on that filesystem, not the database's final size. The following workaround is retained for Linux 1.2.3.

On some Raspberry Pi systems running Debian 13 (Trixie), **Sync FCC** may report less than 12 GiB available even when the SD card or NVMe drive has plenty of free space. Debian Trixie defaults `/tmp` to a memory-backed `tmpfs`, normally capped at half of RAM. A 4 GB Pi can therefore have a roughly 2 GB `/tmp`. See the [Debian release notes](https://www.debian.org/releases/trixie/release-notes/issues.html#the-temporary-files-directory-tmp-is-now-stored-in-a-tmpfs).

CallPerch 1.2.3 checks free space on both the database filesystem and the temporary-download filesystem. **12 GiB means available space for syncing, not the final database size.** When `XDG_DATA_HOME` is unset, the database defaults to `~/.local/share/callperch`; an empty `echo $XDG_DATA_HOME` result is normal.

To check the filesystems:

```sh
df -h "$HOME" /tmp
findmnt /tmp
```

If `/tmp` is a small `tmpfs` and your home filesystem has at least 12 GiB available, close all CallPerch instances and launch the installed app with a temporary folder on your home filesystem:

```sh
mkdir -p "$HOME/.cache/callperch-tmp"
TMPDIR="$HOME/.cache/callperch-tmp" callperch
```

For a source checkout, use the same folder and replace the launch command with:

```sh
TMPDIR="$HOME/.cache/callperch-tmp" .venv/bin/python linux/callperch.py
```

The override applies to that launch only, so start from this command again for future syncs. Your existing database, settings and watchlist are reused. It does not change the system-wide `/tmp` mount or require more RAM. A home directory backed by another small filesystem will still need sufficient free space.

On a Raspberry Pi with a **64-bit** operating system, choose the **arm64** installer. Ubuntu 24.04 is the package build baseline; this note addresses the observed Trixie temporary-storage issue, rather than guaranteeing compatibility with every Raspberry Pi OS image.

## Test and build

```sh
.venv/bin/python -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s linux -p 'test*.py' -v
APP_VERSION=1.3.0 ./scripts/build-linux.sh
```

Native packaging must run on Linux. The build produces a portable archive, checksum, and a `.deb` when `dpkg-deb` is available. Python and Qt are bundled. [Build and reminder instructions](docs/BUILDING.md) explain dependencies, packaging, and optional systemd reminders.

CI tests pull requests and pushes with synthetic records. A packaging workflow builds on Ubuntu x86-64 and ARM64, with read-only repository permissions; it uploads artifacts and does not publish releases automatically. Offscreen checks do not replace desktop testing.

## Privacy, contributions, and licensing

Searches, watchlists, preferences, and derived assignment summaries remain local. Sync connects to FCC servers. External links open the browser. There are no developer-operated accounts, analytics, advertising, or telemetry. See the [bundled privacy policy](docs/privacy.html).

Read [CONTRIBUTING.md](CONTRIBUTING.md) for development and [SECURITY.md](SECURITY.md) for private vulnerability reporting. Use synthetic data in tests and issue reports.

CallPerch Linux code is released under the [MIT license](LICENSE). Dependencies retain their own licenses; see [THIRD_PARTY.md](THIRD_PARTY.md). Public FCC data is not included or licensed by this repository. Other CallPerch implementations and unpublished development history are outside this source release.

## Spoken phonetics

The built-in Linux voice uses local eSpeak and can sound synthetic. See [optional voice downloads](docs/VOICE-QUALITY.md) for a separate Piper listening option. Downloading a Piper voice does not change the app's Speak phonetics button.

Comparison drafts, ratings and named comparisons remain local beside the existing database. Delete local data also removes comparisons; CSV files you export remain where you saved them.
