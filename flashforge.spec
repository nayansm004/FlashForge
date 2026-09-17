# -*- mode: python ; coding: utf-8 -*-
# Build with: pyinstaller flashforge.spec
# Produces a single-folder onedir build per OS (faster startup than onefile).

import sys

# Platform-specific icon: .ico on Windows, .icns on macOS, none needed on Linux
# (Linux desktop icons are handled via the .desktop file / packaging instead).
if sys.platform.startswith('win'):
    icon_file = 'assets/icon.ico'
elif sys.platform == 'darwin':
    icon_file = 'assets/icon.icns'
else:
    icon_file = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['fitz', 'docx'],
    hookspath=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FlashForge',
    debug=False,
    strip=False,
    upx=True,
    console=False,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name='FlashForge',
)

app = BUNDLE(
    coll,
    name='FlashForge.app',
    icon='assets/icon.icns' if sys.platform == 'darwin' else None,
    bundle_identifier='com.flashforge.app',
    info_plist={
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
    },
)
