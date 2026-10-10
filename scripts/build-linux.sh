#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "$(uname -s)" != Linux ]; then echo 'Native Linux packages must be built on Linux (use the release-candidates GitHub workflow).' >&2; exit 1; fi
case "$(uname -m)" in x86_64) ARCH=x86_64; DEB_ARCH=amd64;; aarch64|arm64) ARCH=aarch64; DEB_ARCH=arm64;; *) echo 'Supported Linux architectures: x86_64 and aarch64' >&2; exit 1;; esac
VERSION=${APP_VERSION:-1.3.0}
export PYINSTALLER_CONFIG_DIR="$PWD/.build/pyinstaller-cache-$ARCH"
python3 -m venv .build/linux-venv
.build/linux-venv/bin/python -m pip install -r linux/requirements-build.txt
mkdir -p "dist/linux/$ARCH"
.build/linux-venv/bin/python -m PyInstaller --noconfirm --clean --onedir --name CallPerch --paths backend --paths linux --add-data "$PWD/assets/branding:assets/branding" --add-data "$PWD/docs/privacy.html:docs" --add-data "$PWD/docs/style.css:docs" --add-data "$PWD/docs/logo.png:docs" --exclude-module ssl --exclude-module _ssl --exclude-module _hashlib --exclude-module PySide6.QtNetwork --distpath "dist/linux/$ARCH" --workpath ".build/pyinstaller-$ARCH" --specpath .build linux/callperch.py
BUNDLE="dist/linux/$ARCH/CallPerch"
mkdir -p "$BUNDLE/licenses" "$BUNDLE/systemd"
cp release/linux/callperch-reminders.service release/linux/callperch-reminders.timer "$BUNDLE/systemd/"
cp README.md "$BUNDLE/README.md"
cp LICENSE "$BUNDLE/licenses/CallPerch-MIT-LICENSE.txt"
cp release/linux/VOICE-QUALITY.md "$BUNDLE/VOICE-QUALITY.md"
cp release/linux/THIRD-PARTY-NOTICES.md "$BUNDLE/licenses/THIRD-PARTY-NOTICES.md"
cp release/linux/Python-LICENSE.txt "$BUNDLE/licenses/Python-LICENSE.txt"
.build/linux-venv/bin/python - "$BUNDLE/licenses" <<'PYNOTICES'
import sys, zipfile
from pathlib import Path
with zipfile.ZipFile('release/linux/third-party-notices.zip') as archive:
    archive.extractall(Path(sys.argv[1]))
root=Path(sys.argv[1])
assert (root/'Qt-6.8.3/LICENSES/LGPL-3.0-only.txt').is_file(), 'Qt LGPL notice missing'
assert (root/'PySide-Shiboken-6.8.3/LICENSES/LGPL-3.0-only.txt').is_file(), 'PySide LGPL notice missing'
PYNOTICES
.build/linux-venv/bin/python - <<'PY'
from pathlib import Path
import importlib.metadata,shutil
output=Path('dist/linux')
for distribution in ['PySide6-Essentials','shiboken6','pyinstaller']:
    dist=importlib.metadata.distribution(distribution)
    for filename in dist.files or []:
        name=str(filename)
        if any(token in name.lower() for token in ['license','copying','copyright']) and dist.locate_file(filename).is_file():
            for destination in output.glob('*/CallPerch/licenses'):
                target=destination/distribution/name.replace('/','_');target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dist.locate_file(filename),target)
PY
# The portable folder uses shared Qt libraries, which remain replaceable by users.
QT_QPA_PLATFORM=offscreen "$BUNDLE/CallPerch" --engine --help > /dev/null
QT_QPA_PLATFORM=offscreen timeout 20 "$BUNDLE/CallPerch" --smoke-test > ".build/linux-comparison-$ARCH.log" 2>&1
# Check that the collected Qt GUI actually launches; timeout is expected after 10 seconds.
set +e
QT_QPA_PLATFORM=offscreen timeout 10 "$BUNDLE/CallPerch" > ".build/linux-gui-$ARCH.log" 2>&1
GUI_STATUS=$?
set -e
if [ "$GUI_STATUS" != 124 ]; then cat ".build/linux-gui-$ARCH.log" >&2; echo "Frozen GUI smoke test failed ($GUI_STATUS)" >&2; exit 1; fi
tar -C "dist/linux/$ARCH" -czf "dist/linux/CallPerch-$VERSION-linux-$ARCH.tar.gz" CallPerch
if command -v dpkg-deb >/dev/null; then
    STAGING=".build/deb-$ARCH"
    rm -rf "$STAGING"
    mkdir -p "$STAGING/DEBIAN" "$STAGING/opt/callperch" "$STAGING/usr/share/applications" "$STAGING/usr/share/icons/hicolor/256x256/apps" "$STAGING/usr/bin"
    cp -R "$BUNDLE/." "$STAGING/opt/callperch/"
    cp release/linux/callperch.desktop "$STAGING/usr/share/applications/"
    cp assets/branding/callperch-logo.png "$STAGING/usr/share/icons/hicolor/256x256/apps/callperch.png"
    ln -sfn /opt/callperch/CallPerch "$STAGING/usr/bin/callperch"
    cat > "$STAGING/DEBIAN/control" <<CONTROL
Package: callperch
Version: $VERSION
Architecture: $DEB_ARCH
Maintainer: Arash Manafirad (KR4GOJ)
Depends: pulseaudio-utils, espeak-ng, curl, libnotify-bin, xdg-utils, libegl1, libopengl0, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-render-util0
Section: hamradio
Priority: optional
Description: FCC amateur radio callsign research
 Search callsigns, inspect applications, compare weights, and track estimated availability.
CONTROL
    dpkg-deb --root-owner-group --build "$STAGING" "dist/linux/CallPerch-$VERSION-$DEB_ARCH.deb"
fi
(cd dist/linux && sha256sum "CallPerch-$VERSION-linux-$ARCH.tar.gz" > "CallPerch-$VERSION-linux-$ARCH.tar.gz.sha256")
printf 'Prepared Linux %s packages. Test on a real desktop before publishing.\n' "$ARCH"
