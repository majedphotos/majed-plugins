#!/usr/bin/env python3
"""مرتب الرحلات — يقرا رحلة من تطبيق الصور بالماك ويرتبها حسب المدينة والفعالية.

  trip.py fetch  <work> --query "Thailand" [--from 2026-08-27 --to 2026-09-08]
  trip.py events <work> [--gap 90 --km 2 --min 10]
  trip.py page   <work> [--shape M]
  trip.py albums <work> --folder "رحلة تايلند" [--only "اسم,اسم"] [--no-airports]

كل شي محلي: يقرا اسم الملف والتاريخ واللوكيشن بس، وما يفتح ولا صورة.
أسماء الأماكن من خريطة أبل نفسها (CLGeocoder) — نفس اللي يستخدمه تطبيق الصور.
"""
import argparse, json, math, os, re, shutil, subprocess, sys, tempfile, time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, '..', 'assets')


def osa(script, timeout=600):
    r = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        sys.exit('تطبيق الصور رفض: ' + r.stderr.strip() + '\n(System Settings ← Privacy ← Automation ← اسمح للطرفية تتحكم بـPhotos)')
    return r.stdout


def esc(s):
    return s.replace('\\', '\\\\').replace('"', '\\"')


def load(work):
    with open(os.path.join(work, 'trip.json')) as f: return json.load(f)


def save(work, data):
    with open(os.path.join(work, 'trip.json'), 'w') as f: json.dump(data, f, ensure_ascii=False, indent=1)


# ---------- 1) fetch ----------
def fetch(a):
    os.makedirs(a.work, exist_ok=True)
    out = osa(f'''tell application "Photos"
set r to search for "{esc(a.query)}"
set out to ""
repeat with m in r
  set loc to location of m
  set la to ""
  set lo to ""
  try
    set la to (item 1 of loc) as text
    set lo to (item 2 of loc) as text
  end try
  set out to out & (id of m) & tab & (filename of m) & tab & ((date of m) as «class isot» as string) & tab & la & tab & lo & linefeed
end repeat
return out
end tell''', timeout=1800)
    files = []
    for line in out.splitlines():
        p = line.split('\t')
        if len(p) < 5: continue
        d = p[2][:10]
        if a.from_ and d < a.from_: continue
        if a.to and d > a.to: continue
        try: lat, lon = round(float(p[3]), 5), round(float(p[4]), 5)
        except ValueError: lat = lon = None
        if lat == 0 and lon == 0: lat = lon = None
        files.append({'id': p[0], 'f': p[1], 't': p[2], 'd': d, 'lat': lat, 'lon': lon})
    files.sort(key=lambda r: r['t'])
    save(a.work, {'query': a.query, 'files': files, 'events': []})
    days = sorted({f['d'] for f in files})
    print(f'{len(files)} ملف · {sum(f["lat"] is not None for f in files)} فيها لوكيشن · من {days[0] if days else "-"} إلى {days[-1] if days else "-"}')


# ---------- 2) events ----------
GEO_SWIFT = r'''
import CoreLocation
import Foundation
let a = CommandLine.arguments.dropFirst().map { Double($0)! }
var i = 0
let g = CLGeocoder()
func next() {
  if i >= a.count { exit(0) }
  let loc = CLLocation(latitude: a[i], longitude: a[i+1]); i += 2
  g.reverseGeocodeLocation(loc, preferredLocale: Locale(identifier: "en")) { p, e in
    let m = p?.first
    let parts = [m?.areasOfInterest?.first ?? "", m?.name ?? "", m?.subLocality ?? "", m?.locality ?? "", m?.administrativeArea ?? "", m?.country ?? "", m?.isoCountryCode ?? ""]
    print(parts.joined(separator: "\t"))
    fflush(stdout)
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.3) { next() }
  }
}
next()
RunLoop.main.run()
'''


def geocode(points):
    if not points or not shutil.which('swift'): return [None] * len(points)
    with tempfile.NamedTemporaryFile('w', suffix='.swift', delete=False) as f: f.write(GEO_SWIFT)
    args = [str(v) for p in points for v in p]
    r = subprocess.run(['swift', f.name, *args], capture_output=True, text=True, timeout=60 + 4 * len(points))
    rows = [l.split('\t') for l in r.stdout.splitlines()]
    return rows + [None] * (len(points) - len(rows))


