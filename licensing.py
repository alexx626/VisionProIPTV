"""License state for the desktop app: 60-day trial, lifetime activation by email, limited free mode.

Free mode (no code, trial over): at most FREE_CHANNELS_PER_DAY distinct channels per day, no recording.
Only the public key is embedded here; codes are issued with tools/keygen.py (private key stays offline).
"""
import hashlib
import os
import time
import uuid
import webbrowser
from datetime import date
from pathlib import Path
from PyQt5 import QtCore, QtWidgets

from licensing_protocol import TRIAL_DAYS, normalize_email, verify_entitlement
from player_services import DATA_DIR, settings

PUBLIC_KEY = 'PC6YacBFlJflWwtNaAcGwna_z5Lm0NBQnwX0SU0KrVo'
PRICE_TEXT = '5 EUR'
BUY_URL = 'https://www.paypal.com/donate?business=AleXx626@gmx.de&currency_code=EUR&amount=5'
CONTACT_EMAIL = 'alexx626@gmail.com'
FREE_CHANNELS_PER_DAY = 10
_LOCAL_MARKER = Path(os.environ.get('LOCALAPPDATA', str(DATA_DIR))) / 'VisionProIPTV' / 'install.dat'


def installation_id():
    cfg = settings()
    value = str(cfg.value('License/installation_id', '') or '')
    if not value:
        value = uuid.uuid4().hex
        cfg.setValue('License/installation_id', value)
        cfg.sync()
    return value


def trial_started(now=None):
    """First-run timestamp, kept in config.ini and LOCALAPPDATA; the earliest copy wins."""
    now = int(time.time() if now is None else now)
    cfg = settings()
    stamps = []
    for raw in (cfg.value('License/trial_started', ''), _LOCAL_MARKER.read_text().strip() if _LOCAL_MARKER.is_file() else ''):
        try:
            value = int(str(raw))
            if 0 < value <= now + 86400:
                stamps.append(value)
        except ValueError:
            pass
    started = min(stamps) if stamps else now
    if cfg.value('License/trial_started', '') != str(started):
        cfg.setValue('License/trial_started', str(started))
        cfg.sync()
    try:
        if not _LOCAL_MARKER.is_file() or _LOCAL_MARKER.read_text().strip() != str(started):
            _LOCAL_MARKER.parent.mkdir(parents=True, exist_ok=True)
            _LOCAL_MARKER.write_text(str(started))
    except OSError:
        pass
    return started


def licensed_data():
    cfg = settings()
    token, email = str(cfg.value('License/token', '') or ''), str(cfg.value('License/email', '') or '')
    if not token or not email:
        return None
    try:
        return verify_entitlement(token, email, PUBLIC_KEY, installation_id())
    except ValueError:
        return None


def status(now=None):
    """{'kind': 'licensed'|'trial'|'limited', 'email': str, 'days_left': int}"""
    data = licensed_data()
    if data:
        return {'kind': 'licensed', 'email': data['email'], 'days_left': 0}
    now = int(time.time() if now is None else now)
    elapsed_days = max(0, now - trial_started(now)) // 86400
    days_left = TRIAL_DAYS - elapsed_days
    if days_left > 0:
        return {'kind': 'trial', 'email': '', 'days_left': days_left}
    return {'kind': 'limited', 'email': '', 'days_left': 0}


def is_full(now=None):
    return status(now)['kind'] != 'limited'


def activate(email, code):
    """Verify and store the code; raises ValueError with a user-facing message."""
    email = normalize_email(email)
    data = verify_entitlement(code.strip(), email, PUBLIC_KEY, installation_id())
    cfg = settings()
    cfg.setValue('License/email', email)
    cfg.setValue('License/token', code.strip())
    cfg.sync()
    return data


def deactivate():
    cfg = settings()
    cfg.remove('License/email')
    cfg.remove('License/token')
    cfg.sync()


def _today_channels(cfg):
    today = date.today().isoformat()
    if str(cfg.value('License/day', '')) != today:
        return today, []
    raw = str(cfg.value('License/channels', '') or '')
    return today, [h for h in raw.split(',') if h]


def channels_left_today():
    if is_full():
        return None
    return max(0, FREE_CHANNELS_PER_DAY - len(_today_channels(settings())[1]))


def can_play_channel(url):
    """Free mode: a channel already opened today is always allowed; new ones count toward the daily limit."""
    if is_full():
        return True
    cfg = settings()
    today, played = _today_channels(cfg)
    digest = hashlib.sha1(str(url).encode('utf-8', 'replace')).hexdigest()[:12]
    if digest in played:
        return True
    if len(played) >= FREE_CHANNELS_PER_DAY:
        return False
    played.append(digest)
    cfg.setValue('License/day', today)
    cfg.setValue('License/channels', ','.join(played))
    cfg.sync()
    return True


