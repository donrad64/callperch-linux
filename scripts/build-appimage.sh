#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "$(uname -s)" != Linux ]; then echo 'Linux packages must be built on Linux.' >&2; exit 1; fi
case "$(uname -m)" in x86_64) ARCH=x86_64;; aarch64|arm64) ARCH=aarch64;; *) echo 'Supported Linux architectures: x86_64 and aarch64' >&2; exit 1;; esac
export ARCH
VERSION=${APP_VERSION:-1.2.3}
export VERSION
BUNDLE=${BUNDLE:-"dist/linux/$ARCH/CallPerch"}

if [ ! -d "$BUNDLE" ]; then
    echo "PyInstaller bundle not found at $BUNDLE. Run ./scripts/build-linux.sh first." >&2
    exit 1
fi

mkdir -p "dist/linux/$ARCH"

validate_appimage() {
    case $ARCH in
        x86_64)
            SHA256=7c974f525d5bcde2712dd080e0b079a6c3802113a337f0ab142522dcefbf452d
            ;;
        aarch64)
            SHA256=9a76fcf3ba20a5b7dab5b32295537cc60b83e3f64e19592c3da805969e06070d
            ;;
    esac
    echo "${SHA256}  ${1}" | sha256sum --check
}

APPIMAGETOOL="$(pwd)/.build/appimagetool-$ARCH.AppImage"
export APPIMAGE_EXTRACT_AND_RUN=1
if [ ! -f "$APPIMAGETOOL" ]; then
    rm -rf ".build/appimagetool-$ARCH-extracted"
    TMPTOOL=$(mktemp "${APPIMAGETOOL}.XXXXXXXX")
    (
        # Any failure here will fall through to the cleanup branch
        curl --fail -sL "https://github.com/probonopd/go-appimage/releases/download/continuous/appimagetool-951-$ARCH.AppImage" -o  "${TMPTOOL}"
        validate_appimage "${TMPTOOL}"
        chmod +x "${TMPTOOL}"
    ) || {
        rm "${TMPTOOL}"
        exit 1
    }
    mv "${TMPTOOL}" "${APPIMAGETOOL}"
else
    validate_appimage "${APPIMAGETOOL}"
fi
if [ ! -x ".build/appimagetool-$ARCH-extracted/squashfs-root/AppRun" ]; then
    mkdir -p ".build/appimagetool-$ARCH-extracted"
    (cd ".build/appimagetool-$ARCH-extracted" && "$APPIMAGETOOL" --appimage-extract >/dev/null)
fi

APPDIR=".build/appdir-$ARCH"
rm -rf "$APPDIR"
mkdir -p "$APPDIR"
cp -R "$BUNDLE/." "$APPDIR/"
sed 's|^Exec=.*|Exec=CallPerch|' release/linux/callperch.desktop > "$APPDIR/callperch.desktop"
cp assets/branding/callperch-logo.png "$APPDIR/callperch.png"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp assets/branding/callperch-logo.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/callperch.png"
cat > "$APPDIR/AppRun" << 'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/CallPerch" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

pwd
"$APPIMAGETOOL" "$APPDIR"
mv "CallPerch-$VERSION-$ARCH.AppImage" dist/linux
(cd dist/linux && sha256sum "CallPerch-$VERSION-$ARCH.AppImage" > "CallPerch-$VERSION-$ARCH.AppImage.sha256")

# make sure that it can run as a binary and exit successfully
QT_QPA_PLATFORM=offscreen "dist/linux/CallPerch-$VERSION-$ARCH.AppImage" --engine --help > /dev/null
set +e
QT_QPA_PLATFORM=offscreen timeout 10 "dist/linux/CallPerch-$VERSION-$ARCH.AppImage" > ".build/linux-gui-$ARCH.log" 2>&1
GUI_STATUS=$?
set -e
if [ "$GUI_STATUS" != 124 ]; then
    echo "Frozen GUI appimage smoke test failed ($GUI_STATUS)" >&2;
    exit 1;
fi

printf "Prepared AppImage: dist/linux/CallPerch-$VERSION-$ARCH.AppImage\n"
printf 'Test on a real desktop before publishing.\n'
