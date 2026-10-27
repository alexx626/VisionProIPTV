"""Persistent settings, lossless recording and fullscreen controls."""
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from PyQt5 import QtCore, QtGui, QtWidgets

VERSION = '1.2.0'
DATA_DIR = Path(os.environ.get('APPDATA', str(Path.home()))) / 'VisionProIPTV'
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = DATA_DIR / 'config.ini'


def settings():
    result = QtCore.QSettings(str(CONFIG_PATH), QtCore.QSettings.IniFormat)
    result.setIniCodec('UTF-8')
    return result


def flag(key, default=False):
    return str(settings().value(key, default)).lower() in ('true', '1', 'yes')


def bundled_ffmpeg_candidates():
    """FFmpeg shipped with the application: next to the .exe, in _internal, or vendor/ in source."""
    roots = []
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        roots += [exe_dir, exe_dir / '_internal', Path(getattr(sys, '_MEIPASS', exe_dir))]
    roots.append(Path(__file__).resolve().parent)
    names = ['ffmpeg/ffmpeg.exe', 'vendor/ffmpeg/ffmpeg.exe', 'ffmpeg.exe', 'ffmpeg/ffmpeg', 'ffmpeg']
    return [root / name for root in roots for name in names]


def ffmpeg_path():
    """Preferred order: explicit setting, FFmpeg bundled with the app, then PATH. Empty if none."""
    configured = str(settings().value('Settings/ffmpeg_path', '') or '').strip()
    candidates = [configured] + bundled_ffmpeg_candidates() + [shutil.which('ffmpeg')]
    for path in candidates:
        if path and Path(path).is_file():
            return str(path)
    return ''


def ffmpeg_source():
    """'configured', 'bundled', 'path' or '' for the FFmpeg that ffmpeg_path() would use."""
    found = ffmpeg_path()
    if not found:
        return ''
    configured = str(settings().value('Settings/ffmpeg_path', '') or '').strip()
    if configured and Path(configured).is_file() and Path(configured) == Path(found):
        return 'configured'
    if any(candidate.is_file() and candidate.resolve() == Path(found).resolve() for candidate in bundled_ffmpeg_candidates()):
        return 'bundled'
    return 'path'


def recordings_dir():
    default = Path(QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.MoviesLocation)) / 'VisionPro IPTV'
    return Path(settings().value('Settings/record_dir', str(default)))


