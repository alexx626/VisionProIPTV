"""VisionPro IPTV Keygen - standalone GUI for issuing lifetime activation codes.

Runs from anywhere (also as VisionProKeygen.exe). The private key location is remembered in
%APPDATA%\\VisionProIPTV-Keygen\\keygen.ini. Every issued code is appended to issued_codes.txt
next to the private key and can also be saved as a separate .txt per customer.
NEVER ship this tool or the private key to customers.
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption
from PyQt5 import QtCore, QtGui, QtWidgets
from licensing_protocol import PRODUCT, b64decode, b64encode, normalize_email, verify_entitlement

APP_PUBLIC_KEY = 'PC6YacBFlJflWwtNaAcGwna_z5Lm0NBQnwX0SU0KrVo'   # must equal licensing.PUBLIC_KEY in the player
CONFIG_DIR = Path(os.environ.get('APPDATA', str(Path.home()))) / 'VisionProIPTV-Keygen'
CONFIG = CONFIG_DIR / 'keygen.ini'
STYLE = '''
QWidget {background:#101e2c;color:#e2edf5;font-family:"Segoe UI";font-size:13px;}
QLineEdit, QPlainTextEdit, QListWidget {background:#0c1622;color:#edf5fc;border:1px solid #375469;border-radius:4px;padding:6px;}
QPushButton {background:#20394b;color:white;padding:8px 14px;border-radius:5px;}
QPushButton:hover {background:#007fa9;}
QPushButton#primary {background:#007fa9;font-weight:bold;}
QLabel#status {padding:8px;border-radius:6px;background:#172b3b;}
'''


def settings():
    return QtCore.QSettings(str(CONFIG), QtCore.QSettings.IniFormat)


class Keygen(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('VisionPro IPTV Keygen')
        self.setMinimumSize(760, 560)
        self.setStyleSheet(STYLE)
        self.private = None
        self.key_path = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)
        self.status = QtWidgets.QLabel()
        self.status.setObjectName('status')
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        layout.addWidget(self.status)
        key_row = QtWidgets.QHBoxLayout()
        self.choose_button = QtWidgets.QPushButton('Choose private key...')
        self.choose_button.clicked.connect(self.choose_key)
        self.create_button = QtWidgets.QPushButton('Create new key...')
        self.create_button.clicked.connect(self.create_key)
        self.open_folder_button = QtWidgets.QPushButton('Open key folder')
        self.open_folder_button.clicked.connect(lambda: self.key_path and QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.key_path.parent))))
        for button in (self.choose_button, self.create_button, self.open_folder_button):
            key_row.addWidget(button)
        key_row.addStretch()
        layout.addLayout(key_row)
        form = QtWidgets.QFormLayout()
        self.email = QtWidgets.QLineEdit()
        self.email.setPlaceholderText('customer@email.com')
        self.email.returnPressed.connect(self.generate)
        form.addRow('Customer email', self.email)
        layout.addLayout(form)
        action_row = QtWidgets.QHBoxLayout()
        self.generate_button = QtWidgets.QPushButton('Generate code')
        self.generate_button.setObjectName('primary')
        self.generate_button.clicked.connect(self.generate)
        self.copy_button = QtWidgets.QPushButton('Copy code')
        self.copy_button.clicked.connect(self.copy_code)
        self.save_button = QtWidgets.QPushButton('Save as .txt...')
        self.save_button.clicked.connect(self.save_as)
        for button in (self.generate_button, self.copy_button, self.save_button):
            action_row.addWidget(button)
        action_row.addStretch()
        layout.addLayout(action_row)
        self.code = QtWidgets.QPlainTextEdit()
        self.code.setReadOnly(True)
        self.code.setFixedHeight(90)
        self.code.setPlaceholderText('The activation code appears here and is copied to the clipboard.')
        layout.addWidget(self.code)
        layout.addWidget(QtWidgets.QLabel('Issued codes (issued_codes.txt next to the private key):'))
        self.history = QtWidgets.QListWidget()
        self.history.itemClicked.connect(self.show_history_item)
        layout.addWidget(self.history, 1)
        stored = str(settings().value('private_key', '') or '')
        if stored and Path(stored).is_file():
            self.load_key(Path(stored))
        else:
            self.refresh()
            QtCore.QTimer.singleShot(200, self.first_run)

    # ---------- key management ----------
    def first_run(self):
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle('VisionPro IPTV Keygen')
        box.setText('No private key configured yet.\n\nChoose the existing keys\\private.key of the project, or create a new key (only for a brand-new app build that embeds the new public key).')
        choose = box.addButton('Choose existing key...', QtWidgets.QMessageBox.AcceptRole)
        box.addButton('Create new key...', QtWidgets.QMessageBox.ActionRole)
        box.addButton(QtWidgets.QMessageBox.Cancel)
        box.exec_()
        if box.clickedButton() is choose:
            self.choose_key()
        elif box.clickedButton() is not box.button(QtWidgets.QMessageBox.Cancel):
            self.create_key()

    def choose_key(self):
        start = str(self.key_path.parent) if self.key_path else str(Path.home())
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Choose private.key', start, 'Key files (*.key);;All files (*)')
        if path:
            self.load_key(Path(path))

    def create_key(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, 'Folder where the new private key will be saved', str(Path.home()))
        if not folder:
            return
        target = Path(folder) / 'private.key'
        if target.exists():
            QtWidgets.QMessageBox.warning(self, 'Keygen', f'{target} already exists. Choose it instead of creating a new one.')
            return
        private = Ed25519PrivateKey.generate()
        target.write_text(b64encode(private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())))
        public = b64encode(private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
        (target.parent / 'public.key').write_text(public)
        QtWidgets.QApplication.clipboard().setText(public)
        QtWidgets.QMessageBox.information(self, 'New key created',
            f'Private key: {target}\nPublic key (copied to clipboard):\n{public}\n\n'
            'Codes from this key only work in an app build whose licensing.py has this PUBLIC_KEY. Back up the private key!')
        self.load_key(target)

    def load_key(self, path):
        try:
            self.private = Ed25519PrivateKey.from_private_bytes(b64decode(path.read_text().strip()))
        except (OSError, ValueError) as exc:
            QtWidgets.QMessageBox.critical(self, 'Keygen', f'Cannot read private key:\n{exc}')
            return
        self.key_path = path
        cfg = settings()
        cfg.setValue('private_key', str(path))
        cfg.sync()
        self.refresh()
        self.load_history()

    @property
    def public_key(self):
        return b64encode(self.private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)) if self.private else ''

    @property
    def log_path(self):
        return self.key_path.parent / 'issued_codes.txt' if self.key_path else None

    def refresh(self):
        ready = self.private is not None
        for widget in (self.generate_button, self.email, self.copy_button, self.save_button, self.open_folder_button):
            widget.setEnabled(ready)
        if not ready:
            self.status.setText('<b style="color:#ffb454">No private key loaded.</b> Choose or create one.')
        elif self.public_key != APP_PUBLIC_KEY:
            self.status.setText(f'<b style="color:#ff6b6b">WARNING: this key does not match the public key built into VisionPro IPTV.</b> Codes will be rejected by the app.<br>Key: {self.key_path}')
        else:
            self.status.setText(f'<b style="color:#7be37f">Key OK</b> - matches the app public key.<br>Key: {self.key_path}<br>Log: {self.log_path}')

    # ---------- issuing ----------
    def generate(self):
        if not self.private:
            return
        try:
            email = normalize_email(self.email.text())
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, 'Keygen', str(exc))
            return
        payload = dict(version=1, product=PRODUCT, email=email, kind='lifetime', issued_at=int(time.time()))
        raw = b64encode(json.dumps(payload, separators=(',', ':')).encode())
        token = 'VP1.' + raw + '.' + b64encode(self.private.sign(('VP1.' + raw).encode()))
        verify_entitlement(token, email, self.public_key)
        self.code.setPlainText(token)
        QtWidgets.QApplication.clipboard().setText(token)
        stamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        try:
            with self.log_path.open('a', encoding='utf-8') as log:
                log.write(f'{stamp}\t{email}\t{token}\n')
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, 'Keygen', f'Code generated but could not be written to the log:\n{exc}')
        self.load_history()
        self.status.setText(f'<b style="color:#7be37f">Code issued for {email}</b> - copied to clipboard and saved in {self.log_path}')

    def copy_code(self):
        if self.code.toPlainText():
            QtWidgets.QApplication.clipboard().setText(self.code.toPlainText())

    def save_as(self):
        token = self.code.toPlainText().strip()
        if not token:
            return
        email = normalize_email(self.email.text())
        default = str(self.key_path.parent / (email.replace('@', '_at_') + '.txt'))
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Save activation code', default, 'Text files (*.txt)')
        if path:
            Path(path).write_text(f'VisionPro IPTV - lifetime license\nEmail: {email}\nActivation code:\n{token}\n\n'
                                  'Open VisionPro IPTV > Help > Activate license, enter the email and this code.\n', encoding='utf-8')

    def load_history(self):
        self.history.clear()
        if self.log_path and self.log_path.is_file():
            for line in reversed(self.log_path.read_text(encoding='utf-8').splitlines()):
                parts = line.split('\t')
                if len(parts) == 3:
                    item = QtWidgets.QListWidgetItem(f'{parts[0]}   {parts[1]}')
                    item.setData(QtCore.Qt.UserRole, (parts[1], parts[2]))
                    self.history.addItem(item)

    def show_history_item(self, item):
        email, token = item.data(QtCore.Qt.UserRole)
        self.email.setText(email)
        self.code.setPlainText(token)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = Keygen()
    window.show()
    sys.exit(app.exec_())
