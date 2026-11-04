"""Channel sources like VisionPro IPTV Pro on the TV: bundled playlist + free world channels (iptv-org).

parse_m3u()      -> list of channel dicts {name,url,group,logo,country,cats}
categorize()     -> TV-style category label (Music, Movies, Sports...), guessed from the name when missing
OnlineChannels   -> downloads iptv-org category + country indexes in a thread, caches them in AppData (24 h)
"""
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from PyQt5 import QtCore

from player_services import DATA_DIR

SOURCES = {'cat': 'https://iptv-org.github.io/iptv/index.category.m3u',
           'country': 'https://iptv-org.github.io/iptv/index.country.m3u'}
CACHE_PATH = DATA_DIR / 'online_channels.json'
CACHE_MAX_AGE = 24 * 3600
LABEL = {'music': 'Music', 'movies': 'Movies', 'series': 'Series', 'sports': 'Sports', 'news': 'News', 'kids': 'Kids',
         'animation': 'Animation', 'documentary': 'Documentary', 'entertainment': 'Entertainment', 'comedy': 'Comedy',
         'general': 'General TV', 'public': 'Public TV', 'lifestyle': 'Lifestyle', 'cooking': 'Cooking', 'travel': 'Travel',
         'culture': 'Culture', 'education': 'Education', 'science': 'Science', 'business': 'Business', 'auto': 'Auto',
         'outdoor': 'Outdoor', 'family': 'Family', 'classic': 'Classic', 'relax': 'Relax', 'weather': 'Weather',
         'legislative': 'Politics', 'religious': 'Religious', 'shop': 'Shopping', 'interactive': 'Interactive', 'other': 'Other'}
ORDER = list(LABEL)
CATEGORY_LABELS = list(LABEL.values())
# Existing playlists use free-form group titles; map the common ones onto the TV categories.
GROUP_ALIASES = {'general': 'general', 'muzica': 'music', 'muzică': 'music', 'musik': 'music', 'filme': 'movies', 'film': 'movies',
                 'seriale': 'series', 'sport': 'sports', 'stiri': 'news', 'știri': 'news', 'copii': 'kids', 'desene': 'animation',
                 'documentare': 'documentary', 'divertisment': 'entertainment', 'comedie': 'comedy', 'tv generala': 'general',
                 'tv publica': 'public', 'religie': 'religious', 'religios': 'religious', 'vreme': 'weather', 'gatit': 'cooking'}
GROUP_ALIASES.update({label.lower(): key for key, label in LABEL.items()})
GUESS = [('music', r'music|hits|mtv|vh1|radio|dance|rock|pop|clubbing|manele|folk|muzic|musik|melod|jazz|disco|kiss|deejay'),
         ('news', r'news|nachricht|stiri|noticias|nieuws|haber|cnn|euronews|al jazeera|bloomberg|cnbc|sky news|digi ?24|antena 3|realitatea'),
         ('sports', r'sport|football|futbol|soccer|tennis|golf|nba|nfl|ufc|fight|racing|motor|espn|eurosport|bein|wrestling'),
         ('movies', r'movie|film|cinema|kino|cine|hollywood'), ('series', r'series|serial|novela|drama|sitcom'),
         ('kids', r'kids|junior|cartoon|toon|baby|disney|nick|minimax|boomerang|children|kinder|copii'),
         ('documentary', r'docu|discovery|nat geo|national geographic|history|wild|nature|animal|planet'),
         ('religious', r'relig|church|christ|gospel|bible|islam|quran|catholic|orthodox|trinitas|faith|jesus|3abn|ewtn|tbn'),
         ('shop', r'shop|teleshop|qvc|hse'), ('weather', r'weather|wetter|meteo'), ('cooking', r'cook|food|chef|kitchen')]
COUNTRY_HINTS = [('Romania', r'\b(tvr|pro tv|antena|digi|kanal d|prima tv|romania|român)'), ('Germany', r'\b(rtl|zdf|prosieben|ard|sat\.1|wdr|ndr|dasding)'),
                 ('United Kingdom', r'\b(bbc|itv|channel 4)'), ('Italy', r'\b(rai|mediaset)'), ('France', r'\b(tf1|canal\+|france \d)'),
                 ('United States', r'\b(hbo|nbc|cnn|fox|abc|cbs)'), ('Spain', r'\b(rtve|tve|telecinco)'), ('Turkey', r'\b(trt|show tv)')]

_EXTINF = re.compile(r'^#EXTINF:[^,]*,(.*)$')
_ATTR = re.compile(r'([\w-]+)="([^"]*)"')


def bundled_playlist_dir():
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    return base / 'playlists'


def bundled_playlists():
    """M3U files shipped with the application (playlists/ next to the sources, bundled by the spec)."""
    folder = bundled_playlist_dir()
    return sorted(folder.glob('*.m3u')) + sorted(folder.glob('*.m3u8')) if folder.is_dir() else []


