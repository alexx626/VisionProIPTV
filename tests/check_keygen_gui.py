"""Keygen GUI: load key, issue a code the app accepts, log + history, mismatch warning (offscreen)."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
scratch = tempfile.TemporaryDirectory()
os.environ['APPDATA'] = scratch.name
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt5 import QtWidgets
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
import keygen_gui
from licensing_protocol import b64encode, verify_entitlement

keygen_gui.CONFIG = Path(scratch.name) / 'keygen.ini'
keys = Path(scratch.name) / 'keys'
keys.mkdir()
project_key = Path(__file__).resolve().parents[1] / 'keys' / 'private.key'
if project_key.is_file():
    (keys / 'private.key').write_text(project_key.read_text())
    public = keygen_gui.APP_PUBLIC_KEY
else:  # no project key on this machine: ephemeral key, patch the expected public key
    private = Ed25519PrivateKey.generate()
    (keys / 'private.key').write_text(b64encode(private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())))
    from cryptography.hazmat.primitives.serialization import PublicFormat
    public = keygen_gui.APP_PUBLIC_KEY = b64encode(private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))

app = QtWidgets.QApplication([])
with patch.object(QtWidgets.QMessageBox, 'exec_', return_value=0):
    window = keygen_gui.Keygen()
    assert not window.generate_button.isEnabled()
    window.load_key(keys / 'private.key')
assert window.generate_button.isEnabled() and 'Key OK' in window.status.text(), window.status.text()
window.email.setText(' Buyer@Example.com ')
window.generate()
token = window.code.toPlainText()
assert verify_entitlement(token, 'buyer@example.com', public)['kind'] == 'lifetime'
assert app.clipboard().text() == token
log = (keys / 'issued_codes.txt').read_text(encoding='utf-8')
assert 'buyer@example.com\t' + token in log and window.history.count() == 1
# Remembered key path on next start
window2 = keygen_gui.Keygen()
assert window2.key_path == keys / 'private.key' and window2.history.count() == 1
# Wrong key -> warning
other = Ed25519PrivateKey.generate()
(keys / 'other.key').write_text(b64encode(other.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())))
window.load_key(keys / 'other.key')
assert 'WARNING' in window.status.text()
print('PASS: keygen GUI issues app-valid codes, logs them, remembers the key, warns on key mismatch')
