# VisionProKeygen.exe - single-file GUI for issuing license codes. Private. Never distribute.
from pathlib import Path
root = Path(SPECPATH)
a = Analysis([str(root / 'tools/keygen_gui.py')], pathex=[str(root)], binaries=[], datas=[],
             hiddenimports=['licensing_protocol', 'PyQt5.sip'], hookspath=[], runtime_hooks=[],
             excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'vlc', 'PyQt5.QtWebEngine',
                       'PyQt5.QtWebEngineWidgets', 'PyQt5.QtQml', 'PyQt5.QtQuick', 'PyQt5.QtMultimedia',
                       'PyQt5.QtNetwork', 'PyQt5.QtSql', 'PyQt5.QtTest'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='VisionProKeygen', debug=False,
          strip=False, upx=False, console=False, icon=str(root / 'icons/tray_icon.ico'))
