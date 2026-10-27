# -*- coding: utf-8 -*-
import os
import sys
import configparser
from pathlib import Path
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QTranslator, QLocale
from player_services import settings, flag, VERSION
 
APP_NAME = "VisionPro IPTV"
APP_VERSION = VERSION
 
 
class VisionApp(QtWidgets.QApplication):
    def __init__(self, argv, initialize=True):
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_DontCreateNativeWidgetSiblings, True)
        super().__init__(argv)
        self.setApplicationName(APP_NAME)
        self.setQuitOnLastWindowClosed(False)
        if initialize:
            self.initialize()

    def initialize(self):
 
        # ------------------------------------------------------------
        #  Cale sigură către resurse (icoane, traduceri, etc.)
        #  Funcționează atât în Python, cât și în build .exe
        # ------------------------------------------------------------
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS  # folder temporar PyInstaller
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
 
        # Schimbăm directorul de lucru global (important pentru traduceri și teme)
        os.chdir(base_path)
 
        # ------------------------------------------------------------
        #  Setăm iconul aplicației (titlu + taskbar)
        # ------------------------------------------------------------
        icon_path = os.path.join(base_path, "icons", "tray_icon.ico")
        app_icon = QtGui.QIcon(icon_path)
 
        if os.path.exists(icon_path):
            app_icon = QtGui.QIcon(icon_path)
            self.setWindowIcon(app_icon)
            QtWidgets.QApplication.setWindowIcon(app_icon)
        else:
            print(f"[⚠️] Icon missing: {icon_path}")
 
        # ------------------------------------------------------------
        #  Config global în AppData\Roaming\VisionProIPTV
        # ------------------------------------------------------------
        config_dir = Path(os.getenv("APPDATA")) / "VisionProIPTV"
        config_dir.mkdir(exist_ok=True)
        self.config_path = config_dir / "config.ini"
 
        # ====== Încarcă tema ======
        theme_path = os.path.join("gui", "vision_theme.qss")
        if os.path.exists(theme_path):
            with open(theme_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
 
        # ====== Încarcă starea anterioară ======
        self.settings = self.load_window_state()
 
        # ====== Creează fereastra principală ======
        from vision_main import VisionMainWindow
        self.main_window = VisionMainWindow()
 
        # ------------------------------------------------------------
        #  Aplică limba salvată anterior din AppData
        # ------------------------------------------------------------
        cfg_lang = QtCore.QSettings(str(self.config_path), QtCore.QSettings.IniFormat)
        lang = cfg_lang.value("Settings/language", "en")
        try:
            self.main_window.apply_language(lang)
        except Exception as e:
            print(f"[⚠️] Eroare la aplicarea limbii inițiale: {e}")
 
        # ------------------------------------------------------------
        #  Restaurează poziția și dimensiunea anterioară
        # ------------------------------------------------------------
        cfg = settings()
        if flag('Settings/restore_geometry', True):
            geometry = cfg.value('Window/qt_geometry')
            if isinstance(geometry, QtCore.QByteArray):
                self.main_window.restoreGeometry(geometry)
            else:
                try:
                    values = [int(v) for v in str(cfg.value('Window/geometry', '')).strip('"').split(',')]
                    if len(values) == 4:
                        self.main_window.setGeometry(*values)
                except ValueError:
                    pass
        # A disconnected monitor must not make the window inaccessible.
        if not any(screen.availableGeometry().intersects(self.main_window.frameGeometry()) for screen in self.screens()):
            self.main_window.move(self.primaryScreen().availableGeometry().topLeft() + QtCore.QPoint(50, 50))
        if not flag('Settings/start_minimized'):
            self.show_main_window()

        # ------------------------------------------------------------
        #  Tray Icon + Meniu contextual
        # ------------------------------------------------------------
        self.tray_icon = QtWidgets.QSystemTrayIcon(app_icon, self)
        self.tray_icon.setToolTip(f"{APP_NAME} v{APP_VERSION}")
 
        tray_menu = QtWidgets.QMenu()
        action_show = tray_menu.addAction(self.main_window.tr("Open VisionPro IPTV"))
        tray_menu.addSeparator()
        action_save = tray_menu.addAction(self.main_window.tr("Save Config"))
        tray_menu.addSeparator()
        action_exit = tray_menu.addAction(self.main_window.tr("Exit"))
 
        action_show.triggered.connect(self.show_main_window)
        action_save.triggered.connect(self.save_config_now)
        action_exit.triggered.connect(self.exit_app)
 
        self.tray_actions = [(action_show, "Open VisionPro IPTV"), (action_save, "Save Config"), (action_exit, "Exit")]
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        self.tray_icon.activated.connect(self.on_tray_activated)
 
        # ------------------------------------------------------------
        #  Evenimente pentru salvarea stării ferestrei
        # ------------------------------------------------------------
        self.main_window.closeEvent = self.on_close_event
        self._save_timer = QtCore.QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self.save_window_state)
        self.main_window.installEventFilter(self)
        self.aboutToQuit.connect(self.save_window_state)
        self.aboutToQuit.connect(self.main_window.iptv_tab.save_session)

    def eventFilter(self, obj, event):
        if obj is self.main_window and event.type() in (
                QtCore.QEvent.Move, QtCore.QEvent.Resize, QtCore.QEvent.WindowStateChange):
            self._save_timer.start()
        return super().eventFilter(obj, event)
 
    # --------------------------------------------------------
    #  Gestionare click pe icon tray (stânga = toggle, dreapta = meniu)
    # --------------------------------------------------------
    def on_tray_activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.Trigger:  # click stânga
            if self.main_window.isHidden():
                # 🔹 Redeschide mereu MAXIMIZAT
                self.show_main_window()
            else:
                # 🔹 Ascunde aplicația în tray
                self.save_window_state()
                self.main_window.hide()
 
        elif reason == QtWidgets.QSystemTrayIcon.Context:
            pass  # click dreapta -> meniu tray automat
 
    # --------------------------------------------------------
    #  Deschide fereastra principală din tray sau meniu
    # --------------------------------------------------------
    def show_main_window(self):
        if flag('Settings/restore_geometry', True) and flag('Window/maximized', True):
            self.main_window.showMaximized()
        else:
            self.main_window.showNormal()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def exit_app(self):
        tab = self.main_window.iptv_tab
        if tab.recorder.active:
            if not getattr(self, '_waiting_for_recording', False):
                self._waiting_for_recording = True
                tab.recorder.finished.connect(self.exit_app)
                tab.stop_recording()
            return
        tab.save_session()
        self.save_window_state()
        self.tray_icon.hide()
        self.quit()

    def save_config_now(self):
        """Salvează complet config-ul curent în AppData (volum, playlist, limbă, fereastră)."""
        try:
            cfg = QtCore.QSettings(str(self.config_path), QtCore.QSettings.IniFormat)
 
            # --- Limbă ---
            if hasattr(self.main_window, "_current_lang"):
                cfg.setValue("Settings/language", self.main_window._current_lang)
 
            # --- Volum ---
            iptv = getattr(self.main_window, "iptv_tab", None)
            if iptv and hasattr(iptv, "slider_volume"):
                cfg.setValue("Settings/volume", iptv.slider_volume.value())
 
            # --- Playlist curent ---
            if iptv and hasattr(iptv, "_last_playlist_path") and iptv._last_playlist_path:
                cfg.setValue("LastPlaylist/path", iptv._last_playlist_path)
 
            # --- Record dir ---
            if iptv and hasattr(iptv, "record_dir"):
                cfg.setValue("Settings/record_dir", iptv.record_dir)
 
            # --- Geometrie fereastră ---
            self.save_window_state()
            iptv.save_session()
 
            cfg.sync()
            print(f"[💾] Config salvat în: {self.config_path}")
 
            self.tray_icon.showMessage(
                "VisionPro IPTV",
                self.main_window.tr("✅ Config saved successfully!"),
                QtWidgets.QSystemTrayIcon.Information,
                2000
            )
 
        except Exception as e:
            print(f"[⚠️] Eroare la save_config_now(): {e}")
            self.tray_icon.showMessage(
                "VisionPro IPTV",
                f"❌ Save failed: {e}",
                QtWidgets.QSystemTrayIcon.Warning,
                3000
            )
 
    # --------------------------------------------------------
    #  Minimization to tray la închidere
    # --------------------------------------------------------
    def on_close_event(self, event):
        """Interceptăm închiderea ferestrei principale și o trimitem în tray."""
        if not flag('Settings/close_to_tray', True):
            event.ignore()
            self.exit_app()
            return
        event.ignore()
        self.main_window.iptv_tab.save_session()
 
        # 🔹 Salvăm starea ferestrei (maximized / normal)
        try:
            self.save_window_state()
        except Exception as e:
            print(f"[⚠️] Eroare la salvarea stării ferestrei: {e}")
 
        # 🔹 Ascundem fereastra principală
        self.main_window.hide()
 
        # 🔹 Afișăm notificare scurtă în tray
        self.tray_icon.showMessage(
            "VisionPro IPTV",
            self.main_window.tr("Application minimized to tray. Click the blue icon to reopen."),
            QtWidgets.QSystemTrayIcon.Information,
            2000  # durata 2 secunde
        )
 
    def closeEvent(self, event):
        """Închidere completă din fereastra principală (nu minimize to tray)."""
        try:
            if hasattr(self, "iptv_tab") and hasattr(self.iptv_tab, "_vlc_worker"):
                self.iptv_tab.stop_playback()
 
            if hasattr(self.iptv_tab, "_vlc_thread"):
                self.iptv_tab._vlc_thread.quit()
                self.iptv_tab._vlc_thread.wait(1500)
        except Exception as e:
            print(f"[⚠️] closeEvent VLC cleanup: {e}")
 
        event.accept()
 
    # --------------------------------------------------------
    #  Salvare automată starea ferestrei în AppData
    # --------------------------------------------------------
    def save_window_state(self, event=None):
        """Salvează poziția, dimensiunea și starea (maximized) în config.ini."""
        try:
            if self.main_window.isMinimized():
                return
            cfg = QtCore.QSettings(str(self.config_path), QtCore.QSettings.IniFormat)
            geo = self.main_window.normalGeometry()
            cfg.setValue("Window/qt_geometry", self.main_window.saveGeometry())
            cfg.setValue("Window/geometry", f"{geo.x()},{geo.y()},{geo.width()},{geo.height()}")
            cfg.setValue("Window/maximized", str(self.main_window.isMaximized()))
            cfg.sync()
 
        except Exception as e:
            print(f"[⚠️] Eroare la save_window_state(): {e}")
 
    # --------------------------------------------------------
    #  Încărcare starea anterioară din AppData
    # --------------------------------------------------------
    def load_window_state(self):
        cfg = settings()
        return {'geometry': cfg.value('Window/geometry', ''),
                'maximized': str(cfg.value('Window/maximized', 'True'))}