def parse_m3u(text):
    out, cur = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith('#EXTINF'):
            match = _EXTINF.match(line)
            attrs = dict(_ATTR.findall(line.split(',', 1)[0]))
            name = re.sub(r'(?:\s*\(Unknown\))+$', '', (match.group(1) if match else '').strip(), flags=re.IGNORECASE)
            cur = {'name': name or 'Channel', 'group': attrs.get('group-title', '').strip(), 'logo': attrs.get('tvg-logo', ''),
                   'country': attrs.get('tvg-country', '').strip(), 'id': attrs.get('tvg-id', ''), 'cats': []}
        elif line and not line.startswith('#') and cur is not None:
            cur['url'] = line
            out.append(cur)
            cur = None
    return out


def category_key(group, name):
    """Lower-case category key for a channel, from its group title or guessed from its name."""
    for part in (group or '').split(';'):
        key = part.strip().lower()
        if ' - ' in key:
            key = key.split(' - ', 1)[-1].strip()
        key = GROUP_ALIASES.get(key, key)
        if key in LABEL and key != 'general':
            return key
    lower = (name or '').lower()
    for key, pattern in GUESS:
        if re.search(pattern, lower):
            return key
    for part in (group or '').split(';'):
        key = GROUP_ALIASES.get(part.strip().lower(), part.strip().lower())
        if key in LABEL:
            return key
    return 'general' if (group or '').strip() else 'other'


def categorize(channel):
    cats = [c for c in channel.get('cats', []) if c in LABEL and c != 'general']
    key = min(cats, key=ORDER.index) if cats else category_key(channel.get('group', ''), channel.get('name', ''))
    if key == 'other' and 'general' in channel.get('cats', []):
        key = 'general'
    return LABEL[key]


def guess_country(channel):
    country = (channel.get('country') or '').strip()
    if country and country.lower() not in ('unknown', 'undefined', 'international', 'other'):
        return country.title() if country.islower() else country
    lower = channel.get('name', '').lower()
    for name, pattern in COUNTRY_HINTS:
        if re.search(pattern, lower):
            return name
    return ''


def load_file(path):
    """Channels from an M3U file with TV categories and countries filled in."""
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    rows, seen = [], set()
    for channel in parse_m3u(text):
        if channel['url'] in seen:
            continue
        seen.add(channel['url'])
        channel['category'] = categorize(channel)
        channel['country'] = guess_country(channel)
        rows.append(channel)
    return rows


def _fetch(url, timeout=60):
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 VisionPro IPTV'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode('utf-8', 'replace')


def merge_online(category_text, country_text):
    """Combine iptv-org's category and country indexes into one channel list (same logic as the TV build)."""
    channels = {}
    for channel in parse_m3u(category_text):
        entry = channels.setdefault(channel['url'], dict(channel, cats=[], country=''))
        for key in channel['group'].split(';'):
            key = key.strip().lower()
            if key and key not in ('undefined', 'xxx') and key not in entry['cats']:
                entry['cats'].append(key)
    for channel in parse_m3u(country_text):
        entry = channels.setdefault(channel['url'], dict(channel, cats=[], country=''))
        if not entry.get('logo') and channel['logo']:
            entry['logo'] = channel['logo']
        if channel['group'] not in ('Undefined', 'International') and not entry['country']:
            entry['country'] = channel['group'].split(';')[0]
    rows = []
    for entry in channels.values():
        if 'xxx' in (entry.get('group') or '').lower() and not entry['cats']:
            continue
        entry['category'] = categorize(entry)
        entry['country'] = guess_country(entry)
        entry['group'] = entry['category']
        rows.append(entry)
    return rows


def read_cache():
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding='utf-8'))
        return payload.get('channels', []), float(payload.get('fetched_at', 0))
    except (OSError, ValueError):
        return [], 0.0


def write_cache(channels):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps({'fetched_at': time.time(), 'channels': channels}, ensure_ascii=False), encoding='utf-8')


def cache_is_fresh(fetched_at):
    return fetched_at and time.time() - fetched_at < CACHE_MAX_AGE


class OnlineChannels(QtCore.QThread):
    """Downloads the world channel list in the background; emits (channels, error)."""
    finished_with = QtCore.pyqtSignal(list, str)

    def __init__(self, parent=None, fetch=_fetch):
        super().__init__(parent)
        self._fetch = fetch

    def run(self):
        try:
            rows = merge_online(self._fetch(SOURCES['cat']), self._fetch(SOURCES['country']))
            write_cache(rows)
            self.finished_with.emit(rows, '')
        except Exception as exc:  # network errors must never crash the player
            self.finished_with.emit([], str(exc))
