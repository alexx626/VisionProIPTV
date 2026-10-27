"""Trial, limited mode (10 channels/day, no recording), activation and title status; ephemeral test key."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
scratch = tempfile.TemporaryDirectory()
os.environ['APPDATA'] = scratch.name
os.environ['LOCALAPPDATA'] = scratch.name
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.modules['vlc'] = MagicMock()
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from PyQt5 import QtCore, QtWidgets
import licensing
from licensing_protocol import PRODUCT, b64encode
from player_services import settings
from main import VisionApp

private = Ed25519PrivateKey.generate()
licensing.PUBLIC_KEY = b64encode(private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
licensing._LOCAL_MARKER = Path(scratch.name) / 'install.dat'

def sign(payload):
    raw = b64encode(json.dumps(payload, separators=(',', ':')).encode())
    return 'VP1.' + raw + '.' + b64encode(private.sign(('VP1.' + raw).encode()))

now = int(time.time())
app = VisionApp([], initialize=False)
app.initialize()
window, tab = app.main_window, app.main_window.iptv_tab

# Fresh install: trial with 60 days, everything allowed, title shows it.
info = licensing.status(now)
assert info['kind'] == 'trial' and info['days_left'] == 60, info
assert licensing.recording_allowed() and all(licensing.can_play_channel(f'http://x/{i}') for i in range(25))
assert 'Trial' in window.windowTitle() and '60' in window.license_label.text(), window.windowTitle()

# Trial over: limited mode. Deleting config.ini must not reset the trial (LOCALAPPDATA marker).
cfg = settings()
cfg.setValue('License/trial_started', str(now - 61 * 86400))
cfg.sync()
licensing._LOCAL_MARKER.write_text(str(now - 61 * 86400))
assert licensing.status(now)['kind'] == 'limited'
cfg.remove('License/trial_started'); cfg.sync()
assert licensing.status(now)['kind'] == 'limited', 'trial must survive config reset'
cfg.remove('License/day'); cfg.remove('License/channels'); cfg.sync()
assert licensing.channels_left_today() == 10
for i in range(10):
    assert licensing.can_play_channel(f'http://x/{i}')
assert licensing.can_play_channel('http://x/3'), 'replaying a channel from today is free'
assert not licensing.can_play_channel('http://x/new') and licensing.channels_left_today() == 0
assert not licensing.recording_allowed()
window.refresh_license_status()
assert 'Not activated' in window.windowTitle() and '0 of 10' in window.license_label.text(), window.windowTitle()

# UI gates: 11th channel and recording show the activation offer and do nothing.
offers = []
tab._offer_activation = lambda text: offers.append(text)
tab.player.play.reset_mock()
tab.playlist_tree.clear()
tab.tree_helper.add_channel('Manual', 'Blocked', 'http://x/blocked')
item = tab.playlist_tree.topLevelItem(0).child(0)
tab._play_tree_item(item, 0)
assert not tab.player.play.called and len(offers) == 1, offers
tab.current_url = 'http://x/3'
started = []
tab.recorder.start = lambda url, name: started.append(url)
tab.start_recording()
assert not started and len(offers) == 2
print('PASS: trial 60 days, limited mode 10 channels/day with replay, recording gate, config-reset protection, title status')

# Activation: wrong email rejected, right email accepted, status persists via settings, removal works.
token = sign(dict(version=1, product=PRODUCT, email='buyer@example.com', kind='lifetime', issued_at=now))
try:
    licensing.activate('other@example.com', token)
    raise AssertionError('wrong email accepted')
except ValueError as exc:
    assert 'different email' in str(exc)
assert licensing.activate(' Buyer@Example.com ', token)['kind'] == 'lifetime'
assert licensing.status(now)['kind'] == 'licensed' and licensing.recording_allowed()
assert licensing.can_play_channel('http://x/new')
window.refresh_license_status()
assert 'Registered: buyer@example.com' in window.windowTitle(), window.windowTitle()
window.apply_language('ro')
assert 'Înregistrat' in window.license_label.text(), window.license_label.text()
licensing.deactivate()
assert licensing.status(now)['kind'] == 'limited'

# Activation dialog: fill email + code, press Activate, dialog reports success.
captured = {}
with patch.object(QtWidgets.QDialog, 'exec_', lambda d: captured.setdefault('dialog', d) and 0):
    licensing.activation_dialog(window)
dialog = captured['dialog']
dialog.findChild(QtWidgets.QLineEdit).setText('buyer@example.com')
dialog.findChild(QtWidgets.QPlainTextEdit).setPlainText(token)
next(b for b in dialog.findChildren(QtWidgets.QPushButton) if b.text() == 'Activează').click()
assert licensing.status(now)['kind'] == 'licensed'
print('PASS: lifetime activation by email, RO/EN status, activation dialog')

# Registered view: badge is not clickable, dialog hides buy/activate/fields and shows only Remove/Close.
window.refresh_license_status()
assert window.license_label.cursor().shape() == QtCore.Qt.ArrowCursor and window.license_label.text().startswith('✔')
captured.clear()
with patch.object(QtWidgets.QDialog, 'exec_', lambda d: captured.setdefault('dialog', d) and 0):
    licensing.activation_dialog(window)
dialog = captured['dialog']
buttons = {b.text(): b for b in dialog.findChildren(QtWidgets.QPushButton)}
assert not buttons['Activează'].isVisibleTo(dialog) and not any(t.startswith('Cumpără') and b.isVisibleTo(dialog) for t, b in buttons.items())
assert buttons['Șterge codul'].isVisibleTo(dialog) and not dialog.findChild(QtWidgets.QPlainTextEdit).isVisibleTo(dialog)
licensing.deactivate(); window.refresh_license_status()
assert window.license_label.cursor().shape() == QtCore.Qt.PointingHandCursor
print('PASS: registered state shows plain badge and a dialog without buy/activate controls')
