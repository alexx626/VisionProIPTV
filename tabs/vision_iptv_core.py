# -*- coding: utf-8 -*-
import os
from pathlib import Path
from configparser import ConfigParser
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtWidgets import QTreeWidget, QTreeWidgetItem, QMenu
import vlc
from player_services import Recorder, RecordingIndicator, FullscreenWindow, settings, flag, DATA_DIR, recordings_dir
 
# ------------------------------------------------------------
#  CONFIG GLOBAL – permanent în AppData (nu în dist/)
# ------------------------------------------------------------
CONFIG_PATH = Path(os.getenv("APPDATA")) / "VisionProIPTV" / "config.ini"
CONFIG_PATH.parent.mkdir(exist_ok=True)
 
 
import channel_sources

NUMBER_ROLE = QtCore.Qt.UserRole + 1
SUBTITLE_ROLE = QtCore.Qt.UserRole + 2
GROUP_KEY_ROLE = QtCore.Qt.UserRole + 3
MAX_RECENTS = 30


class ChannelDelegate(QtWidgets.QStyledItemDelegate):
    """Draws the channel number in a dim column on the left, like the TV list."""
    NUMBER_WIDTH = 54

    def paint(self, painter, option, index):
        number = index.data(NUMBER_ROLE)
        if not number:
            return super().paint(painter, option, index)
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = opt.widget
        style = widget.style() if widget else QtWidgets.QApplication.style()
        background = QtWidgets.QStyleOptionViewItem(opt)
        background.text = ''
        style.drawControl(QtWidgets.QStyle.CE_ItemViewItem, background, painter, widget)
        text = QtWidgets.QStyleOptionViewItem(opt)
        text.rect = opt.rect.adjusted(self.NUMBER_WIDTH, 0, 0, 0)
        style.drawControl(QtWidgets.QStyle.CE_ItemViewItem, text, painter, widget)
        painter.save()
        selected = bool(opt.state & QtWidgets.QStyle.State_Selected)
        painter.setPen(QtGui.QColor('#0A2233' if selected else '#5E8BAA'))
        painter.drawText(QtCore.QRect(opt.rect.left() + 6, opt.rect.top(), self.NUMBER_WIDTH - 12, opt.rect.height()),
                         QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, str(number))
        painter.restore()


