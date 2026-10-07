#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "$(uname -s)" != Linux ]; then echo 'Linux packages must be built on Linux.' >&2; exit 1; fi
case "$(uname -m)" in x86_64) ARCH=x86_64; DEB_ARCH=amd64;; aarch64|arm64) ARCH=aarch64; DEB_ARCH=arm64;; *) echo 'Supported Linux architectures: x86_64 and aarch64' >&2; exit 1;; esac
VERSION=${APP_VERSION:-1.2.3}
BUNDLE=${BUNDLE:-"dist/linux/$ARCH/CallPerch"}

if [ ! -d "$BUNDLE" ]; then
    echo "PyInstaller bundle not found at $BUNDLE. Run ./scripts/build-linux.sh first." >&2
    exit 1
fi

if ! command -v dpkg-deb >/dev/null; then
    echo "dpkg-deb not found; skipping Debian package build." >&2
    exit 0
fi

STAGING=".build/deb-$ARCH"
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
Depends: curl, libnotify-bin, xdg-utils, libegl1, libopengl0, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-render-util0
Section: hamradio
Priority: optional
Description: FCC amateur radio callsign research
 Search callsigns, inspect applications, compare weights, and track estimated availability.
CONTROL

dpkg-deb --root-owner-group --build "$STAGING" "dist/linux/CallPerch-$VERSION-$DEB_ARCH.deb"
(cd dist/linux && sha256sum "CallPerch-$VERSION-$DEB_ARCH.deb" > "CallPerch-$VERSION-$DEB_ARCH.deb.sha256")

printf 'Prepared Debian package: dist/linux/CallPerch-$VERSION-$DEB_ARCH.deb\n'
printf 'Test on a real desktop before publishing.\n'
