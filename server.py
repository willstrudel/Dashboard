# Serves this folder at http://127.0.0.1:8420 (static files, same as `python -m
# http.server`), plus these routes:
#   POST /api/poll-bluetooth     runs check-bluetooth-battery.ps1 on demand
#   GET  /api/calendar-events    reads ical-config.json (a list of {label, url}
#                                 calendars — iCloud public link, Google Calendar
#                                 secret iCal address, etc.), fetches + parses each
#                                 feed, returns merged upcoming events
#   GET  /api/ical-config        returns the raw connected-calendars list, for the
#                                 "⚙ Sync calendars" modal's manage/remove view
#   POST /api/ical-config        appends (or replaces, by url) a {label, url} calendar
#   POST /api/ical-config/remove removes a calendar by url
#   GET  /api/library-scan       reads library-config.json's epub_folder, opens every
#                                 .epub in it (they're just zip files) and pulls
#                                 title/author/cover straight from the embedded OPF
#                                 metadata — powers the Library page's bookcases
#   GET  /api/library-config     returns the configured epub_folder
#   POST /api/library-config     updates epub_folder
import base64
import hashlib
import http.server
import io
import json
import mimetypes
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    from PIL import Image  # optional — only used to color-match spines to real cover art
except Exception:
    Image = None

try:
    from zoneinfo import ZoneInfo
    EASTERN = ZoneInfo('America/New_York')
except Exception:
    ZoneInfo = None
    EASTERN = None

DIR = Path(__file__).resolve().parent
PS_SCRIPT = DIR / 'check-bluetooth-battery.ps1'
ICAL_CONFIG = DIR / 'ical-config.json'
LIBRARY_CONFIG = DIR / 'library-config.json'
PORT = 8420

ICAL_CACHE_SECONDS = 15 * 60
_ical_cache = {}  # url -> {'fetched_at': float, 'events': [...], 'error': str|None}


# ---------- minimal ICS parser (VEVENT + a pragmatic RRULE subset) ----------
# Only day-level granularity is needed — the dashboard's calendar tracks events
# by date, not time of day — so timed events are reduced to their local calendar
# date and no per-occurrence time is preserved.

def unfold_ics(text):
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = text.split('\n')
    out = []
    for line in lines:
        if line.startswith((' ', '\t')) and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def parse_dt_value(prop_line):
    """Returns (date, is_all_day, time_str) for a DTSTART/DTEND/EXDATE line, or
    (None, False, None). time_str is 'HH:MM' in Eastern local time for timed
    events, None for all-day ones — occurrence dates still collapse to a single
    date (recurrence only varies by day), but the time-of-day is now kept."""
    name_params, _, value = prop_line.partition(':')
    value = value.strip()
    params = {}
    for p in name_params.split(';')[1:]:
        if '=' in p:
            k, v = p.split('=', 1)
            params[k] = v
    if not value:
        return None, False, None
    if params.get('VALUE') == 'DATE' or (len(value) == 8 and value.isdigit()):
        try:
            return datetime.strptime(value[:8], '%Y%m%d').date(), True, None
        except ValueError:
            return None, False, None
    is_utc = value.endswith('Z')
    dt_str = value.rstrip('Z')
    try:
        dt = datetime.strptime(dt_str[:15], '%Y%m%dT%H%M%S')
    except ValueError:
        return None, False, None
    if is_utc:
        dt = dt.replace(tzinfo=timezone.utc)
    elif 'TZID' in params and ZoneInfo:
        try:
            dt = dt.replace(tzinfo=ZoneInfo(params['TZID']))
        except Exception:
            pass
    if dt.tzinfo and EASTERN:
        dt = dt.astimezone(EASTERN)
    return dt.date(), False, dt.strftime('%H:%M')


def parse_rrule(rrule_str):
    return dict(p.split('=', 1) for p in rrule_str.split(';') if '=' in p)