class VisionIPTVTab(QtWidgets.QWidget):
    """Fereastra principală VisionPro IPTV – player + playlist + tray."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent = parent
        self.current_url = None
        # Channel model (url -> dict): numbers, categories and countries like VisionPro IPTV Pro on the TV.
        self.channels = {}
        self._next_number = 1
        self.view_mode = 'category'      # 'category' | 'country' | 'group'
        self.current_view = 'all'        # 'all' | 'fav' | 'recent' | 'group:<name>'
        self._online_worker = None
        self._rebuilding = False
 
        # ===============================
        #     INSTANȚĂ VLC + VARIABILE
        # ===============================
        try:
            # --------------------------------------------------------
            #  Inițializare VLC – stabilitate + compatibilitate Intel HD
            # --------------------------------------------------------
            #  --no-xlib             → compatibil cu PyQt5 pe Windows
            #  --no-video-title-show → ascunde titlurile video în overlay
            #  --network-caching     → reduce buffer pentru streamuri mari
            #  --file-caching        → reduce lag la fișiere locale
            #  --live-caching        → stabilitate pentru fluxuri IPTV HLS
            #  --no-hw-decoding      → dezactivează decodarea hardware (evită crash D3D11VA)
            #  (dacă vrei GPU decoding stabil: folosește "--avcodec-hw=dxva2")
            self._vlc_instance = vlc.Instance(
                "--no-xlib",
                "--no-video-title-show",
                "--network-caching=3000",
                "--file-caching=2000",
                "--live-caching=3000",
                "--avcodec-hw=dxva2",       # hardware decoding DXVA2 (Windows) – calitate maximă
                "--avcodec-fast",            # decodare rapidă fără pierdere de calitate vizibilă
                "--no-sub-autodetect-file",
                "--deinterlace=-1",          # auto-deinterlace (canale TV live)
                "--deinterlace-mode=blend"   # modul cel mai stabil pentru IPTV
            )
            print("[✅] VLC core initialized with DXVA2 hardware decoding + high quality.")
        except Exception as e:
            print(f"[⚠️] VLC init warning: {e}")
            self._vlc_instance = None
 
        # ------------------------------------------------------------
        #  Fallback – în cazul în care instanța principală eșuează
        # ------------------------------------------------------------
        if not self._vlc_instance:
            try:
                self._vlc_instance = vlc.Instance()
                print("[ℹ️] VLC fallback instance created successfully.")
            except Exception as e:
                raise RuntimeError(f"❌ VLC core initialization failed: {e}")
 
        # ------------------------------------------------------------
        #  Creăm playerul media și variabilele implicite
        # ------------------------------------------------------------
        self.player = self._vlc_instance.media_player_new()
 
        self._last_playlist_path = ""
        self.recording = False
        self.record_proc_media = None
 
        # ------------------------------------------------------------
        #  CONFIG permanent (din AppData)
        # ------------------------------------------------------------
        cfg = QtCore.QSettings(str(CONFIG_PATH), QtCore.QSettings.IniFormat)
        default_record_dir = str(recordings_dir())
        self.record_dir = cfg.value("Settings/record_dir", default_record_dir)
 
        # ===============================
        #     STRUCTURĂ PRINCIPALĂ
        # ===============================
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
 
        # 🔹 Fix layout alignment: centrează video_container vertical și elimină spațiile fantomă
        if hasattr(self, "video_container"):
            main_layout.setStretchFactor(left_side, 0)
            main_layout.setStretchFactor(right_side, 1)
 
            # forțează video_container să se extindă complet
            self.video_container.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding,
                QtWidgets.QSizePolicy.Expanding
            )
 
            # setează alinierea conținutului video în centru vertical
            main_layout.setAlignment(self.video_container, QtCore.Qt.AlignVCenter)
            print("[🧩] Video container alignment fixed (centered + expanded).")
 
        # -------------------------------
        #      PLAYLIST STÂNGA
        # -------------------------------
        # === Bara deasupra playlistului (Favorites + Search) ===
        top_playlist_frame = QtWidgets.QFrame()
        top_playlist_frame.setStyleSheet("""
            QFrame {
                background-color: #0E1620;
                border-bottom: 1px solid #0E2638;
            }
            QPushButton {
                background-color: #1B3144;
                color: #E0E0E0;
                border-radius: 5px;
                padding: 4px 10px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #00A8FF;
                color: #000;
            }
            QLineEdit {
                background-color: #162430;
                color: #E0E0E0;
                border: 1px solid #0E2638;
                border-radius: 4px;
                padding: 3px 6px;
                font-size: 12px;
            }
        """)
        top_layout = QtWidgets.QHBoxLayout(top_playlist_frame)
        top_layout.setContentsMargins(6, 4, 6, 4)
        top_layout.setSpacing(6)
 
        # === Zona de control pentru playlist (Favorites + Add + Search) ===
        self.btn_fav = QtWidgets.QPushButton("⭐ Favorites")
        self.btn_fav.setCheckable(True)
        self.btn_fav.setChecked(False)
        self.btn_fav.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.btn_fav.setToolTip("Toggle favorites view")
        self.btn_fav.clicked.connect(self.toggle_favorites_view)
 
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("Search channel...")
        self.search_box.setClearButtonEnabled(True)
        self._search_timer = QtCore.QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(
            lambda: self.filter_playlist(self.search_box.text()))
        self.search_box.textChanged.connect(lambda: self._search_timer.start())
 
        top_layout.addWidget(self.btn_fav)
        top_layout.addWidget(self.search_box)
 
        # === Arbore QTreeWidget pentru categorii + canale ===
        from PyQt5.QtWidgets import QTreeWidget, QTreeWidgetItem, QMenu
 
        self.playlist_tree = QTreeWidget()
        self.playlist_tree.setHeaderHidden(True)
        self.playlist_tree.setColumnCount(1)
        self.playlist_tree.setIndentation(14)
        self.playlist_tree.setAnimated(False)
        self.playlist_tree.setUniformRowHeights(True)
        self.playlist_tree.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        # Keep controls in Qt's backing store; only the VLC video host is native.
        self.playlist_tree.setMinimumWidth(240)
        self.playlist_tree.setAlternatingRowColors(True)
        self.playlist_tree.setTextElideMode(QtCore.Qt.ElideRight)
        self.playlist_tree.setStyleSheet("""
            QTreeWidget {
                background-color: #0E1620;
                color: #E0E0E0;
                border-right: 1px solid #0E2638;
                font-size: 13px;
                outline: 0;
                alternate-background-color: #111D29;
            }
            QTreeWidget::item { padding: 5px 4px; }
            QTreeWidget::item:hover {
                background-color: #122636;
                color: #00A8FF;
            }
            QTreeWidget::item:selected {
                background-color: #00A8FF;
                color: #000;
            }
        """)
 
        self.playlist_tree.itemDoubleClicked.connect(self._play_tree_item)
        self.playlist_tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.playlist_tree.customContextMenuRequested.connect(self._show_tree_menu)
 
        self.playlist_tree.setItemDelegate(ChannelDelegate(self.playlist_tree))
        self.playlist_tree.setIndentation(0)
        self.playlist_tree.setRootIsDecorated(False)

        # helper pentru categorii (înregistrează și în modelul de canale)
        self.tree_helper = VisionTreeHelper(self.playlist_tree, self)

        # === Sidebar categorii (ca pe TV): Căutare / Favorite / Recente / Toate + categorii cu număr ===
        self.sidebar_frame = QtWidgets.QFrame()
        self.sidebar_frame.setFixedWidth(210)
        self.sidebar_frame.setStyleSheet("""
            QFrame { background-color: #0B1521; border-right: 1px solid #0E2638; }
            QLabel#sideTitle { color: #7FB4D6; font-size: 13px; font-weight: bold; padding: 8px 10px 4px 10px; }
            QPushButton { background: #13283A; color: #B8CEDD; border-radius: 4px; padding: 4px 6px; font-size: 11px; }
            QPushButton:checked { background: #00A8FF; color: #000; }
            QListWidget { background: transparent; border: 0; outline: 0; font-size: 13px; color: #D6E6F2; }
            QListWidget::item { padding: 6px 8px; }
            QListWidget::item:selected { background: #00A8FF; color: #000; border-radius: 4px; }
            QListWidget::item:hover { background: #122636; color: #00A8FF; }
            QListWidget::item:disabled { color: #4E6C84; font-size: 10px; }
        """)
        sidebar_layout = QtWidgets.QVBoxLayout(self.sidebar_frame)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(2)
        self.sidebar_title = QtWidgets.QLabel(self.tr("Categories"))
        self.sidebar_title.setObjectName("sideTitle")
        sidebar_layout.addWidget(self.sidebar_title)
        mode_row = QtWidgets.QHBoxLayout()
        mode_row.setContentsMargins(8, 0, 8, 4)
        mode_row.setSpacing(4)
        self.mode_buttons = {}
        for mode, label in (('category', 'Categories'), ('country', 'Countries'), ('group', 'Groups')):
            button = QtWidgets.QPushButton(self.tr(label))
            button.setCheckable(True)
            button.setChecked(mode == self.view_mode)
            button.clicked.connect(lambda checked, m=mode: self.set_view_mode(m))
            self.mode_buttons[mode] = button
            mode_row.addWidget(button)
        sidebar_layout.addLayout(mode_row)
        self.category_list = QtWidgets.QListWidget()
        self.category_list.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.category_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.category_list.setTextElideMode(QtCore.Qt.ElideRight)
        self.category_list.setWordWrap(False)
        self.category_list.currentItemChanged.connect(lambda current, previous: self._sidebar_selected(current))
        self.category_list.itemClicked.connect(self._sidebar_selected)
        sidebar_layout.addWidget(self.category_list, 1)
        self.channel_badge = QtWidgets.QLabel()
        self.channel_badge.setStyleSheet("color: #7be37f; font-size: 11px; font-weight: bold; padding: 0 6px;")
 
        # === Layout vertical playlist + status ===
        playlist_layout = QtWidgets.QVBoxLayout()
        playlist_layout.setContentsMargins(0, 0, 0, 0)
        playlist_layout.setSpacing(2)
        top_layout.addWidget(self.channel_badge)
        playlist_layout.addWidget(top_playlist_frame)
        lists_row = QtWidgets.QHBoxLayout()
        lists_row.setContentsMargins(0, 0, 0, 0)
        lists_row.setSpacing(0)
        lists_row.addWidget(self.sidebar_frame)
        lists_row.addWidget(self.playlist_tree, 1)
        playlist_layout.addLayout(lists_row, 1)
 
        # === Status label sub playlist ===
        self.playlist_status = QtWidgets.QLabel("No playlist loaded")
        self.playlist_status.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.playlist_status.setStyleSheet("""
            QLabel {
                color: rgba(0, 200, 255, 200);
                font-size: 11px;
                font-weight: 600;
                background-color: rgba(0, 0, 0, 40);
                border-top: 1px solid #0E2638;
                padding: 3px 6px;
            }
        """)
        playlist_layout.addWidget(self.playlist_status)
 
        # === Cadru playlist complet ===
        playlist_frame = QtWidgets.QFrame()
        self.playlist_frame = playlist_frame
        playlist_frame.setLayout(playlist_layout)
        playlist_frame.setMinimumWidth(470)
        self.workspace_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.setHandleWidth(6)
        self.workspace_splitter.setStyleSheet(
            "QSplitter::handle { background: #152B3D; }"
            "QSplitter::handle:hover { background: #00A8FF; }")
        self.workspace_splitter.addWidget(playlist_frame)
        main_layout.addWidget(self.workspace_splitter)
 
        # -------------------------------
        #      VIDEO + CONTROALE
        # -------------------------------
        right_side = QtWidgets.QVBoxLayout()
        right_side.setContentsMargins(0, 0, 0, 0)
        right_side.setSpacing(0)
        self.now_playing = QtWidgets.QLabel("Select a channel to start watching")
        self.now_playing.setMinimumWidth(0)
        self.now_playing.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.now_playing.setFixedHeight(48)
        self.now_playing.setTextFormat(QtCore.Qt.RichText)
        self.now_playing.setStyleSheet(
            "background: #101F2C; color: #A7CCE5; padding: 0 14px; font-size: 13px;")
        right_side.addWidget(self.now_playing)
 
        # ======================================
        #      VIDEO CONTAINER + CONTROL BAR
        # ======================================
        self.video_container = QtWidgets.QFrame()
        video_layout = QtWidgets.QVBoxLayout(self.video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(0)
 
        # === Cadru video ===
        self.video_frame = QtWidgets.QFrame()
        self.video_frame.setAttribute(QtCore.Qt.WA_DontCreateNativeAncestors, True)
        self.video_frame.setAttribute(QtCore.Qt.WA_NativeWindow, True)
        self.video_frame.setStyleSheet("background-color: black;")
 
        # folosim stretch 1, nu 5 → previne separarea barei
        video_layout.addWidget(self.video_frame, stretch=1)
 
        # ======================================
        #        CONTROL BAR VIDEO (LOCAL)
        # ======================================
        self.control_frame = QtWidgets.QFrame()
        self.control_frame.setObjectName("controlFrame")
        self.control_frame.setStyleSheet("""
            QFrame#controlFrame {
                background-color: #0A1A2A;
                border-top: 1px solid #0E2A3A;
            }
            QPushButton {
                background: #13283C;
                color: white;
                font-size: 14px;
                border-radius: 6px;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background: #1C3F5F;
            }
            QPushButton:pressed {
                background: #244F70;
            }
        """)
 
        control_layout = QtWidgets.QHBoxLayout(self.control_frame)
        control_layout.setContentsMargins(10, 6, 10, 6)
        control_layout.setSpacing(10)
 
        # --- Butoane control ---
        self.btn_play = QtWidgets.QPushButton("▶")
        self.btn_pause = QtWidgets.QPushButton("⏸")
        self.btn_stop = QtWidgets.QPushButton("⏹")
        self.btn_mute = QtWidgets.QPushButton("🔇")
        self.btn_full = QtWidgets.QPushButton("⛶")
        self.btn_rec = QtWidgets.QPushButton("⏺")
        self.btn_rec.setToolTip("Pornire / oprire înregistrare")
        self.btn_rec.setCheckable(True)
        self.btn_rec.setVisible(False)
 
        # --- Slider volum ---
        self.slider_volume = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(settings().value('Settings/volume', 70, type=int))
        self.slider_volume.setFixedWidth(220)
 
        # --- Conectări ---
        self.btn_play.clicked.connect(self.play_current)
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_stop.clicked.connect(self.stop_playback)
        self.btn_mute.clicked.connect(self.toggle_mute)
        self.btn_full.clicked.connect(self.toggle_fullscreen)
        self.slider_volume.valueChanged.connect(self.set_volume)
 
        # --- Aranjare ---
        for b in [self.btn_play, self.btn_pause, self.btn_stop, self.btn_mute, self.btn_full, self.btn_rec]:
            control_layout.addWidget(b)
        control_layout.addSpacing(12)
        control_layout.addWidget(self.slider_volume)
        control_layout.addStretch()
 
        # 🔹 Bara control lipită sub video
        video_layout.addWidget(self.control_frame)
        video_layout.setStretchFactor(self.video_frame, 10)
        video_layout.setStretchFactor(self.control_frame, 0)
 
        # 🔹 Adăugăm containerul complet (video + control) în partea dreaptă
        right_side.addWidget(self.video_container, stretch=5)
 
        # === Label informativ jos ===
        self.info_label = QtWidgets.QLabel("")
        self.info_label.setStyleSheet("""
            color: #00A8FF;
            font-size: 12px;
            padding-left: 10px;
        """)
        self.info_label.setFixedHeight(26)
        right_side.addWidget(self.info_label)
 
        self.player_panel = QtWidgets.QWidget()
        self.player_panel.setLayout(right_side)
        self.workspace_splitter.addWidget(self.player_panel)
        self.workspace_splitter.setStretchFactor(0, 0)
        self.workspace_splitter.setStretchFactor(1, 1)
        self.workspace_splitter.setSizes([360, 1100])
        saved_splitter = cfg.value("Window/playlist_splitter")
        if isinstance(saved_splitter, QtCore.QByteArray):
            self.workspace_splitter.restoreState(saved_splitter)
        self.workspace_splitter.splitterMoved.connect(self._save_splitter)
        self._info_timer = QtCore.QTimer(self)
        self._info_timer.setSingleShot(True)
        self._info_timer.timeout.connect(self.info_label.clear)
 
        # ======================================
        #   Conexiuni pentru Search și Filter
        # ======================================
        # Search is connected once, through the debounce timer above.
 
        # -------------------------------
        #        RESTAURARE PLAYLIST
        # -------------------------------
        self.load_last_playlist()
        self.load_favorites()
 
        # -------------------------------
        #        CONFIG
        # -------------------------------
        self.load_config()
        self.record_dir = str(recordings_dir())
        self.recorder = Recorder(self)
        self.recorder.changed.connect(self._recording_changed)
        self.record_status = RecordingIndicator(self.recorder, lambda text: self.tr(text))
        control_layout.addWidget(self.record_status)
        self.player.audio_set_volume(self.slider_volume.value())
        self.player.audio_set_mute(flag('Settings/muted'))
        self._session_timer = QtCore.QTimer(self)
        self._session_timer.timeout.connect(self.save_session)
        self._session_timer.start(30000)
        self._session_debounce = QtCore.QTimer(self)
        self._session_debounce.setSingleShot(True)
        self._session_debounce.setInterval(800)
        self._session_debounce.timeout.connect(self.save_session)
        model = self.playlist_tree.model()
        for signal in (model.rowsInserted, model.rowsRemoved, model.modelReset, model.dataChanged):
            signal.connect(lambda *args: self._session_debounce.start())
        self._fs_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence('F11'), self)
        self._fs_shortcut.activated.connect(self.toggle_fullscreen)


    def _save_splitter(self, *args):
        cfg = QtCore.QSettings(str(CONFIG_PATH), QtCore.QSettings.IniFormat)
        cfg.setValue("Window/playlist_splitter", self.workspace_splitter.saveState())

    def restore_native_panels(self):
        """Refresh Qt sibling surfaces after Windows restores the native video host."""
        if not self.isVisible() or self.window().isMinimized():
            return
        self.layout().activate()
        self.playlist_frame.layout().activate()
        self.playlist_frame.raise_()
        self.playlist_tree.raise_()
        self.playlist_tree.viewport().update()
        self.playlist_tree.verticalScrollBar().update()
        self.update()
 
    # --------------------------------------------------------
    #  CONFIG – Salvare și încărcare în AppData\VisionProIPTV
    # --------------------------------------------------------
    from pathlib import Path
    from configparser import ConfigParser
    import os
 
    def load_config(self):
        self.config = settings()
        self.CONFIG_FILE = CONFIG_PATH
        self.CONFIG_PATH = DATA_DIR

    def save_config(self):
        self.config.sync()

    def play_current(self):
        item = self.playlist_tree.currentItem()
        if item is not None and item.data(0, QtCore.Qt.UserRole):
            self._play_tree_item(item, 0)
            return
        if not self.current_url:
            iterator = QtWidgets.QTreeWidgetItemIterator(self.playlist_tree)
            while iterator.value():
                item = iterator.value()
                if item.data(0, QtCore.Qt.UserRole):
                    self._play_tree_item(item, 0)
                    return
                iterator += 1
        if self.current_url:
            media = self._media_with_headers(self.current_url)
            self.player.set_hwnd(self.video_frame.winId())
            self.player.set_media(media)
            self.player.play()
            QtCore.QTimer.singleShot(300, lambda: self.player.audio_set_volume(self.slider_volume.value()))
 
    def play_selected_item(self, item):
        self.current_url = item.data(QtCore.Qt.UserRole)
        media = self._media_with_headers(self.current_url)
        self.player.set_hwnd(self.video_frame.winId())
        self.player.set_media(media)
        self.player.play()
 
    def toggle_pause(self):
        """Oprire/Reluare redare fără crash (safe pause)"""
        try:
            state = self.player.get_state()
            if state in (vlc.State.Playing, vlc.State.Buffering):
                self.player.set_pause(True)
            elif state in (vlc.State.Paused, vlc.State.Stopped, vlc.State.Ended):
                self.player.play()
        except Exception as e:
            print(f"[⚠️] Pause toggle error: {e}")
 
    def _media_with_headers(self, url: str):
        """Creează obiectul media VLC cu opțiuni de calitate maximă (DXVA2 + caching)."""
        try:
            media = self._vlc_instance.media_new(
                url,
                f":network-caching={settings().value('Settings/network_cache', 3000, type=int)}",
                ":live-caching=3000",
                ":file-caching=2000",
                f":avcodec-hw={settings().value('Settings/hardware', 'dxva2')}",
                ":avcodec-fast",
            )
            return media
        except Exception as e:
            print(f"[⚠️] media_new error: {e}")
            return self._vlc_instance.media_new(url)
 
    def toggle_mute(self):
        self.player.audio_toggle_mute()
        settings().setValue('Settings/muted', bool(self.player.audio_get_mute()))
 
    def set_volume(self, val):
        self.player.audio_set_volume(val)
        settings().setValue('Settings/volume', val)
 
    # ===================================
    #     FULLSCREEN – reparenting pur (identic Vision Player)
    # ===================================
    def toggle_fullscreen(self):
        if getattr(self, '_fs_mode', False):
            self._fs_mode = False
            window, self._fs_win = self._fs_win, None
            window.detach()
            self.player.set_hwnd(int(self.video_frame.winId()))
            self.restore_native_panels()
        else:
            self._fs_mode = True
            self._fs_win = FullscreenWindow(self)
            self.player.set_hwnd(int(self.video_frame.winId()))

    def _save_current_selection(self, row):
        """Salvează poziția și calea playlistului în config.ini"""
        if row < 0:
            return  # prevenim salvarea unei selecții invalide
 
        cfg = QtCore.QSettings(str(CONFIG_PATH), QtCore.QSettings.IniFormat)
        cfg.setValue("LastPlaylist/path", self._last_playlist_path)
        cfg.setValue("LastPlaylist/index", row)
        cfg.sync()
 
    def _load_playlist_file(self, path):
        """Încarcă un M3U în modelul de canale (categorii TV + țări) și reconstruiește lista."""
        if not os.path.exists(path):
            QtWidgets.QMessageBox.warning(self, self.tr("Error"), self.tr(f"Playlist not found:\n{path}"))
            return
        self.playlist_status.setText(self.tr("Loading playlist (smart hybrid)..."))
        self._last_playlist_path = path
        QtCore.QCoreApplication.processEvents()
        try:
            rows = channel_sources.load_file(path)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, self.tr("Error"), self.tr(f"Could not load playlist:\n{e}"))
            return
        self._clear_channels(keep_online=True)
        for row in rows:
            self.register_channel(row, source='user')
        self._rebuild_tree()
        total = sum(1 for c in self.channels.values() if c['source'] != 'online')
        base = os.path.basename(path)
        self.show_info(f"✅ Loaded playlist: {base} ({total} channels, Smart Hybrid + AutoCountry)")
        self.playlist_status.setText(self.tr(f"Loaded {total} channels (auto categories + countries)"))

    # ===================================
    #     CHANNEL MODEL (ca pe TV)
    # ===================================
    def register_channel(self, row, source='user'):
        """Adaugă un canal în model (număr fix per sesiune). Returnează intrarea sau None dacă există."""
        url = (row.get('url') or '').strip()
        if not url or url in self.channels:
            return None
        name = (row.get('name') or os.path.basename(url)).strip() or 'Channel'
        group = (row.get('group') or 'General').strip() or 'General'
        entry = {'n': self._next_number, 'name': name, 'url': url, 'group': group,
                 'category': row.get('category') or channel_sources.categorize({'group': group, 'name': name, 'cats': row.get('cats', [])}),
                 'country': row.get('country') or channel_sources.guess_country({'name': name, 'country': ''}),
                 'logo': row.get('logo', ''), 'source': source}
        self._next_number += 1
        self.channels[url] = entry
        return entry

    def _clear_channels(self, keep_online=False):
        if keep_online:
            self.channels = {u: c for u, c in self.channels.items() if c['source'] == 'online'}
        else:
            self.channels = {}
        if not self.channels:
            self._next_number = 1
        self.playlist_tree.clear()
        self.tree_helper.categories.clear()

    def _group_key(self, entry):
        if self.view_mode == 'country':
            return entry['country'] or 'International'
        if self.view_mode == 'group':
            return entry['group'] or 'General'
        return entry['category']

    def _group_order(self, names):
        if self.view_mode == 'category':
            order = {label: i for i, label in enumerate(channel_sources.CATEGORY_LABELS)}
            return sorted(names, key=lambda n: (order.get(n, 999), n.lower()))
        if self.view_mode == 'country':
            pinned = ['Romania', 'Germany', 'Moldova', 'Italy', 'Spain', 'United Kingdom', 'United States', 'France']
            return sorted(names, key=lambda n: (n == 'International', pinned.index(n) if n in pinned else 99, n.lower()))
        return list(names)

    def _display_group(self, name):
        return self.tr(name) if self.view_mode == 'category' else name

    def _rebuild_tree(self):
        """Reconstruiește arborele din model după modul curent (categorii / țări / grupuri)."""
        self._rebuilding = True
        try:
            selected = self.current_url
            self.playlist_tree.setRootIndex(QtCore.QModelIndex())
            self.playlist_tree.clear()
            self.tree_helper.categories.clear()
            groups = {}
            for entry in self.channels.values():
                groups.setdefault(self._group_key(entry), []).append(entry)
            for name in self._group_order(list(groups)):
                group_item = QtWidgets.QTreeWidgetItem([self._display_group(name)])
                group_item.setData(0, GROUP_KEY_ROLE, name)
                self.playlist_tree.addTopLevelItem(group_item)
                self.tree_helper.categories[name] = group_item
                self.tree_helper.categories[self._display_group(name)] = group_item
                for entry in groups[name]:
                    group_item.addChild(self._make_item(entry))
            self.load_favorites()
            self._refresh_sidebar()
            self._apply_view()
            if selected:
                for item in self._iter_channel_items():
                    if item.data(0, QtCore.Qt.UserRole) == selected:
                        self.playlist_tree.setCurrentItem(item)
                        break
        finally:
            self._rebuilding = False

    def _make_item(self, entry):
        item = QtWidgets.QTreeWidgetItem([entry['name']])
        item.setData(0, QtCore.Qt.UserRole, entry['url'])
        item.setData(0, NUMBER_ROLE, entry['n'])
        item.setData(0, SUBTITLE_ROLE, self._subtitle(entry))
        item.setToolTip(0, f"{entry['n']}  {entry['name']} • {self._subtitle(entry)}")
        return item

    def _update_now_playing(self, url, channel_name):
        """Sub video: număr + nume pe prima linie, categorie • țară pe a doua (ca pe TV)."""
        entry = self.channels.get(url)
        number = f"{entry['n']}  " if entry else ''
        subtitle = self._subtitle(entry) if entry else ''
        self.now_playing.setText(f'<span style="font-size:14px;color:#EAF4FB">▶  <b>{number}{channel_name}</b></span>'
                                 + (f'<br><span style="font-size:11px;color:#7FB4D6">{subtitle}</span>' if subtitle else ''))
        self.now_playing.setToolTip(channel_name)

    def _subtitle(self, entry):
        parts = [self.tr(entry['category'])]
        if entry['country']:
            parts.append(entry['country'])
        if entry['source'] == 'online':
            parts.append(self.tr('world'))
        return ' • '.join(parts)

    def _iter_channel_items(self):
        for i in range(self.playlist_tree.topLevelItemCount()):
            group = self.playlist_tree.topLevelItem(i)
            for j in range(group.childCount()):
                yield group.child(j)

    def set_view_mode(self, mode):
        self.view_mode = mode
        for key, button in self.mode_buttons.items():
            button.setChecked(key == mode)
        self.current_view = 'all'
        self._rebuild_tree()

    # ---------- sidebar ----------
    def _favorite_urls(self):
        favorites = settings().value("Favorites/list", "")
        return {f.split("::", 1)[1] for f in (favorites.split("|") if favorites else []) if "::" in f}

    def _recent_urls(self):
        raw = settings().value('Recents/list', '')
        return [u for u in str(raw).split('|') if u] if raw else []

    def _remember_recent(self, url):
        recents = [u for u in self._recent_urls() if u != url]
        recents.insert(0, url)
        cfg = settings()
        cfg.setValue('Recents/list', '|'.join(recents[:MAX_RECENTS]))
        cfg.sync()
        self._refresh_sidebar_counts()

    def _refresh_sidebar(self):
        lst = self.category_list
        lst.blockSignals(True)
        lst.clear()
        def add(key, text, count=None, selectable=True):
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.UserRole, key)
            item.setData(QtCore.Qt.UserRole + 1, count)
            if not selectable:
                item.setFlags(QtCore.Qt.NoItemFlags)
            lst.addItem(item)
            return item
        add('search', '🔍 ' + self.tr('Search'))
        add('fav', '★ ' + self.tr('Favorites'), 0)
        add('recent', '⟲ ' + self.tr('Recent'), 0)
        add('all', '☰ ' + self.tr('All channels'), 0)
        add('header', self.tr({'category': 'CATEGORIES', 'country': 'COUNTRIES', 'group': 'GROUPS'}[self.view_mode]), selectable=False)
        for i in range(self.playlist_tree.topLevelItemCount()):
            group = self.playlist_tree.topLevelItem(i)
            add('group:' + str(group.data(0, GROUP_KEY_ROLE)), group.text(0), group.childCount())
        lst.blockSignals(False)
        self._refresh_sidebar_counts()
        self._select_sidebar(self.current_view)

    def _refresh_sidebar_counts(self):
        lst = self.category_list
        favorites, recents = self._favorite_urls(), set(self._recent_urls())
        counts = {'fav': sum(1 for u in self.channels if u in favorites),
                  'recent': sum(1 for u in self.channels if u in recents), 'all': len(self.channels)}
        for i in range(lst.count()):
            item = lst.item(i)
            key = item.data(QtCore.Qt.UserRole)
            count = counts.get(key, item.data(QtCore.Qt.UserRole + 1))
            base = item.text().split('   ')[0]
            item.setText(base if count is None else f"{base}   {count}")
        online = sum(1 for c in self.channels.values() if c['source'] == 'online')
        badge = self.tr('{0} channels').format(len(self.channels))
        if online:
            badge += ' (+' + self.tr('{0} world').format(online) + ')'
        self.channel_badge.setText('✔ ' + badge if self.channels else '')

    def _select_sidebar(self, key):
        lst = self.category_list
        lst.blockSignals(True)
        for i in range(lst.count()):
            if lst.item(i).data(QtCore.Qt.UserRole) == key:
                lst.setCurrentRow(i)
                break
        else:
            lst.setCurrentRow(3 if lst.count() > 3 else -1)
        lst.blockSignals(False)

    def _sidebar_selected(self, item):
        if item is None or self._rebuilding:
            return
        key = item.data(QtCore.Qt.UserRole)
        if key == 'search':
            self.search_box.setFocus()
            self.search_box.selectAll()
            self._select_sidebar(self.current_view)
            return
        if key == 'header':
            return
        self.current_view = key
        self.btn_fav.blockSignals(True)
        self.btn_fav.setChecked(key == 'fav')
        self.btn_fav.setText(self.tr("📺 Show All" if key == 'fav' else "⭐ Favorites"))
        self.btn_fav.blockSignals(False)
        self._apply_view()

    def _apply_view(self):
        """Aplică vizualizarea curentă: toate / favorite / recente / un singur grup (listă plată, ca pe TV)."""
        tree = self.playlist_tree
        if self.current_view.startswith('group:'):
            name = self.current_view[6:]
            group_item = self.tree_helper.categories.get(name)
            if group_item is None:
                self.current_view = 'all'
                return self._apply_view()
            group_item.setExpanded(True)
            tree.setRootIndex(tree.indexFromItem(group_item))
        else:
            tree.setRootIndex(QtCore.QModelIndex())
            tree.expandAll()
        self.filter_playlist(self.search_box.text())
        tree.scrollToTop()

    def load_playlist(self):
        """Deschide un fișier M3U nou și îl salvează în config.ini (QTreeWidget version)."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("Open Playlist"),
            "",
            "M3U Files (*.m3u *.m3u8)"
        )
 
        if not path:
            return  # utilizatorul a anulat
 
        if not os.path.exists(path):
            QtWidgets.QMessageBox.warning(self, self.tr("Error"), self.tr(f"File not found:\n{path}"))
            return
 
        # Încărcăm fișierul selectat
        self._load_playlist_file(path)
 
        # Salvăm ultima cale
        cfg = QtCore.QSettings(str(CONFIG_PATH), QtCore.QSettings.IniFormat)
        cfg.setValue("LastPlaylist/path", path)
        cfg.sync()
 
        self._last_playlist_path = path
 
        # Feedback vizual + status
        total = sum(
            self.playlist_tree.topLevelItem(i).childCount()
            for i in range(self.playlist_tree.topLevelItemCount())
        )
        base = os.path.basename(path)
        self.show_info(f"✅ Loaded playlist: {base} ({total} channels)")
        self.playlist_status.setText(self.tr(f"Loaded {total} channels from {base}"))
 
    def append_playlist(self):
        """Adaugă un fișier M3U suplimentar fără a șterge canalele existente."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr(self.tr("Append Playlist") if hasattr(self, "tr") else "Append Playlist"),
            "",
            "M3U Files (*.m3u *.m3u8)"
        )
 
        if not path:
            return  # utilizatorul a anulat
 
        if not os.path.exists(path):
            QtWidgets.QMessageBox.warning(
                self,
                self.tr(self.tr("Error") if hasattr(self, "tr") else "Error"),
                self.tr(f"File not found:\n{path}")
            )
            return
 
        try:
            added_count = 0
            for row in channel_sources.load_file(path):
                if self.register_channel(row, source='user'):
                    added_count += 1
            self._rebuild_tree()
 
            # feedback
            self.playlist_status.setText(self.tr(f"➕ Appended {added_count} channels from {os.path.basename(path)}"))
            self.show_info(f"✅ Appended {added_count} new channels.")
            self.filter_playlist(self.search_box.text())
            self.save_session()
 
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr(self.tr("Error") if hasattr(self, "tr") else "Error"),
                self.tr(f"Failed to append playlist:\n{e}")
            )
 
    def refresh_playlist(self):
        """Reîncarcă playlistul curent din fișierul salvat (QTreeWidget version)."""
        cfg = QtCore.QSettings(str(CONFIG_PATH), QtCore.QSettings.IniFormat)
        last_path = self._last_playlist_path or cfg.value("LastPlaylist/path", "")
 
        if last_path and os.path.exists(last_path):
            self._load_playlist_file(last_path)
            total = sum(
                self.playlist_tree.topLevelItem(i).childCount()
                for i in range(self.playlist_tree.topLevelItemCount())
            )
            self.show_info(f"🔄 Reloaded playlist ({total} channels)")
            self.playlist_status.setText(self.tr(f"🔄 Reloaded {total} channels"))
        else:
            QtWidgets.QMessageBox.information(
                self, self.tr("No playlist"), self.tr("No last playlist found. Use 'Load Playlist'.")
            )
 
    def load_last_playlist(self):
        """Reîncarcă automat ultimul playlist salvat (QTreeWidget version)."""
        if not flag('Settings/restore_playlist', True):
            return
        import json
        try:
            session = DATA_DIR / 'session.json'
            if session.exists():
                payload = json.loads(session.read_text(encoding='utf-8'))
                seen = set()
                for row in payload['channels']:
                    if row['url'] not in seen:
                        self.register_channel(row, source='user')
                        seen.add(row['url'])
                self._rebuild_tree()
                self._last_playlist_path = payload.get('source', '')
                QtCore.QTimer.singleShot(0, lambda: self._restore_session_view(payload))
                return
        except (OSError, ValueError, KeyError, TypeError):
            self.playlist_tree.clear()
            self.tree_helper.categories.clear()
        try:
            cfg = QtCore.QSettings(str(CONFIG_PATH), QtCore.QSettings.IniFormat)
            last_path = cfg.value("LastPlaylist/path", "")
            if last_path and os.path.exists(last_path):
                self._load_playlist_file(last_path)
                total = sum(
                    self.playlist_tree.topLevelItem(i).childCount()
                    for i in range(self.playlist_tree.topLevelItemCount())
                )
                self.show_info(f"Loaded last playlist: {os.path.basename(last_path)}")
                self.playlist_status.setText(self.tr(f"Loaded {total} channels"))
            else:
                bundled = channel_sources.bundled_playlists()
                if bundled:
                    self._load_playlist_file(str(bundled[0]))
                else:
                    self.playlist_status.setText(self.tr("No saved playlist found."))
        except Exception as e:
            self.playlist_status.setText(self.tr(f"⚠️ Error loading last playlist: {e}"))
            self.show_info(f"⚠️ Error loading last playlist: {e}")

    # ===================================
    #     CANALE ONLINE (iptv-org, ca pe TV)
    # ===================================
    def load_online_channels(self, force=False):
        """Canalele din lume: din cache imediat, apoi descărcare în fundal dacă e vechi de peste 24h."""
        if not flag('Settings/online_channels', True):
            self._drop_online_channels()
            return
        rows, fetched_at = channel_sources.read_cache()
        if rows and not any(c['source'] == 'online' for c in self.channels.values()):
            self._merge_online(rows)
        if force or not channel_sources.cache_is_fresh(fetched_at):
            self.refresh_online_channels()

    def refresh_online_channels(self):
        if self._online_worker is not None and self._online_worker.isRunning():
            return
        self.playlist_status.setText(self.tr('Downloading world channels...'))
        self._online_worker = channel_sources.OnlineChannels(self)
        self._online_worker.finished_with.connect(self._online_finished)
        self._online_worker.start()

    def _online_finished(self, rows, error):
        if error:
            self.playlist_status.setText(self.tr('World channels could not be updated.') + ' ' + error[:80])
            return
        self._drop_online_channels(rebuild=False)
        self._merge_online(rows)
        self.playlist_status.setText(self.tr('{0} world channels updated.').format(len(rows)))

    def _merge_online(self, rows):
        added = 0
        for row in rows:
            if self.register_channel(row, source='online'):
                added += 1
        if added:
            self._rebuild_tree()
        return added

    def _drop_online_channels(self, rebuild=True):
        if any(c['source'] == 'online' for c in self.channels.values()):
            self.channels = {u: c for u, c in self.channels.items() if c['source'] != 'online'}
            if rebuild:
                self._rebuild_tree()
 
    def filter_playlist(self, text):
        """Filtrează canalele după textul introdus (QTreeWidget version)."""
        text = text.lower().strip()
        if self.btn_fav.isChecked() and self.current_view != 'fav':
            self.current_view = 'fav'
            self._select_sidebar('fav')
        elif not self.btn_fav.isChecked() and self.current_view == 'fav':
            self.current_view = 'all'
            self._select_sidebar('all')
        is_fav_mode = self.current_view == 'fav'
        recent_urls = set(self._recent_urls()) if self.current_view == 'recent' else None
        fav_urls = self._favorite_urls()
 
        visible_count = 0
        root_key = self.current_view[6:] if self.current_view.startswith('group:') else None
 
        for i in range(self.playlist_tree.topLevelItemCount()):
            cat_item = self.playlist_tree.topLevelItem(i)
            cat_visible = False
            in_root = root_key is None or cat_item.data(0, GROUP_KEY_ROLE) == root_key
            for j in range(cat_item.childCount()):
                ch_item = cat_item.child(j)
                url = ch_item.data(0, QtCore.Qt.UserRole)
                name = ch_item.text(0).lower()
 
                in_fav = url in fav_urls
                visible = (text in name) and (in_fav if is_fav_mode else True)
                if recent_urls is not None and url not in recent_urls:
                    visible = False
 
                ch_item.setHidden(not visible)
                if visible:
                    cat_visible = True
                    if in_root:
                        visible_count += 1
            cat_item.setHidden(not cat_visible)
            if (text or self.current_view != 'all') and cat_visible:
                cat_item.setExpanded(True)
 
        self.playlist_status.setText(self.tr(f"🔍 Found {visible_count} results"))
        if visible_count > 0:
            self.show_info(f"🔍 {visible_count} channels match filter.")
        else:
            self.show_info("⚠️ No results found.")
 
    def show_playlist_menu(self, pos):
        """Afișează meniul contextual complet (pentru compatibilitate cu QTreeWidget)."""
        item = self.playlist_tree.itemAt(pos)
        if not item:
            return
 
        url = item.data(0, QtCore.Qt.UserRole)
        name = item.text(0)
 
        # Citim lista de favorite
        cfg = QtCore.QSettings(str(CONFIG_PATH), QtCore.QSettings.IniFormat)
        favorites = cfg.value("Favorites/list", "")
        fav_list = favorites.split("|") if favorites else []
        entry = f"{name.replace('⭐ ', '')}::{url}" if url else ""
        is_fav = entry in fav_list
 
        texts = getattr(self, "context_menu_texts", {})
        tr = lambda key, default: texts.get(key, default)
 
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #0E1620;
                color: #E0E0E0;
                border: 1px solid #0E2638;
                font-size: 13px;
            }
            QMenu::item:selected {
                background-color: #00A8FF;
                color: #000;
            }
        """)
 
        if url:
            play_action = menu.addAction(tr("play", "▶ Play"))
            if is_fav:
                fav_action = menu.addAction(tr("remove_fav", "💔 Remove from Favorites"))
            else:
                fav_action = menu.addAction(tr("add_fav", "⭐ Add to Favorites"))
 
            menu.addSeparator()
            rem_action = menu.addAction(tr("remove", "❌ Remove from playlist"))
            perm_action = menu.addAction(tr("remove_perm", "🗑 Remove permanently from playlist"))
 
            if url.lower().endswith((".mp4", ".mov", ".mkv")):
                dl_action = menu.addAction(tr("download", "⬇ Record selected channel"))
 
            action = menu.exec_(self.playlist_tree.mapToGlobal(pos))
 
            if action == play_action:
                self._play_tree_item(item, 0)
            elif action == fav_action:
                if is_fav:
                    self.remove_from_favorites(name, url)
                    if item.text(0).startswith("⭐ "):
                        item.setText(item.text(0).replace("⭐ ", ""))
                else:
                    self.add_to_favorites(name, url)
                    if not item.text(0).startswith("⭐ "):
                        item.setText(f"⭐ {item.text(0)}")
            elif action == rem_action:
                parent = item.parent()
                if parent:
                    parent.removeChild(item)
            elif action == perm_action:
                self.remove_permanent(item)
            elif url and action and action.text().startswith("⬇"):
                self.record_selected(url)
        else:
            remove_cat = menu.addAction("🗑 Remove Category")
            action = menu.exec_(self.playlist_tree.mapToGlobal(pos))
            if action == remove_cat:
                idx = self.playlist_tree.indexOfTopLevelItem(item)
                if idx >= 0:
                    self.playlist_tree.takeTopLevelItem(idx)
 
    def add_to_favorites(self, name, url):
        """Adaugă canalul la favorite (QTreeWidget version + efect vizual auriu)"""
        try:
            clean_name = name[2:] if name.startswith("⭐ ") else name
            if not url:
                self.show_info("⚠️ No URL found.")
                return
 
            cfg = QtCore.QSettings(str(CONFIG_PATH), QtCore.QSettings.IniFormat)
            favorites = cfg.value("Favorites/list", "")
            fav_list = favorites.split("|") if favorites else []
 
            entry = f"{clean_name}::{url}"
            if entry in fav_list:
                self.show_info(f"{clean_name} already in favorites.")
                return
 
            fav_list.append(entry)
            cfg.setValue("Favorites/list", "|".join(fav_list))
            cfg.sync()
 
            # Caută și marchează itemul din arbore
            for i in range(self.playlist_tree.topLevelItemCount()):
                cat_item = self.playlist_tree.topLevelItem(i)
                for j in range(cat_item.childCount()):
                    ch_item = cat_item.child(j)
                    if ch_item.data(0, QtCore.Qt.UserRole) == url:
                        if not ch_item.text(0).startswith("⭐ "):
                            ch_item.setText(0, f"⭐ {ch_item.text(0)}")
                        # 🔸 efect vizual – text auriu și bold
                        ch_item.setForeground(0, QtGui.QBrush(QtGui.QColor("#FFD700")))
                        font = ch_item.font(0)
                        font.setBold(True)
                        ch_item.setFont(0, font)
                        break
 
            self._refresh_sidebar_counts()
            self.playlist_status.setText(self.tr(f"⭐ Added to favorites: {clean_name}"))
            self.show_info(f"⭐ Added to favorites: {clean_name}")
 
        except Exception as e:
            self.playlist_status.setText(self.tr(f"❌ Favorites add error: {e}"))
            self.show_info(f"❌ Favorites add error: {e}")
 
    def remove_from_favorites(self, name, url):
        """Șterge canalul din favorite (QTreeWidget version + revocă efectul vizual)"""
        try:
            cfg = QtCore.QSettings(str(CONFIG_PATH), QtCore.QSettings.IniFormat)
            favorites = cfg.value("Favorites/list", "")
            fav_list = favorites.split("|") if favorites else []
 
            entry = f"{name.replace('⭐ ', '')}::{url}"
            if entry in fav_list:
                fav_list.remove(entry)
                cfg.setValue("Favorites/list", "|".join(fav_list))
                cfg.sync()
 
                # Elimină simbolul ⭐ și revine la stilul normal
                for i in range(self.playlist_tree.topLevelItemCount()):
                    cat_item = self.playlist_tree.topLevelItem(i)
                    for j in range(cat_item.childCount()):
                        ch_item = cat_item.child(j)
                        if ch_item.data(0, QtCore.Qt.UserRole) == url:
                            if ch_item.text(0).startswith("⭐ "):
                                ch_item.setText(0, ch_item.text(0).replace("⭐ ", ""))
                            ch_item.setForeground(0, QtGui.QBrush(QtGui.QColor("#E0E0E0")))
                            font = ch_item.font(0)
                            font.setBold(False)
                            ch_item.setFont(0, font)
                            break
 
                self._refresh_sidebar_counts()
                self.playlist_status.setText(self.tr(f"💔 Removed from favorites: {name}"))
                self.show_info(f"💔 Removed from favorites: {name}")
            else:
                self.show_info(f"{name} not found in favorites.")
        except Exception as e:
            self.show_info(f"❌ Favorites remove error: {e}")
            self.playlist_status.setText(self.tr(f"❌ Favorites remove error: {e}"))
 
    def load_favorites(self):
        """Marchează în arbore toate canalele care sunt salvate ca favorite (cu stil auriu)."""
        try:
            cfg = QtCore.QSettings(str(CONFIG_PATH), QtCore.QSettings.IniFormat)
            favorites = cfg.value("Favorites/list", "")
            if not favorites:
                return
 
            fav_list = favorites.split("|")
 
            # Iterăm toate categoriile și canalele
            for i in range(self.playlist_tree.topLevelItemCount()):
                cat_item = self.playlist_tree.topLevelItem(i)
                for j in range(cat_item.childCount()):
                    ch_item = cat_item.child(j)
                    url = ch_item.data(0, QtCore.Qt.UserRole)
                    if any(url in fav for fav in fav_list):
                        if not ch_item.text(0).startswith("⭐ "):
                            ch_item.setText(0, f"⭐ {ch_item.text(0)}")
                        # 🔸 aplicăm stil vizual pentru favorite la pornire
                        ch_item.setForeground(0, QtGui.QBrush(QtGui.QColor("#FFD700")))
                        font = ch_item.font(0)
                        font.setBold(True)
                        ch_item.setFont(0, font)
 
            self.show_info("⭐ Favorites loaded.")
        except Exception as e:
            self.playlist_status.setText(self.tr(f"❌ Error loading favorites: {e}"))
            self.show_info(f"❌ Error loading favorites: {e}")
 
    def toggle_favorites_view(self):
        self.btn_fav.setText(self.tr("📺 Show All" if self.btn_fav.isChecked() else "⭐ Favorites"))
        self.current_view = 'fav' if self.btn_fav.isChecked() else 'all'
        self._select_sidebar(self.current_view)
        self._apply_view()

    def remove_permanent(self, item):
        """Șterge canalul din fișierul M3U și îl elimină vizual cu fade-out (QTreeWidget version)."""
        try:
            cfg = QtCore.QSettings(str(CONFIG_PATH), QtCore.QSettings.IniFormat)
            last_path = cfg.value("LastPlaylist/path", "")
 
            if not last_path or not os.path.exists(last_path):
                self.playlist_status.setText(self.tr("⚠️ No saved playlist file found."))
                return
 
            url = item.data(0, QtCore.Qt.UserRole)
            if not url:
                self.playlist_status.setText(self.tr("⚠️ No URL found for selected item."))
                return
 
            # Citim fișierul M3U
            with open(last_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
 
            new_lines = []
            skip_next = False
 
            # Eliminăm canalul din fișier (linia #EXTINF + URL)
            for i, line in enumerate(lines):
                if skip_next:
                    skip_next = False
                    continue
 
                if line.strip().startswith("#EXTINF") and i + 1 < len(lines) and url.strip() in lines[i + 1]:
                    skip_next = True
                    continue
 
                new_lines.append(line)
 
            # Scriem fișierul actualizat
            with open(last_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
 
            # Efect vizual fade-out în arbore
            effect = QtWidgets.QGraphicsOpacityEffect(item.treeWidget())
            item.setForeground(0, QtGui.QBrush(QtGui.QColor("#FF4444")))
            anim = QtCore.QPropertyAnimation(effect, b"opacity")
            anim.setDuration(400)
            anim.setStartValue(1.0)
            anim.setEndValue(0.0)
            anim.setEasingCurve(QtCore.QEasingCurve.InOutQuad)
 
            def finalize_remove():
                parent = item.parent()
                if parent:
                    parent.removeChild(item)
                self.playlist_status.setText(self.tr(f"🗑 Removed permanently: {item.text(0)}"))
                self.show_info(f"Updated playlist: {os.path.basename(last_path)}")
 
            anim.finished.connect(finalize_remove)
            anim.start(QtCore.QAbstractAnimation.DeleteWhenStopped)
 
        except Exception as e:
            self.playlist_status.setText(self.tr(f"❌ Error removing: {e}"))
            self.show_info(f"❌ Error removing: {e}")
 
    def remove_from_playlist(self, item):
        """Șterge canalul doar din arborele curent (fără a modifica fișierul)."""
        try:
            parent = item.parent()
            if parent:
                parent.removeChild(item)
                self.playlist_status.setText(self.tr(f"Removed: {item.text(0)}"))
                self.show_info(f"Removed: {item.text(0)}")
            else:
                self.playlist_status.setText(self.tr("⚠️ Cannot remove root category."))
        except Exception as e:
            self.playlist_status.setText(self.tr(f"❌ Error removing: {e}"))
 
    # ===================================
    #          LICENSE GATES
    # ===================================
    def _license_allows_channel(self, url):
        import licensing
        if licensing.can_play_channel(url):
            return True
        self.show_info(self.tr('Daily channel limit reached.'))
        self._offer_activation(licensing.limit_message(self.tr))
        return False

    def _license_allows_recording(self):
        import licensing
        if licensing.recording_allowed():
            return True
        self.show_info(self.tr('Recording is not available without a license.'))
        self._offer_activation(licensing.recording_message(self.tr))
        return False

    def _offer_activation(self, text):
        window = self.window()
        box = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Information, 'VisionPro IPTV', text, parent=window)
        activate = box.addButton(self.tr('Activate license...'), QtWidgets.QMessageBox.AcceptRole)
        box.addButton(self.tr('Close'), QtWidgets.QMessageBox.RejectRole)
        box.exec_()
        if box.clickedButton() is activate and hasattr(window, 'open_activation_dialog'):
            window.open_activation_dialog()

    def record_selected(self, url):
        if not self._license_allows_recording():
            return
        item = self.playlist_tree.currentItem()
        name = item.text(0).removeprefix('⭐ ') if item else 'channel'
        self.recorder.start(url, name)

    def _play_tree_item(self, item, column):
        """Redă canalul selectat din arbore + monitorizare stare VLC."""
        url = item.data(0, QtCore.Qt.UserRole)
        if not url:
            item.setExpanded(not item.isExpanded())
            return
        if not self._license_allows_channel(url):
            return
 
        self.current_url = url
        self.player.video_set_aspect_ratio(str(settings().value('Settings/aspect', '')) or None)
        channel_name = item.text(0).replace("⭐ ", "")
        self._update_now_playing(url, channel_name)
        self._remember_recent(url)
 
        media = self._media_with_headers(url)
        self.player.set_hwnd(self.video_frame.winId())
        self.player.set_media(media)
        self.player.play()
        self.show_info(f"⏳ Connecting: {channel_name}...")
 
        # ── Oprim orice monitor anterior ──────────────────────────
        if hasattr(self, "_state_timer") and self._state_timer:
            self._state_timer.stop()
            self._state_timer = None
 
        self._state_check_count = 0
        self._state_channel_name = channel_name
 
        self._state_timer = QtCore.QTimer(self)
        self._state_timer.setInterval(800)
        self._state_timer.timeout.connect(self._check_vlc_state)
        self._state_timer.start()
 
    def _check_vlc_state(self):
        """Verifică starea VLC la fiecare 800ms și afișează status clar."""
        try:
            self._state_check_count += 1
            state = self.player.get_state()
            name = getattr(self, "_state_channel_name", "Channel")
 
            if state == vlc.State.Playing:
                self.show_info(f"✅ Playing: {name}")
                self._state_timer.stop()
                self._state_timer = None
 
            elif state == vlc.State.Buffering:
                dots = "." * (self._state_check_count % 4)
                self.show_info(f"⏳ Buffering{dots} {name}")
 
            elif state in (vlc.State.Error, vlc.State.Ended):
                self.show_info(f"❌ Cannot play: {name} — stream offline or link error")
                self._state_timer.stop()
                self._state_timer = None
                if hasattr(self, "playlist_status"):
                    self.playlist_status.setText(self.tr(f"❌ Stream error: {name}"))
 
            elif state == vlc.State.Stopped:
                self.show_info(f"⏹ Stopped: {name}")
                self._state_timer.stop()
                self._state_timer = None
 
            elif self._state_check_count >= 12:
                # ~10 sec fără răspuns = timeout
                self.show_info(f"⚠️ Timeout: {name} — no response from server")
                if hasattr(self, "playlist_status"):
                    self.playlist_status.setText(self.tr(f"⚠️ Timeout: {name}"))
                self._state_timer.stop()
                self._state_timer = None
 
        except Exception as e:
            print(f"[⚠️] _check_vlc_state error: {e}")
            if hasattr(self, "_state_timer") and self._state_timer:
                self._state_timer.stop()
                self._state_timer = None
 
    def _show_tree_menu(self, pos):
        """Meniu click dreapta complet pentru QTreeWidget (Play, Fav, Remove, Download, traductibil complet)."""
        item = self.playlist_tree.itemAt(pos)
        if not item:
            return
 
        url = item.data(0, QtCore.Qt.UserRole)
        name = item.text(0)
 
        # === Obținem lista de favorite din config ===
        cfg = QtCore.QSettings(str(CONFIG_PATH), QtCore.QSettings.IniFormat)
        favorites = cfg.value("Favorites/list", "")
        fav_list = favorites.split("|") if favorites else []
        entry = f"{name.replace('⭐ ', '')}::{url}" if url else ""
        is_fav = entry in fav_list
 
        # === Folosește traducerea activă din VisionMainWindow ===
        parent_window = self.window()
        if parent_window and hasattr(parent_window, "tr"):
            tr = parent_window.tr
        elif hasattr(self, "tr"):
            tr = self.tr
        else:
            tr = lambda x: x  # fallback
 
        # === Creăm meniul contextual ===
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #0E1620;
                color: #E0E0E0;
                border: 1px solid #0E2638;
                font-size: 13px;
            }
            QMenu::item:selected {
                background-color: #00A8FF;
                color: #000;
            }
        """)
 
        # === Meniu pentru canal individual ===
        if url:
            play_action = menu.addAction(f"▶ {tr('Play')}")
            if is_fav:
                fav_action = menu.addAction(f"💔 {tr('Remove from Favorites')}")
            else:
                fav_action = menu.addAction(f"⭐ {tr('Add to Favorites')}")
 
            menu.addSeparator()
            rem_action = menu.addAction(f"❌ {tr('Remove from playlist')}")
            perm_action = menu.addAction(f"🗑 {tr('Remove permanently from playlist')}")
 
            if url.lower().endswith((".mp4", ".mov", ".mkv", ".m3u8")):
                dl_action = menu.addAction(f"⬇ {tr('Record selected channel')}")
 
            action = menu.exec_(self.playlist_tree.mapToGlobal(pos))
 
            # === Execuție acțiuni ===
            if action == play_action:
                self._play_tree_item(item, 0)
 
            elif action == fav_action:
                if is_fav:
                    self.remove_from_favorites(name, url)
                    if item.text(0).startswith("⭐ "):
                        item.setText(0, item.text(0).replace("⭐ ", ""))
                    self.show_info(f"💔 {tr('Removed from favorites:')} {name}")
                else:
                    self.add_to_favorites(name, url)
                    if not item.text(0).startswith("⭐ "):
                        item.setText(0, f"⭐ {item.text(0)}")
                    self.show_info(f"⭐ {tr('Added to favorites:')} {name}")
 
            elif action == rem_action:
                parent = item.parent()
                if parent:
                    parent.removeChild(item)
                    self.show_info(f"❌ {tr('Removed:')} {name}")
 
            elif action == perm_action:
                self.remove_permanent(item)
 
            elif url and action and action.text().startswith("⬇"):
                self.record_selected(url)
 
        # === Meniu pentru categorie ===
        else:
            remove_cat = menu.addAction(f"🗑 {tr('Remove Category')}")
            action = menu.exec_(self.playlist_tree.mapToGlobal(pos))
            if action == remove_cat:
                idx = self.playlist_tree.indexOfTopLevelItem(item)
                if idx >= 0:
                    self.playlist_tree.takeTopLevelItem(idx)
                    self.show_info(f"🗑 {tr('Category removed:')} {item.text(0)}")
 
    # ======================================
    #        FUNCȚIE – ADD URL MANUAL
    # ======================================
    def add_url(self):
        """Adaugă manual un stream URL într-o categorie existentă sau nouă."""
        url, ok = QtWidgets.QInputDialog.getText(
            self, self.tr("Add Stream URL"), self.tr("Enter stream URL (M3U8 or direct stream):")
        )
        if ok and url.strip():
            for i in range(self.playlist_tree.topLevelItemCount()):
                group = self.playlist_tree.topLevelItem(i)
                if any(group.child(j).data(0, QtCore.Qt.UserRole) == url.strip() for j in range(group.childCount())):
                    self.show_info('Channel already exists in the playlist.')
                    return
            category, ok2 = QtWidgets.QInputDialog.getText(
                self, self.tr("Category"), self.tr("Enter category (default: Manual):")
            )
            if not ok2:
                return
            if not category.strip():
                category = "Manual"
 
            self.tree_helper.add_channel(category, os.path.basename(url.strip()), url.strip())
 
            self.playlist_status.setText(self.tr(f"✅ Added stream: {url.strip()}"))
            self.show_info(f"Added stream to '{category}'")
 
    # ======================================
    #        FUNCȚIE – SAVE PLAYLIST
    # ======================================
    def save_playlist(self):
        """Salvează structura actuală (categorii + canale) într-un fișier M3U."""
        try:
            total = sum(
                self.playlist_tree.topLevelItem(i).childCount()
                for i in range(self.playlist_tree.topLevelItemCount())
            )
            if total == 0:
                self.show_info("⚠️ No channels to save.")
                return
 
            # Dialog de salvare
            file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                self.tr("Save Playlist As"),
                "",
                "M3U Playlist (*.m3u);;All Files (*)"
            )
            if not file_path:
                self.show_info("Save cancelled.")
                return
 
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for i in range(self.playlist_tree.topLevelItemCount()):
                    cat_item = self.playlist_tree.topLevelItem(i)
                    cat_name = cat_item.text(0)
                    for j in range(cat_item.childCount()):
                        ch_item = cat_item.child(j)
                        name = ch_item.text(0).replace("⭐ ", "")
                        url = ch_item.data(0, QtCore.Qt.UserRole)
                        if url:
                            f.write(f'#EXTINF:-1 group-title="{cat_name}",{name}\n')
                            f.write(f"{url}\n")
 
            # Salvăm în config.ini pentru autoload
            cfg = QtCore.QSettings(str(CONFIG_PATH), QtCore.QSettings.IniFormat)
            self._last_playlist_path = file_path
            cfg.setValue("LastPlaylist/path", file_path)
            cfg.sync()
 
            self.playlist_status.setText(self.tr(f"💾 Playlist saved: {os.path.basename(file_path)}"))
            self.show_info(f"✅ Saved {total} channels to {os.path.basename(file_path)}")
 
        except Exception as e:
            self.show_info(f"❌ Error saving playlist: {e}")
            self.playlist_status.setText(self.tr(f"❌ Error saving: {e}"))
 
    # ======================================
    #        FUNCȚIE – CLEAR PLAYLIST
    # ======================================
    def clear_playlist(self):
        """Curăță complet lista de canale și categoriile din arbore."""
        try:
            self._clear_channels(keep_online=False)
            self._rebuild_tree()
            self.playlist_status.setText(self.tr("🧹 Playlist cleared."))
            self.show_info("🧹 Playlist cleared successfully.")
 
            # Ștergem și ultima cale salvată
            cfg = QtCore.QSettings(str(CONFIG_PATH), QtCore.QSettings.IniFormat)
            self._last_playlist_path = ""
            cfg.remove("LastPlaylist/path")
            cfg.sync()
 
        except Exception as e:
            self.show_info(f"❌ Error clearing playlist: {e}")
            self.playlist_status.setText(self.tr(f"❌ Error clearing: {e}"))
 
    # ===================================
    #          RECORD FUNCTIONS
    # ===================================
    def start_recording(self):
        if not self.current_url:
            self.show_info(self.tr('No channel selected.'))
            return
        if not self._license_allows_recording():
            return
        self.recorder.start(self.current_url, getattr(self, '_state_channel_name', 'channel'))

    def stop_recording(self):
        self.recorder.stop()

    def _recording_changed(self, state, detail):
        self.recording = self.recorder.active
        labels = {'connecting': 'Connecting recorder', 'recording': 'Recording',
                  'stopping': 'Finalizing recording', 'remuxing': 'Preparing MP4', 'saved': 'Recording saved', 'error': 'Recording error'}
        self.record_status.setToolTip(detail if state != 'error' else self.tr(detail))
        if state in ('saved', 'error'):
            self.show_info(self.tr(labels[state]) + ': ' + (self.tr(detail) if state == 'error' else detail))
        self._last_record_path = str(self.recorder.output or '')

    def stop_playback(self):
        self.player.stop()
        self.now_playing.setText(self.tr('Stopped'))

    def save_session(self):
        import json
        rows = [{'name': c['name'], 'url': c['url'], 'group': c['group'], 'country': c['country'], 'logo': c['logo']}
                for c in self.channels.values() if c['source'] != 'online']
        payload = {'channels': rows, 'source': self._last_playlist_path,
                   'selected': self.current_url, 'search': self.search_box.text(),
                   'favorites_only': self.btn_fav.isChecked(),
                   'expanded': [self.playlist_tree.topLevelItem(i).text(0) for i in range(self.playlist_tree.topLevelItemCount()) if self.playlist_tree.topLevelItem(i).isExpanded()],
                   'scroll': self.playlist_tree.verticalScrollBar().value()}
        output = QtCore.QSaveFile(str(DATA_DIR / 'session.json'))
        if output.open(QtCore.QIODevice.WriteOnly):
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            if output.write(data) != len(data) or not output.commit():
                self.show_info(self.tr('Could not save session.') + ' ' + output.errorString())
        else:
            self.show_info(self.tr('Could not save session.') + ' ' + output.errorString())
        cfg = settings()
        cfg.setValue('Settings/volume', self.slider_volume.value())
        cfg.setValue('Settings/muted', bool(self.player.audio_get_mute()))
        cfg.setValue('LastPlaylist/path', self._last_playlist_path)
        cfg.sync()

    def _restore_session_view(self, payload):
        selected = payload.get('selected')
        for i in range(self.playlist_tree.topLevelItemCount()):
            group = self.playlist_tree.topLevelItem(i)
            group.setExpanded(group.text(0) in payload.get('expanded', []))
            for j in range(group.childCount()):
                item = group.child(j)
                if item.data(0, QtCore.Qt.UserRole) == selected:
                    self.playlist_tree.setCurrentItem(item)
                    self.current_url = selected
                    self._state_channel_name = item.text(0)
        self.load_favorites()
        self.btn_fav.setChecked(payload.get('favorites_only', False))
        self.current_view = 'fav' if self.btn_fav.isChecked() else 'all'
        self._select_sidebar(self.current_view)
        self.search_box.setText(payload.get('search', ''))
        self._apply_view()
        self.playlist_tree.verticalScrollBar().setValue(payload.get('scroll', 0))
        if selected and flag('Settings/autoplay'):
            self.play_current()

    def retranslate_ui(self, tr):
        self.tr = tr
        """Retraduce toate textele și butoanele din tabul IPTV."""
        try:
            # === Bara superioară de control ===
            if hasattr(self, "btn_load"):
                self.btn_load.setText(f"📂 {tr('Load Playlist')}")
            if hasattr(self, "btn_add_url"):
                self.btn_add_url.setText(f"➕ {tr('Add URL')}")
            if hasattr(self, "btn_save_playlist"):
                self.btn_save_playlist.setText(f"💾 {tr('Save Playlist')}")
            if hasattr(self, "btn_clear"):
                self.btn_clear.setText(f"🧹 {tr('Clear')}")
            if hasattr(self, "btn_refresh"):
                self.btn_refresh.setText(f"🔄 {tr('Refresh')}")
            if hasattr(self, "btn_fullscreen"):
                self.btn_fullscreen.setText(f"⛶ {tr('Fullscreen')}")
            if hasattr(self, "btn_start_rec"):
                self.btn_start_rec.setText(f"⏺ {tr('Start Rec')}")
            if hasattr(self, "btn_stop_rec"):
                self.btn_stop_rec.setText(f"⏹ {tr('Stop Rec')}")
 
            # === Bara de control video ===
            if hasattr(self, "btn_play"):
                self.btn_play.setToolTip(tr("Play"))
            if hasattr(self, "btn_pause"):
                self.btn_pause.setToolTip(tr("Pause"))
            if hasattr(self, "btn_stop"):
                self.btn_stop.setToolTip(tr("Stop"))
            if hasattr(self, "btn_mute"):
                self.btn_mute.setToolTip(tr("Mute"))
            if hasattr(self, "btn_full"):
                self.btn_full.setToolTip(tr("Fullscreen"))
 
            # === Bara de favorite și căutare ===
            if hasattr(self, "btn_fav"):
                if self.btn_fav.isChecked():
                    self.btn_fav.setText(tr("📺 Show All"))
                else:
                    self.btn_fav.setText(tr("⭐ Favorites"))
                self.btn_fav.setToolTip(tr("Toggle favorites view"))
 
            if hasattr(self, "search_box"):
                self.search_box.setPlaceholderText(tr("Search channel..."))
            if hasattr(self, "mode_buttons"):
                for mode, label in (('category', 'Categories'), ('country', 'Countries'), ('group', 'Groups')):
                    self.mode_buttons[mode].setText(tr(label))
                self.sidebar_title.setText(tr("Categories"))
                self._rebuild_tree()
 
            self.filter_playlist(self.search_box.text())
            if getattr(self, '_state_channel_name', '') and self.current_url:
                self._update_now_playing(self.current_url, self._state_channel_name)
            else:
                self.now_playing.setText(tr('Select a channel to start watching'))

            # === Eticheta de înregistrare ===
            if hasattr(self, "rec_label"):
                self.rec_label.setText(tr("🔴 Recording"))
 
        except Exception as e:
            print(f"[⚠️] Eroare la retranslate_ui() în VisionIPTVTab: {e}")
 
 
    def retranslate_context_menu(self, tr):
        """Retraduce textele meniului contextual de click dreapta."""
        try:
            self.context_menu_texts = {
                "play": f"▶ {tr('Play')}",
                "add_fav": f"⭐ {tr('Add to Favorites')}",
                "remove_fav": f"💔 {tr('Remove from Favorites')}",
                "remove": f"❌ {tr('Remove from playlist')}",
                "remove_perm": f"🗑 {tr('Remove permanently from playlist')}",
                "download": f"⬇ {tr('Record selected channel')}",
                "remove_category": f"🗑 {tr('Remove Category')}"
            }
        except Exception as e:
            print(f"[⚠️] Eroare la retranslate_context_menu() în VisionIPTVTab: {e}")
 
    # ===================================
    #         MESAJ TEMPORAR JOS
    # ===================================
    def show_info(self, text):
        if not hasattr(self, "info_label"):
            return
        self.info_label.setText(self.tr(text))
        if hasattr(self, "_info_timer"):
            self._info_timer.start(5000)

    def closeEvent(self, event):
        """Curățare sigură la închidere pentru a evita blocarea Qt/VLC."""
        try:
            print("[🔻] Closing VisionPro IPTV... cleaning up VLC player.")
 
            # --------------------------------------------------------
            #  Detașăm playerul de la orice fereastră activă
            # --------------------------------------------------------
            if hasattr(self, "player") and self.player:
                try:
                    self.player.set_hwnd(0)    # detașează complet fluxul video
                    self.player.stop()
                    print("[🧹] VLC player stopped.")
                except Exception as e:
                    print(f"[⚠️] Player stop error: {e}")
 
                QtCore.QTimer.singleShot(200, lambda: self._safe_release_player())
 
            # --------------------------------------------------------
            #  Eliberăm instanța VLC după un mic delay
            # --------------------------------------------------------
            if hasattr(self, "_vlc_instance") and self._vlc_instance:
                QtCore.QTimer.singleShot(400, lambda: self._safe_release_instance())
 
            QtCore.QCoreApplication.processEvents()
            print("[🧹] VLC și animațiile au fost curățate corect.")
 
        except Exception as e:
            print(f"[⚠️] Cleanup error on close: {e}")
 
        finally:
            event.accept()
 
    # ------------------------------------------------------------
    #  Funcții helper interne pentru cleanup asigurat (non-blocking)
    # ------------------------------------------------------------
    def _safe_release_player(self):
        """Eliberare sigură media_player."""
        try:
            if hasattr(self, "player") and self.player:
                self.player.release()
                self.player = None
                print("[✅] VLC player released successfully.")
        except Exception as e:
            print(f"[⚠️] Player release error: {e}")
 
    def _safe_release_instance(self):
        """Eliberare sigură instanță VLC."""
        try:
            if hasattr(self, "_vlc_instance") and self._vlc_instance:
                self._vlc_instance.release()
                self._vlc_instance = None
                print("[✅] VLC instance released successfully.")
        except Exception as e:
            print(f"[⚠️] VLC instance release error: {e}")
 
    def _safe_btn(self, name):
        """Returnează un buton din fereastra principală (globală) dacă există."""
        try:
            return getattr(self.parent(), f"btn_{name}", None)
        except Exception:
            return None
 
# ------------------------------------------------------------
#  QTreeWidget Helper – management categorii + canale
# ------------------------------------------------------------
class VisionTreeHelper:
    def __init__(self, tree_widget, tab=None):
        self.tree = tree_widget
        self.tab = tab
        self.categories = {}
 
    def add_channel(self, category, name, url):
        """Adaugă un canal în model și în arbore, în grupul potrivit modului curent."""
        entry = None
        if self.tab is not None:
            entry = self.tab.register_channel({'name': name, 'url': url, 'group': category}, source='user')
            if entry is None:
                return
            category = self.tab._group_key(entry)
        try:
            stale = category in self.categories and self.tree.indexOfTopLevelItem(self.categories[category]) < 0
        except RuntimeError:  # the tree was cleared and the old group item deleted
            stale = True
        if stale:
            self.categories = {k: v for k, v in self.categories.items() if v is not self.categories.get(category)}
        if category not in self.categories:
            cat_item = QTreeWidgetItem([self.tab._display_group(category) if self.tab else category])
            cat_item.setData(0, GROUP_KEY_ROLE, category)
            self.tree.addTopLevelItem(cat_item)
            self.categories[category] = cat_item
            if self.tab:
                self.categories[self.tab._display_group(category)] = cat_item
        if entry is not None:
            ch_item = self.tab._make_item(entry)
        else:
            ch_item = QTreeWidgetItem([name])
            ch_item.setData(0, QtCore.Qt.UserRole, url)
        self.categories[category].addChild(ch_item)
        if self.tab is not None and not self.tab._rebuilding:
            self.tab._refresh_sidebar()
