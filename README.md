# VisionPro IPTV

Desktop IPTV player for Windows, built with Python 3.11, PyQt5 and libVLC, with lossless
recording through FFmpeg. Created and developed by AleXx626.

## Features

- M3U / M3U8 playlists with groups, favorites, search and session restore
- libVLC playback with hardware decoding, fullscreen HUD and tray integration
- Recording of the playing channel without re-encoding (TS / MKV, automatic MP4 remux)
- Unlimited, 5 / 10 minute or custom recording duration with a quick 1–180 min slider
- FFmpeg detection: Preferences path → FFmpeg bundled with the app → system PATH
- Romanian / English interface

## Run from source

```
python -m venv venv
venv\Scripts\pip install PyQt5==5.15.11 python-vlc cryptography
venv\Scripts\python main.py
```

VLC 64-bit must be installed (https://www.videolan.org/vlc/).

## Build

Run `build_visionpro.bat` (PyInstaller, see `BUILD_README.txt`). Put `ffmpeg.exe` in
`vendor\ffmpeg\` first to ship FFmpeg inside `dist\VisionProIPTV` (see `vendor\README.txt`).

## Tests

```
set PYTHONUTF8=1
venv\Scripts\python tests\check_playlist_ui.py
venv\Scripts\python tests\check_restore.py
venv\Scripts\python tests\check_release.py
venv\Scripts\python tests\check_preferences.py
venv\Scripts\python tests\check_licensing_protocol.py
venv\Scripts\python tests\check_recording.py vendor\ffmpeg\ffmpeg.exe vendor\ffmpeg\ffprobe.exe
```

## License

VisionPro IPTV is released under the GNU General Public License v3.0 (see `LICENSE`),
compatible with PyQt5 (GPLv3) and the GPL FFmpeg builds from BtbN. VLC is not redistributed.
The application does not provide TV subscriptions or guarantee the availability of external streams.