def expand_occurrences(anchor, rrule, exdates, window_start, window_end):
    freq = rrule.get('FREQ', '')
    interval = int(rrule.get('INTERVAL', '1') or 1)
    count = int(rrule['COUNT']) if 'COUNT' in rrule else None
    until = None
    if 'UNTIL' in rrule:
        try:
            until = datetime.strptime(rrule['UNTIL'][:8], '%Y%m%d').date()
        except ValueError:
            pass
    byday = rrule.get('BYDAY')
    dates = []
    max_iter = 2000

    if freq == 'WEEKLY' and byday:
        dow_map = {'MO': 0, 'TU': 1, 'WE': 2, 'TH': 3, 'FR': 4, 'SA': 5, 'SU': 6}
        target_dows = sorted(dow_map[d] for d in byday.split(',') if d in dow_map)
        week_start = anchor - timedelta(days=anchor.weekday())
        n = 0
        for _ in range(max_iter):
            if week_start > window_end or (until and week_start > until):
                break
            for dow in target_dows:
                d = week_start + timedelta(days=dow)
                if d < anchor or d > window_end or (until and d > until):
                    continue
                n += 1
                if count and n > count:
                    break
                if d >= window_start:
                    dates.append(d)
            if count and n >= count:
                break
            week_start += timedelta(weeks=interval)
        return [d for d in dates if d not in exdates]

    cur = anchor
    n = 0
    for _ in range(max_iter):
        if cur > window_end or (until and cur > until):
            break
        n += 1
        if count and n > count:
            break
        if cur >= window_start:
            dates.append(cur)
        if freq == 'DAILY':
            cur = cur + timedelta(days=interval)
        elif freq == 'WEEKLY':
            cur = cur + timedelta(weeks=interval)
        elif freq == 'MONTHLY':
            month0 = cur.month - 1 + interval
            year = cur.year + month0 // 12
            month = month0 % 12 + 1
            leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
            days_in_month = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
            cur = date(year, month, min(cur.day, days_in_month))
        elif freq == 'YEARLY':
            try:
                cur = cur.replace(year=cur.year + interval)
            except ValueError:
                cur = cur.replace(year=cur.year + interval, day=28)
        else:
            break
    return [d for d in dates if d not in exdates]


def parse_vevent(lines, window_start, window_end):
    summary = ''
    anchor = None
    all_day = False
    anchor_time = None
    rrule = None
    exdates = set()
    for line in lines:
        if line.startswith('SUMMARY'):
            summary = line.partition(':')[2].strip()
            summary = summary.replace('\\,', ',').replace('\\;', ';').replace('\\n', ' ').replace('\\\\', '\\')
        elif line.startswith('DTSTART'):
            d, is_all_day, t = parse_dt_value(line)
            if d:
                anchor, all_day, anchor_time = d, is_all_day, t
        elif line.startswith('RRULE'):
            rrule = parse_rrule(line.partition(':')[2].strip())
        elif line.startswith('EXDATE'):
            d, _, _ = parse_dt_value(line)
            if d:
                exdates.add(d)
    if anchor is None or not summary:
        return []
    if rrule:
        occ_dates = expand_occurrences(anchor, rrule, exdates, window_start, window_end)
    else:
        occ_dates = [anchor] if window_start <= anchor <= window_end and anchor not in exdates else []
    return [{'date': d.isoformat(), 'summary': summary, 'allDay': all_day, 'time': anchor_time} for d in occ_dates]


def parse_ics(text, window_start, window_end):
    events = []
    block = None
    for line in unfold_ics(text):
        stripped = line.strip()
        if stripped == 'BEGIN:VEVENT':
            block = []
        elif stripped == 'END:VEVENT':
            if block is not None:
                events.extend(parse_vevent(block, window_start, window_end))
            block = None
        elif block is not None:
            block.append(line)
    return events


_HTTP_ONLY_OPENER = urllib.request.build_opener(urllib.request.HTTPHandler, urllib.request.HTTPSHandler)


def get_ical_events(url):
    """Fetch+parse a single calendar's ICS feed, cached per-URL for ICAL_CACHE_SECONDS."""
    now = time.time()
    cached = _ical_cache.get(url)
    if cached and cached['events'] is not None and (now - cached['fetched_at']) < ICAL_CACHE_SECONDS:
        return cached['events'], cached['error']
    fetch_url = url.replace('webcal://', 'https://', 1)
    # Only ever fetch http(s) — without this, a saved url of file:///... or
    # ftp://... would be dereferenced by urllib's default openers, letting a
    # crafted calendar url read local files off this machine instead of
    # fetching a calendar feed.
    if urllib.parse.urlparse(fetch_url).scheme not in ('http', 'https'):
        return (cached['events'] if cached else []), 'only http(s)/webcal calendar links are allowed'
    try:
        req = urllib.request.Request(fetch_url, headers={'User-Agent': 'MAGI-Dashboard/1.0'})
        with _HTTP_ONLY_OPENER.open(req, timeout=15) as resp:
            text = resp.read().decode('utf-8', errors='replace')
        if 'BEGIN:VCALENDAR' not in text.upper():
            # The link resolved, but isn't actually an ICS feed — most often a Google
            # Calendar "shareable link" (an HTML view page) pasted in by mistake instead
            # of the "Secret address in iCal format" from Settings > Integrate calendar.
            raise ValueError("that link didn't return calendar data (ICS) — double-check "
                              "it's the iCal/ICS feed link, not a general share link")
        window_start = date.today() - timedelta(days=7)
        window_end = date.today() + timedelta(days=365)
        events = parse_ics(text, window_start, window_end)
        events.sort(key=lambda e: e['date'])
        _ical_cache[url] = {'fetched_at': now, 'events': events, 'error': None}
        return events, None
    except Exception as e:
        err = str(e)
        prev_events = cached['events'] if cached else None
        _ical_cache[url] = {'fetched_at': now, 'events': prev_events, 'error': err}
        return (prev_events or []), err