class Recorder(QtCore.QObject):
    changed = QtCore.pyqtSignal(str, str)
    finished = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.output = None
        self.state = 'idle'
        self.started_at = None
        self._tail = ''
        self._stopping = False
        self.elapsed_seconds = 0
        self.duration_seconds = 0
        self._progress_buffer = ''
        self._remuxing = False
        self._kill_timer = QtCore.QTimer(self)
        self._kill_timer.setSingleShot(True)
        self._kill_timer.timeout.connect(self._force_stop)

    @property
    def active(self):
        return self.process is not None

    def start(self, url, name):
        if self.active:
            return
        executable = ffmpeg_path()
        if not executable:
            self.changed.emit('error', 'FFmpeg was not found. Select the FFmpeg executable in Preferences > Recording.')
            return
        directory = recordings_dir()
        cfg = settings()
        mode = str(cfg.value('Settings/record_duration', 'unlimited'))
        self.duration_seconds = {'5': 300, '10': 600}.get(mode, 0)
        if mode == 'custom':
            self.duration_seconds = max(1, min(604799,
                cfg.value('Settings/record_hours', 0, type=int) * 3600 +
                cfg.value('Settings/record_minutes', 5, type=int) * 60 +
                cfg.value('Settings/record_seconds', 0, type=int)))
        self.auto_remux = flag('Settings/auto_remux', True)
        self.keep_original = flag('Settings/keep_recording_original', False)
        self.elapsed_seconds = 0
        self._progress_buffer = ''
        self._remuxing = False
        self._executable = executable
        try:
            directory.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r'[^\w.-]+', '_', name, flags=re.UNICODE).strip('._')[:70] or 'channel'
            # Microseconds + -n protect existing recordings from overwrite.
            extension = str(settings().value('Settings/record_format', 'ts'))
            if extension not in ('ts', 'mkv'):
                extension = 'ts'
            self.output = directory / f'{safe}_{datetime.now():%Y%m%d_%H%M%S_%f}.{extension}'
        except OSError as exc:
            self.changed.emit('error', str(exc))
            return
        proc = QtCore.QProcess(self)
        proc.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self._read)
        proc.errorOccurred.connect(self._error)
        proc.finished.connect(self._done)
        self.process = proc
        self._tail = ''
        self._stopping = False
        self.state = 'connecting'
        args = ['-hide_banner', '-loglevel', 'warning', '-stats_period', '1', '-progress', 'pipe:1', '-n']
        if url.lower().startswith(('http://', 'https://', 'rtsp://')):
            args += ['-rw_timeout', '15000000']
        if urlsplit(url).path.lower().endswith('.m3u8'):
            args += ['-http_persistent', '0']
        # Let FFmpeg choose the best available video/audio pair in HLS masters.
        # The first variant can be unavailable even when another variant plays.
        args += ['-i', url]
        if self.duration_seconds:
            args += ['-t', str(self.duration_seconds)]
        args += ['-c', 'copy', str(self.output)]
        self.started_at = QtCore.QElapsedTimer()
        self.started_at.start()
        self.changed.emit('connecting', str(self.output))
        proc.start(executable, args)

    def _read(self):
        if self.process is None:
            return
        chunk = bytes(self.process.readAllStandardOutput()).decode('utf-8', 'replace')
        self._tail = (self._tail + chunk)[-12000:]
        self._progress_buffer += chunk
        while '\n' in self._progress_buffer:
            line, self._progress_buffer = self._progress_buffer.split('\n', 1)
            if line.startswith('out_time_us=') and not self._remuxing:
                try:
                    self.elapsed_seconds = max(self.elapsed_seconds, int(line.split('=', 1)[1]) / 1000000)
                except ValueError:
                    pass
        self._progress_buffer = self._progress_buffer[-12000:]
        if self._remuxing:
            return
        if not self._stopping and self.output and self.output.exists() and self.output.stat().st_size > 0:
            if self.state != 'recording':
                self.state = 'recording'
                self.changed.emit('recording', str(self.output))

    def stop(self):
        if not self.active or self._stopping or self._remuxing:
            return
        self._stopping = True
        self.state = 'stopping'
        self.changed.emit('stopping', str(self.output))
        self.process.write(b'q\n')
        self._kill_timer.start(10000)

    def _force_stop(self):
        if self.process:
            self.process.kill()

    def _error(self, error):
        if error == QtCore.QProcess.FailedToStart and self.process:
            message = self.process.errorString()
            self._done(-1, QtCore.QProcess.CrashExit, message)

    def _done(self, code, status, message=''):
        if self.process is None:
            return
        self._read()
        self._kill_timer.stop()
        proc, self.process = self.process, None
        proc.deleteLater()
        valid = self.output and self.output.exists() and self.output.stat().st_size > 0
        ok = code == 0 and status == QtCore.QProcess.NormalExit and valid
        if self._remuxing:
            self._remuxing = False
            # The intermediate is kept until FFmpeg has successfully closed MP4.
            if ok:
                if not self.keep_original:
                    try:
                        self._original.unlink()
                    except OSError:
                        pass
            else:
                failed_mp4 = self.output
                self.output = self._original
                try:
                    if failed_mp4.exists():
                        failed_mp4.unlink()
                except OSError:
                    pass
                self.state = 'idle'
                self.changed.emit('error', 'MP4 conversion failed. The original recording was kept: ' + str(self.output))
                self.finished.emit()
                return
        elif ok and self.auto_remux:
            self._start_remux()
            return
        self.state = 'idle'
        if ok:
            self.changed.emit('saved', str(self.output))
        else:
            # Do not echo input URLs/credentials from FFmpeg diagnostics into the UI.
            http = re.search(r'HTTP error (\d{3})', self._tail)
            if http:
                message = 'Recording source returned HTTP ' + http.group(1) + '.'
            if self.output and self.output.exists() and not valid:
                try:
                    self.output.unlink()  # Only the empty file created by this recording.
                except OSError:
                    pass
            self.changed.emit('error', message or 'Recording failed or was interrupted. Check the source and output folder.')
        self.finished.emit()

    def _start_remux(self):
        self._original = self.output
        self.output = self._original.with_suffix('.mp4')
        if self.output.exists():
            self.output = self._original
            self.state = 'idle'
            self.changed.emit('error', 'MP4 already exists. The original recording was kept: ' + str(self.output))
            self.finished.emit()
            return
        self._remuxing = True
        self.state = 'remuxing'
        self._tail = ''
        self._progress_buffer = ''
        proc = QtCore.QProcess(self)
        self.process = proc
        proc.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self._read)
        proc.errorOccurred.connect(self._error)
        proc.finished.connect(self._done)
        self.changed.emit('remuxing', str(self.output))
        proc.start(self._executable, ['-hide_banner', '-loglevel', 'warning', '-n',
            '-i', str(self._original), '-map', '0:v:0?', '-map', '0:a:0?',
            '-c', 'copy', '-movflags', '+faststart', str(self.output)])