def is_airport(*fields):
    t = ' '.join(fields).lower()
    return bool(re.search(r'\bairport\b|مطار|^(main|passenger|international|domestic) terminal', t))


def events(a):
    data = load(a.work)
    files, evs, cur = data['files'], [], None
    for r in files:
        if r['lat'] is None: continue
        T = datetime.fromisoformat(r['t'])
        if cur:
            km = math.hypot(r['lat'] - cur['lat'], (r['lon'] - cur['lon']) * math.cos(math.radians(r['lat']))) * 111
            if (T - cur['end']).total_seconds() < a.gap * 60 and km < a.km:
                cur['n'] += 1; cur['end'] = T
                cur['lat'] += (r['lat'] - cur['lat']) / cur['n']; cur['lon'] += (r['lon'] - cur['lon']) / cur['n']
                cur['ids'].append(r['id']); continue
        cur = {'start': T, 'end': T, 'lat': r['lat'], 'lon': r['lon'], 'n': 1, 'ids': [r['id']]}
        evs.append(cur)
    big = [e for e in evs if e['n'] >= a.min]
    print(f'{len(big)} فعالية (من {len(evs)} تجمّع) — أطلب أسماءها من خريطة أبل…')
    names = geocode([(round(e['lat'], 5), round(e['lon'], 5)) for e in big])
    out, by_id = [], {}
    for k, (e, g) in enumerate(zip(big, names)):
        aoi, nm, sub, city, admin, country, cc = (g + [''] * 7)[:7] if g else [''] * 7
        # a street address means a house or hotel, so name it after the neighbourhood
        address = any(ch.isdigit() for ch in nm)
        name = (sub or city) if address else (aoi or nm or sub or city)
        name = name or f'{e["lat"]:.3f}, {e["lon"]:.3f}'
        ev = {'id': k, 'name_en': name, 'name': name, 'city': admin or city or country, 'country': country, 'cc': cc,
              'start': e['start'].isoformat(), 'end': e['end'].isoformat(), 'count': e['n'],
              'lat': round(e['lat'], 5), 'lon': round(e['lon'], 5), 'airport': is_airport(name, aoi), 'stay': address}
        out.append(ev)
        for i in e['ids']: by_id[i] = k
    # same place visited twice (the hotel) → one event
    merged = {}
    def km(a, b): return math.hypot(a['lat'] - b['lat'], (a['lon'] - b['lon']) * math.cos(math.radians(a['lat']))) * 111
    for ev in out:
        key = ev['name_en']
        if key not in merged:
            key = next((k for k, m in merged.items() if km(m, ev) < 0.3), key)
        if key in merged:
            m = merged[key]; m['count'] += ev['count']; m['end'] = max(m['end'], ev['end'])
            for i, k in list(by_id.items()):
                if k == ev['id']: by_id[i] = m['id']
        else: merged[key] = ev
    data['events'] = list(merged.values())
    # no province from the geocoder (a beach, open sea) → borrow the nearest event's city
    known = [e for e in data['events'] if e['city'] and e['city'] != e['country']]
    for e in data['events']:
        if known and (not e['city'] or e['city'] == e['country']):
            e['city'] = min(known, key=lambda k: abs(k['lat'] - e['lat']) + abs(k['lon'] - e['lon']))['city']
    for r in files:
        r['ev'] = by_id.get(r['id'])
        if r['ev'] is None and r['lat'] is not None:  # loose shots inherit the nearest event's city
            near = min(data['events'], key=lambda e: abs(e['lat'] - r['lat']) + abs(e['lon'] - r['lon']), default=None)
            r['city'] = near['city'] if near else None
        elif r['ev'] is not None:
            r['city'] = next(e['city'] for e in data['events'] if e['id'] == r['ev'])
    save(a.work, data)
    for ev in sorted(data['events'], key=lambda e: e['start']):
        tag = ' ✈' if ev['airport'] else ' 🏨' if ev['stay'] else ''
        print(f'  {ev["start"][:10]}  {ev["count"]:4d}  {ev["name_en"]} · {ev["city"]}{tag}')