# ============================================================
#  MAIN ENTRY + SINGLE INSTANCE + SPLASH SCREEN
# ============================================================
if __name__ == "__main__":
    from PyQt5.QtNetwork import QLocalServer, QLocalSocket
    # Exactly one QApplication must own every widget and native VLC surface.
    vision_app = VisionApp(sys.argv, initialize=False)
 
    # ------------------------------------------------------------
    #  1️⃣ Verificăm dacă aplicația e deja pornită
    # ------------------------------------------------------------
    server_name = "VisionProIPTV_InstanceLock"
    socket = QLocalSocket()
    socket.connectToServer(server_name)
 
    if socket.waitForConnected(100):
        # deja există o instanță pornită
        print("[⚠️] VisionPro IPTV este deja deschis!")
        msg_box = QtWidgets.QMessageBox()
        msg_box.setIcon(QtWidgets.QMessageBox.Information)
        msg_box.setWindowTitle("VisionPro IPTV")
        msg_box.setText("Aplicația este deja deschisă și rulează în fundal.\n"
                        "Poți accesa fereastra din System Tray.")
        msg_box.exec_()
        sys.exit(0)
    else:
        # nu există altă instanță, creăm una nouă
        server = QLocalServer()
        server.listen(server_name)
 
    # ------------------------------------------------------------
    #  2️⃣ Inițializăm aplicația
    # ------------------------------------------------------------
    app = vision_app
 
    # ------------------------------------------------------------
    #  3️⃣ Detectăm calea pentru splash (compatibil cu PyInstaller)
    # ------------------------------------------------------------
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
 
    splash_path = os.path.join(base_path, "icons", "splash.png")
 
    # ------------------------------------------------------------
    #  4️⃣ Splash Screen (cu imagine validă)
    # ------------------------------------------------------------
    splash_pix = QtGui.QPixmap(splash_path)
    if not splash_pix.isNull():
        splash = QtWidgets.QSplashScreen(
            splash_pix.scaled(800, 600, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation),
            QtCore.Qt.WindowStaysOnTopHint
        )
        splash.showMessage(
            "Initializing VisionPro IPTV...\nThe Future of Streaming Starts Here\nDeveloped by AleXx626",
            QtCore.Qt.AlignBottom | QtCore.Qt.AlignHCenter,
            QtGui.QColor("#00A8FF")
        )
        splash.show()
        QtWidgets.qApp.processEvents()
 
    # ------------------------------------------------------------
    #  5️⃣ Lansare aplicație principală
    # ------------------------------------------------------------
    try:
        vision_app.initialize()
    except (ImportError, OSError, RuntimeError) as exc:
        QtWidgets.QMessageBox.critical(None, APP_NAME,
            "VisionPro IPTV could not start. Install VLC 64-bit and try again.\n"
            "VisionPro IPTV nu a putut porni. Instalează VLC pe 64 de biți.\n\n" + str(exc))
        sys.exit(1)
    if 'splash' in locals():
        splash.finish(vision_app.main_window)
 
    sys.exit(vision_app.exec_())
 