class RecordingIndicator(QtWidgets.QWidget):
    """REC blink and media-time progress, shared by the player and its HUD."""
    def __init__(self, recorder, tr, parent=None):
        super().__init__(parent)
        self.recorder, self.tr = recorder, tr
        self._state, self._detail = '', ''
        self._blink = False
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(2)
        self.label = QtWidgets.QLabel()
        self.label.setTextFormat(QtCore.Qt.RichText)
        self.bar = QtWidgets.QProgressBar()
        self.bar.setFixedHeight(5)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet('QProgressBar{border:0;background:#294153;} QProgressBar::chunk{background:#ed404f;}')
        layout.addWidget(self.label)
        layout.addWidget(self.bar)
        self.setMinimumWidth(160)
        recorder.changed.connect(self.changed)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    @staticmethod
    def clock(seconds):
        seconds = max(0, int(seconds))
        return f'{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}'

    def changed(self, state, detail):
        self._state, self._detail = state, detail
        self.refresh()

    def refresh(self):
        self._blink = not self._blink
        recorder = self.recorder
        state = recorder.state if recorder.active else self._state
        self.bar.setVisible(state in ('recording', 'stopping', 'remuxing'))
        if state == 'recording':
            color = '#ff4055' if self._blink else '#64252e'
            elapsed = self.clock(recorder.elapsed_seconds)
            total = ' / ' + self.clock(recorder.duration_seconds) if recorder.duration_seconds else ''
            self.label.setText(f'<span style="color:{color}">●</span> <b>REC</b> {elapsed}{total}')
            self.bar.setRange(0, max(1, recorder.duration_seconds))
            self.bar.setValue(min(int(recorder.elapsed_seconds), recorder.duration_seconds) if recorder.duration_seconds else 0)
        else:
            labels = {'connecting': 'Connecting recorder', 'stopping': 'Finalizing recording',
                      'remuxing': 'Preparing MP4', 'saved': 'Recording saved', 'error': 'Recording error'}
            self.label.setText(self.tr(labels.get(state, '')))
            if state == 'remuxing':
                self.bar.setRange(0, 0)
        self.setToolTip(self._detail if self._state != 'error' else self.tr(self._detail))


