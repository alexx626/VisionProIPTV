"""Session/translation/HUD regression, without network or user configuration."""
import os
import sys
import tempfile
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
scratch = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
os.environ['APPDATA'] = scratch.name
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.modules['vlc'] = MagicMock()
from PyQt5 import QtCore, QtWidgets, QtTest
from main import VisionApp
from player_services import settings, DATA_DIR
from tabs.vision_iptv_core import VisionIPTVTab

app = VisionApp([], initialize=False)
app.initialize()
w = app.main_window
t = w.iptv_tab
playlist = Path(scratch.name) / 'input.m3u'
playlist.write_text('#EXTM3U\n#EXTINF:-1 group-title="News",Alpha\nhttps://example.test/a\n'
                    '#EXTINF:-1 group-title="News",Duplicate\nhttps://example.test/a\n'
                    '#EXTINF:-1 group-title="News",Beta\nhttps://example.test/b\n', encoding='utf-8')
t._load_playlist_file(str(playlist))
with patch.object(QtWidgets.QFileDialog, 'getOpenFileName', return_value=(str(playlist), '')):
    t.append_playlist()
assert sum(t.playlist_tree.topLevelItem(i).childCount() for i in range(t.playlist_tree.topLevelItemCount())) == 2
t.tree_helper.add_channel('Manual', 'Gamma', 'https://example.test/c')
t.current_url = 'https://example.test/c'
t.slider_volume.setValue(37)
t.player.audio_get_mute.return_value = True
t.search_box.setText('Gamma')
QtTest.QTest.qWait(220)
t.save_session()
playlist.unlink()  # The session must survive missing/moved source files.
restored = VisionIPTVTab()
app.processEvents()
assert restored.current_url == 'https://example.test/c'
assert restored.search_box.text() == 'Gamma'
assert restored.slider_volume.value() == 37
restored.player.audio_set_mute.assert_called_with(True)
assert sum(restored.playlist_tree.topLevelItem(i).childCount() for i in range(restored.playlist_tree.topLevelItemCount())) == 3
for language in ('ro', 'en', 'ro', 'en'):
    w.apply_language(language)
    assert w.toolbar_buttons[0][0].text().endswith(w.tr('Load Playlist'))
    assert t.search_box.placeholderText() == w.tr('Search channel...')
w.apply_language('ro')
assert w.tr('🔍 Found 123 results') == '🔍 123 rezultate'
assert 'Gamma' in w.tr('❌ Stream error: Gamma')
t.toggle_fullscreen()
fs = t._fs_win
QtTest.QTest.qWait(2300)
assert not fs.panel.isVisible(), 'HUD did not auto-hide after two seconds'
fs.show_hud()
assert fs.panel.isVisible()
t.toggle_fullscreen()
app.processEvents()
assert t.video_frame.parent() == t.video_container
assert not t.playlist_tree.testAttribute(QtCore.Qt.WA_NativeWindow)
t.clear_playlist()
t.save_session()
assert json.loads((DATA_DIR / 'session.json').read_text(encoding='utf-8'))['channels'] == []
print('PASS: dedup append, missing-source session restore, mute/volume/search, RO/EN round-trip, HUD timeout and reparent, clear persistence')
app.tray_icon.hide()
w.hide()
