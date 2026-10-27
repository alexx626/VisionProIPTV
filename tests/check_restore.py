"""Regression: one application, restore cycles, search/favorites and config retention."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
scratch = tempfile.TemporaryDirectory()
os.environ['APPDATA'] = scratch.name
sys.modules['vlc'] = MagicMock()
from PyQt5 import QtCore, QtWidgets, QtTest
from main import VisionApp

app = VisionApp([], initialize=False)
assert QtWidgets.QApplication.instance() is app
app.initialize()
window = app.main_window
tab = window.iptv_tab
app.processEvents()
assert tab.height() > window.height() * 0.65
settings = QtCore.QSettings(str(app.config_path), QtCore.QSettings.IniFormat)
settings.setValue('Favorites/list', 'Test::https://example.test/channel')
settings.setValue('LastPlaylist/path', 'keep-me.m3u')
tab.slider_volume.setValue(37)
settings.sync()
tab._load_playlist_file(str(Path(__file__).resolve().parents[1] / '6304cannel.m3u'))
tab.playlist_tree.expandAll()
for _ in range(3):
    window.showMinimized()
    QtTest.QTest.qWait(50)
    window.showMaximized()
    QtTest.QTest.qWait(200)
    bar = tab.playlist_tree.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    assert bar.value() > 0
    window.hide()
    window.showNormal()
    QtTest.QTest.qWait(200)
app.save_window_state()
settings.sync()
assert Path(settings.value('LastPlaylist/path')).name == '6304cannel.m3u'
assert settings.value('Settings/volume', type=int) == 37
assert settings.value('Favorites/list').startswith('Test::')
tab.search_box.setText('BBC')
QtTest.QTest.qWait(250)
tab.btn_fav.setChecked(True)
tab.toggle_favorites_view()
assert 'Found 0' in tab.playlist_status.text()
tab.btn_fav.setChecked(False)
tab.toggle_favorites_view()
assert 'Found 0' not in tab.playlist_status.text()
for i in range(tab.playlist_tree.topLevelItemCount()):
    group = tab.playlist_tree.topLevelItem(i)
    for j in range(group.childCount()):
        child = group.child(j)
        if not child.isHidden():
            assert 'bbc' in child.text(0).lower()
assert QtWidgets.QApplication.instance() is app
print('PASS: single QApplication, 3 minimize/restore + hide/show cycles, retained settings, combined filters')
app.tray_icon.hide()
window.hide()
