# -*- coding: utf-8 -*-
import sys
import os
import math
import json                      # ✅ necesar pentru fișierele de traduceri JSON
from pathlib import Path
from PyQt5 import QtWidgets, QtGui, QtCore
from tabs.vision_iptv_core import VisionIPTVTab
from player_services import preferences, show_about, settings, flag
import licensing
from localization import Translator

# ------------------------------------------------------------
#  CONFIG GLOBAL (salvat permanent în AppData)
# ------------------------------------------------------------
CONFIG_PATH = Path(os.getenv("APPDATA")) / "VisionProIPTV" / "config.ini"
CONFIG_PATH.parent.mkdir(exist_ok=True)  # creăm folderul dacă nu există


# ------------------------------------------------------------
#  Bara de titlu personalizată VisionPro IPTV
# ------------------------------------------------------------
class VisionTitleBar(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(36)

        self.setStyleSheet("""
            QFrame {
                background-color: qlineargradient(
                    spread:pad, x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1B2E42, stop:1 #0E1620
                );
                border-bottom: 1px solid #0E2638;
            }
            QPushButton {
                color: #E0E0E0;
                background: transparent;
                border: none;
                padding: 4px 10px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00A8FF;
                color: black;
                border-radius: 3px;
            }
        """)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(6)

        # === Titlu și icon aplicație ===
        self.icon_label = QtWidgets.QLabel()
        icon_path = os.path.join("icons", "tray_icon.png")
        if os.path.exists(icon_path):
            self.icon_label.setPixmap(QtGui.QPixmap(icon_path).scaled(18, 18, QtCore.Qt.KeepAspectRatio))
        layout.addWidget(self.icon_label)

        self.title = QtWidgets.QLabel("VisionPro IPTV")
        self.title.setStyleSheet("color: #00A8FF; font-weight: bold; font-size: 13px;")
        layout.addWidget(self.title)
        layout.addStretch()

        # === Butoane sistem (Minimize / Close) ===
        self.btn_min = QtWidgets.QPushButton("—")
        self.btn_close = QtWidgets.QPushButton("✕")
        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_close)

        # === Conectări ===
        self.btn_min.clicked.connect(parent.showMinimized)
        self.btn_close.clicked.connect(parent.close)

    # === Permite mutarea ferestrei cu mouse-ul ===
    def mousePressEvent(self, event):
        """Salvează poziția inițială a cursorului la click."""
        if event.button() == QtCore.Qt.LeftButton:
            self.old_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        """Permite mutarea doar dacă fereastra NU este maximizată."""
        if event.buttons() == QtCore.Qt.LeftButton:
            # 🔹 Blocăm mutarea dacă fereastra e maximizată
            if self.parent.isMaximized():
                return

            try:
                delta = event.globalPos() - self.old_pos
                self.parent.move(self.parent.x() + delta.x(), self.parent.y() + delta.y())
                self.old_pos = event.globalPos()
            except Exception as e:
                print(f"[⚠️] Mouse move error: {e}")

