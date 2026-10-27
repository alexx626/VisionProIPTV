VisionPro IPTV 1.2.0 - AleXx626
Local testing build / build instructions

BUILD
Run build_visionpro.bat, or powershell -File build_visionpro.ps1.
Uses venv\Scripts\python.exe. Does not install packages or sign automatically.
Previous dist/build folders are moved into build_archive with a timestamp.
Output: dist\VisionProIPTV\VisionProIPTV.exe. Keep the entire folder together.
The spec excludes user playlists, settings and recordings.

RUNTIME
Windows 64-bit and VLC desktop 64-bit are required (https://www.videolan.org/vlc/).
Recording uses FFmpeg. Detection order: Preferences > Recording path (optional),
FFmpeg bundled with the app (_internal\ffmpeg\ffmpeg.exe or ffmpeg\ffmpeg.exe next to
VisionProIPTV.exe), then ffmpeg on the system PATH. Leave the path empty for automatic.
To bundle FFmpeg, place ffmpeg.exe (+ LICENSE.txt) in vendor\ffmpeg\ before building;
the spec picks it up automatically. vendor\ is not committed to git (large binary).
FFmpeg builds: https://github.com/BtbN/FFmpeg-Builds (GPL) or https://www.gyan.dev/ffmpeg/builds/
VLC is not redistributed in this build.
Choose MPEG-TS (.ts) for live recording, or Matroska (.mkv).
Start Rec records the playing channel; Stop Rec finalizes the output.
Default: automatically remux to MP4 after stopping (without re-encoding).
The original TS/MKV is removed only after successful conversion; on failure it is kept.
Preferences offers Unlimited, 5 min, 10 min or Custom hours/minutes/seconds.
Duration is measured in captured media time. Live-source stalls can extend wall time.
The REC dot blinks and the bar shows progress toward the selected duration.
Recording copies original audio/video without re-encoding or increasing resolution.
It uses a second source connection and continues while switching channels.
A provider allowing only one connection may reject concurrent recording/playback.
Exit from File or tray finalizes active recording before quitting.

CONTROLS / DATA
F11 enters fullscreen. Escape or F11 returns. Space toggles pause.
Fullscreen controls appear on pointer movement, then hide after 2 seconds of inactivity
(they remain visible while the pointer is over them or the volume is being dragged).
Settings: %APPDATA%\VisionProIPTV\config.ini
Playlist snapshot: %APPDATA%\VisionProIPTV\session.json
Window size/position/state, sidebar width, language, volume/mute, favorites,
playlist entries, selected channel and search are retained.
Autoplay is optional and off by default. Close-to-tray is configurable.
Default recording folder: Windows Videos\VisionPro IPTV (configurable).
Session snapshots contain stream URLs; keep them private if they include credentials.

RELEASE STATUS
Prepared for local builds and testing. Not a signed installer or licensed commercial release.
Before public redistribution choose compatible licensing and include required source,
license texts and notices for the chosen Qt/PyQt distribution and other dependencies.
PyQt5 is GPLv3 or commercially licensed; free-of-charge does not permit proprietary distribution by itself.
https://www.riverbankcomputing.com/software/pyqt
https://riverbankcomputing.com/commercial/license-faq
https://www.videolan.org/legal.html
https://ffmpeg.org/legal.html
External playlist availability/rights are independent of the player.
No payment, trial restrictions or activation system is implemented.

DEVELOPMENT CHECKS
Use PYTHONUTF8=1 with venv\Scripts\python.exe for tests.
tests\check_playlist_ui.py, tests\check_restore.py, tests\check_release.py, tests\check_preferences.py
tests\check_recording.py <ffmpeg.exe> <ffprobe.exe>   (e.g. vendor\ffmpeg\ffmpeg.exe vendor\ffmpeg\ffprobe.exe)
GUI regression tests use mocked VLC; verify real playback/fullscreen/minimize separately.
Validated dependencies: PyQt5 5.15.11, PyQt5-Qt5 5.15.2, PyQt5-sip 12.18.0,
python-vlc 3.0.21203, PyInstaller 6.19.0, Python 3.11.
Activation signature foundation: cryptography 50.0.2.