# ---------- 3) page ----------
def page(a):
    data = load(a.work)
    names = {e['id']: e for e in data['events']}
    rows = []
    for r in data['files']:
        ev = names.get(r.get('ev'))
        if ev and ev['airport'] and a.no_airports: continue
        rows.append({'f': r['f'], 'd': r['d'], 'lat': r['lat'], 'lon': r['lon'], 'city': r.get('city'),
                     'ev': ev['name'] if ev else ((r.get('city') or 'بلا لوكيشن') + ' · متفرقات')})
    site = os.path.join(a.work, 'page')
    os.makedirs(site, exist_ok=True)
    shutil.copy(os.path.join(ASSETS, 'index.html'), os.path.join(site, 'index.html'))
    with open(os.path.join(site, 'trip-data.js'), 'w') as f:
        f.write('window.TRIP=' + json.dumps({'name': a.name or data['query'], 'files': rows}, ensure_ascii=False) + ';\n')
    url = 'file://' + os.path.join(site, 'index.html') + (f'?shape={a.shape}' if a.shape else '')
    print(url)
    # `open` drops ?query on file URLs, so hand the URL to the browser itself
    subprocess.run(['osascript', '-e', f'open location "{url}"'])


# ---------- 4) thumbs + review ----------
def thumbs(a):
    """Export a couple of photos per event, shrink them, delete the big export (private, for the owner's eyes only)."""
    import random
    data = load(a.work)
    out = os.path.join(a.work, 'review', 'thumbs'); os.makedirs(out, exist_ok=True)
    if a.fresh:
        for f in os.listdir(out): os.remove(os.path.join(out, f))
    tmp = tempfile.mkdtemp()
    for ev in sorted(data['events'], key=lambda e: e['start']):
        if all(os.path.exists(os.path.join(out, f'{ev["id"]}-{k}.jpg')) for k in range(a.per)): continue
        mine = [r for r in data['files'] if r.get('ev') == ev['id']]
        photos = [r for r in mine if r['f'].lower().endswith(('.heic', '.jpg', '.jpeg'))]
        pool = photos if len(photos) >= a.per else photos + [r for r in mine if r not in photos]
        # one random pick from each slice of the event, so the two don't come from the same burst
        n = min(a.per, len(pool))
        pick = [random.choice(pool[k * len(pool) // n:(k + 1) * len(pool) // n]) for k in range(n)]
        if not pick: continue
        items = ', '.join(f'media item id "{esc(r["id"])}"' for r in pick)
        osa(f'tell application "Photos" to export {{{items}}} to (POSIX file "{tmp}" as alias) without using originals')
        for k, r in enumerate(pick):
            stem = os.path.splitext(r['f'])[0]
            src = next((os.path.join(tmp, f) for f in os.listdir(tmp) if os.path.splitext(f)[0] == stem), None)
            if not src: continue
            dst = os.path.join(out, f'{ev["id"]}-{k}.jpg')
            if src.lower().endswith(('.mov', '.mp4', '.m4v')):  # a video: let Quick Look draw its poster frame
                subprocess.run(['qlmanage', '-t', '-s', '420', '-o', tmp, src], capture_output=True)
                png = src + '.png'
                if os.path.exists(png):
                    subprocess.run(['sips', '-s', 'format', 'jpeg', png, '--out', dst], capture_output=True); os.remove(png)
            else:
                subprocess.run(['sips', '-Z', '420', '-s', 'format', 'jpeg', src, '--out', dst], capture_output=True)
            os.remove(src)
        print(f'  ✓ {ev["name"]}', flush=True)
    shutil.rmtree(tmp, ignore_errors=True)


def review(a):
    """Local page: the trip day by day, real thumbs, editable names. Saves straight into trip.json."""
    import http.server
    site = os.path.join(a.work, 'review'); os.makedirs(site, exist_ok=True)
    shutil.copy(os.path.join(ASSETS, 'review.html'), os.path.join(site, 'index.html'))
    work = a.work

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *x, **k): super().__init__(*x, directory=site, **k)
        def log_message(self, *x): pass
        def do_GET(self):
            if self.path.startswith('/data'):
                body = json.dumps(load(work), ensure_ascii=False).encode()
                self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(body)
            else: super().do_GET()
        def do_POST(self):
            edits = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            data = load(work)
            for ev in data['events']:
                e = edits.get(str(ev['id']))
                if e: ev['name'] = e['name'].strip() or ev['name']; ev['skip'] = bool(e.get('skip'))
            save(work, data)
            self.send_response(200); self.end_headers(); self.wfile.write(b'ok')

    for port in range(a.port, a.port + 20):  # another app may already own the port
        try: srv = http.server.ThreadingHTTPServer(('127.0.0.1', port), H); break
        except OSError: continue
    url = f'http://localhost:{port}/'
    print(url, flush=True)
    subprocess.run(['open', url])
    srv.serve_forever()


# ---------- 5) albums ----------
def albums(a):
    data = load(a.work)
    only = {x.strip() for x in a.only.split(',')} if a.only else None
    evs = sorted((e for e in data['events'] if not e.get('skip') and not (a.no_airports and e['airport'])
                  and (not only or e['name'] in only)), key=lambda e: e['start'])
    keep = {e['id'] for e in evs}
    names, by_name = [], {}
    for e in evs:
        if e['name'] not in by_name: names.append(e['name']); by_name[e['name']] = set()
        by_name[e['name']].add(e['id'])
    by_ev = {n: [r['id'] for r in data['files'] if r.get('ev') in ids] for n, ids in by_name.items()}
    whole = [r['id'] for r in data['files'] if r.get('ev') in keep]  # files are already in time order
    fo = esc(a.folder)
    script = ['tell application "Photos"',
              f'if not (exists folder "{fo}") then make new folder named "{fo}"',
              f'set fo to folder "{fo}"']
    def add(name, ids):
        n = esc(name)
        script.append(f'if not (exists album "{n}" of fo) then make new album named "{n}" at fo')
        for i in range(0, len(ids), 200):
            items = ', '.join(f'media item id "{esc(x)}"' for x in ids[i:i + 200])
            script.append(f'add {{{items}}} to album "{n}" of fo')
    if not only: add(a.whole, whole)
    for k, n in enumerate(names, 1):
        add(f'{k:02d} · {n}', by_ev[n])
    script.append('end tell')
    osa('\n'.join(script), timeout=1800)
    if not only: print(f'  {len(whole):4d}  {a.folder} ← {a.whole}')
    for k, n in enumerate(names, 1): print(f'  {len(by_ev[n]):4d}  {a.folder} ← {k:02d} · {n}')


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    p = sp.add_parser('fetch'); p.add_argument('work'); p.add_argument('--query', required=True)
    p.add_argument('--from', dest='from_'); p.add_argument('--to'); p.set_defaults(fn=fetch)
    p = sp.add_parser('events'); p.add_argument('work'); p.add_argument('--gap', type=int, default=90)
    p.add_argument('--km', type=float, default=2); p.add_argument('--min', type=int, default=10); p.set_defaults(fn=events)
    p = sp.add_parser('page'); p.add_argument('work'); p.add_argument('--shape', default='')
    p.add_argument('--name'); p.add_argument('--no-airports', action='store_true'); p.set_defaults(fn=page)
    p = sp.add_parser('thumbs'); p.add_argument('work'); p.add_argument('--per', type=int, default=2)
    p.add_argument('--fresh', action='store_true', help='اختار صور جديدة'); p.set_defaults(fn=thumbs)
    p = sp.add_parser('review'); p.add_argument('work'); p.add_argument('--port', type=int, default=8790); p.set_defaults(fn=review)
    p = sp.add_parser('albums'); p.add_argument('work'); p.add_argument('--folder', required=True)
    p.add_argument('--whole', default='الرحلة كاملة')
    p.add_argument('--only'); p.add_argument('--no-airports', action='store_true'); p.set_defaults(fn=albums)
    a = ap.parse_args(); a.fn(a)


if __name__ == '__main__':
    main()