# ------------------------------------------------------------
#  Fereastra principală VisionPro IPTV
# ------------------------------------------------------------
class VisionMainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        # ------------------------------------------------------------
        #  Setări fereastră principală
        # ------------------------------------------------------------
        self.setWindowTitle("VisionPro IPTV")
        self.setMinimumSize(1100, 720)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowSystemMenuHint)

        # ------------------------------------------------------------
        #  Cale sigură către icon (funcționează și în .exe)
        # ------------------------------------------------------------
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS  # folder temporar PyInstaller
        else:
            base_path = os.path.abspath(".")

        icon_path = os.path.join(base_path, "icons", "tray_icon.ico")
        self.setWindowIcon(QtGui.QIcon(icon_path))
        QtWidgets.QApplication.setWindowIcon(QtGui.QIcon(icon_path))

        # ======================================
        #              STIL GENERAL
        # ======================================
        self.setStyleSheet("""
            QMainWindow {
                background-color: #101922;
                color: #E0E0E0;
                font-family: 'Segoe UI';
            }

            /* ===== MENIU SUS ===== */
            QMenuBar {
                background-color: #13283A;
                color: #FFFFFF;
                font-size: 14px;
                padding: 4px;
            }
            QMenuBar::item:selected {
                background-color: #0E2233;
            }
            QMenu {
                background-color: #13283A;
                color: #E0E0E0;
                border: 1px solid #0A1A25;
            }
            QMenu::item:selected {
                background-color: #00A8FF;
                color: #000;
            }

            /* ===== FOOTER ===== */
            QFrame#footerFrame {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0E1620, stop:0.5 #13283A, stop:1 #0E1620
                );
                border-top: 1px solid #102A3D;
            }

            /* ===== QMESSAGEBOX + QDIALOG ===== */
            QMessageBox {
                background-color: #101922;
                color: #E0E0E0;
                font-family: 'Segoe UI';
                font-size: 13px;
            }
            QMessageBox QLabel {
                color: #E0E0E0;
                font-size: 13px;
            }
            QMessageBox QPushButton {
                background-color: #1B3144;
                color: #E0E0E0;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: 600;
            }
            QMessageBox QPushButton:hover {
                background-color: #00A8FF;
                color: #000;
            }

            QDialog {
                background-color: #101922;
                color: #E0E0E0;
                font-family: 'Segoe UI';
                font-size: 13px;
            }
            QDialog QPushButton {
                background-color: #1B3144;
                color: #E0E0E0;
                border-radius: 6px;
                padding: 6px 16px;
            }
            QDialog QPushButton:hover {
                background-color: #00A8FF;
                color: #000;
            }

            QLineEdit {
                background-color: #0F1A26;
                color: #E0E0E0;
                border: 1px solid #1E3448;
                border-radius: 4px;
                padding: 4px 6px;
            }
            QLineEdit:focus {
                border: 1px solid #00A8FF;
            }
        """)

        # ======================================
        #           LAYOUT PRINCIPAL
        # ======================================
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ======================================
        #       BARĂ DE TITLU PERSONALIZATĂ
        # ======================================
        self.title_bar = QtWidgets.QFrame()
        self.title_bar.setFixedHeight(38)
        self.title_bar.setStyleSheet("""
            QFrame {
                background-color: qlineargradient(
                    spread:pad, x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1B2E42, stop:1 #0E1620
                );
                border-bottom: 1px solid #0E2638;
            }
            QPushButton {
                background: transparent;
                color: #E0E0E0;
                font-size: 15px;
                border: none;
            }
            QPushButton:hover {
                color: #00A8FF;
            }
            QPushButton#closeBtn:hover {
                color: #FF4C4C;
            }
        """)
        title_layout = QtWidgets.QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(10, 0, 10, 0)
        title_layout.setSpacing(6)

        # --- ICON din tray_icon.ico (nu Logobara.png) ---
        logo_label = QtWidgets.QLabel()
        try:
            logo_pix = QtGui.QPixmap(icon_path).scaledToHeight(20, QtCore.Qt.SmoothTransformation)
            if not logo_pix.isNull():
                logo_label.setPixmap(logo_pix)
        except Exception:
            pass
        title_layout.addWidget(logo_label)

        # --- TITLU ---
        self.title_label = QtWidgets.QLabel("VisionPro IPTV")
        self.title_label.setStyleSheet("color: #00A8FF; font-size: 14px; font-weight: bold;")
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()

        # --- STARE LICENȚĂ (Trial / Înregistrat / Neactivat) — click deschide activarea ---
        self.license_label = QtWidgets.QLabel()
        self.license_label.setCursor(QtCore.Qt.PointingHandCursor)
        self.license_label.setToolTip(self.tr("Click to activate or buy the lifetime license"))
        self.license_label.mousePressEvent = lambda event: self.open_activation_dialog()
        title_layout.addWidget(self.license_label)
        title_layout.addSpacing(12)
        self._license_timer = QtCore.QTimer(self)
        self._license_timer.setInterval(60000)
        self._license_timer.timeout.connect(self.refresh_license_status)
        self._license_timer.start()
        self.refresh_license_status()

        # --- BUTOANE ---
        btn_min = QtWidgets.QPushButton("—")
        btn_min.setFixedSize(28, 22)
        btn_min.clicked.connect(self.showMinimized)

        self.btn_max = QtWidgets.QPushButton("▢")
        self.btn_max.setFixedSize(28, 22)
        self.btn_max.clicked.connect(self.toggle_max_restore)

        btn_close = QtWidgets.QPushButton("✕")
        btn_close.setObjectName("closeBtn")
        btn_close.setFixedSize(28, 22)
        btn_close.clicked.connect(self.hide_to_tray)

        title_layout.addWidget(btn_min)
        title_layout.addWidget(self.btn_max)
        title_layout.addWidget(btn_close)

        # 🔹 adăugăm bara de titlu în layout, prima
        main_layout.addWidget(self.title_bar)

        # ======================================
        #           MENIU SUB TITLU
        # ======================================
        # ascundem menubar-ul nativ ca să nu stea deasupra
        try:
            self.menuBar().hide()
        except Exception:
            pass

        # folosim un QMenuBar ca widget în layout (sub titlu)
        self.menu_bar = QtWidgets.QMenuBar()
        self.menu_bar.setStyleSheet("""
            QMenuBar {
                background-color: #13283A;
                color: #FFFFFF;
                font-size: 14px;
                padding: 4px;
                border-bottom: 1px solid #0E2638;
            }
            QMenuBar::item:selected {
                background-color: #0E2233;
            }
            QMenu {
                background-color: #13283A;
                color: #E0E0E0;
                border: 1px solid #0A1A25;
            }
            QMenu::item:selected {
                background-color: #00A8FF;
                color: #000;
            }
        """)

        # --- Logo + Titlu în meniu (aici rămâne Logobara.png) ---
        logo_action = QtWidgets.QAction(QtGui.QIcon("icons/Logobara.png"), "VisionPro IPTV", self)
        logo_action.setEnabled(False)
        self.menu_bar.addAction(logo_action)

        # --- Meniuri principale ---
        file_menu = self.menu_bar.addMenu(self.tr("File"))
        settings_menu = self.menu_bar.addMenu(self.tr("Settings"))
        help_menu = self.menu_bar.addMenu(self.tr("Help"))

        exit_action = QtWidgets.QAction("Exit", self)
        exit_action.triggered.connect(lambda: QtWidgets.QApplication.instance().exit_app())
        file_menu.addAction(exit_action)

        open_settings_action = QtWidgets.QAction(self.tr("Preferences"), self)
        open_settings_action.triggered.connect(self.open_settings_dialog)
        settings_menu.addAction(open_settings_action)

        lang_menu = settings_menu.addMenu(self.tr("Language"))
        lang_en = QtWidgets.QAction("English", self)
        lang_ro = QtWidgets.QAction("Română", self)
        lang_en.triggered.connect(lambda: self.set_language("en"))
        lang_ro.triggered.connect(lambda: self.set_language("ro"))
        lang_menu.addAction(lang_en)
        lang_menu.addAction(lang_ro)

        about_action = QtWidgets.QAction(self.tr("About VisionPro IPTV"), self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        activate_action = QtWidgets.QAction(f"🔑 {self.tr('Activate license...')}", self)
        activate_action.triggered.connect(self.open_activation_dialog)
        help_menu.addAction(activate_action)

        # 🔹 adăugăm menubar-ul în layout, imediat sub titlu
        main_layout.addWidget(self.menu_bar)

        # ======================================
        #          TOOLBAR IPTV
        # ======================================
        toolbar_frame = QtWidgets.QFrame()
        toolbar_frame.setStyleSheet("""
            QFrame {
                background-color: #101E2C;
                border-bottom: 1px solid #0E2638;
            }
            QPushButton {
                background-color: #1B3144;
                color: #E0E0E0;
                font-size: 13px;
                padding: 6px 14px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #00A8FF;
                color: #000;
            }
        """)
        toolbar_layout = QtWidgets.QGridLayout(toolbar_frame)
        toolbar_layout.setContentsMargins(10, 6, 10, 6)
        toolbar_layout.setSpacing(12)

        btn_load = QtWidgets.QPushButton("📂 Load Playlist")
        btn_append = QtWidgets.QPushButton("➕ Add Playlist")
        self.btn_add_url = QtWidgets.QPushButton("➕ Add URL")
        self.btn_save_playlist = QtWidgets.QPushButton("💾 Save Playlist")
        self.btn_clear = QtWidgets.QPushButton("🧹 Clear")
        btn_refresh = QtWidgets.QPushButton("🔄 Refresh")
        btn_fullscreen = QtWidgets.QPushButton("⛶ Fullscreen")
        btn_rec_start = QtWidgets.QPushButton("⏺ Start Rec")
        btn_rec_stop = QtWidgets.QPushButton("⏹ Stop Rec")

        self.toolbar_buttons = [(btn_load, '📂', 'Load Playlist'), (btn_append, '➕', 'Add Playlist'),
            (btn_refresh, '🔄', 'Refresh'), (btn_fullscreen, '⛶', 'Fullscreen'),
            (btn_rec_start, '⏺', 'Start Rec'), (btn_rec_stop, '⏹', 'Stop Rec')]
        btn_load.clicked.connect(self.load_playlist_action)
        btn_append.clicked.connect(self.append_playlist_action)
        self.btn_add_url.clicked.connect(self.add_url_action)
        self.btn_save_playlist.clicked.connect(self.save_playlist_action)
        self.btn_clear.clicked.connect(self.clear_playlist_action)
        btn_refresh.clicked.connect(self.refresh_playlist_action)
        btn_fullscreen.clicked.connect(self.fullscreen_action)
        btn_rec_start.clicked.connect(self.record_start_action)
        btn_rec_stop.clicked.connect(self.record_stop_action)

        self._toolbar_layout = toolbar_layout
        self._toolbar_widgets = [btn_load, btn_append, self.btn_add_url,
            self.btn_save_playlist, self.btn_clear, btn_refresh, btn_fullscreen,
            btn_rec_start, btn_rec_stop]
        self._toolbar_columns = 0
        self._layout_toolbar()
        main_layout.addWidget(toolbar_frame)

        # ======================================
        #             CONȚINUT IPTV
        # ======================================
        self.iptv_tab = VisionIPTVTab(self)
        main_layout.addWidget(self.iptv_tab, 1)
        
        # Conectăm bara globală de control la instanța IPTV
        self.iptv_tab_ref = self.iptv_tab

        # ======================================
        #             FOOTER BAR
        # ======================================
        self.footer = QtWidgets.QFrame()
        self.footer.setObjectName("footerFrame")
        footer_layout = QtWidgets.QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(0, 6, 0, 6)

        self.footer_text = QtWidgets.QLabel("VisionPro IPTV  •  Live TV workspace")
        self.footer_text.setAlignment(QtCore.Qt.AlignCenter)
        self.footer_text.setStyleSheet("color: #00A8FF; font-size: 14px; font-weight: 600;")

        footer_layout.addStretch()
        footer_layout.addWidget(self.footer_text)
        footer_layout.addStretch()
        main_layout.addWidget(self.footer)

        # ======================================
        #           ANIMAȚII FOOTER (optimizat)
        # ======================================
        # 🔹 Inițializăm variabilele de animație
        self.glow_phase = 0.0
        self.gloss_pos = 0.0
        self.gloss_direction = 1

        # 🔹 Oprire preventivă a oricărui timer vechi
        try:
            if hasattr(self, "timer") and self.timer.isActive():
                self.timer.stop()
                self.timer.deleteLater()
        except Exception:
            pass

        # 🔹 Creăm timerul unic, controlat de fereastra principală
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(200)  # rulare la 5x/sec - suficient pentru glow lin
        self.timer.timeout.connect(self.animate_footer, QtCore.Qt.QueuedConnection)
        # Keep the status bar static; repeated stylesheet changes force repaints.

        # 🔹 Ne asigurăm că se oprește corect la distrugerea ferestrei
        self.destroyed.connect(self.stop_animations_safe)

    # ======================================
    #         FUNCȚII SUPLIMENTARE
    # ======================================
    def toggle_max_restore(self):
        """Comută între maximizare și restaurare."""
        if self.isMaximized():
            self.showNormal()
            self.btn_max.setText("▢")
        else:
            self.showMaximized()
            self.btn_max.setText("🗗")

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule_surface_restore()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.WindowStateChange:
            self._schedule_surface_restore()

    def _schedule_surface_restore(self):
        if hasattr(self, "iptv_tab") and not self.isMinimized():
            QtCore.QTimer.singleShot(0, self.iptv_tab.restore_native_panels)
            QtCore.QTimer.singleShot(150, self.iptv_tab.restore_native_panels)

    # ======================================
    #         MINIMIZE TO TRAY LOGIC
    # ======================================
    def init_tray_system(self, icon_path: str):
        """Inițializează tray iconul și meniul contextual (multilingv)."""
        try:
            self.tray_icon = QtWidgets.QSystemTrayIcon(self)
            self.tray_icon.setIcon(QtGui.QIcon(icon_path))
            self.tray_icon.setVisible(True)

            # === Meniu click dreapta ===
            tray_menu = QtWidgets.QMenu()
            action_open = tray_menu.addAction(f"🟢 {self.tr('Open VisionPro IPTV')}")
            action_exit = tray_menu.addAction(f"❌ {self.tr('Exit VisionPro IPTV')}")

            action_open.triggered.connect(self.show_from_tray)
            action_exit.triggered.connect(QtWidgets.QApplication.quit)

            self.tray_icon.setContextMenu(tray_menu)

            # === Click pe icon (stânga / dublu click) ===
            self.tray_icon.activated.connect(self._on_tray_activated)

        except Exception as e:
            print(f"[⚠️] init_tray_system error: {e}")

    def hide_to_tray(self):
        """Ascunde aplicația în tray (fără să o închidă)."""
        try:
            self.hide()
            if hasattr(self, "tray_icon"):
                self.tray_icon.showMessage(
                    "VisionPro IPTV",
                    f"🔹 {self.tr('The app is still running in the system tray.')}\n"
                    f"{self.tr('Right-click the tray icon to open or exit.')}",
                    QtWidgets.QSystemTrayIcon.Information,
                    3000
                )
        except Exception as e:
            print(f"[⚠️] hide_to_tray error: {e}")

    def show_from_tray(self):
        """Afișează aplicația maximizată și activă."""
        try:
            self.showMaximized()
            self.activateWindow()
            self.raise_()
        except Exception as e:
            print(f"[⚠️] show_from_tray error: {e}")

    def _on_tray_activated(self, reason):
        """Click pe icon → stânga/dublu-click = open, dreapta = meniu."""
        if reason in (QtWidgets.QSystemTrayIcon.Trigger, QtWidgets.QSystemTrayIcon.DoubleClick):
            self.show_from_tray()

    def closeEvent(self, event):
        """Pe ✕ sau Alt+F4 → minimize în tray."""
        event.ignore()
        self.hide_to_tray()

    # ======================================
    #             FUNCȚII BUTOANE
    # ======================================
    def stop_animations_safe(self):
        """Oprește toate animațiile active (footer + info) pentru stabilitate."""
        try:
            if hasattr(self, "timer") and self.timer.isActive():
                self.timer.stop()
                self.timer.deleteLater()

            if hasattr(self, "_info_anim") and self._info_anim.state() == QtCore.QAbstractAnimation.Running:
                self._info_anim.stop()

        except Exception as e:
            print(f"[⚠️] stop_animations_safe() error: {e}")

    def load_playlist_action(self):
        """Deschide un playlist nou (înlocuiește lista curentă)."""
        try:
            self.iptv_tab.load_playlist()
        except Exception as e:
            print(f"[⚠️] Load playlist error: {e}")

    def append_playlist_action(self):
        """Adaugă un playlist suplimentar (fără a șterge lista curentă)."""
        try:
            self.iptv_tab.append_playlist()
        except Exception as e:
            print(f"[⚠️] Append playlist error: {e}")

    def refresh_playlist_action(self):
        """Reîncarcă playlistul curent din fișierul memorat."""
        try:
            self.iptv_tab.refresh_playlist()
        except Exception as e:
            print(f"[⚠️] Refresh error: {e}")

    def record_start_action(self):
        """Pornește înregistrarea video curentă."""
        try:
            self.iptv_tab.start_recording()
        except Exception as e:
            print(f"[⚠️] Record start error: {e}")

    def record_stop_action(self):
        """Oprește înregistrarea video curentă."""
        try:
            self.iptv_tab.stop_recording()
        except Exception as e:
            print(f"[⚠️] Record stop error: {e}")

    def fullscreen_action(self):
        """Comută modul full-screen pentru fereastra video."""
        try:
            self.iptv_tab.toggle_fullscreen()
        except Exception as e:
            print(f"[⚠️] Fullscreen error: {e}")

    def add_url_action(self):
        """Adaugă manual un stream URL nou."""
        try:
            self.iptv_tab.add_url()
        except Exception as e:
            print(f"[⚠️] Add URL error: {e}")

    def save_playlist_action(self):
        """Salvează playlistul curent în format M3U."""
        try:
            self.iptv_tab.save_playlist()
        except Exception as e:
            print(f"[⚠️] Save playlist error: {e}")

    def clear_playlist_action(self):
        """Curăță complet lista de canale."""
        try:
            self.iptv_tab.clear_playlist()
        except Exception as e:
            print(f"[⚠️] Clear playlist error: {e}")

    # ======================================
    #     FUNCȚII BUTOANE MEDIA GLOBALE
    # ======================================

    def play_action(self):
        """Pornește redarea canalului curent."""
        try:
            self.iptv_tab.play_current()
        except Exception as e:
            print(f"[⚠️] Play action error: {e}")

    def pause_action(self):
        """Pauză / reluare redare."""
        try:
            self.iptv_tab.toggle_pause()
        except Exception as e:
            print(f"[⚠️] Pause action error: {e}")

    def stop_action(self):
        """Oprește complet redarea."""
        try:
            self.iptv_tab.player.stop()
        except Exception as e:
            print(f"[⚠️] Stop action error: {e}")

    def mute_action(self):
        """Activează / dezactivează sunetul."""
        try:
            self.iptv_tab.toggle_mute()
        except Exception as e:
            print(f"[⚠️] Mute action error: {e}")

    def fullscreen_action(self):
        """Comută modul Fullscreen."""
        try:
            self.iptv_tab.toggle_fullscreen()
        except Exception as e:
            print(f"[⚠️] Fullscreen action error: {e}")

    def volume_action(self, value):
        """Schimbă volumul redării."""
        try:
            self.iptv_tab.set_volume(value)
        except Exception as e:
            print(f"[⚠️] Volume action error: {e}")

    # ======================================
    #          FOOTER ANIMAȚIE
    # ======================================
    def animate_footer(self):
        self.glow_phase += 0.08
        glow = int(128 + 127 * abs(math.sin(self.glow_phase)))
        base_color = f"rgb(0, {glow}, 255)"
        self.gloss_pos += 0.02 * self.gloss_direction
        if self.gloss_pos >= 1.0 or self.gloss_pos <= 0.0:
            self.gloss_direction *= -1
        p1 = max(0.0, min(1.0, self.gloss_pos - 0.1))
        p2 = max(0.0, min(1.0, self.gloss_pos))
        p3 = max(0.0, min(1.0, self.gloss_pos + 0.1))
        grad = f"""
            QLinearGradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(0,0,0,0),
                stop:{p1:.2f} rgba(255,255,255,0),
                stop:{p2:.2f} rgba(255,255,255,0.7),
                stop:{p3:.2f} rgba(255,255,255,0),
                stop:1 rgba(0,0,0,0))
        """
        self.footer_text.setStyleSheet(f"""
            color: {base_color};
            font-size: 14px;
            font-weight: 600;
            background: {grad};
            background-clip: text;
        """)

    # ======================================
    #          SETTINGS DIALOG
    # ======================================
    def open_settings_dialog(self):
        preferences(self)

    def _layout_toolbar(self):
        if not hasattr(self, '_toolbar_widgets'):
            return
        columns = 9 if self.width() >= 1450 else 5
        if columns == self._toolbar_columns:
            return
        self._toolbar_columns = columns
        for button in self._toolbar_widgets:
            self._toolbar_layout.removeWidget(button)
        for column in range(9):
            self._toolbar_layout.setColumnStretch(column, 0)
        for index, button in enumerate(self._toolbar_widgets):
            self._toolbar_layout.addWidget(button, index // columns, index % columns)
        for column in range(columns):
            self._toolbar_layout.setColumnStretch(column, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_toolbar()

    def exit_app(self):
        QtWidgets.QApplication.instance().exit_app()

    def apply_language(self, lang_code):
        """Încarcă traducerile JSON și actualizează instant interfața (fără restart)."""
        import json
        path = f"translations/{lang_code}.json"
        self._current_lang = lang_code
        self.translations = {}

        # --- Verificăm existența fișierului de limbă ---
        if not os.path.exists(path):
            print(f"[⚠️] Fișier de limbă lipsă: {path}")
            self.tr = lambda text: text
            return

        # --- Citim fișierul JSON ---
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.translations = json.load(f)
        except Exception as e:
            print(f"[❌] Eroare la citirea fișierului de limbă {lang_code}: {e}")
            self.tr = lambda text: text
            return

        # --- Funcție de traducere locală ---
        self.tr = Translator(self.translations)

        for action, key in getattr(QtWidgets.QApplication.instance(), 'tray_actions', []):
            action.setText(self.tr(key))
        print(f"[🌍] Limbă activă: {lang_code.upper()} ({len(self.translations)} texte încărcate din JSON)")

        # --- Retraducem tot UI-ul instant ---
        try:
            # Retraduce meniurile principale, toolbarul și footerul
            self.retranslate_ui(self.tr)

            # Retraduce tab-ul principal IPTV (butoane, playlist, context menu)
            if hasattr(self, "iptv_tab"):
                self.iptv_tab.retranslate_ui(self.tr)
                self.iptv_tab.retranslate_context_menu(self.tr)

        except Exception as e:
            print(f"[⚠️] Retraducerea UI a eșuat: {e}")

    def set_language(self, lang_code):
        """Schimbă instant limba și salvează alegerea în config (fără restart)."""
        cfg = QtCore.QSettings(str(CONFIG_PATH), QtCore.QSettings.IniFormat)
        cfg.setValue("Settings/language", lang_code)
        cfg.sync()

        # Aplică traducerea imediat
        self.apply_language(lang_code)

        # Mesaj de confirmare traductibil
        try:
            QtWidgets.QMessageBox.information(
                self,
                "VisionPro IPTV",
                f"{self.tr('Language changed to')} {lang_code.upper()}."
            )
        except Exception as e:
            print(f"[⚠️] Eroare la mesajul de limbă: {e}")
      
    # ======================================
    #           RETRADUCERE UI
    # ======================================
    def retranslate_ui(self, tr):
        """Retraduce toate textele, meniurile și butoanele principale."""
        try:
            # === Bara de meniu ===
            menubar = self.menu_bar
            menubar.clear()

            logo_action = QtWidgets.QAction(QtGui.QIcon("icons/Logobara.png"), "VisionPro IPTV", self)
            logo_action.setEnabled(False)
            menubar.addAction(logo_action)

            # --- Meniuri principale ---
            file_menu = menubar.addMenu(tr("File"))
            settings_menu = menubar.addMenu(tr("Settings"))
            help_menu = menubar.addMenu(tr("Help"))

            # --- File ---
            exit_action = QtWidgets.QAction(tr("Exit"), self)
            exit_action.triggered.connect(lambda: QtWidgets.QApplication.instance().exit_app())
            file_menu.addAction(exit_action)

            # --- Settings ---
            open_settings_action = QtWidgets.QAction(tr("Preferences"), self)
            open_settings_action.triggered.connect(self.open_settings_dialog)
            settings_menu.addAction(open_settings_action)

            lang_menu = settings_menu.addMenu(tr("Language"))
            lang_en = QtWidgets.QAction(tr("English"), self)
            lang_ro = QtWidgets.QAction(tr("Română"), self)
            lang_en.triggered.connect(lambda: self.set_language("en"))
            lang_ro.triggered.connect(lambda: self.set_language("ro"))
            lang_menu.addAction(lang_en)
            lang_menu.addAction(lang_ro)

            # --- Help ---
            about_action = QtWidgets.QAction(tr("About VisionPro IPTV"), self)
            about_action.triggered.connect(self.show_about)
            help_menu.addAction(about_action)

            activate_action = QtWidgets.QAction(f"🔑 {tr('Activate license...')}", self)
            activate_action.triggered.connect(self.open_activation_dialog)
            help_menu.addAction(activate_action)

            # --- Donate ---
            donate_action = QtWidgets.QAction(f"💙 {tr('Donate 5 EUR')}", self)
            donate_action.triggered.connect(self.donate)
            help_menu.addAction(donate_action)

            # === Toolbar Buttons ===
            if hasattr(self, "btn_add_url"):
                self.btn_add_url.setText(f"➕ {tr('Add URL')}")
            if hasattr(self, "btn_save_playlist"):
                self.btn_save_playlist.setText(f"💾 {tr('Save Playlist')}")
            if hasattr(self, "btn_clear"):
                self.btn_clear.setText(f"🧹 {tr('Clear')}")

            for button, icon, key in self.toolbar_buttons:
                button.setText(f'{icon} {tr(key)}')

            if hasattr(self, "license_label"):
                self.refresh_license_status()

            # === Footer ===
            if hasattr(self, "footer_text"):
                self.footer_text.setText(tr("VisionPro IPTV  •  Live TV workspace"))

            # === Retraducere tab IPTV ===
            if hasattr(self, "iptv_tab"):
                try:
                    self.iptv_tab.retranslate_ui(tr)
                    self.iptv_tab.retranslate_context_menu(tr)
                except Exception as e:
                    print(f"[⚠️] Eroare la retraducerea tabului IPTV: {e}")

        except Exception as e:
            print(f"[⚠️] Eroare la retranslate_ui() în VisionMainWindow: {e}")
      
    # ======================================
    #             ABOUT + DONATE
    # ======================================
    def show_about(self):
        show_about(self)

    # ======================================
    #             LICENȚĂ / ACTIVARE
    # ======================================
    def refresh_license_status(self):
        """Actualizează eticheta din bara de titlu și titlul ferestrei după starea licenței."""
        try:
            text = licensing.status_text(self.tr)
            registered = licensing.status()['kind'] == 'licensed'
            self.license_label.setText(('✔ ' if registered else '') + text)
            self.license_label.setStyleSheet(f"color: {licensing.status_color()}; font-size: 12px; font-weight: bold; "
                                             "padding: 2px 10px; border: 1px solid #1E3A52; border-radius: 9px; background: #0E2233;")
            # Registered: plain status text, no click target; otherwise click opens activation.
            self.license_label.setCursor(QtCore.Qt.ArrowCursor if registered else QtCore.Qt.PointingHandCursor)
            self.license_label.setToolTip(self.tr("Lifetime license active on this computer") if registered
                                          else self.tr("Click to activate or buy the lifetime license"))
            self.license_label.mousePressEvent = (lambda event: None) if registered else (lambda event: self.open_activation_dialog())
            self.setWindowTitle(f"VisionPro IPTV — {text}")
        except Exception as e:
            print(f"[⚠️] refresh_license_status(): {e}")

    def open_activation_dialog(self):
        licensing.activation_dialog(self)
        self.refresh_license_status()

    def donate(self):
        """Deschide pagina PayPal pentru donație 5 EUR."""
        import webbrowser
        try:
            url = "https://www.paypal.com/donate?business=AleXx626@gmx.de&currency_code=EUR&amount=5"
            webbrowser.open(url)
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Error") if hasattr(self, "tr") else "Error",
                f"{self.tr('Could not open donate page:') if hasattr(self, 'tr') else 'Could not open donate page:'}\n{e}"
            )
