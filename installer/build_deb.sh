#!/usr/bin/env bash
# Builds FlashForge_<version>_amd64.deb from the PyInstaller dist/ output.
# Run from the repo root (flashforge/) after `pyinstaller flashforge.spec`.
# Usage: bash installer/build_deb.sh 1.0.0
set -euo pipefail

VERSION="${1:-1.0.0}"
PKG_DIR="dist_deb/flashforge_${VERSION}_amd64"

rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/opt/flashforge"
mkdir -p "$PKG_DIR/usr/share/applications"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$PKG_DIR/usr/bin"

# App payload (the onedir PyInstaller build)
cp -r dist/FlashForge/* "$PKG_DIR/opt/flashforge/"

# Desktop entry + icon so it shows up in the app menu
cp installer/flashforge.desktop "$PKG_DIR/usr/share/applications/flashforge.desktop"
cp assets/icon_256.png "$PKG_DIR/usr/share/icons/hicolor/256x256/apps/flashforge.png"

# Symlink so `flashforge` also works from a terminal
ln -sf /opt/flashforge/FlashForge "$PKG_DIR/usr/bin/flashforge"

# Debian control file
cat > "$PKG_DIR/DEBIAN/control" << EOF
Package: flashforge
Version: ${VERSION}
Section: education
Priority: optional
Architecture: amd64
Maintainer: FlashForge <noreply@example.com>
Description: AI Flashcard Software
 FlashForge generates and reviews AI-powered flashcards from your notes
 and documents.
EOF

chmod -R 755 "$PKG_DIR/DEBIAN"
dpkg-deb --build --root-owner-group "$PKG_DIR"

mkdir -p dist_installer
mv "dist_deb/flashforge_${VERSION}_amd64.deb" "dist_installer/FlashForge-${VERSION}-linux-amd64.deb"
echo "Built dist_installer/FlashForge-${VERSION}-linux-amd64.deb"