def load_calendar_configs():
    """Reads ical-config.json, migrating the old single-{url} shape to a
    {calendars:[{label,url}]} list transparently."""
    if not ICAL_CONFIG.exists():
        return []
    try:
        cfg = json.loads(ICAL_CONFIG.read_text(encoding='utf-8'))
    except Exception:
        return []
    if 'calendars' in cfg:
        return [c for c in cfg['calendars'] if c.get('url')]
    if cfg.get('url'):
        return [{'label': cfg.get('label', 'iCloud'), 'url': cfg['url']}]
    return []


def save_calendar_configs(calendars):
    ICAL_CONFIG.write_text(json.dumps({'calendars': calendars}, indent=2), encoding='utf-8')


# ---------- epub library (Library page) ----------
# An .epub is just a zip file. META-INF/container.xml points at the OPF package
# document, which carries <dc:title>/<dc:creator> and (EPUB2 or EPUB3 style) a
# reference to the cover image — that's all we need for the bookshelf view.

OPF_NS = {
    'opf': 'http://www.idpf.org/2007/opf',
    'dc': 'http://purl.org/dc/elements/1.1/',
}
CONTAINER_NS = {'c': 'urn:oasis:names:tc:opendocument:xmlns:container'}

_library_cache = {}  # abs path str -> {'mtime': float, 'book': {...}}


def _safe_xml_fromstring(data):
    """Parses XML after rejecting any DOCTYPE declaration, which is what a
    "billion laughs" entity-expansion bomb rides in on — real epub
    container.xml/OPF files never declare one. Stdlib ElementTree already
    ignores external entities (no XXE risk here), so blocking DOCTYPE entirely
    is sufficient and — unlike reaching into expat's handler internals, whose
    attribute access keeps changing across Python versions — stays portable."""
    check = data if isinstance(data, (bytes, bytearray)) else data.encode('utf-8')
    if b'<!DOCTYPE' in check:
        raise ET.ParseError('DOCTYPE declarations are not allowed in epub metadata')
    return ET.fromstring(data)


def load_library_config():
    if not LIBRARY_CONFIG.exists():
        return {'epub_folder': ''}
    try:
        return json.loads(LIBRARY_CONFIG.read_text(encoding='utf-8'))
    except Exception:
        return {'epub_folder': ''}


def save_library_config(cfg):
    LIBRARY_CONFIG.write_text(json.dumps(cfg, indent=2), encoding='utf-8')


def _cover_spine_color(cover_bytes):
    """The book's actual cover color, used to color its spine instead of an
    arbitrary hash-based palette. A flat pixel average blends everything into
    mud, and the single largest color cluster is usually just a plain
    background or a dark vignette border, not a color anyone would call "the
    cover's color" — so this quantizes the cover to a small palette and picks
    the most common cluster that still reads as an actual color (not
    near-black/near-white/near-gray), falling back to the top cluster as-is
    if the cover really is that neutral. Returns '#rrggbb', or None if
    Pillow isn't installed or the image can't be decoded."""
    if Image is None:
        return None
    try:
        img = Image.open(io.BytesIO(cover_bytes)).convert('RGB')
        thumb = img.copy()
        thumb.thumbnail((120, 120))
        paletted = thumb.quantize(colors=12, method=Image.MEDIANCUT)
        palette = paletted.getpalette()
        candidates = sorted(paletted.getcolors(), reverse=True)  # [(count, palette_index), ...]
        rgbs = [tuple(palette[i * 3:i * 3 + 3]) for _count, i in candidates]
        for r, g, b in rgbs:
            mx, mn = max(r, g, b), min(r, g, b)
            if mx >= 30 and mn <= 225 and (mx - mn) >= 18:  # skip near-black/near-white/near-gray
                return f'#{r:02x}{g:02x}{b:02x}'
        r, g, b = rgbs[0]
        return f'#{r:02x}{g:02x}{b:02x}'
    except Exception:
        return None


