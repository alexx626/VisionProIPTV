"""Preferences dialog regression: quick-duration slider sync and FFmpeg detection (mocked VLC, offscreen)."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
scratch = tempfile.TemporaryDirectory()
os.environ['APPDATA'] = scratch.name
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.modules['vlc'] = MagicMock()
from PyQt5 import QtWidgets
import player_services
from player_services import settings, preferences, ffmpeg_path, ffmpeg_source
from main import VisionApp

app = VisionApp([], initialize=False)
app.initialize()
window = app.main_window
cfg = settings()
cfg.setValue('Settings/record_duration', 'unlimited')
cfg.setValue('Settings/ffmpeg_path', '')
cfg.sync()

captured = {}
def fake_exec(dialog):
    captured['dialog'] = dialog
    return 0
with patch.object(QtWidgets.QDialog, 'exec_', fake_exec):
    preferences(window)
dialog = captured['dialog']
sliders = [s for s in dialog.findChildren(QtWidgets.QSlider) if s.maximum() == 180]
assert len(sliders) == 1, 'quick duration slider missing'
slider = sliders[0]
combos = {c for c in dialog.findChildren(QtWidgets.QComboBox) if c.findData('custom') >= 0}
combo = combos.pop()
spins = [s for s in dialog.findChildren(QtWidgets.QSpinBox) if s.suffix() in (' h', ' min', ' s')]
hours = next(s for s in spins if s.suffix() == ' h')
minutes = next(s for s in spins if s.suffix() == ' min')
seconds = next(s for s in spins if s.suffix() == ' s')

assert slider.isEnabled(), 'slider must be usable even when duration is not Custom'
slider.setValue(90)
app.processEvents()
assert combo.currentData() == 'custom', combo.currentData()
assert (hours.value(), minutes.value(), seconds.value()) == (1, 30, 0), (hours.value(), minutes.value(), seconds.value())
minutes.setValue(45)
app.processEvents()
assert slider.value() == 105, slider.value()
hours.setValue(3)  # 225 min -> clamps slider to 180, fields untouched
app.processEvents()
assert slider.value() == 180 and hours.value() == 3 and minutes.value() == 45
print('PASS: quick-duration slider switches to Custom, fills h/min, fields move the slider')

# FFmpeg detection: configured path wins, bundled/PATH fallback reported, empty field means automatic.
fake = Path(scratch.name) / 'ffmpeg.exe'
fake.write_bytes(b'x')
with patch.object(player_services, 'bundled_ffmpeg_candidates', return_value=[fake]):
    assert Path(ffmpeg_path()) == fake and ffmpeg_source() == 'bundled'
cfg.setValue('Settings/ffmpeg_path', str(fake))
cfg.sync()
assert ffmpeg_source() == 'configured'
cfg.setValue('Settings/ffmpeg_path', '')
cfg.sync()
line = next(e for e in dialog.findChildren(QtWidgets.QLineEdit) if e.placeholderText())
assert line.text() == '', 'auto-detected path must not be written into the setting field'
print('PASS: FFmpeg detection order and empty-field automatic mode')
dialog.deleteLater()