def recording_allowed():
    return is_full()


def status_text(tr, now=None):
    info = status(now)
    if info['kind'] == 'licensed':
        return tr('Registered') + ': ' + info['email']
    if info['kind'] == 'trial':
        return tr('Trial') + ': ' + tr('{0} days left').format(info['days_left'])
    left = channels_left_today()
    return tr('Not activated') + ' - ' + tr('{0} of {1} channels left today, recording off').format(left, FREE_CHANNELS_PER_DAY)


def status_color():
    return {'licensed': '#7be37f', 'trial': '#ffd166'}.get(status()['kind'], '#ff6b6b')


def limit_message(tr):
    return tr('Free mode allows {0} different channels per day. Activate the lifetime license ({1}) to remove the limit.').format(FREE_CHANNELS_PER_DAY, PRICE_TEXT)


def recording_message(tr):
    return tr('Recording requires an active trial or a lifetime license ({0}).').format(PRICE_TEXT)


def activation_dialog(window):
    """Email + code activation; Buy opens PayPal and explains how the code is delivered."""
    tr = window.tr
    cfg = settings()
    dialog = QtWidgets.QDialog(window)
    dialog.setWindowTitle(tr('Activate VisionPro IPTV'))
    dialog.setMinimumWidth(640)
    dialog.setStyleSheet('QDialog{background:#101e2c;color:#e2edf5;} QLabel{color:#d2e3ef;} '
                         'QLineEdit, QPlainTextEdit{background:#0c1622;color:#edf5fc;border:1px solid #375469;border-radius:4px;padding:7px;} '
                         'QPushButton{background:#20394b;color:white;padding:9px 14px;border-radius:5px;} QPushButton:hover{background:#007fa9;}')
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setSpacing(12)
    state = QtWidgets.QLabel()
    state.setWordWrap(True)
    state.setStyleSheet('font-size:14px;font-weight:bold;padding:10px;background:#172b3b;border-radius:8px;')
    layout.addWidget(state)
    form = QtWidgets.QFormLayout()
    email = QtWidgets.QLineEdit(str(cfg.value('License/email', '') or ''))
    email.setPlaceholderText(tr('The email address used for the purchase'))
    code = QtWidgets.QPlainTextEdit(str(cfg.value('License/token', '') or ''))
    code.setPlaceholderText('VP1.…')
    code.setFixedHeight(90)
    form.addRow(tr('Email'), email)
    form.addRow(tr('Activation code'), code)
    layout.addLayout(form)
    help_text = QtWidgets.QLabel(tr('Lifetime license: {0}, one email, all future versions. After paying with PayPal, send the PayPal email to {1} and you receive the code by email.').format(PRICE_TEXT, CONTACT_EMAIL))
    help_text.setWordWrap(True)
    help_text.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
    layout.addWidget(help_text)
    message = QtWidgets.QLabel()
    message.setWordWrap(True)
    layout.addWidget(message)
    buttons = QtWidgets.QHBoxLayout()
    buy = QtWidgets.QPushButton(tr('Buy lifetime license ({0})').format(PRICE_TEXT))
    activate_button = QtWidgets.QPushButton(tr('Activate'))
    remove_button = QtWidgets.QPushButton(tr('Remove code'))
    close = QtWidgets.QPushButton(tr('Close'))
    for button in (buy, activate_button, remove_button, close):
        buttons.addWidget(button)
    layout.addLayout(buttons)

    def refresh():
        state.setText(status_text(tr))
        state.setStyleSheet(state.styleSheet() + f'color:{status_color()};')
        remove_button.setVisible(licensed_data() is not None)
        if hasattr(window, 'refresh_license_status'):
            window.refresh_license_status()

    def do_activate():
        try:
            data = activate(email.text(), code.toPlainText())
        except ValueError as exc:
            message.setText('<span style="color:#ff6b6b">' + tr(str(exc)) + '</span>')
            return
        message.setText('<span style="color:#7be37f">' + tr('License activated for {0}. Thank you!').format(data['email']) + '</span>')
        refresh()

    def do_remove():
        deactivate()
        code.clear()
        message.setText(tr('The activation code was removed from this computer.'))
        refresh()

    buy.clicked.connect(lambda: webbrowser.open(BUY_URL))
    activate_button.clicked.connect(do_activate)
    remove_button.clicked.connect(do_remove)
    close.clicked.connect(dialog.accept)
    refresh()
    dialog.exec_()