def _resolve_opf_relative(opf_dir, href):
    """Joins an OPF-relative href (which may contain ../) against the OPF's own
    directory inside the zip, returning a normalized zip member path."""
    raw = (opf_dir + '/' + href) if opf_dir else href
    parts = []
    for seg in raw.replace('\\', '/').split('/'):
        if seg == '..':
            if parts:
                parts.pop()
        elif seg not in ('', '.'):
            parts.append(seg)
    return '/'.join(parts)


def parse_epub(path):
    """Returns {'id','title','author','cover','filename'} or None if the file
    isn't a readable epub."""
    try:
        with zipfile.ZipFile(path) as zf:
            container = _safe_xml_fromstring(zf.read('META-INF/container.xml'))
            rootfile = container.find('.//c:rootfile', CONTAINER_NS)
            opf_path = rootfile.get('full-path')
            opf_dir = opf_path.rsplit('/', 1)[0] if '/' in opf_path else ''
            opf = _safe_xml_fromstring(zf.read(opf_path))

            metadata = opf.find('opf:metadata', OPF_NS)
            title_el = metadata.find('dc:title', OPF_NS) if metadata is not None else None
            creator_el = metadata.find('dc:creator', OPF_NS) if metadata is not None else None
            title = (title_el.text or '').strip() if title_el is not None and title_el.text else path.stem
            author = (creator_el.text or '').strip() if creator_el is not None and creator_el.text else 'Unknown'

            manifest = opf.find('opf:manifest', OPF_NS)
            cover_href = None
            if manifest is not None:
                for item in manifest.findall('opf:item', OPF_NS):
                    if 'cover-image' in (item.get('properties') or ''):  # EPUB3
                        cover_href = item.get('href')
                        break
                if cover_href is None and metadata is not None:  # EPUB2
                    for meta in metadata.findall('opf:meta', OPF_NS):
                        if meta.get('name') == 'cover':
                            item = manifest.find(f"opf:item[@id='{meta.get('content')}']", OPF_NS)
                            if item is not None:
                                cover_href = item.get('href')
                            break

            cover_data_uri = None
            spine_color = None
            if cover_href:
                cover_zip_path = _resolve_opf_relative(opf_dir, cover_href)
                try:
                    cover_bytes = zf.read(cover_zip_path)
                    mime = mimetypes.guess_type(cover_zip_path)[0] or 'image/jpeg'
                    cover_data_uri = f'data:{mime};base64,{base64.b64encode(cover_bytes).decode("ascii")}'
                    spine_color = _cover_spine_color(cover_bytes)
                except KeyError:
                    pass

            book_id = hashlib.sha1(str(path).encode('utf-8')).hexdigest()[:16]
            return {'id': book_id, 'title': title, 'author': author, 'cover': cover_data_uri,
                    'spineColor': spine_color, 'filename': path.name}
    except Exception:
        return None


