#!/bin/sh
# Samovar Lite installer for the current user.
#
#   ./install.sh               install or update: Python environment, `samovar-lite` command, menu entry
#   ./install.sh --no-desktop  only build the environment in .venv (development, CI)
#   ./install.sh --remove      remove the command and the menu entry again
#
# Nothing is written outside this folder and ~/.local. Root is only asked for when a required
# system library (libmpv) is missing and has to come from the distribution.
set -e
DIR="$(dirname "$(readlink -f "$0")")"
cd "$DIR"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APPS="$DATA/applications"
ICONS="$DATA/icons/hicolor/256x256/apps"
BIN="$HOME/.local/bin"
VENDORED="$DIR/vendor/libmpv/usr/lib/x86_64-linux-gnu/libmpv.so.2"

if [ "$1" = "--remove" ]; then
    rm -f "$APPS/samovar-lite.desktop" "$ICONS/samovar-lite.png" "$BIN/samovar-lite"
    update-desktop-database "$APPS" 2>/dev/null || true
    echo "Removed the samovar-lite command and menu entry. Settings stay in ~/.config/samovar-lite."
    exit 0
fi

apt_install() {
    if ! command -v apt-get >/dev/null 2>&1; then
        echo "Please install with your package manager: $*" >&2
        return 1
    fi
    echo "Installing system packages: $*"
    if [ "$(id -u)" = 0 ]; then apt-get install -y "$@"; else sudo apt-get install -y "$@"; fi
}

# 1. Python environment with the player installed in it
if [ ! -x .venv/bin/python ]; then
    if command -v uv >/dev/null 2>&1; then
        uv venv .venv
    elif ! python3 -m venv .venv 2>/dev/null; then
        rm -rf .venv
        apt_install python3-venv
        python3 -m venv .venv
    fi
fi
if command -v uv >/dev/null 2>&1; then
    uv pip install --python .venv/bin/python -e .
else
    .venv/bin/python -m pip install --quiet --upgrade pip
    .venv/bin/python -m pip install --quiet -e .
fi

# 2. libmpv: the system library, else a copy unpacked earlier into vendor/, else install it
libmpv_ok() {
    ldconfig -p 2>/dev/null | grep -q 'libmpv\.so\.2' && return 0
    [ -e "$VENDORED" ] && ! ldd "$VENDORED" 2>/dev/null | grep -q 'not found'
}
if ! libmpv_ok; then
    apt_install libmpv2 libxcb-cursor0 || true
fi
if ! libmpv_ok && command -v apt >/dev/null 2>&1; then
    # No root available: unpack the package locally. Works when its dependencies are present
    # already, which is the case wherever mpv itself is installed.
    echo "Unpacking libmpv2 into vendor/"
    rm -rf vendor/deb vendor/libmpv
    mkdir -p vendor/deb
    (cd vendor/deb && apt download libmpv2)
    for deb in vendor/deb/*.deb; do dpkg -x "$deb" vendor/libmpv; done
fi
if ! libmpv_ok; then
    echo "libmpv could not be set up. Install it (Debian/Ubuntu: sudo apt install libmpv2) and run this again." >&2
    exit 1
fi

if [ "$1" = "--no-desktop" ]; then
    echo "Environment ready: $DIR/.venv/bin/samovar-lite"
    exit 0
fi

# 3. Command, icon and menu entry
mkdir -p "$APPS" "$ICONS" "$BIN"
ln -sf "$DIR/.venv/bin/samovar-lite" "$BIN/samovar-lite"
QT_QPA_PLATFORM=offscreen .venv/bin/python -c "
import sys
from PySide6.QtGui import QGuiApplication
from samovar_lite import skin
app = QGuiApplication(sys.argv[:1])
skin.app_icon_pixmap(256).save(sys.argv[1])
" "$ICONS/samovar-lite.png"
cat > "$APPS/samovar-lite.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Samovar Lite
GenericName=Media Player
Comment=Play videos and music
Exec="$DIR/.venv/bin/samovar-lite" %U
Icon=samovar-lite
Terminal=false
Categories=AudioVideo;Video;Player;
StartupWMClass=samovar-lite
MimeType=video/mp4;video/x-matroska;video/webm;video/x-msvideo;video/quicktime;video/mpeg;video/x-flv;video/x-ms-wmv;video/mp2t;video/3gpp;video/ogg;video/x-m4v;audio/mpeg;audio/flac;audio/x-flac;audio/mp4;audio/ogg;audio/x-wav;audio/wav;audio/aac;audio/x-matroska;audio/opus;application/x-subrip;application/vnd.apple.mpegurl;audio/x-mpegurl;
DESKTOP
update-desktop-database "$APPS" 2>/dev/null || true

echo "Installed. Start Samovar Lite from the application menu, or run: samovar-lite movie.mkv"
case ":$PATH:" in
    *":$BIN:"*) ;;
    *) echo "Note: $BIN is not on your PATH yet; log out and in again, or run $BIN/samovar-lite" ;;
esac
