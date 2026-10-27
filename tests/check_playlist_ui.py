"""Isolated playlist interaction regression check (no network or user settings)."""
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
scratch = tempfile.TemporaryDirectory()
os.environ['APPDATA'] = scratch.name
sys.modules['vlc'] = MagicMock()
from PyQt5 import QtCore, QtWidgets, QtTest
from tabs.vision_iptv_core import VisionIPTVTab

app = QtWidgets.QApplication([])
tab = VisionIPTVTab()
tab.resize(1000, 600)
tab.show()
started = time.perf_counter()
tab._load_playlist_file(str(Path(__file__).resolve().parents[1] / '6304cannel.m3u'))
tree = tab.playlist_tree
urls = []
iterator = QtWidgets.QTreeWidgetItemIterator(tree)
while iterator.value():
    url = iterator.value().data(0, QtCore.Qt.UserRole)
    if url:
        urls.append(url)
    iterator += 1
assert len(urls) == len(set(urls)), 'Duplicate channel URLs in loaded playlist'
print('Unique channels:', len(urls))
tree.expandAll()
app.processEvents()
bar = tree.verticalScrollBar()
assert bar.maximum() > 0
bar.setValue(bar.maximum() // 2)
app.processEvents()
assert bar.value() > 0
item = tree.itemAt(60, 60)
assert item is not None
QtTest.QTest.mouseClick(tree.viewport(), QtCore.Qt.LeftButton, pos=tree.visualItemRect(item).center())
assert tree.currentItem() == item
tab.search_box.setText('BBC')
QtTest.QTest.qWait(250)
assert 'Found' in tab.playlist_status.text()
tab.search_box.clear()
QtTest.QTest.qWait(250)
group = tree.topLevelItem(0)
channel = group.child(0)
assert channel is not None
tree.setCurrentItem(channel)
tab.play_current()
assert tab.current_url == channel.data(0, QtCore.Qt.UserRole)
print('PASS: large playlist load, scroll, click, debounced search, selected-channel Play')
print('Elapsed: %.2fs' % (time.perf_counter() - started))
tab.hide()