def scan_epub_folder(folder):
    """Returns a list of parsed books, or None if the folder doesn't exist.
    Recurses into subfolders (books are organized into series/genre folders,
    not left flat) and reuses cached results for files whose mtime hasn't
    changed since the last scan. Each book's immediate subfolder name (if any)
    is attached as 'series'."""
    folder_path = Path(folder)
    if not folder_path.exists() or not folder_path.is_dir():
        return None
    books = []
    for f in sorted(folder_path.rglob('*.epub')):
        try:
            mtime = f.stat().st_mtime
        except OSError:
            continue
        cached = _library_cache.get(str(f))
        if cached and cached['mtime'] == mtime:
            books.append(cached['book'])
            continue
        book = parse_epub(f)
        if book:
            book['series'] = f.parent.name if f.parent != folder_path else ''
            _library_cache[str(f)] = {'mtime': mtime, 'book': book}
            books.append(book)
    return books


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIR), **kwargs)

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path == '/api/calendar-events':
            self.handle_calendar_events()
            return
        if path == '/api/ical-config':
            self.handle_get_ical_config()
            return
        if path == '/api/library-scan':
            self.handle_library_scan()
            return
        if path == '/api/library-config':
            self.handle_get_library_config()
            return
        super().do_GET()

    def do_POST(self):
        if not self._is_trusted_origin():
            # These endpoints change local state (calendar feeds, epub folder, running
            # a script) — without this check, any webpage open in the same browser
            # could quietly POST to 127.0.0.1:8420 and rewrite that state. Browsers
            # always attach Origin on a cross-site request; same-origin dashboard
            # calls and non-browser tools (curl, etc., which send no Origin) still
            # get through.
            self._json(403, {'ok': False, 'error': 'cross-origin request blocked'})
            return
        path = self.path.split('?', 1)[0]
        if path == '/api/poll-bluetooth':
            self.handle_poll_bluetooth()
        elif path == '/api/ical-config':
            self.handle_ical_config()
        elif path == '/api/ical-config/remove':
            self.handle_ical_config_remove()
        elif path == '/api/library-config':
            self.handle_library_config()
        else:
            self.send_response(404)
            self.end_headers()

    def handle_poll_bluetooth(self):
        try:
            result = subprocess.run(
                ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(PS_SCRIPT)],
                capture_output=True, text=True, timeout=30
            )
            ok = result.returncode == 0
            payload = {'ok': ok}
            if not ok:
                payload['error'] = result.stderr[-800:]
        except Exception as e:
            ok = False
            payload = {'ok': False, 'error': str(e)}
        self._json(200 if ok else 500, payload)

    def handle_calendar_events(self):
        calendars = load_calendar_configs()
        if not calendars:
            self._json(200, {'configured': False, 'events': [], 'sources': []})
            return
        all_events = []
        sources = []
        for cal in calendars:
            label = cal.get('label', 'Calendar')
            events, error = get_ical_events(cal['url'])
            for ev in events:
                ev = dict(ev)
                ev['source'] = label
                all_events.append(ev)
            sources.append({'label': label, 'error': error})
        all_events.sort(key=lambda e: e['date'])
        self._json(200, {'configured': True, 'events': all_events, 'sources': sources})

    def handle_ical_config(self):
        length = int(self.headers.get('Content-Length', 0))
        try:
            body = json.loads(self.rfile.read(length))
            url = (body.get('url') or '').strip()
            label = (body.get('label') or 'Calendar').strip()
            if not url:
                raise ValueError('missing url')
            scheme = urllib.parse.urlparse(url.replace('webcal://', 'https://', 1)).scheme
            if scheme not in ('http', 'https'):
                raise ValueError('only http(s)/webcal calendar links are allowed')
            calendars = load_calendar_configs()
            calendars = [c for c in calendars if c.get('url') != url]  # replace if re-added
            calendars.append({'label': label, 'url': url})
            save_calendar_configs(calendars)
            _ical_cache.pop(url, None)  # force a fresh fetch of this calendar next read
            self._json(200, {'ok': True})
        except Exception as e:
            self._json(400, {'ok': False, 'error': str(e)})

    def handle_get_ical_config(self):
        self._json(200, {'calendars': load_calendar_configs()})

    def handle_ical_config_remove(self):
        length = int(self.headers.get('Content-Length', 0))
        try:
            body = json.loads(self.rfile.read(length))
            url = (body.get('url') or '').strip()
            if not url:
                raise ValueError('missing url')
            calendars = [c for c in load_calendar_configs() if c.get('url') != url]
            save_calendar_configs(calendars)
            _ical_cache.pop(url, None)
            self._json(200, {'ok': True})
        except Exception as e:
            self._json(400, {'ok': False, 'error': str(e)})

    def handle_library_scan(self):
        cfg = load_library_config()
        folder = cfg.get('epub_folder', '')
        if not folder:
            self._json(200, {'configured': False, 'folder': '', 'books': []})
            return
        books = scan_epub_folder(folder)
        if books is None:
            self._json(200, {'configured': True, 'folder': folder,
                              'error': f"Folder not found: {folder}", 'books': []})
            return
        books.sort(key=lambda b: b['title'].lower())
        self._json(200, {'configured': True, 'folder': folder, 'books': books})

    def handle_get_library_config(self):
        self._json(200, {'epub_folder': load_library_config().get('epub_folder', '')})

    def handle_library_config(self):
        length = int(self.headers.get('Content-Length', 0))
        try:
            body = json.loads(self.rfile.read(length))
            folder = (body.get('epub_folder') or '').strip()
            if not folder:
                raise ValueError('missing epub_folder')
            save_library_config({'epub_folder': folder})
            self._json(200, {'ok': True})
        except Exception as e:
            self._json(400, {'ok': False, 'error': str(e)})

    def _is_trusted_origin(self):
        origin = self.headers.get('Origin')
        if not origin:
            return True  # no browser cross-site request sends this blank — non-browser tools land here
        return origin in (f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}')

    def _json(self, status, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


if __name__ == '__main__':
    server = http.server.HTTPServer(('127.0.0.1', PORT), Handler)
    server.serve_forever()
