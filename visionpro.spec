# Absolute paths; user playlists/config/media are never bundled.
from pathlib import Path
root = Path(SPECPATH)
datas = [(str(root / 'gui/vision_theme.qss'), 'gui'),
         (str(root / 'icons/*.png'), 'icons'), (str(root / 'icons/*.ico'), 'icons'),
         (str(root / 'translations/*.json'), 'translations'),
         (str(root / 'BUILD_README.txt'), '.')]
# Optional bundled FFmpeg: drop ffmpeg.exe (and its LICENSE) in vendor/ffmpeg/ before building.
# It is shipped as _internal/ffmpeg/ffmpeg.exe and detected automatically by player_services.ffmpeg_path().
binaries = []
ffmpeg_exe = root / 'vendor/ffmpeg/ffmpeg.exe'
if ffmpeg_exe.is_file():
    binaries.append((str(ffmpeg_exe), 'ffmpeg'))
    for notice in ('LICENSE.txt', 'LICENSE', 'README.txt'):
        if (ffmpeg_exe.parent / notice).is_file():
            datas.append((str(ffmpeg_exe.parent / notice), 'ffmpeg'))
    print('visionpro.spec: bundling FFmpeg from', ffmpeg_exe)
else:
    print('visionpro.spec: vendor/ffmpeg/ffmpeg.exe not found - recording will need an external FFmpeg')
a = Analysis([str(root / 'main.py')], pathex=[str(root)], binaries=binaries, datas=datas,
             hiddenimports=['vlc', 'PyQt5.sip'], hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'PyQt5.QtWebEngine',
                       'PyQt5.QtWebEngineWidgets', 'PyQt5.QtQml', 'PyQt5.QtQuick'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='VisionProIPTV',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, icon=str(root / 'icons/tray_icon.ico'), version=str(root / 'version_info.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='VisionProIPTV')
