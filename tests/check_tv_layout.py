"""TV-style channel workspace: sidebar views, categories/countries, numbers, recents, online merge, session."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
scratch = tempfile.TemporaryDirectory()
os.environ['APPDATA'] = scratch.name
os.environ['LOCALAPPDATA'] = scratch.name
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['VISIONPRO_NO_ONLINE'] = '1'
sys.modules['vlc'] = MagicMock()
from PyQt5 import QtCore, QtWidgets, QtTest
import channel_sources
from tabs.vision_iptv_core import VisionIPTVTab, NUMBER_ROLE
from player_services import settings

app = QtWidgets.QApplication([])
tab = VisionIPTVTab()
tab.resize(1100, 650)
tab.show()
playlist = Path(scratch.name) / 'own.m3u'
playlist.write_text('#EXTM3U\n'
                    '#EXTINF:-1 tvg-country="Romania" group-title="Romania",Pro TV HD\nhttp://own/1\n'
                    '#EXTINF:-1 group-title="Muzica",Kiss FM TV\nhttp://own/2\n'
                    '#EXTINF:-1 group-title="General",Digi 24\nhttp://own/3\n'
                    '#EXTINF:-1 group-title="General",Some Channel\nhttp://own/4\n', encoding='utf-8')
tab._load_playlist_file(str(playlist))
tree, side = tab.playlist_tree, tab.category_list

# Model: numbers 1..4, TV categories guessed from group/name, countries guessed from name.
assert [tab.channels[f'http://own/{i}']['n'] for i in range(1, 5)] == [1, 2, 3, 4]
assert tab.channels['http://own/2']['category'] == 'Music' and tab.channels['http://own/3']['category'] == 'News'
assert tab.channels['http://own/1']['country'] == 'Romania' and tab.channels['http://own/3']['country'] == 'Romania'
groups = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
assert groups == ['Music', 'News', 'General TV'], groups
assert tree.topLevelItem(0).child(0).data(0, NUMBER_ROLE) == 2

# Sidebar: Search / Favorites / Recent / All / header / categories with counts.
keys = [side.item(i).data(QtCore.Qt.UserRole) for i in range(side.count())]
assert keys[:5] == ['search', 'fav', 'recent', 'all', 'header'] and keys[5:] == ['group:Music', 'group:News', 'group:General TV'], keys
assert side.item(3).text().endswith('4') and side.item(7).text().endswith('2'), [side.item(i).text() for i in range(side.count())]
assert '4' in tab.channel_badge.text()

# Category view = flat list rooted at that group; All = everything expanded.
side.setCurrentItem(side.item(7))
tab._sidebar_selected(side.item(7))
assert tab.current_view == 'group:General TV' and tree.rootIndex() == tree.indexFromItem(tree.topLevelItem(2))
assert tree.model().rowCount(tree.rootIndex()) == 2
tab._sidebar_selected(side.item(3))
assert tab.current_view == 'all' and not tree.rootIndex().isValid() and tree.topLevelItem(0).isExpanded()

# Favorites: count in sidebar, favorites view shows only them, button and sidebar stay in sync.
tab.add_to_favorites('Kiss FM TV', 'http://own/2')
assert side.item(1).text().endswith('1')
tab._sidebar_selected(side.item(1))
visible = [i.text(0) for i in tab._iter_channel_items() if not i.isHidden()]
assert visible == ['⭐ Kiss FM TV'] and tab.btn_fav.isChecked(), visible
tab.btn_fav.setChecked(False)
tab.toggle_favorites_view()
assert tab.current_view == 'all' and side.currentItem().data(QtCore.Qt.UserRole) == 'all'

# Playing records a recent, shows number + category/country under the video.
tab.player.play.reset_mock()
tab._play_tree_item(tree.topLevelItem(1).child(0), 0)
assert tab.player.play.called and tab._recent_urls() == ['http://own/3']
assert '3  Digi 24' in tab.now_playing.text() and 'News' in tab.now_playing.text() and 'Romania' in tab.now_playing.text()
assert side.item(2).text().endswith('1')
tab._sidebar_selected(side.item(2))
assert [i.text(0) for i in tab._iter_channel_items() if not i.isHidden()] == ['Digi 24']

# Countries mode regroups the same channels; groups mode keeps original group titles.
tab.set_view_mode('country')
assert [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())] == ['Romania', 'International']
tab.set_view_mode('group')
assert [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())] == ['Romania', 'Muzica', 'General']
tab.set_view_mode('category')
print('PASS: TV-style sidebar (search/favorites/recent/all + categories with counts), flat category view, numbers, recents, countries/groups modes')

# Online world channels: fake fetch with the real builder files, merged after own list, cached, excluded from session.
cat_text = (ROOT / 'VisionPro - Toate canalele (verificat).m3u').read_text(encoding='utf-8', errors='replace')
country_text = (ROOT / 'VisionPro - Pe tari (verificat).m3u').read_text(encoding='utf-8', errors='replace')
texts = {channel_sources.SOURCES['cat']: cat_text, channel_sources.SOURCES['country']: country_text}
rows = channel_sources.merge_online(cat_text, country_text)
assert len(rows) > 5000 and all(r['category'] in channel_sources.CATEGORY_LABELS for r in rows)
assert any(r['country'] == 'Albania' for r in rows)
worker = channel_sources.OnlineChannels(tab, fetch=lambda url, timeout=60: texts[url])
done = []
worker.finished_with.connect(lambda rows, error: done.append((rows, error)))
worker.start()
worker.wait(60000)
app.processEvents()
assert done and not done[0][1], done
tab._online_finished(*done[0])
online = sum(1 for c in tab.channels.values() if c['source'] == 'online')
assert online == len(rows) and len(tab.channels) == online + 4
assert 'world' in tab.channel_badge.text() and tab.channels['http://own/1']['n'] == 1
assert min(c['n'] for c in tab.channels.values() if c['source'] == 'online') == 5, 'own channels keep the first numbers'
cached, fetched_at = channel_sources.read_cache()
assert len(cached) == online and channel_sources.cache_is_fresh(fetched_at)
tab.save_session()
payload = json.loads((Path(scratch.name) / 'VisionProIPTV' / 'session.json').read_text(encoding='utf-8'))
assert len(payload['channels']) == 4, 'world channels must not be written into the session'
# Restart: own channels from session, world channels from cache, no download needed.
tab2 = VisionIPTVTab()
tab2.load_last_playlist()
app.processEvents()
assert len(tab2.channels) == 4
with patch.object(channel_sources.OnlineChannels, 'start', lambda self: None):
    tab2.load_online_channels()
assert len(tab2.channels) == online + 4 and tab2._online_worker is None
# Setting off removes them again.
cfg = settings(); cfg.setValue('Settings/online_channels', False); cfg.sync()
tab2.load_online_channels()
assert len(tab2.channels) == 4
print('PASS: world channels merged from iptv-org texts, numbered after own list, cached, restored from cache, excluded from session, switchable off')