class FullscreenWindow(QtWidgets.QWidget):
    """Owned HUD stays above native VLC, without resizing video on auto-hide."""
    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self._main_window = tab.window()
        self._main_was_maximized = self._main_window.isMaximized()
        self.setWindowTitle('VisionPro IPTV — Fullscreen')
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
        self.setContentsMargins(0, 0, 0, 0)
        self.setStyleSheet('background:black;border:0;margin:0;padding:0;')
        self.video_layout = QtWidgets.QVBoxLayout(self)
        self.video_layout.setContentsMargins(0, 0, 0, 0)
        self.video_layout.setSpacing(0)
        self.video_layout.addWidget(tab.video_frame)
        self.panel = QtWidgets.QFrame(self, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
        self.panel.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.panel.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.panel.setStyleSheet('QFrame {background:#101f2c;color:#edf5fc;border:1px solid #28465b;border-radius:12px;} QPushButton {background:#20394b;color:white;padding:10px;border-radius:6px;} QPushButton:hover {background:#007fa9;} QLabel{border:0;padding:4px;}')
        row = QtWidgets.QHBoxLayout(self.panel)
        self.name = QtWidgets.QLabel(tab.now_playing.text())
        self.name.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        row.addWidget(self.name, 1)
        self.record_indicator = RecordingIndicator(tab.recorder, lambda text: tab.tr(text), self.panel)
        row.addWidget(self.record_indicator)
        for symbol, title, action in [('▶ / ❚❚', 'Play / Pause', tab.toggle_pause), ('■', 'Stop', tab.stop_playback), ('●', 'Record', tab.start_recording), ('□', 'Stop recording', tab.stop_recording)]:
            button = QtWidgets.QPushButton(symbol)
            button.setToolTip(tab.tr(title))
            button.clicked.connect(action)
            row.addWidget(button)
        self.volume = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setFixedWidth(130)
        self.volume.setValue(tab.slider_volume.value())
        self.volume.valueChanged.connect(tab.slider_volume.setValue)
        row.addWidget(self.volume)
        exit_button = QtWidgets.QPushButton(tab.tr('Exit fullscreen'))
        exit_button.clicked.connect(tab.toggle_fullscreen)
        row.addWidget(exit_button)
        self.shortcuts = []
        for widget in (self, self.panel):
            for key, action in [('Escape', tab.toggle_fullscreen), ('F11', tab.toggle_fullscreen), ('Space', tab.toggle_pause)]:
                shortcut = QtWidgets.QShortcut(QtGui.QKeySequence(key), widget)
                shortcut.activated.connect(action)
                self.shortcuts.append(shortcut)
        self._idle = QtCore.QElapsedTimer()
        self._idle.start()
        self._last_pos = QtGui.QCursor.pos()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)
        self._main_window.hide()
        self.showFullScreen()
        QtCore.QTimer.singleShot(0, self.show_hud)

    def show_hud(self):
        width = min(1100, self.width() - 48)
        point = self.mapToGlobal(QtCore.QPoint((self.width() - width) // 2, self.height() - 100))
        self.panel.setGeometry(point.x(), point.y(), width, 70)
        self.panel.show()
        self.panel.raise_()
        self._idle.restart()

    def tick(self):
        pos = QtGui.QCursor.pos()
        if pos != self._last_pos:
            self._last_pos = pos
            self.show_hud()
        elif self._idle.elapsed() >= 2000 and not self.panel.underMouse() and not self.volume.isSliderDown():
            self.panel.hide()
        self.volume.blockSignals(True)
        self.volume.setValue(self.tab.slider_volume.value())
        self.volume.blockSignals(False)
        self.name.setText(self.tab.now_playing.text())

    def closeEvent(self, event):
        event.ignore()
        self.tab.toggle_fullscreen()

    def detach(self):
        self.timer.stop()
        self.panel.hide()
        frame = self.tab.video_frame
        self.video_layout.removeWidget(frame)
        self.tab.video_container.layout().insertWidget(0, frame, 1)
        frame.show()
        self.hide()
        if self._main_was_maximized:
            self._main_window.showMaximized()
        else:
            self._main_window.showNormal()
        self._main_window.raise_()
        self._main_window.activateWindow()
        self.deleteLater()


def show_about(window):
    tr = window.tr
    dialog = QtWidgets.QDialog(window)
    dialog.setWindowTitle(tr('About VisionPro IPTV'))
    dialog.setMinimumWidth(600)
    dialog.setStyleSheet('QDialog{background:#0c1622;color:white;} QLabel{color:#d2e3ef;} QPushButton{padding:9px 18px;}')
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setContentsMargins(30, 26, 30, 24)
    hero = QtWidgets.QLabel(f'<span style="color:#58d5ff;font-size:13pt">A L E X X 6 2 6</span><br><br><span style="font-size:30pt;color:white"><b>VisionPro IPTV</b></span><br><span style="color:#a8bed0;font-size:12pt">DESKTOP PLAYER · {VERSION}</span>')
    hero.setStyleSheet('background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #183951,stop:1 #10202e);border-radius:16px;padding:28px;')
    layout.addWidget(hero)
    text = QtWidgets.QLabel(tr('Your channels. Your workspace.') + '\n\n' + tr('Created and developed by AleXx626.') + '\n\n' + tr('Live TV, personal playlists, favorites and original-quality recordings in one desktop player.') + '\n\n' + tr('The application does not provide TV subscriptions or guarantee the availability of external streams.') + '\n\n' + tr('Built with Python, Qt / PyQt5, libVLC and optional FFmpeg.'))
    text.setWordWrap(True)
    text.setStyleSheet('font-size:13px;padding:14px 0;')
    layout.addWidget(text)
    close = QtWidgets.QPushButton(tr('Close'))
    close.clicked.connect(dialog.accept)
    layout.addWidget(close, alignment=QtCore.Qt.AlignRight)
    dialog.exec_()


def preferences(window):
    tr, cfg = window.tr, settings()
    dialog = QtWidgets.QDialog(window)
    dialog.setWindowTitle(tr('Preferences'))
    dialog.resize(720, 640)
    dialog.setStyleSheet('''
        QDialog, QWidget#settingsPage {background:#101e2c;color:#e2edf5;}
        QLabel, QCheckBox {color:#d2e3ef;background:transparent;}
        QTabWidget::pane {border:1px solid #28465b;background:#101e2c;}
        QTabBar::tab {background:#172b3b;color:#b8cedd;padding:10px 18px;}
        QTabBar::tab:selected {background:#25485e;color:white;}
        QLineEdit, QSpinBox, QComboBox {background:#0c1622;color:#edf5fc;
            border:1px solid #375469;border-radius:4px;padding:7px;}
        QComboBox QAbstractItemView {background:#172b3b;color:white;selection-background-color:#007fa9;}
        QPushButton {background:#20394b;color:white;padding:9px 14px;border-radius:5px;}
        QPushButton:hover {background:#007fa9;}
    ''')
    layout = QtWidgets.QVBoxLayout(dialog)
    tabs = QtWidgets.QTabWidget()
    layout.addWidget(tabs)
    controls = {}
    def page(title):
        widget = QtWidgets.QWidget()
        widget.setObjectName('settingsPage')
        form = QtWidgets.QFormLayout(widget)
        form.setSpacing(14)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setWidget(widget)
        tabs.addTab(scroll, tr(title))
        return form
    def check(form, label, key, default=False):
        widget = QtWidgets.QCheckBox(tr(label))
        widget.setChecked(flag(key, default))
        form.addRow(widget)
        controls[key] = widget
    def combo(form, label, key, options, default):
        widget = QtWidgets.QComboBox()
        for value, text in options:
            widget.addItem(tr(text), value)
        widget.setCurrentIndex(max(0, widget.findData(cfg.value(key, default))))
        controls[key] = widget
        form.addRow(tr(label), widget)
    def path(form, label, key, default, directory=False):
        widget = QtWidgets.QLineEdit(str(cfg.value(key, default)))
        row = QtWidgets.QHBoxLayout()
        row.addWidget(widget)
        button = QtWidgets.QPushButton(tr('Browse...'))
        def browse():
            value = QtWidgets.QFileDialog.getExistingDirectory(dialog, tr(label), widget.text()) if directory else QtWidgets.QFileDialog.getOpenFileName(dialog, tr(label), widget.text(), '*.exe')[0]
            if value:
                widget.setText(value)
        button.clicked.connect(browse)
        row.addWidget(button)
        form.addRow(tr(label), row)
        controls[key] = widget
    general = page('General')
    combo(general, 'Language', 'Settings/language', [('ro', 'Română'), ('en', 'English')], 'en')
    check(general, 'Remember window size and position', 'Settings/restore_geometry', True)
    check(general, 'Restore playlist and selection', 'Settings/restore_playlist', True)
    check(general, 'Resume last channel on startup', 'Settings/autoplay', False)
    check(general, 'Start minimized to tray', 'Settings/start_minimized')
    check(general, 'Close button minimizes to tray', 'Settings/close_to_tray', True)
    playback = page('Playback')
    buffer = QtWidgets.QSpinBox()
    buffer.setRange(300, 15000)
    buffer.setSingleStep(250)
    buffer.setSuffix(' ms')
    buffer.setValue(cfg.value('Settings/network_cache', 3000, type=int))
    playback.addRow(tr('Network buffer'), buffer)
    controls['Settings/network_cache'] = buffer
    combo(playback, 'Hardware decoding', 'Settings/hardware', [('any', 'Automatic'), ('dxva2', 'DXVA2'), ('none', 'Software')], 'dxva2')
    combo(playback, 'Aspect ratio', 'Settings/aspect', [('', 'Original'), ('16:9', '16:9'), ('4:3', '4:3')], '')
    help_text = QtWidgets.QLabel(tr('Playback changes apply to the next channel. A larger buffer reduces interruptions but increases delay. Quality cannot exceed the source stream.'))
    help_text.setWordWrap(True)
    playback.addRow(help_text)
    recording = page('Recording')
    path(recording, 'Recordings folder', 'Settings/record_dir', recordings_dir(), True)
    path(recording, 'FFmpeg executable', 'Settings/ffmpeg_path', '')
    controls['Settings/ffmpeg_path'].setPlaceholderText(tr('Automatic (bundled FFmpeg or PATH)'))
    ffmpeg_status = QtWidgets.QLabel()
    ffmpeg_status.setWordWrap(True)
    ffmpeg_status.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
    def refresh_ffmpeg_status():
        typed = controls['Settings/ffmpeg_path'].text().strip()
        if typed:
            if Path(typed).is_file():
                ffmpeg_status.setText('<span style="color:#7be37f">✔</span> ' + tr('Using the selected FFmpeg:') + ' ' + typed)
            else:
                ffmpeg_status.setText('<span style="color:#ff6b6b">✘</span> ' + tr('FFmpeg executable was not found.'))
            return
        found = ffmpeg_path()
        if found:
            source = {'bundled': tr('bundled with the application'), 'path': tr('found in system PATH')}.get(ffmpeg_source(), '')
            ffmpeg_status.setText('<span style="color:#7be37f">✔</span> ' + tr('FFmpeg detected') + (' (' + source + '): ' if source else ': ') + found)
        else:
            ffmpeg_status.setText('<span style="color:#ffb454">⚠</span> ' + tr('FFmpeg was not found. Recording is unavailable until you select ffmpeg.exe or place it in the ffmpeg folder next to the application.'))
    controls['Settings/ffmpeg_path'].textChanged.connect(refresh_ffmpeg_status)
    refresh_ffmpeg_status()
    recording.addRow(ffmpeg_status)
    combo(recording, 'Recording container', 'Settings/record_format', [('ts', 'MPEG-TS (.ts)'), ('mkv', 'Matroska (.mkv)')], 'ts')
    check(recording, 'Automatically finalize as MP4', 'Settings/auto_remux', True)
    check(recording, 'Keep the original TS / MKV after MP4 succeeds', 'Settings/keep_recording_original', False)
    combo(recording, 'Recording duration', 'Settings/record_duration',
          [('unlimited', 'Unlimited'), ('5', '5 minutes'), ('10', '10 minutes'), ('custom', 'Custom')], 'unlimited')
    custom_row = QtWidgets.QWidget()
    custom_layout = QtWidgets.QHBoxLayout(custom_row)
    custom_layout.setContentsMargins(0, 0, 0, 0)
    duration_boxes = []
    for part, maximum, default, unit in [('hours', 167, 0, 'h'), ('minutes', 59, 5, 'min'), ('seconds', 59, 0, 's')]:
        spin = QtWidgets.QSpinBox()
        spin.setRange(0, maximum)
        spin.setSuffix(' ' + unit)
        key = 'Settings/record_' + part
        spin.setValue(cfg.value(key, default, type=int))
        controls[key] = spin
        duration_boxes.append(spin)
        custom_layout.addWidget(spin)
    recording.addRow(tr('Custom duration'), custom_row)
    slider_row = QtWidgets.QWidget()
    slider_layout = QtWidgets.QHBoxLayout(slider_row)
    slider_layout.setContentsMargins(0, 0, 0, 0)
    duration_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    duration_slider.setRange(1, 180)
    duration_slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
    duration_slider.setTickInterval(15)
    duration_slider.setPageStep(5)
    duration_slider.setMinimumWidth(260)
    duration_slider.setStyleSheet('QSlider::groove:horizontal{height:6px;background:#294153;border-radius:3px;}'
        'QSlider::sub-page:horizontal{background:#007fa9;border-radius:3px;}'
        'QSlider::handle:horizontal{background:#58d5ff;width:16px;margin:-6px 0;border-radius:8px;}'
        'QSlider::handle:horizontal:disabled{background:#4a5c6a;}')
    duration_slider.setToolTip(tr('Quick duration: 1–180 minutes; use the fields for hours and seconds.'))
    slider_value = QtWidgets.QLabel()
    slider_value.setMinimumWidth(70)
    slider_layout.addWidget(duration_slider, 1)
    slider_layout.addWidget(slider_value)
    recording.addRow(tr('Quick duration'), slider_row)
    syncing = {'busy': False}
    def minutes_from_boxes():
        return duration_boxes[0].value() * 60 + duration_boxes[1].value()
    def show_slider_value(value):
        slider_value.setText(f'{value // 60} h {value % 60:02d} min' if value >= 60 else f'{value} min')
    def slide_duration(value):
        # Dragging the slider is an explicit choice: switch to Custom and fill the fields.
        if syncing['busy']:
            return
        syncing['busy'] = True
        try:
            combo_widget = controls['Settings/record_duration']
            if combo_widget.currentData() != 'custom':
                combo_widget.setCurrentIndex(combo_widget.findData('custom'))
            duration_boxes[0].setValue(value // 60)
            duration_boxes[1].setValue(value % 60)
            duration_boxes[2].setValue(0)
            show_slider_value(value)
        finally:
            syncing['busy'] = False
    def boxes_changed(_value=None):
        # Hours/minutes typed by hand move the slider too (seconds alone do not).
        if syncing['busy']:
            return
        syncing['busy'] = True
        try:
            minutes = max(1, min(180, minutes_from_boxes()))
            duration_slider.setValue(minutes)
            show_slider_value(minutes)
        finally:
            syncing['busy'] = False
    duration_slider.valueChanged.connect(slide_duration)
    duration_boxes[0].valueChanged.connect(boxes_changed)
    duration_boxes[1].valueChanged.connect(boxes_changed)
    boxes_changed()
    def update_duration_controls():
        custom = controls['Settings/record_duration'].currentData() == 'custom'
        custom_row.setEnabled(custom)
        slider_value.setEnabled(custom)
    controls['Settings/record_duration'].currentIndexChanged.connect(update_duration_controls)
    update_duration_controls()
    remux_info = QtWidgets.QLabel(tr('MP4 is prepared after Stop or the time limit, without re-encoding. The original is kept if conversion fails. Duration changes apply to the next recording.'))
    remux_info.setWordWrap(True)
    recording.addRow(remux_info)
    info = QtWidgets.QLabel(tr('Original quality: video and audio are copied without re-encoding. Recording uses a separate connection and continues when you change channels. Some providers allow only one connection.'))
    info.setWordWrap(True)
    recording.addRow(info)
    open_folder = QtWidgets.QPushButton(tr('Open recordings folder'))
    open_folder.clicked.connect(lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(recordings_dir()))))
    recording.addRow(open_folder)
    buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
    buttons.button(QtWidgets.QDialogButtonBox.Save).setText(tr('Save'))
    buttons.button(QtWidgets.QDialogButtonBox.Cancel).setText(tr('Cancel'))
    layout.addWidget(buttons)
    def save():
        if controls['Settings/record_duration'].currentData() == 'custom' and not any(box.value() for box in duration_boxes):
            QtWidgets.QMessageBox.warning(dialog, tr('Error'), tr('Choose a duration of at least one second.'))
            return
        executable = controls['Settings/ffmpeg_path'].text().strip()
        if executable and not Path(executable).is_file():
            QtWidgets.QMessageBox.warning(dialog, tr('Error'), tr('FFmpeg executable was not found.'))
            return
        try:
            destination = Path(controls['Settings/record_dir'].text().strip())
            if not destination.is_absolute():
                raise ValueError(tr('Choose an absolute recordings folder.'))
            destination.mkdir(parents=True, exist_ok=True)
        except (ValueError, OSError) as exc:
            QtWidgets.QMessageBox.warning(dialog, tr('Error'), str(exc))
            return
        for key, widget in controls.items():
            if isinstance(widget, QtWidgets.QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QtWidgets.QComboBox):
                value = widget.currentData()
            elif isinstance(widget, QtWidgets.QSpinBox):
                value = widget.value()
            else:
                value = widget.text().strip()
            cfg.setValue(key, value)
        cfg.sync()
        window.apply_language(cfg.value('Settings/language', 'en'))
        window.iptv_tab.record_dir = str(destination)
        dialog.accept()
    buttons.accepted.connect(save)
    buttons.rejected.connect(dialog.reject)
    dialog.exec_()
