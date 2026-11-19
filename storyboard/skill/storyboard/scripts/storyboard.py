#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
storyboard.py — يحوّل وصف اللقطات (JSON) إلى ستوري بورد: ملف HTML واحد والرسمات داخله SVG بقلم رصاص.

    python3 storyboard.py spec.json -o storyboard.html [--svgs مجلد] [--strict]

بلا أي مكتبة خارجية. شرح الحقول كلها بـ references/shot-language.md
الإحداثيات نسبة مئوية من الكادر: x من يسار الكادر لليمين (0-100)، y من فوق لتحت (0-100).
«يسار/يمين» دايماً يسار ويمين الكادر مثل ما يشوفه المشاهد.
"""
import sys, json, math, random, re, argparse, colorsys, os
from contextlib import contextmanager
from html import escape

# ───────────────────────────── الألوان: كلها مشتقة من هوية المستخدم
WH, BK = '#FFFFFF', '#000000'


def _rgb(c):
    c = str(c).strip().lstrip('#')
    if len(c) == 3:
        c = ''.join(ch * 2 for ch in c)
    if not re.fullmatch(r'[0-9a-fA-F]{6}', c):
        raise ValueError('لون غير مفهوم: %r — اكتبه بصيغة #RRGGBB' % c)
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(rgb):
    return '#%02X%02X%02X' % tuple(max(0, min(255, int(round(v * 255)))) for v in rgb)


def mix(a, b, t):
    A, B = _rgb(a), _rgb(b)
    return _hex(tuple(A[i] + (B[i] - A[i]) * t for i in range(3)))


def lum(c):
    def f(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(c)
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def hls(c):
    return colorsys.rgb_to_hls(*_rgb(c))


def rotate(c, deg, l=None, s=None):
    h, li, sa = hls(c)
    return _hex(colorsys.hls_to_rgb((h + deg / 360.0) % 1, li if l is None else l, sa if s is None else s))


def ensure(c, bg, ratio=3.0):
    """يحرّك إضاءة اللون بعيد عن الخلفية لين يوصل تباين مقروء."""
    h, li, sa = hls(c)
    step = -0.03 if lum(bg) > 0.4 else 0.03
    out = c
    for _ in range(30):
        if contrast(out, bg) >= ratio:
            break
        li = max(0.04, min(0.96, li + step))
        out = _hex(colorsys.hls_to_rgb(h, li, sa))
    return out


def hue_gap(a, b):
    d = abs(hls(a)[0] - hls(b)[0])
    return min(d, 1 - d) * 360


def build_theme(brand):
    if not brand.get('bg') or not brand.get('accent'):
        raise SystemExit('ناقص هوية المستخدم: brand.bg (لون الخلفية) و brand.accent (لون التمييز). '
                         'خذهم من ملف هويته أو اسأله سؤال واحد — لا تحط ألوان من عندك بدون ما تقول له.')
    bg = _hex(_rgb(brand['bg']))
    dark = lum(bg) < 0.2
    ink = brand.get('ink') or (mix(bg, BK, 0.86) if not dark else mix(bg, WH, 0.9))
    card = mix(bg, WH, 0.9) if not dark else mix(bg, WH, 0.07)
    paper = mix(bg, WH, 0.62) if not dark else mix(bg, WH, 0.035)
    pen = mix(ink, paper, 0.07)
    accent = ensure(_hex(_rgb(brand['accent'])), card, 3.0)
    note = ensure(accent, paper, 3.0)
    a2 = brand.get('accent2')
    if a2:
        a2 = _hex(_rgb(a2))
        if hls(a2)[2] < 0.18 or hue_gap(a2, accent) < 28:   # رمادي أو قريب من لون التمييز ← ما يتميّز عن الرصاص/الملاحظات
            a2 = None
    h, li, sa = hls(accent)
    ov1 = ensure(a2 or rotate(accent, 195, l=min(0.52, max(0.42, li)), s=max(0.45, min(0.62, sa))), paper, 3.0)
    a3 = brand.get('accent3')
    if a3:
        a3 = _hex(_rgb(a3))
        if hls(a3)[2] < 0.18 or hue_gap(a3, ov1) < 28:
            a3 = None
    warm = h * 360 >= 330 or h * 360 <= 70          # لون تمييز دافي ← الثاني ذهبي جنبه، وإلا لون بعيد عن الاثنين
    ov2 = ensure(a3 or rotate(accent, 28 if warm else -105, l=0.42 if not dark else 0.6, s=0.72), paper, 3.0)
    return dict(bg=bg, dark=dark, ink=ink, card=card, paper=paper, pen=pen, accent=accent, note=note, ov1=ov1, ov2=ov2,
                muted=mix(ink, card, 0.38), rule=mix(ink, card, 0.86), soft=mix(card, accent, 0.08),
                chip=mix(card, bg, 0.9) if not dark else mix(card, WH, 0.08))


# ───────────────────────────── قياس عرض الكتابة
# تقدير محافظ (مضبوط على قياس حقيقي لخط Playpen Sans Arabic الثقيل): يُستخدم للفحص ولتقسيم السطور،
# والصفحة نفسها تضبط الحجم بالضبط وقت الفتح (سكربت صغير آخر الملف).
_W = {}
for _ch in 'اأإآل': _W[_ch] = 0.28
for _ch in 'بتثنيىئ': _W[_ch] = 0.40
for _ch in 'رزدذوؤةه': _W[_ch] = 0.46
for _ch in 'سشصض': _W[_ch] = 0.90
for _ch in 'جحخعغفقكمطظ': _W[_ch] = 0.58
for _ch in '%@&': _W[_ch] = 0.85
for _ch in 'MWmw': _W[_ch] = 0.92


def is_ar(t):
    return any('\u0600' <= c <= '\u06ff' for c in str(t))


def text_w(t, size):
    w = 0.0
    for word in str(t).split(' '):
        if is_ar(word):
            w += 0.27                      # ذيل الحرف الأخير بالكلمة العربية
        for ch in word:
            o = ord(ch)
            if 0x64b <= o <= 0x652 or o in (0x670, 0x200f, 0x200e, 0x61c):
                continue
            if ch in _W:
                w += _W[ch]
            elif 0x600 <= o <= 0x6ff:
                w += 0.5
            elif ch.isdigit():
                w += 0.64
            elif ch.isupper():
                w += 0.74
            elif ch.islower():
                w += 0.59
            else:
                w += 0.42
    w += 0.2 * str(t).count(' ')
    return w * size * 1.15


def wrap_lines(t, k):
    """يقسم السطر على k سطور متوازنة بالكلمات."""
    words = str(t).split()
    if k <= 1 or len(words) <= 1:
        return [' '.join(words)]
    total = text_w(' '.join(words), 10)
    target = total / k
    lines, cur = [], []
    for wd in words:
        trial = ' '.join(cur + [wd])
        if cur and text_w(trial, 10) > target * 1.12 and len(lines) < k - 1:
            lines.append(' '.join(cur))
            cur = [wd]
        else:
            cur.append(wd)
    if cur:
        lines.append(' '.join(cur))
    return lines


def fit_text(t, size, maxw, minsize=9.0, maxlines=3):
    base = [ln for ln in str(t).split('\n') if ln.strip()] or ['']
    best = None
    for extra in range(0, maxlines):
        lines = []
        for ln in base:
            lines += wrap_lines(ln, 1 + extra) if extra else [ln]
        if len(lines) > max(maxlines, len(base)):
            break
        wide = max(text_w(ln, size) for ln in lines) or 1
        sc = min(1.0, maxw / wide)
        if best is None or sc > best[2] + 0.02:
            best = (lines, size * sc, sc)
        if sc >= 0.82:
            break
    lines, sz, sc = best
    ok = sz >= minsize
    return lines, max(sz, minsize), ok


# ───────────────────────────── القلم الرصاص
def clamp(v, a, b):
    return max(a, min(b, v))


class Sk:
    def __init__(s, seed, w, h, pal, uid):
        s.r = random.Random(seed); s.o = []; s.w = w; s.h = h; s.cid = 0; s.uid = uid
        s.pal = pal; s.paper = pal['paper']; s.pen = pal['pen']; s.cur = s.pen; s.dash = None; s.M = None
        s.faces = []; s.texts = []; s.warn = []; s.anchors = {}; s.objs = []; s.zooms = []; s.bodies = []; s.hands = []; s.shapes = []; s.backs = []
        s.K = min(w, h) / 270.0          # مقياس الخطوط حسب مقاس الكادر

    # — تحويلات وسياق اللون
    def tp(s, pts):
        if not s.M:
            return [(float(x), float(y)) for x, y in pts]
        a, b, c, d, e, f = s.M
        return [(a * x + c * y + e, b * x + d * y + f) for x, y in pts]

    @contextmanager
    def rot(s, deg, cx, cy):
        old = s.M
        if deg:
            r = math.radians(deg); co, si = math.cos(r), math.sin(r)
            n = (co, si, -si, co, cx - co * cx + si * cy, cy - si * cx - co * cy)
            if old:
                a, b, c, d, e, f = old; a2, b2, c2, d2, e2, f2 = n
                n = (a * a2 + c * b2, b * a2 + d * b2, a * c2 + c * d2, b * c2 + d * d2, a * e2 + c * f2 + e, b * e2 + d * f2 + f)
            s.M = n
        try:
            yield
        finally:
            s.M = old

    @contextmanager
    def ink(s, color, dash=None):
        oc, od = s.cur, s.dash
        s.cur, s.dash = color, dash
        try:
            yield
        finally:
            s.cur, s.dash = oc, od

    def j(s, a):
        return (s.r.random() - 0.5) * 2 * a

    # — مسارات
    def _d(s, pts, closed=False):
        n = len(pts)
        if n == 2:
            return "M%.1f,%.1f L%.1f,%.1f" % (pts[0][0], pts[0][1], pts[1][0], pts[1][1])
        P = ([pts[-1]] + pts + [pts[0], pts[1]]) if closed else ([pts[0]] + pts + [pts[-1]])
        d = "M%.1f,%.1f" % P[1]
        for i in range(1, len(P) - 2):
            p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
            c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
            c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
            d += " C%.1f,%.1f %.1f,%.1f %.1f,%.1f" % (c1[0], c1[1], c2[0], c2[1], p2[0], p2[1])
        return d + (" Z" if closed else "")

    def _dl(s, pts):
        return "M" + " L".join("%.1f,%.1f" % p for p in pts) + " Z"

    def fill(s, pts, color=None, op=1, smooth=True):
        pts = s.tp(pts)
        d = s._d(pts, True) if smooth else s._dl(pts)
        s.o.append('<path d="%s" fill="%s" fill-opacity="%s" stroke="none"></path>' % (d, color or s.paper, op))

    def _stroke(s, pts, sw=1.5, color=None, op=0.88, j=1.1, passes=2, closed=False, dash=None):
        color = color or s.cur
        dash = dash if dash is not None else s.dash
        sw = sw * s.K
        for p in range(passes):
            q = [(x + s.j(j), y + s.j(j)) for x, y in pts]
            da = ' stroke-dasharray="%s"' % dash if dash else ''
            s.o.append('<path d="%s" fill="none" stroke="%s" stroke-opacity="%.2f" stroke-width="%.2f" stroke-linecap="round" stroke-linejoin="round"%s></path>'
                       % (s._d(q, closed), color, op * (0.95 if p == 0 else 0.6), sw * (1 if p == 0 else 0.8), da))

    def stroke(s, pts, **k):
        s._stroke(s.tp(pts), **k)

    def _line(s, a, b, **k):
        L = math.hypot(b[0] - a[0], b[1] - a[1]); bb = min(2.2, L * 0.02)
        s._stroke([a, ((a[0] + b[0]) / 2 + s.j(bb), (a[1] + b[1]) / 2 + s.j(bb)), b], **k)

    def line(s, x1, y1, x2, y2, **k):
        a, b = s.tp([(x1, y1), (x2, y2)])
        s._line(a, b, **k)

    def poly(s, pts, closed=True, fillc=None, fop=1, **k):
        if fillc:
            s.fill(pts, fillc, fop, smooth=False)
        P = s.tp(pts)
        P = P + [P[0]] if closed else P
        for a, b in zip(P, P[1:]):
            s._line(a, b, **k)

    def epts(s, cx, cy, rx, ry, a0=0, a1=None, n=16, rot=0):
        a1 = a0 + 2 * math.pi if a1 is None else a1; out = []
        for i in range(n + 1):
            a = a0 + (a1 - a0) * i / n; x = rx * math.cos(a); y = ry * math.sin(a)
            out.append((cx + x * math.cos(rot) - y * math.sin(rot), cy + x * math.sin(rot) + y * math.cos(rot)))
        return out

    def ellipse(s, cx, cy, rx, ry, fillc=None, fop=1, rot=0, **k):
        if fillc:
            s.fill(s.epts(cx, cy, rx, ry, n=18, rot=rot)[:-1], fillc, fop)
        a0 = s.r.random() * 6.28
        s.stroke(s.epts(cx, cy, rx, ry, a0, a0 + 6.28 + 0.5, n=18, rot=rot), **k)

    def hatch(s, pts, ang=-0.9, gap=5, color=None, op=0.35, sw=0.9, smooth=False):
        pts = s.tp(pts)
        color = color or s.cur
        s.cid += 1; cid = 'c%s_%d' % (s.uid, s.cid)
        d = s._d(pts, True) if smooth else s._dl(pts)
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        cx = (min(xs) + max(xs)) / 2; cy = (min(ys) + max(ys)) / 2
        R = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) / 2 + 4
        g = ['<clipPath id="%s"><path d="%s"></path></clipPath><g clip-path="url(#%s)">' % (cid, d, cid)]
        k = -R; gap = max(1.6, gap)
        while k <= R:
            ox = cx + k * math.cos(ang + math.pi / 2); oy = cy + k * math.sin(ang + math.pi / 2)
            g.append('<path d="M%.1f,%.1f L%.1f,%.1f" stroke="%s" stroke-opacity="%s" stroke-width="%.2f" stroke-linecap="round" fill="none"></path>'
                     % (ox - R * math.cos(ang) + s.j(1.5), oy - R * math.sin(ang) + s.j(1.5),
                        ox + R * math.cos(ang) + s.j(1.5), oy + R * math.sin(ang) + s.j(1.5), color, op, sw * s.K))
            k += gap * (0.8 + 0.4 * s.r.random())
        g.append('</g>'); s.o.append(''.join(g))

    def tube(s, pts, wd=16, sw=1.5):
        L = []; R = []
        for i, (x, y) in enumerate(pts):
            a = pts[max(i - 1, 0)]; b = pts[min(i + 1, len(pts) - 1)]
            dx, dy = b[0] - a[0], b[1] - a[1]; n = math.hypot(dx, dy) or 1; nx, ny = -dy / n, dx / n
            L.append((x + nx * wd / 2, y + ny * wd / 2)); R.append((x - nx * wd / 2, y - ny * wd / 2))
        pl = L + R[::-1]
        s.fill(pl, s.paper); s.stroke(pl, sw=sw, closed=True)

    def rrect(s, x0, y0, x1, y1, r):
        r = min(r, abs(x1 - x0) / 2, abs(y1 - y0) / 2); out = []
        for (cx, cy, a0) in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
            for i in range(4):
                a = math.radians(a0 + i * 30)
                out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        # نقطة بنص كل ضلع عشان يبقى مستقيم مع التنعيم
        res = []
        for i, p in enumerate(out):
            res.append(p)
            if i % 4 == 3:
                q = out[(i + 1) % len(out)]
                res.append(((p[0] * 2 + q[0]) / 3, (p[1] * 2 + q[1]) / 3)); res.append(((p[0] + q[0] * 2) / 3, (p[1] + q[1] * 2) / 3))
        return res

    def rbox(s, x0, y0, x1, y1, r=4, fillc=None, fop=1, **k):
        pts = s.rrect(x0, y0, x1, y1, r)
        if fillc:
            s.fill(pts, fillc, fop)
        s.stroke(pts, closed=True, **k)
        return pts

    def arrow(s, pts, color=None, sw=1.8, head=7, dash=None):
        pts = s.tp(pts)
        s._stroke(pts, sw=sw, color=color, op=0.95, j=0.7, passes=2, dash=dash)
        (x1, y1), (x2, y2) = pts[-2], pts[-1]; a = math.atan2(y2 - y1, x2 - x1)
        for da in (2.6, -2.6):
            s._line((x2, y2), (x2 + head * s.K * math.cos(a + da), y2 + head * s.K * math.sin(a + da)), sw=sw, color=color, op=0.95, j=0.4, passes=1, dash='')

    # — كتابة داخل الرسمة: تتصغّر وتنقسم لين تدخل بعرضها، وتنسجّل عشان الفحص
    def text(s, t, x, y, size=12, color=None, maxw=None, w=700, kind='overlay', minsize=None, op=1, maxlines=3, rot=0, fam=None, reg=True):
        t = str(t)
        maxw = maxw or (s.w - 16 * s.K)
        lines, sz, ok = fit_text(t, size, maxw, minsize or (5.0 if kind == 'label' else 9.0) * s.K, maxlines)
        if not ok and kind != 'label':
            s.warn.append('الكتابة «%s» طويلة على مكانها — قصّرها أو كبّر مساحتها' % t[:40])
        lh = sz * 1.32; H = lh * len(lines); x0 = x1 = x
        grow = min(float(size), sz * (1.16 if len(lines) == 1 else 1.08))    # الصفحة تكبّره لين هالحد لو طلع أضيق من التقدير
        for i, ln in enumerate(lines):
            by = y - H / 2 + i * lh + sz * 0.92
            tw = text_w(ln, sz); x0 = min(x0, x - tw / 2); x1 = max(x1, x + tw / 2)
            tr = ' transform="rotate(%s %.1f %.1f)"' % (rot, x, y) if rot else ''
            halo = '' if kind == 'label' else ' stroke="%s" stroke-width="%.1f" stroke-linejoin="round" paint-order="stroke"' % (s.paper, max(1.6, sz * 0.2))
            s.o.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="%.1f" data-fs="%.1f" data-mw="%.0f" font-weight="%s" fill="%s" fill-opacity="%s" text-anchor="middle" direction="%s"%s%s>%s</text>'
                       % (x, by, fam or s.pal['sketch_font'], sz, grow, maxw, w, color or s.cur, op, 'rtl' if is_ar(ln) else 'ltr', halo, tr, escape(ln)))
        box = (x0, y - H / 2 + sz * 0.14, x1, y + H / 2 - sz * 0.18)
        if reg:
            s.texts.append(dict(t=t, box=box, kind=kind))
        return box

    def svg(s, label, extra_style='display:block;width:100%;height:auto'):
        return ('<svg viewBox="0 0 %d %d" role="img" aria-label="%s" style="%s"><rect x="0" y="0" width="%d" height="%d" fill="%s"></rect>'
                % (s.w, s.h, escape(label, quote=True), extra_style, s.w, s.h, s.paper)) + ''.join(s.o) + '</svg>'


# ───────────────────────────── الشخصية (عامة: شكلها من اختيارات المستخدم)
def draw_head(s, cx, cy, rx, ry, turn=0, ch=None):
    ch = ch or {}
    k = rx / 24.0; kk = clamp(k, 0.6, 1.6); P = s.paper; N = s.cur
    hw = ch.get('headwear', 'none'); hair = ch.get('hair', 'short'); beard = bool(ch.get('beard'))
    tx = turn * 3 * k
    if hw == 'hijab':
        out = s.epts(cx, cy - ry * 0.04, rx * 1.24, ry * 1.17, math.radians(-180), math.radians(0), n=12)
        out += [(cx + rx * 1.26, cy + ry * 0.5), (cx + rx * 1.4, cy + ry * 1.25), (cx + rx * 1.95, cy + ry * 1.95), (cx + rx * 1.1, cy + ry * 2.3), (cx, cy + ry * 2.42),
                (cx - rx * 1.1, cy + ry * 2.3), (cx - rx * 1.95, cy + ry * 1.95), (cx - rx * 1.4, cy + ry * 1.25), (cx - rx * 1.26, cy + ry * 0.5)]
        s.fill(out, P); s.hatch(out, ang=-1.1, gap=3.4 * kk, op=0.3, sw=0.8, smooth=True); s.stroke(out, sw=1.6 * kk, closed=True)
        frx, fry, fcy = rx * 0.86, ry * 0.93, cy + ry * 0.05
        s.ellipse(cx, fcy, frx, fry, fillc=P, sw=1.5 * kk)
        s.stroke([(cx - rx * 0.78, cy + ry * 0.95), (cx, cy + ry * 1.3), (cx + rx * 0.78, cy + ry * 0.95)], sw=1.1 * kk, op=0.6, j=0.5, passes=1)
        s.stroke([(cx - rx * 1.2, cy + ry * 1.5), (cx - rx * 0.2, cy + ry * 1.95), (cx + rx * 0.9, cy + ry * 1.7)], sw=1.0 * kk, op=0.45, j=0.5, passes=1)
    else:
        if hw == 'none' and hair == 'long':
            back = s.epts(cx, cy - ry * 0.05, rx * 1.2, ry * 1.14, math.radians(-180), math.radians(0), n=12)
            back += [(cx + rx * 1.28, cy + ry * 0.6), (cx + rx * 1.34, cy + ry * 1.5), (cx + rx * 0.7, cy + ry * 1.62), (cx, cy + ry * 1.2),
                     (cx - rx * 0.7, cy + ry * 1.62), (cx - rx * 1.34, cy + ry * 1.5), (cx - rx * 1.28, cy + ry * 0.6)]
            s.fill(back, N, 0.74); s.hatch(back, ang=-1.3, gap=2.8 * kk, op=0.5, sw=0.8, smooth=True)
        s.ellipse(cx, cy, rx, ry, fillc=P, sw=1.6 * kk)
        if hw in ('none', 'glasses') and hair != 'none':
            top = s.epts(cx, cy, rx + 1.5 * k, ry + 2 * k, math.radians(-168), math.radians(-12), n=12)
            low = [(cx + rx * 0.9, cy - ry * 0.5), (cx + rx * 0.42, cy - ry * 0.74), (cx - rx * 0.4, cy - ry * 0.72), (cx - rx * 0.92, cy - ry * 0.48)]
            if hair == 'long':
                low = [(cx + rx * 0.96, cy - ry * 0.2), (cx + rx * 0.5, cy - ry * 0.62), (cx - rx * 0.1, cy - ry * 0.78), (cx - rx * 0.7, cy - ry * 0.5), (cx - rx * 0.97, cy - ry * 0.15)]
            s.fill(top + low, N, 0.78); s.hatch(top + low, ang=-1.2 + turn * 0.3, gap=2.6 * kk, op=0.5, sw=0.8, smooth=True)
        if beard:
            o = s.epts(cx, cy, rx + 0.6 * k, ry + 0.8 * k, math.radians(8), math.radians(172), n=12)
            inn = [(cx - rx * 0.78, cy + ry * 0.12), (cx - rx * 0.5, cy + ry * 0.5), (cx - rx * 0.18, cy + ry * 0.34), (cx + turn * 2 * k, cy + ry * 0.3),
                   (cx + rx * 0.18, cy + ry * 0.34), (cx + rx * 0.5, cy + ry * 0.5), (cx + rx * 0.78, cy + ry * 0.12)]
            s.fill(o + inn, N, 0.5); s.hatch(o + inn, ang=1.1, gap=2.4 * kk, op=0.45, sw=0.8, smooth=True)
        frx, fry, fcy = rx, ry, cy
    # ملامح الوجه
    ex = frx * 0.4; ey = fcy - fry * 0.06
    for sx in (-1, 1):
        s.stroke([(cx + sx * ex - 4 * k + tx, ey - 7 * k), (cx + sx * ex + tx, ey - 8.5 * k), (cx + sx * ex + 4.5 * k + tx, ey - 7 * k)], sw=1.5 * kk, j=0.4, passes=1)
        s.ellipse(cx + sx * ex + tx, ey, 1.7 * k, 2.0 * k, fillc=N, sw=0.8 * kk, j=0.2, passes=1)
    s.stroke([(cx + tx, ey + 2 * k), (cx - 2 * k + tx * 1.3, ey + 9 * k), (cx + 2.5 * k + tx, ey + 10.5 * k)], sw=1.2 * kk, j=0.4, passes=1)
    my = fcy + fry * 0.44
    if beard and hw != 'hijab':
        s.stroke([(cx - 7 * k + tx, my), (cx + tx, my + fry * 0.08), (cx + 7 * k + tx, my)], sw=1.5 * kk, color=P, op=1, j=0.3, passes=1)
    else:
        s.stroke([(cx - 6.5 * k + tx, my), (cx + tx, my + fry * 0.1), (cx + 6.5 * k + tx, my)], sw=1.4 * kk, j=0.3, passes=1)
    if hw not in ('hijab', 'ghutra', 'shemagh') and hair != 'long':
        for sx in (-1, 1):
            s.stroke([(cx + sx * (rx + 0.5 * k), cy - 4 * k), (cx + sx * (rx + 4 * k), cy), (cx + sx * (rx + 1 * k), cy + 6 * k)], sw=1.2 * kk, j=0.4, passes=1)
    if ch.get('glasses'):
        for sx in (-1, 1):
            s.ellipse(cx + sx * ex + tx, ey + 0.5 * k, 6.4 * k, 5.2 * k, sw=1.3 * kk, j=0.3, passes=1)
        s.line(cx - ex + 6.4 * k + tx, ey, cx + ex - 6.4 * k + tx, ey, sw=1.2 * kk, j=0.2, passes=1)
    if hw in ('ghutra', 'shemagh'):
        for sx in (-1, 1):
            dr = [(cx + sx * rx * 0.98, cy - ry * 0.3), (cx + sx * rx * 1.34, cy + ry * 0.25), (cx + sx * rx * 1.52, cy + ry * 1.15), (cx + sx * rx * 1.7, cy + ry * 2.05),
                  (cx + sx * rx * 0.98, cy + ry * 2.15), (cx + sx * rx * 0.86, cy + ry * 1.25), (cx + sx * rx * 0.99, cy + ry * 0.45)]
            s.fill(dr, P)
            if hw == 'shemagh':
                s.hatch(dr, ang=0.8, gap=3.4 * kk, op=0.34, sw=0.8, smooth=True); s.hatch(dr, ang=-0.8, gap=3.4 * kk, op=0.34, sw=0.8, smooth=True)
            s.stroke(dr, sw=1.5 * kk, closed=True)
            s.stroke([(cx + sx * rx * 1.2, cy + ry * 0.5), (cx + sx * rx * 1.3, cy + ry * 1.9)], sw=0.9 * kk, op=0.45, j=0.5, passes=1)
        top = s.epts(cx, cy, rx + 3.4 * k, ry + 3.6 * k, math.radians(-184), math.radians(4), n=12)
        low = [(cx + rx * 1.02, cy - ry * 0.24), (cx + rx * 0.5, cy - ry * 0.6), (cx, cy - ry * 0.7), (cx - rx * 0.5, cy - ry * 0.6), (cx - rx * 1.02, cy - ry * 0.24)]
        s.fill(top + low, P)
        if hw == 'shemagh':
            s.hatch(top + low, ang=0.8, gap=3.4 * kk, op=0.34, sw=0.8, smooth=True); s.hatch(top + low, ang=-0.8, gap=3.4 * kk, op=0.34, sw=0.8, smooth=True)
        s.stroke(top, sw=1.6 * kk); s.stroke(low, sw=1.4 * kk, j=0.5)
        for dy in (0, 4.2 * k):
            s.stroke([(cx - rx * 0.92, cy - ry * 0.86 + dy), (cx, cy - ry * 1.07 + dy), (cx + rx * 0.92, cy - ry * 0.86 + dy)], sw=3.0 * kk, op=0.95, j=0.4, passes=1)
    if hw == 'cap':
        top = s.epts(cx, cy, rx + 2.5 * k, ry + 3 * k, math.radians(-176), math.radians(-4), n=12)
        low = [(cx + rx * 1.06, cy - ry * 0.42), (cx, cy - ry * 0.5), (cx - rx * 1.06, cy - ry * 0.42)]
        s.fill(top + low, P); s.hatch(top + low, ang=-1.0, gap=3 * kk, op=0.4, sw=0.8, smooth=True); s.stroke(top + low, sw=1.5 * kk, closed=True)
        brim = [(cx - rx * 1.12, cy - ry * 0.42), (cx - rx * 0.5, cy - ry * 0.3), (cx + rx * 0.5, cy - ry * 0.3), (cx + rx * 1.12, cy - ry * 0.42), (cx, cy - ry * 0.52)]
        s.fill(brim, N, 0.7); s.stroke(brim[:4], sw=1.6 * kk)
    if hw in ('ghutra', 'shemagh'):
        s.faces.append((cx - rx * 1.6, cy - ry - 4 * k, cx + rx * 1.6, cy + ry * 1.25))
    elif hw == 'hijab' or hair == 'long':
        s.faces.append((cx - rx * 1.3, cy - ry * 1.22, cx + rx * 1.3, cy + ry * 1.3))
    else:
        s.faces.append((cx - frx * 0.98, fcy - fry * 0.98 - (2 * k if hair != 'none' or hw == 'cap' else 0), cx + frx * 0.98, fcy + fry * 0.98))


def draw_fingers(s, x, y, hs, side=1, n=4, ang=0.0):
    """أصابع ماسكة طرف الغرض: side=1 الأصابع جاية من يمين الغرض."""
    for i in range(n):
        yy = y + (i - (n - 1) / 2) * hs * 0.52
        s.ellipse(x - side * hs * 0.3, yy, hs * 0.62, hs * 0.25, fillc=s.paper, sw=1.2, j=0.3, rot=ang, passes=1)


def draw_hand(s, cx, cy, rx, ry, rot=0, fingers=True, sw=1.5):
    s.ellipse(cx, cy, rx, ry, fillc=s.paper, sw=sw, rot=rot)
    if fingers:
        for k in (-0.5, 0, 0.5):
            ax = cx + k * rx * 1.1 * math.cos(rot) + ry * 0.2 * math.sin(rot); ay = cy + k * rx * 1.1 * math.sin(rot) - ry * 0.2 * math.cos(rot)
            s.line(ax, ay, ax + ry * 0.75 * math.sin(rot), ay - ry * 0.75 * math.cos(rot), sw=0.9, op=0.55, j=0.3, passes=1)


def draw_person(s, p, ch, desk_y=None):
    """p: cx, cy (مركز الراس), u (نص عرض الراس), pose, turn, arms/left/right/point/hold. يرجّع مواقع مفيدة."""
    cx, cy, u = p['cx'], p['cy'], p['u']; ry = 1.25 * u; kk = clamp(u / 23.0, 0.6, 1.6); P = s.paper
    turn = p.get('turn', 0); pose = p.get('pose', 'stand'); H = s.h
    hw = ch.get('headwear', 'none')
    outfit = ch.get('outfit') or ('thobe' if hw in ('ghutra', 'shemagh') else 'dress' if hw == 'hijab' else 'tshirt')
    robe = outfit in ('thobe', 'abaya', 'dress')
    dark = bool(ch.get('dark_outfit')) or outfit == 'abaya'
    wide = u < 16 * s.K
    hip = cy + (7.6 if pose == 'sit' else 8.2) * u
    full = hip < H - 0.03 * H and desk_y is None and not (pose == 'sit' and not wide)
    hem = cy + 16.7 * u
    long_robe = full and robe and pose != 'sit'
    bottom = (desk_y + 4) if desk_y is not None else (hem if long_robe else hip if full else H + 12)
    feet = None
    hatch_op = 0.5 if dark else 0.24; hatch_gap = (2.8 if dark else 4.5) * kk
    # الرجلين (لما الكادر يبيّنهم)
    if full:
        if pose == 'sit':
            if robe:
                lap = [(cx - 2.2 * u, hip - 0.5 * u), (cx - 2.5 * u, cy + 14.3 * u), (cx + 2.5 * u, cy + 14.3 * u), (cx + 2.2 * u, hip - 0.5 * u)]
                s.fill(lap, P, smooth=False); s.hatch(lap, ang=-1.0, gap=hatch_gap, op=hatch_op); s.poly(lap, closed=False, sw=1.6 * kk)
                s.line(cx - 2.4 * u, cy + 14.3 * u, cx + 2.4 * u, cy + 14.3 * u, sw=1.4 * kk)
                s.stroke([(cx - 2.3 * u, cy + 9.9 * u), (cx, cy + 10.2 * u), (cx + 2.3 * u, cy + 9.9 * u)], sw=1.0 * kk, op=0.5, passes=1)
            else:
                for sx in (-1, 1):
                    s.tube([(cx + sx * 1.0 * u, hip - 0.2 * u), (cx + sx * 1.3 * u, cy + 9.9 * u), (cx + sx * 1.35 * u, cy + 14.3 * u)], 1.8 * u, sw=1.5 * kk)
            feet = cy + 14.8 * u; fx = 1.5
        else:
            if not robe:
                for sx in (-1, 1):
                    s.tube([(cx + sx * 1.0 * u, hip - 0.5 * u), (cx + sx * 1.02 * u, cy + 12.4 * u), (cx + sx * 1.05 * u, cy + 16.6 * u)], 1.85 * u, sw=1.5 * kk)
            feet = cy + 17.1 * u; fx = 1.0 if robe else 1.2
        for sx in (-1, 1):
            s.ellipse(cx + sx * fx * u, feet, 0.95 * u, 0.4 * u, fillc=s.cur, fop=0.7, sw=1.2 * kk, passes=1)
        sh = s.epts(cx, feet + 0.5 * u, 3.6 * u, 0.5 * u, n=14)[:-1]
        s.hatch(sh, ang=0.1, gap=2.2 * kk, op=0.3, smooth=True)
    # الجسم
    sh_pts = [(cx - 2.43 * u, cy + 3.3 * u), (cx - 1.74 * u, cy + 2.17 * u), (cx - 0.7 * u, cy + 1.76 * u), (cx + 0.7 * u, cy + 1.76 * u),
              (cx + 1.74 * u, cy + 2.17 * u), (cx + 2.43 * u, cy + 3.3 * u)]
    if long_robe:
        body = [(cx - 2.8 * u, hem), (cx - 2.35 * u, cy + 7.0 * u)] + sh_pts + [(cx + 2.35 * u, cy + 7.0 * u), (cx + 2.8 * u, hem)]
    elif full:
        body = [(cx - 2.0 * u, hip), (cx - 2.2 * u, cy + 5.6 * u)] + sh_pts + [(cx + 2.2 * u, cy + 5.6 * u), (cx + 2.0 * u, hip)]
    else:
        body = [(cx - 2.62 * u, bottom)] + ([(cx - 2.6 * u, cy + 4.6 * u)] if bottom > cy + 5.4 * u else []) + sh_pts \
            + ([(cx + 2.6 * u, cy + 4.6 * u)] if bottom > cy + 5.4 * u else []) + [(cx + 2.62 * u, bottom)]
    s.fill(body, P, smooth=not (full or long_robe)) if not full else s.fill(body, P)
    s.hatch(body, ang=-1.0, gap=hatch_gap, op=hatch_op, smooth=True); s.stroke(body, sw=1.8 * kk)
    if full:
        s.line(body[0][0], body[0][1], body[-1][0], body[-1][1], sw=1.3 * kk, op=0.75, passes=1)
    # الرقبة والياقة
    if hw != 'hijab':
        s.poly([(cx - 0.43 * u, cy + 1.0 * u), (cx - 0.46 * u, cy + 1.86 * u)], closed=False, sw=1.3 * kk, passes=1)
        s.poly([(cx + 0.43 * u, cy + 1.0 * u), (cx + 0.46 * u, cy + 1.86 * u)], closed=False, sw=1.3 * kk, passes=1)
        if outfit in ('thobe', 'shirt'):
            s.stroke([(cx - 0.72 * u, cy + 1.72 * u), (cx - 0.3 * u, cy + 2.3 * u), (cx, cy + 2.05 * u), (cx + 0.3 * u, cy + 2.3 * u), (cx + 0.72 * u, cy + 1.72 * u)], sw=1.3 * kk, j=0.4)
            s.line(cx, cy + 2.1 * u, cx, min(bottom, cy + 4.6 * u), sw=1.0 * kk, op=0.6, passes=1)
            for i in range(3):
                by = cy + (2.6 + i * 0.7) * u
                if by < bottom - 0.2 * u:
                    s.ellipse(cx + 0.02 * u, by, 0.08 * u, 0.08 * u, fillc=s.cur, sw=0.6 * kk, j=0.1, passes=1)
        else:
            s.stroke([(cx - 0.7 * u, cy + 1.76 * u), (cx, cy + 2.28 * u), (cx + 0.7 * u, cy + 1.76 * u)], sw=1.3 * kk, j=0.5)
            s.line(cx, cy + 2.28 * u, cx, cy + 3.05 * u, sw=1.0 * kk, op=0.6, passes=1)
    draw_head(s, cx, cy, u, ry, turn, ch)
    # الأذرع
    A = p.get('arms', 'rest' if u >= 16 * s.K else 'down')
    if desk_y is not None and A == 'rest' and desk_y < cy + 5.6 * u:
        A = 'desk' if desk_y < cy + 4.4 * u else 'rest'
    left = p.get('left', A); right = p.get('right', A)
    hold = p.get('hold'); point = p.get('point')
    out = dict(cx=cx, cy=cy, u=u, held=None)
    tw = 0.74 * u

    def arm(sx, g):
        if g in ('hide', None, 'none'):
            return
        S = (cx + sx * 2.1 * u, cy + 3.45 * u)
        if g == 'rest':
            s.hands.append((cx + sx * 0.33 * u, cy + 4.92 * u, 0.6 * u))
            s.tube([(cx + sx * 2.0 * u, cy + 3.5 * u), (cx + sx * 2.12 * u, cy + 5.67 * u), (cx + sx * 0.46 * u, cy + 5.1 * u)], tw, sw=1.5 * kk)
            s.ellipse(cx + sx * 0.33 * u, cy + 4.92 * u, 0.5 * u, 0.42 * u, fillc=P, sw=1.5 * kk, rot=sx * 0.4)
        elif g == 'down':
            s.tube([(cx + sx * 2.3 * u, cy + 3.4 * u), (cx + sx * 2.78 * u, cy + 5.6 * u), (cx + sx * 2.72 * u, cy + 7.7 * u)], tw, sw=1.5 * kk)
            s.ellipse(cx + sx * 2.72 * u, cy + 8.2 * u, 0.42 * u, 0.52 * u, fillc=P, sw=1.4 * kk)
        elif g == 'open':
            s.tube([(cx + sx * 2.15 * u, cy + 3.5 * u), (cx + sx * 2.5 * u, cy + 6.0 * u), (cx + sx * 1.5 * u, cy + 4.85 * u)], tw, sw=1.5 * kk)
            draw_hand(s, cx + sx * 1.36 * u, cy + 4.0 * u, 0.48 * u, 0.7 * u, rot=-sx * 0.28, sw=1.5 * kk)
            s.hands.append((cx + sx * 1.36 * u, cy + 4.0 * u, 0.8 * u))
        elif g == 'wave':
            s.tube([(cx + sx * 2.2 * u, cy + 3.5 * u), (cx + sx * 3.35 * u, cy + 3.7 * u), (cx + sx * 3.4 * u, cy + 1.5 * u)], tw, sw=1.5 * kk)
            draw_hand(s, cx + sx * 3.42 * u, cy + 0.7 * u, 0.55 * u, 0.8 * u, rot=sx * 0.15, sw=1.5 * kk)
            s.hands.append((cx + sx * 3.42 * u, cy + 0.7 * u, 0.9 * u))
        elif g == 'cross':
            s.tube([(cx + sx * 2.2 * u, cy + 3.5 * u), (cx + sx * 2.35 * u, cy + 5.3 * u), (cx - sx * 1.0 * u, cy + (4.75 if sx < 0 else 5.05) * u)], tw, sw=1.5 * kk)
            s.ellipse(cx - sx * 1.25 * u, cy + (4.7 if sx < 0 else 5.0) * u, 0.45 * u, 0.4 * u, fillc=P, sw=1.4 * kk)
        elif g == 'desk':
            dy = (desk_y if desk_y is not None else cy + 6.0 * u) - 0.3 * u
            s.tube([(cx + sx * 2.1 * u, cy + 3.5 * u), (cx + sx * 2.5 * u, min(dy, cy + 5.2 * u)), (cx + sx * 1.25 * u, dy)], tw, sw=1.5 * kk)
            s.ellipse(cx + sx * 1.0 * u, dy, 0.55 * u, 0.36 * u, fillc=P, sw=1.4 * kk)
        elif g == 'point-camera':
            s.tube([(cx + sx * 2.09 * u, cy + 3.3 * u), (cx + sx * 3.04 * u, cy + 2.87 * u)], 0.96 * u, sw=1.5 * kk)
            s.ellipse(cx + sx * 3.39 * u, cy + 2.35 * u, 0.74 * u, 0.65 * u, fillc=P, sw=1.7 * kk, rot=sx * 0.2)
            s.hands.append((cx + sx * 3.39 * u, cy + 2.35 * u, 0.9 * u))
            s.tube([(cx + sx * 3.04 * u, cy + 2.61 * u), (cx + sx * 1.83 * u, cy + 3.13 * u)], 0.39 * u, sw=1.3 * kk)
            s.ellipse(cx + sx * 1.74 * u, cy + 3.17 * u, 0.22 * u, 0.2 * u, fillc=P, sw=1.3 * kk)
            for i in range(3):
                bx = cx + sx * (3.83 - i * 0.3) * u
                s.stroke([(bx, cy + 2.78 * u), (bx - sx * 0.13 * u, cy + 3.09 * u)], sw=1.0 * kk, op=0.6, j=0.3, passes=1)
        elif isinstance(g, (list, tuple)):               # يأشّر على نقطة
            T = g; dx, dy = T[0] - S[0], T[1] - S[1]; d = math.hypot(dx, dy) or 1; dx, dy = dx / d, dy / d
            reach = min(max(d - 0.9 * u, 1.6 * u), 4.3 * u)
            E = (S[0] + dx * reach * 0.5 - dy * 0.35 * u * sx, S[1] + dy * reach * 0.5 + 0.5 * u)
            Hn = (S[0] + dx * reach, S[1] + dy * reach)
            s.tube([S, E, Hn], tw, sw=1.5 * kk)
            s.ellipse(Hn[0], Hn[1], 0.46 * u, 0.4 * u, fillc=P, sw=1.4 * kk)
            s.hands.append((Hn[0] + dx * 0.4 * u, Hn[1] + dy * 0.4 * u, 0.9 * u))
            s.tube([Hn, (Hn[0] + dx * 0.85 * u, Hn[1] + dy * 0.85 * u)], 0.26 * u, sw=1.1 * kk)

    if point:
        T = point if isinstance(point, (list, tuple)) else point.get('to')
        side = None if isinstance(point, (list, tuple)) else point.get('arm')
        sx = (-1 if T[0] < cx else 1) if side not in ('left', 'right') else (-1 if side == 'left' else 1)
        if sx < 0:
            left = T
        else:
            right = T
    if hold:
        at = hold.get('at', 'side-right'); item = dict(hold.get('item') or {'type': 'box'})
        sx = -1 if 'left' in at else 1
        typ = alias(item.get('type', 'box')); asp = float(item.get('ratio') or ASPECT.get(typ, 1.0))
        custom = bool(item.get('ratio') or item.get('hpx'))
        if at == 'chest':
            iw = item.get('wpx') or min(2.3 * u, 3.2 * u / asp); ih = item.get('hpx') or iw * asp; ix, iy = cx, cy + 4.25 * u
            item['hpx'] = ih if custom else None
            for q in (-1, 1):
                s.tube([(cx + q * 2.0 * u, cy + 3.5 * u), (cx + q * 2.45 * u, cy + 5.5 * u), (cx + q * (iw / 2 + 0.2 * u), cy + 4.75 * u)], tw, sw=1.5 * kk)
                s.ellipse(cx + q * (iw / 2 + 0.05 * u), iy + min(ih * 0.2, 0.5 * u), 0.5 * u, 0.55 * u, fillc=P, sw=1.4 * kk)
            draw_prop(s, dict(item, type=typ), ix, iy, iw)
            for q in (-1, 1):
                draw_fingers(s, cx + q * (iw / 2 - 0.02 * u), iy + min(ih * 0.2, 0.5 * u), 0.5 * u, side=q, n=3)
            left = right = 'hide'
        elif at.startswith('forward'):
            iw = item.get('wpx') or min(3.1 * u, 5.6 * u / asp); ih = item.get('hpx') or iw * asp; ix, iy = cx + sx * 1.55 * u, cy + 4.5 * u
            item['hpx'] = ih if custom else None
            hy = iy + ih * 0.22
            s.tube([(cx + sx * 2.3 * u, cy + 3.8 * u), (ix + sx * 0.4 * u, hy + 0.3 * u)], 1.05 * u, sw=1.6 * kk)
            s.ellipse(ix + sx * iw * 0.3, hy, 0.95 * u, 0.85 * u, fillc=P, sw=1.6 * kk)
            draw_prop(s, dict(item, type=typ), ix, iy, iw)
            draw_fingers(s, ix + sx * iw / 2, hy, 0.8 * u, side=sx, n=4)
            if sx < 0:
                left = 'hide'
            else:
                right = 'hide'
        else:
            iw = item.get('wpx') or min(1.75 * u, 3.7 * u / asp); ih = item.get('hpx') or iw * asp
            item['hpx'] = ih if custom else None
            hx, hy = cx + sx * 3.0 * u, cy + 2.7 * u
            ix, iy = hx, hy - ih * 0.3
            s.tube([(cx + sx * 2.2 * u, cy + 3.5 * u), (cx + sx * 3.4 * u, cy + 4.9 * u), (hx + sx * 0.1 * u, hy + 0.45 * u)], tw, sw=1.5 * kk)
            s.ellipse(hx + sx * iw * 0.28, hy, 0.5 * u, 0.56 * u, fillc=P, sw=1.4 * kk)
            draw_prop(s, dict(item, type=typ), ix, iy, iw)
            draw_fingers(s, hx + sx * iw / 2, hy, 0.48 * u, side=sx, n=4)
            if sx < 0:
                left = 'hide'
            else:
                right = 'hide'
        out['held'] = (ix, iy, iw, ih)
    arm(-1, left); arm(1, right)
    return out


# ───────────────────────────── العناصر (اللي ينصوّر) — أي نوع ينرسم بلون المونتاج لو انحط بقائمة overlay
ASPECT = {'phone': 2.05, 'tablet': 1.36, 'box': 1.0, 'bottle': 2.3, 'perfume': 1.5, 'cup': 1.35, 'can': 1.8, 'jar': 1.25, 'tube': 2.6, 'bag': 1.25,
          'card': 0.63, 'watch': 1.7, 'book': 1.4, 'plate': 0.55, 'mic': 2.2, 'camera': 0.72, 'headphones': 1.05, 'shape': 1.0, 'laptop': 0.74,
          'monitor': 0.78, 'car': 0.4, 'plant': 1.6, 'window': 1.25, 'picture': 1.2, 'shelf': 0.3, 'sofa': 0.5, 'chair': 1.2, 'storefront': 0.95,
          'whiteboard': 0.66, 'lights': 0.2, 'softbox': 1.9, 'ringlight': 2.2, 'tripod': 2.0, 'door': 2.1, 'burger': 0.8, 'shoe': 0.5, 'tv': 0.6, 'keyboard': 0.3}
ALIASES = {'screen': 'monitor', 'display': 'monitor', 'mobile': 'phone', 'iphone': 'phone', 'ipad': 'tablet', 'product': 'box', 'package': 'box', 'coffee': 'cup',
           'mug': 'cup', 'desk': 'table', 'counter': 'table', 'frame': 'picture', 'spotlights': 'lights', 'ring-light': 'ringlight', 'shop': 'storefront',
           'store': 'storefront', 'board': 'whiteboard', 'food': 'plate', 'dish': 'plate', 'microphone': 'mic', 'couch': 'sofa', 'creditcard': 'card',
           'credit-card': 'card', 'bottle-square': 'perfume', 'rect': 'shape', 'circle': 'shape', 'television': 'tv', 'device': 'shape', 'gadget': 'shape',
           'powerbank': 'shape', 'power-bank': 'shape', 'speaker': 'shape'}
BACK_TYPES = {'shelf', 'plant', 'window', 'picture', 'lights', 'sofa', 'chair', 'car', 'storefront', 'whiteboard', 'monitor', 'tv', 'door', 'backdrop',
              'car-interior', 'softbox', 'ringlight'}


def alias(t):
    t = str(t or 'shape').strip().lower().replace('_', '-')
    return ALIASES.get(t, t)


def quad_map(q):
    tl, tr, br, bl = q

    def Q(a, b):
        tx = tl[0] + (tr[0] - tl[0]) * a; ty = tl[1] + (tr[1] - tl[1]) * a
        bx = bl[0] + (br[0] - bl[0]) * a; by = bl[1] + (br[1] - bl[1]) * a
        return (tx + (bx - tx) * b, ty + (by - ty) * b)
    return Q


def screen_content(s, Q, kind, label=None, wpx=60):
    """محتوى شاشة داخل رباعي (يمشي مع ميلان الشاشة)."""
    kind = (kind or ('label' if label else 'blank')).lower()

    def R(a0, b0, a1, b1):
        return [Q(a0, b0), Q(a1, b0), Q(a1, b1), Q(a0, b1)]
    th = clamp(wpx / 110.0, 0.55, 1.2)
    if kind == 'page':
        sh = R(0.13, 0.06, 0.78, 0.94); s.fill(sh, s.paper, smooth=False); s.poly(sh, sw=1.2 * th, j=0.5)
        band = R(0.13, 0.06, 0.78, 0.34); s.fill(band, s.cur, 0.6, smooth=False); s.hatch(band, ang=0.6, gap=3, op=0.5)
        c = Q(0.26, 0.2); s.ellipse(c[0], c[1], wpx * 0.06, wpx * 0.07, fillc=s.paper, sw=1.0 * th, passes=1)
        for i in range(3):
            a, b = Q(0.4, 0.15 + i * 0.06), Q(0.72, 0.15 + i * 0.06); s.line(a[0], a[1], b[0], b[1], sw=1.5 * th, color=s.paper, op=0.95, j=0.3, passes=1)
        s.poly(R(0.17, 0.42, 0.32, 0.7), sw=1.0 * th, op=0.8, j=0.4)
        for i in range(7):
            a, b = Q(0.38, 0.44 + i * 0.07), Q(0.74, 0.44 + i * 0.07); s.line(a[0], a[1], b[0], b[1], sw=1.0 * th, op=0.55, j=0.5, passes=1)
    elif kind == 'chart':
        a, b, c = Q(0.14, 0.12), Q(0.14, 0.86), Q(0.9, 0.86); s.stroke([a, b, c], sw=1.3 * th, j=0.4)
        for i, hgt in enumerate((0.2, 0.32, 0.28, 0.5, 0.66)):
            x0 = 0.22 + i * 0.135; bar = R(x0, 0.86 - hgt, x0 + 0.085, 0.86); s.fill(bar, s.cur, 0.35, smooth=False); s.poly(bar, sw=1.0 * th, j=0.3, passes=1)
        s.arrow([Q(0.2, 0.62), Q(0.45, 0.5), Q(0.62, 0.36), Q(0.86, 0.14)], sw=1.4 * th, head=5)
    elif kind == 'video':
        t = [Q(0.4, 0.3), Q(0.66, 0.5), Q(0.4, 0.7)]; s.fill(t, s.cur, 0.6, smooth=False); s.poly(t, sw=1.2 * th, j=0.3)
        a, b = Q(0.1, 0.9), Q(0.9, 0.9); s.line(a[0], a[1], b[0], b[1], sw=1.6 * th, op=0.6, passes=1)
        c = Q(0.38, 0.9); s.ellipse(c[0], c[1], 2.2 * th, 2.2 * th, fillc=s.cur, sw=0.8, passes=1)
    elif kind == 'chat':
        for i, (a0, a1, b0) in enumerate(((0.1, 0.62, 0.1), (0.36, 0.9, 0.34), (0.1, 0.7, 0.58))):
            bub = R(a0, b0, a1, b0 + 0.17)
            if i == 1:
                s.fill(bub, s.cur, 0.3, smooth=False)
            s.poly(bub, sw=1.1 * th, j=0.4)
            a, b = Q(a0 + 0.06, b0 + 0.085), Q(a1 - 0.06, b0 + 0.085); s.line(a[0], a[1], b[0], b[1], sw=0.9 * th, op=0.5, passes=1)
        s.poly(R(0.1, 0.84, 0.9, 0.94), sw=1.0 * th, op=0.7, j=0.3, passes=1)
    elif kind == 'grid':
        for r in range(3):
            for c in range(3):
                cell = R(0.1 + c * 0.28, 0.1 + r * 0.28, 0.32 + c * 0.28, 0.32 + r * 0.28)
                if (r + c) % 2 == 0:
                    s.hatch(cell, ang=0.7, gap=3.2, op=0.3)
                s.poly(cell, sw=1.0 * th, j=0.3, passes=1)
    elif kind == 'app':
        top = R(0.0, 0.0, 1.0, 0.14); s.fill(top, s.cur, 0.3, smooth=False)
        for i in range(3):
            row = R(0.08, 0.2 + i * 0.25, 0.92, 0.4 + i * 0.25); s.poly(row, sw=1.0 * th, j=0.3, passes=1)
            thumb = R(0.12, 0.23 + i * 0.25, 0.3, 0.37 + i * 0.25); s.hatch(thumb, ang=0.7, gap=3, op=0.35); s.poly(thumb, sw=0.8 * th, j=0.2, passes=1)
            for q in (0.27, 0.33):
                a, b = Q(0.36, q + i * 0.25), Q(0.84 - (q - 0.27) * 3, q + i * 0.25); s.line(a[0], a[1], b[0], b[1], sw=0.9 * th, op=0.5, passes=1)
    elif kind == 'shop':
        img = R(0.12, 0.08, 0.88, 0.5); s.hatch(img, ang=0.7, gap=3.6, op=0.3); s.poly(img, sw=1.0 * th, j=0.3)
        for i, wd in enumerate((0.7, 0.45)):
            a, b = Q(0.14, 0.6 + i * 0.08), Q(0.14 + wd, 0.6 + i * 0.08); s.line(a[0], a[1], b[0], b[1], sw=1.1 * th, op=0.6, passes=1)
        btn = R(0.14, 0.78, 0.86, 0.92); s.fill(btn, s.cur, 0.55, smooth=False); s.poly(btn, sw=1.0 * th, j=0.3, passes=1)
    elif kind == 'code':
        for i, (ind, wd) in enumerate(((0, 0.5), (0.08, 0.6), (0.08, 0.42), (0.16, 0.5), (0.08, 0.3), (0, 0.2), (0, 0.55), (0.08, 0.48))):
            a, b = Q(0.1 + ind, 0.12 + i * 0.1), Q(0.1 + ind + wd, 0.12 + i * 0.1); s.line(a[0], a[1], b[0], b[1], sw=1.1 * th, op=0.6, j=0.3, passes=1)
    elif kind == 'photo':
        s.stroke([Q(0.06, 0.82), Q(0.3, 0.45), Q(0.48, 0.7), Q(0.66, 0.36), Q(0.94, 0.82)], sw=1.2 * th, j=0.5)
        c = Q(0.76, 0.24); s.ellipse(c[0], c[1], wpx * 0.07, wpx * 0.07, sw=1.0 * th, passes=1)
    if label:
        c = Q(0.5, 0.5)
        if kind in ('label', 'blank'):
            s.text(label, c[0], c[1], size=clamp(wpx * 0.17, 9, 26), maxw=wpx * 0.82, kind='label', maxlines=2)
        else:
            size = clamp(wpx * 0.115, 8, 18); lines, sz, ok = fit_text(label, size, wpx * 0.74, 5.0, 2)
            tw = max(text_w(ln, sz) for ln in lines); hh = sz * 1.32 * len(lines)
            s.rbox(c[0] - tw / 2 - sz * 0.6, c[1] - hh / 2 - sz * 0.3, c[0] + tw / 2 + sz * 0.6, c[1] + hh / 2 + sz * 0.3, sz * 0.5, fillc=s.paper, sw=1.0, op=0.8, j=0.3, dash='', passes=1)
            s.text(label, c[0], c[1], size=size, maxw=wpx * 0.74, kind='label', maxlines=2)


def prop_table(s, x, y, w, sp):
    x0 = sp.get('x0px', 0); x1 = sp.get('x1px', s.w)
    if sp.get('fill', True):
        s.fill([(x0, y), (x1, y), (x1, s.h + 4), (x0, s.h + 4)], s.paper, smooth=False)
    s.line(x0 + 4, y, x1 - 4, y, sw=1.7); s.line(x0 + 4, y + 6 * s.K, x1 - 4, y + 6 * s.K, sw=1.0, op=0.45, passes=1)


def prop_laptop(s, x, y, w, sp):
    view = sp.get('view', 'back')
    if view == 'screen':
        h = w * 0.62
        scr = [(x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x + w / 2, y + h / 2), (x - w / 2, y + h / 2)]
        s.fill(scr, s.paper, smooth=False); s.poly(scr, sw=2.0, j=0.9)
        screen_content(s, quad_map([(x - w * 0.46, y - h * 0.44), (x + w * 0.46, y - h * 0.44), (x + w * 0.46, y + h * 0.42), (x - w * 0.46, y + h * 0.42)]), sp.get('content'), sp.get('label'), w * 0.92)
        base = [(x - w / 2, y + h / 2), (x + w / 2, y + h / 2), (x + w * 0.62, y + h / 2 + w * 0.26), (x - w * 0.62, y + h / 2 + w * 0.26)]
        s.fill(base, s.paper, smooth=False); s.poly(base, sw=1.7, j=0.8)
        for i in range(4):
            yy = y + h / 2 + w * (0.04 + i * 0.035); sp_ = w * (0.46 + i * 0.022)
            s.line(x - sp_, yy, x + sp_, yy, sw=0.8, op=0.45, j=0.3, passes=1)
        s.poly([(x - w * 0.14, y + h / 2 + w * 0.19), (x + w * 0.14, y + h / 2 + w * 0.19), (x + w * 0.15, y + h / 2 + w * 0.245), (x - w * 0.15, y + h / 2 + w * 0.245)], sw=0.9, op=0.6, j=0.3, passes=1)
        return
    h = w * 0.7
    lid = [(x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x + w / 2 + w * 0.015, y + h / 2), (x - w / 2 - w * 0.015, y + h / 2)]
    s.fill(lid, s.paper, smooth=False); s.hatch(lid, ang=-0.5, gap=7, op=0.15); s.poly(lid, sw=2.2, j=0.9)
    s.poly([(x - w * 0.55, y + h / 2), (x + w * 0.55, y + h / 2), (x + w * 0.57, y + h / 2 + w * 0.04), (x - w * 0.57, y + h / 2 + w * 0.04)], fillc=s.paper, sw=1.5, j=0.8)
    logo = sp.get('logo', sp.get('label'))
    if logo == 'apple':
        A = w * 0.073; ax, ay = x, y
        ap = [(0, -0.5), (0.38, -0.74), (0.82, -0.5), (0.96, 0.02), (0.74, 0.62), (0.4, 0.96), (0, 0.8), (-0.4, 0.96), (-0.74, 0.62), (-0.96, 0.02), (-0.82, -0.5), (-0.38, -0.74)]
        s.fill([(ax + px * A, ay + py * A) for px, py in ap], s.cur, 0.88); s.fill(s.epts(ax + A * 1.0, ay - A * 0.12, A * 0.42, A * 0.42, n=10)[:-1], s.paper)
        s.fill(s.epts(ax + A * 0.22, ay - A * 1.2, A * 0.34, A * 0.16, n=8, rot=-0.8)[:-1], s.cur, 0.88)
    elif logo:
        s.text(logo, x, y, size=clamp(w * 0.12, 9, 24), maxw=w * 0.7, kind='label', maxlines=1)


def prop_monitor(s, x, y, w, sp):
    h = sp.get('hpx') or w * (0.6 if sp.get('type') == 'tv' else 0.62)
    t = clamp(float(sp.get('tilt', 0)), -1, 1) * 0.14
    q = [(x - w / 2, y - h / 2 * (1 + t)), (x + w / 2, y - h / 2 * (1 - t)), (x + w / 2, y + h / 2 * (1 - t)), (x - w / 2, y + h / 2 * (1 + t))]
    if sp.get('stand', sp.get('type') != 'tv'):
        s.poly([(x - w * 0.05, y + h / 2 - 2), (x - w * 0.04, y + h / 2 + w * 0.15)], closed=False, sw=1.7)
        s.poly([(x + w * 0.05, y + h / 2 - 2), (x + w * 0.05, y + h / 2 + w * 0.14)], closed=False, sw=1.7)
        s.ellipse(x, y + h / 2 + w * 0.17, w * 0.2, w * 0.04, fillc=s.paper, sw=1.5)
    s.fill(q, s.paper, smooth=False); s.hatch(q, ang=0.5, gap=4.5, op=0.16); s.poly(q, sw=2.3, j=0.9)
    Q = quad_map(q); ins = [Q(0.04, 0.05), Q(0.96, 0.05), Q(0.96, 0.95), Q(0.04, 0.95)]
    screen_content(s, quad_map(ins), sp.get('content'), sp.get('label'), w * 0.9)


def prop_phone(s, x, y, w, sp):
    h = sp.get('hpx') or w * ASPECT['tablet' if sp.get('type') == 'tablet' else 'phone']
    r = w * (0.07 if sp.get('type') == 'tablet' else 0.16)
    s.rbox(x - w / 2, y - h / 2, x + w / 2, y + h / 2, r, fillc=s.paper, sw=2.0 * clamp(w / 60, 0.6, 1.2), j=0.7)
    if sp.get('view') == 'back':
        s.rbox(x - w * 0.36, y - h * 0.42, x - w * 0.02, y - h * 0.42 + w * 0.34, w * 0.08, sw=1.1, j=0.3, passes=1)
        for dx, dy in ((-0.27, 0.09), (-0.11, 0.09), (-0.19, 0.25)):
            s.ellipse(x + w * dx, y - h * 0.42 + w * dy, w * 0.06, w * 0.06, fillc=s.cur, fop=0.5, sw=0.8, j=0.2, passes=1)
        if sp.get('label'):
            s.text(sp['label'], x, y + h * 0.1, size=clamp(w * 0.2, 8, 20), maxw=w * 0.8, kind='label', maxlines=1)
        return
    m = w * 0.07
    ins = [(x - w / 2 + m, y - h / 2 + m), (x + w / 2 - m, y - h / 2 + m), (x + w / 2 - m, y + h / 2 - m), (x - w / 2 + m, y + h / 2 - m)]
    s.poly(ins, sw=0.9, op=0.5, j=0.3, passes=1)
    if sp.get('type') != 'tablet':
        s.rbox(x - w * 0.13, y - h / 2 + m * 1.35, x + w * 0.13, y - h / 2 + m * 1.35 + w * 0.07, w * 0.035, fillc=s.cur, fop=0.75, sw=0.6, j=0.2, passes=1)
        ins[0] = (ins[0][0], ins[0][1] + w * 0.16); ins[1] = (ins[1][0], ins[1][1] + w * 0.16)
    screen_content(s, quad_map(ins), sp.get('content'), sp.get('label'), w * 0.86)


def _label(s, sp, x, y, maxw, size):
    if sp.get('label'):
        s.text(sp['label'], x, y, size=size, maxw=maxw, kind='label', maxlines=2)


def _mini_screen(s, x, y, w, h, txt):
    """شاشة صغيرة على جهاز، مكتوب فيها اللي يطلع عليها."""
    s.rbox(x - w / 2, y - h / 2, x + w / 2, y + h / 2, min(w, h) * 0.18, fillc=s.paper, sw=1.4, j=0.4)
    if txt is not True:
        s.text(str(txt), x, y, size=clamp(h * 0.62, 6, 22), maxw=w * 0.84, kind='label', maxlines=1)


def prop_box(s, x, y, w, sp):
    h = sp.get('hpx') or w * ASPECT['box']; d = w * 0.16
    f = [(x - w / 2, y - h / 2 + d * 0.5), (x + w / 2 - d, y - h / 2 + d * 0.5), (x + w / 2 - d, y + h / 2), (x - w / 2, y + h / 2)]
    top = [f[0], (x - w / 2 + d, y - h / 2 - d * 0.1), (x + w / 2, y - h / 2 - d * 0.1), f[1]]
    side = [f[1], (x + w / 2, y - h / 2 - d * 0.1), (x + w / 2, y + h / 2 - d * 0.6), f[2]]
    s.fill(f, s.paper, smooth=False); s.fill(top, s.paper, smooth=False); s.fill(side, s.paper, smooth=False)
    s.hatch(side, ang=-1.0, gap=3.2, op=0.35); s.poly(f, sw=1.9, j=0.7); s.poly(top, sw=1.4, j=0.6); s.poly(side, sw=1.4, j=0.6)
    fx = (f[0][0] + f[1][0]) / 2; fy = (f[0][1] + f[2][1]) / 2; fw = f[1][0] - f[0][0]
    if sp.get('screen'):
        _mini_screen(s, fx, fy - h * 0.2, fw * 0.62, h * 0.22, sp['screen'])
        _label(s, sp, fx, fy + h * 0.16, fw * 0.84, clamp(fw * 0.18, 8, 24))
    elif sp.get('label'):
        _label(s, sp, fx, fy, fw * 0.84, clamp(fw * 0.2, 8, 26))
    else:
        s.poly([(fx - fw * 0.3, fy - h * 0.12), (fx + fw * 0.3, fy - h * 0.12), (fx + fw * 0.3, fy + h * 0.12), (fx - fw * 0.3, fy + h * 0.12)], sw=1.0, op=0.6, j=0.4, passes=1)


def prop_bottle(s, x, y, w, sp):
    sq = sp.get('type') == 'perfume'
    h = sp.get('hpx') or w * ASPECT['perfume' if sq else 'bottle']
    t = y - h / 2; b = y + h / 2
    if sq:
        s.rbox(x - w * 0.2, t, x + w * 0.2, t + h * 0.2, w * 0.04, fillc=s.cur, fop=0.6, sw=1.3, j=0.4)
        s.poly([(x - w * 0.1, t + h * 0.2), (x + w * 0.1, t + h * 0.2), (x + w * 0.1, t + h * 0.28), (x - w * 0.1, t + h * 0.28)], sw=1.2, j=0.3, passes=1)
        body = s.rbox(x - w / 2, t + h * 0.28, x + w / 2, b, w * 0.1, fillc=s.paper, sw=1.9, j=0.7)
        s.hatch([(x + w * 0.24, t + h * 0.3), (x + w / 2, t + h * 0.3), (x + w / 2, b), (x + w * 0.24, b)], ang=-1.1, gap=3.2, op=0.25)
        _label(s, sp, x, t + h * 0.66, w * 0.8, clamp(w * 0.2, 7.5, 22))
        if not sp.get('label'):
            s.poly([(x - w * 0.3, t + h * 0.52), (x + w * 0.3, t + h * 0.52), (x + w * 0.3, t + h * 0.8), (x - w * 0.3, t + h * 0.8)], sw=1.0, op=0.6, j=0.4, passes=1)
        return
    body = [(x - w * 0.16, t + h * 0.1), (x - w * 0.17, t + h * 0.2), (x - w * 0.46, t + h * 0.34), (x - w / 2, t + h * 0.46), (x - w / 2, b - w * 0.1), (x - w * 0.4, b),
            (x + w * 0.4, b), (x + w / 2, b - w * 0.1), (x + w / 2, t + h * 0.46), (x + w * 0.46, t + h * 0.34), (x + w * 0.17, t + h * 0.2), (x + w * 0.16, t + h * 0.1)]
    s.fill(body, s.paper); s.stroke(body, sw=1.9, j=0.7, closed=True)
    s.rbox(x - w * 0.2, t, x + w * 0.2, t + h * 0.1, w * 0.04, fillc=s.cur, fop=0.6, sw=1.3, j=0.4)
    lab = [(x - w / 2, t + h * 0.52), (x + w / 2, t + h * 0.52), (x + w / 2, t + h * 0.8), (x - w / 2, t + h * 0.8)]
    s.poly(lab, sw=1.1, op=0.8, j=0.4, passes=1)
    s.hatch([(x + w * 0.28, t + h * 0.36), (x + w / 2, t + h * 0.4), (x + w / 2, t + h * 0.5), (x + w * 0.28, t + h * 0.5)], ang=-1.1, gap=3, op=0.25)
    _label(s, sp, x, t + h * 0.66, w * 0.86, clamp(w * 0.22, 7.5, 22))


def prop_cup(s, x, y, w, sp):
    h = sp.get('hpx') or w * ASPECT['cup']; t = y - h / 2; b = y + h / 2
    cup = [(x - w * 0.46, t + h * 0.16), (x + w * 0.46, t + h * 0.16), (x + w * 0.34, b), (x - w * 0.34, b)]
    s.fill(cup, s.paper, smooth=False); s.poly(cup, sw=1.9, j=0.7)
    s.rbox(x - w / 2, t + h * 0.06, x + w / 2, t + h * 0.17, w * 0.05, fillc=s.paper, sw=1.5, j=0.5)
    s.rbox(x - w * 0.36, t, x + w * 0.36, t + h * 0.07, w * 0.04, fillc=s.paper, sw=1.2, j=0.4, passes=1)
    band = [(x - w * 0.43, t + h * 0.4), (x + w * 0.43, t + h * 0.4), (x + w * 0.38, t + h * 0.78), (x - w * 0.38, t + h * 0.78)]
    s.hatch(band, ang=-0.9, gap=3.4, op=0.22); s.poly(band, sw=1.0, op=0.8, j=0.4, passes=1)
    _label(s, sp, x, t + h * 0.59, w * 0.7, clamp(w * 0.2, 7.5, 20))
    if sp.get('steam'):
        for dx in (-0.16, 0.06, 0.26):
            s.stroke([(x + w * dx, t - h * 0.04), (x + w * (dx + 0.07), t - h * 0.14), (x + w * (dx - 0.04), t - h * 0.24), (x + w * (dx + 0.05), t - h * 0.34)], sw=1.0, op=0.5, j=0.5, passes=1)


def prop_can(s, x, y, w, sp):
    jar = sp.get('type') == 'jar'
    h = sp.get('hpx') or w * ASPECT['jar' if jar else 'can']; t = y - h / 2; b = y + h / 2; e = w * 0.1
    body = [(x - w / 2, t + e), (x + w / 2, t + e), (x + w / 2, b - e), (x + w * 0.3, b), (x - w * 0.3, b), (x - w / 2, b - e)]
    s.fill(body, s.paper, smooth=False); s.poly(body, sw=1.9, j=0.7)
    if jar:
        s.rbox(x - w * 0.52, t - e * 0.4, x + w * 0.52, t + e * 1.6, e * 0.5, fillc=s.cur, fop=0.55, sw=1.5, j=0.5)
    else:
        s.ellipse(x, t + e, w / 2, e, fillc=s.paper, sw=1.5)
        s.ellipse(x + w * 0.08, t + e, w * 0.13, e * 0.4, sw=0.9, op=0.6, passes=1)
    s.hatch([(x + w * 0.26, t + e * 2), (x + w / 2, t + e * 2), (x + w / 2, b - e), (x + w * 0.26, b - e)], ang=-1.1, gap=3, op=0.25)
    _label(s, sp, x, y + h * 0.06, w * 0.8, clamp(w * 0.22, 7.5, 22))
    if not sp.get('label'):
        s.poly([(x - w * 0.34, y - h * 0.1), (x + w * 0.2, y - h * 0.1), (x + w * 0.2, y + h * 0.2), (x - w * 0.34, y + h * 0.2)], sw=1.0, op=0.6, j=0.4, passes=1)


def prop_tube(s, x, y, w, sp):
    h = sp.get('hpx') or w * ASPECT['tube']; t = y - h / 2; b = y + h / 2
    body = [(x - w / 2, t), (x + w / 2, t), (x + w * 0.3, b - h * 0.14), (x - w * 0.3, b - h * 0.14)]
    s.fill(body, s.paper, smooth=False); s.poly(body, sw=1.9, j=0.7)
    s.line(x - w / 2, t + h * 0.035, x + w / 2, t + h * 0.035, sw=1.0, op=0.6, passes=1)
    s.rbox(x - w * 0.24, b - h * 0.14, x + w * 0.24, b, w * 0.05, fillc=s.cur, fop=0.6, sw=1.4, j=0.4)
    _label(s, sp, x, t + h * 0.4, w * 0.74, clamp(w * 0.22, 7.5, 20))


def prop_bag(s, x, y, w, sp):
    h = sp.get('hpx') or w * ASPECT['bag']; t = y - h / 2 + h * 0.2; b = y + h / 2
    for dx in (-0.2, 0.2):
        s.stroke([(x + w * (dx - 0.1), t), (x + w * (dx - 0.07), t - h * 0.18), (x + w * (dx + 0.07), t - h * 0.18), (x + w * (dx + 0.1), t)], sw=1.4, j=0.5)
    body = [(x - w * 0.44, t), (x + w * 0.44, t), (x + w / 2, b), (x - w / 2, b)]
    s.fill(body, s.paper, smooth=False); s.poly(body, sw=1.9, j=0.7)
    s.hatch([(x + w * 0.3, t), (x + w * 0.44, t), (x + w / 2, b), (x + w * 0.34, b)], ang=-1.1, gap=3, op=0.25)
    _label(s, sp, x - w * 0.03, (t + b) / 2, w * 0.7, clamp(w * 0.2, 7.5, 24))


def prop_card(s, x, y, w, sp):
    h = sp.get('hpx') or w * ASPECT['card']
    s.rbox(x - w / 2, y - h / 2, x + w / 2, y + h / 2, w * 0.06, fillc=s.paper, sw=1.8, j=0.6)
    s.rbox(x - w * 0.38, y - h * 0.2, x - w * 0.2, y + h * 0.05, w * 0.02, fillc=s.cur, fop=0.4, sw=1.0, j=0.3, passes=1)
    s.line(x - w * 0.38, y + h * 0.28, x + w * 0.2, y + h * 0.28, sw=1.1, op=0.6, passes=1)
    if sp.get('label'):
        s.text(sp['label'], x + w * 0.12, y - h * 0.2, size=clamp(w * 0.12, 7, 18), maxw=w * 0.5, kind='label', maxlines=1)


def prop_watch(s, x, y, w, sp):
    h = w * ASPECT['watch']
    for sgn in (-1, 1):
        st = [(x - w * 0.3, y + sgn * w * 0.4), (x + w * 0.3, y + sgn * w * 0.4), (x + w * 0.24, y + sgn * h / 2), (x - w * 0.24, y + sgn * h / 2)]
        s.fill(st, s.paper, smooth=False); s.hatch(st, ang=0.1, gap=3.4, op=0.3); s.poly(st, sw=1.4, j=0.5)
    s.rbox(x - w / 2, y - w * 0.5, x + w / 2, y + w * 0.5, w * 0.2, fillc=s.paper, sw=2.0, j=0.6)
    s.rbox(x - w * 0.4, y - w * 0.4, x + w * 0.4, y + w * 0.4, w * 0.15, sw=0.9, op=0.5, j=0.3, passes=1)
    if sp.get('label'):
        s.text(sp['label'], x, y, size=clamp(w * 0.22, 7, 18), maxw=w * 0.7, kind='label', maxlines=1)
    else:
        s.line(x, y, x, y - w * 0.24, sw=1.3, passes=1); s.line(x, y, x + w * 0.18, y + w * 0.06, sw=1.3, passes=1)


def prop_book(s, x, y, w, sp):
    h = sp.get('hpx') or w * ASPECT['book']
    cov = [(x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x + w / 2, y + h / 2), (x - w / 2, y + h / 2)]
    s.fill(cov, s.paper, smooth=False); s.poly(cov, sw=1.9, j=0.7); s.line(x - w * 0.4, y - h / 2, x - w * 0.4, y + h / 2, sw=1.0, op=0.6, passes=1)
    if sp.get('label'):
        s.text(sp['label'], x + w * 0.04, y - h * 0.12, size=clamp(w * 0.18, 7.5, 22), maxw=w * 0.72, kind='label', maxlines=3)
    else:
        for i in range(3):
            s.line(x - w * 0.24, y - h * 0.2 + i * h * 0.1, x + w * (0.34 - i * 0.1), y - h * 0.2 + i * h * 0.1, sw=1.2, op=0.6, passes=1)


def prop_plate(s, x, y, w, sp):
    h = w * ASPECT['plate']
    s.ellipse(x, y, w / 2, h / 2, fillc=s.paper, sw=1.8); s.ellipse(x, y, w * 0.36, h * 0.34, sw=0.9, op=0.5, passes=1)
    food = [(x - w * 0.26, y), (x - w * 0.14, y - h * 0.42), (x + w * 0.06, y - h * 0.56), (x + w * 0.24, y - h * 0.3), (x + w * 0.28, y + h * 0.04), (x, y + h * 0.16)]
    s.fill(food, s.paper); s.hatch(food, ang=0.8, gap=3, op=0.4, smooth=True); s.stroke(food, sw=1.5, closed=True, j=0.8)
    if sp.get('label'):
        s.text(sp['label'], x, y + h * 0.82, size=clamp(w * 0.13, 8, 18), maxw=w, kind='label', maxlines=1)


def prop_burger(s, x, y, w, sp):
    h = w * ASPECT['burger']; t = y - h / 2
    bun = s.epts(x, t + h * 0.42, w / 2, h * 0.42, math.radians(180), math.radians(360), n=10)
    s.fill(bun, s.paper); s.stroke(bun, sw=1.8, closed=True)
    for i in range(5):
        s.line(x - w * 0.3 + i * w * 0.14, t + h * (0.18 + (i % 2) * 0.08), x - w * 0.27 + i * w * 0.14, t + h * (0.2 + (i % 2) * 0.08), sw=1.2, passes=1)
    s.stroke([(x - w * 0.52, t + h * 0.5), (x - w * 0.3, t + h * 0.6), (x - w * 0.1, t + h * 0.5), (x + w * 0.1, t + h * 0.6), (x + w * 0.3, t + h * 0.5), (x + w * 0.52, t + h * 0.6)], sw=1.4, j=0.6)
    pat = [(x - w * 0.48, t + h * 0.62), (x + w * 0.48, t + h * 0.62), (x + w * 0.48, t + h * 0.78), (x - w * 0.48, t + h * 0.78)]
    s.fill(pat, s.cur, 0.55, smooth=False); s.hatch(pat, ang=0.6, gap=2.6, op=0.5)
    s.rbox(x - w / 2, t + h * 0.8, x + w / 2, t + h, h * 0.1, fillc=s.paper, sw=1.7, j=0.6)


def prop_shoe(s, x, y, w, sp):
    h = w * ASPECT['shoe']; b = y + h / 2
    sh = [(x - w / 2, b - h * 0.2), (x - w * 0.46, b - h * 0.9), (x - w * 0.2, b - h * 0.95), (x - w * 0.05, b - h * 0.6), (x + w * 0.3, b - h * 0.42), (x + w / 2, b - h * 0.2), (x + w / 2, b), (x - w / 2, b)]
    s.fill(sh, s.paper); s.stroke(sh, sw=1.8, closed=True, j=0.7)
    s.line(x - w / 2, b - h * 0.16, x + w / 2, b - h * 0.16, sw=1.2, op=0.7, passes=1)
    for i in range(3):
        s.line(x - w * 0.12 + i * w * 0.1, b - h * 0.62 + i * h * 0.05, x - w * 0.02 + i * w * 0.1, b - h * 0.8 + i * h * 0.06, sw=1.0, op=0.6, passes=1)


def prop_mic(s, x, y, w, sp):
    h = w * ASPECT['mic']; t = y - h / 2
    s.rbox(x - w * 0.3, t, x + w * 0.3, t + h * 0.46, w * 0.28, fillc=s.paper, sw=1.9, j=0.6)
    s.hatch(s.rrect(x - w * 0.3, t, x + w * 0.3, t + h * 0.3, w * 0.28), ang=0.8, gap=2.8, op=0.4, smooth=True)
    s.hatch(s.rrect(x - w * 0.3, t, x + w * 0.3, t + h * 0.3, w * 0.28), ang=-0.8, gap=2.8, op=0.4, smooth=True)
    s.stroke([(x - w * 0.44, t + h * 0.3), (x - w * 0.42, t + h * 0.52), (x, t + h * 0.6), (x + w * 0.42, t + h * 0.52), (x + w * 0.44, t + h * 0.3)], sw=1.4, j=0.4)
    s.line(x, t + h * 0.6, x, t + h * 0.92, sw=1.8); s.ellipse(x, t + h * 0.95, w * 0.42, w * 0.08, fillc=s.paper, sw=1.5)


def prop_camera(s, x, y, w, sp):
    h = w * ASPECT['camera']
    s.rbox(x - w / 2, y - h * 0.34, x + w / 2, y + h / 2, w * 0.06, fillc=s.paper, sw=1.9, j=0.6)
    s.poly([(x - w * 0.2, y - h * 0.34), (x - w * 0.12, y - h / 2), (x + w * 0.12, y - h / 2), (x + w * 0.2, y - h * 0.34)], closed=False, sw=1.5, j=0.5)
    s.ellipse(x, y + h * 0.08, w * 0.24, w * 0.24, fillc=s.paper, sw=1.8); s.ellipse(x, y + h * 0.08, w * 0.15, w * 0.15, fillc=s.cur, fop=0.5, sw=1.0, passes=1)
    s.rbox(x + w * 0.28, y - h * 0.24, x + w * 0.42, y - h * 0.1, w * 0.02, sw=1.0, op=0.7, j=0.3, passes=1)
    if sp.get('tripod'):
        for dx in (-0.36, 0, 0.36):
            s.line(x, y + h / 2, x + w * dx, y + h / 2 + w * 1.5, sw=1.5)


def prop_headphones(s, x, y, w, sp):
    h = w * ASPECT['headphones']
    s.stroke(s.epts(x, y, w * 0.42, h * 0.46, math.radians(180), math.radians(360), n=10), sw=2.6, j=0.6)
    for sx in (-1, 1):
        s.rbox(x + sx * w * 0.42 - w * 0.12, y - h * 0.04, x + sx * w * 0.42 + w * 0.12, y + h * 0.46, w * 0.1, fillc=s.cur, fop=0.5, sw=1.6, j=0.5)


def prop_keyboard(s, x, y, w, sp):
    h = w * ASPECT['keyboard']
    kb = [(x - w * 0.46, y - h / 2), (x + w * 0.46, y - h / 2), (x + w / 2, y + h / 2), (x - w / 2, y + h / 2)]
    s.fill(kb, s.paper, smooth=False); s.poly(kb, sw=1.3, j=0.5)
    for i in range(3):
        yy = y - h * 0.25 + i * h * 0.25; s.line(x - w * 0.43, yy, x + w * 0.43, yy, sw=0.8, op=0.5, j=0.3, passes=1)


def prop_shape(s, x, y, w, sp):
    form = sp.get('shape') or {'circle': 'circle', 'rect': 'rect'}.get(str(sp.get('type')), 'round')
    h = sp.get('hpx') or w * float(sp.get('ratio', 1.0))
    if form == 'circle':
        pts = s.epts(x, y, w / 2, h / 2, n=18)[:-1]; s.fill(pts, s.paper); s.ellipse(x, y, w / 2, h / 2, sw=1.9)
    else:
        pts = s.rbox(x - w / 2, y - h / 2, x + w / 2, y + h / 2, 0 if form == 'rect' else min(w, h) * 0.12, fillc=s.paper, sw=1.9, j=0.7)
    if sp.get('hatch', True):
        s.hatch(pts, ang=-0.7, gap=6, op=0.16, smooth=True)
    if sp.get('screen'):
        _mini_screen(s, x, y - h * 0.24, w * 0.6, h * 0.24, sp['screen'])
        _label(s, sp, x, y + h * 0.16, w * 0.82, clamp(min(w, h) * 0.18, 8, 24))
    else:
        _label(s, sp, x, y, w * 0.82, clamp(min(w, h) * 0.2, 8.5, 26))


def prop_shelf(s, x, y, w, sp):
    s.line(x - w / 2, y, x + w / 2, y, sw=1.3, op=0.75); s.line(x - w / 2, y + 4 * s.K, x + w / 2, y + 4 * s.K, sw=0.9, op=0.45, passes=1)
    xx = x - w * 0.42
    for hgt in (0.26, 0.34, 0.22, 0.3):
        bw = w * 0.09; s.poly([(xx, y), (xx, y - w * hgt), (xx + bw, y - w * hgt), (xx + bw, y)], closed=False, sw=0.95, op=0.7, j=0.5, passes=1); xx += bw + w * 0.02
    s.poly([(x + w * 0.1, y), (x + w * 0.1, y - w * 0.2), (x + w * 0.28, y - w * 0.2), (x + w * 0.28, y)], closed=False, sw=0.9, op=0.7, j=0.5, passes=1)
    s.ellipse(x + w * 0.4, y - w * 0.1, w * 0.07, w * 0.09, sw=0.9, op=0.7, passes=1)


def prop_plant(s, x, y, w, sp):
    h = w * ASPECT['plant']; b = y + h / 2
    for ang, ln in ((-1.9, 0.9), (-1.57, 1.0), (-1.2, 0.9), (-2.3, 0.7), (-0.85, 0.7)):
        tipx = x + math.cos(ang) * h * 0.62 * ln; tipy = b - h * 0.34 + math.sin(ang) * h * 0.62 * ln
        mx = (x + tipx) / 2; my = (b - h * 0.34 + tipy) / 2; nx = -(tipy - (b - h * 0.34)); ny = tipx - x; nn = math.hypot(nx, ny) or 1
        leaf = [(x, b - h * 0.34), (mx + nx / nn * w * 0.12, my + ny / nn * w * 0.12), (tipx, tipy), (mx - nx / nn * w * 0.12, my - ny / nn * w * 0.12)]
        s.fill(leaf, s.paper); s.stroke(leaf, sw=1.1, op=0.8, closed=True, j=0.5, passes=1)
    pot = [(x - w * 0.3, b - h * 0.34), (x + w * 0.3, b - h * 0.34), (x + w * 0.22, b), (x - w * 0.22, b)]
    s.fill(pot, s.paper, smooth=False); s.hatch(pot, ang=-0.9, gap=3, op=0.3); s.poly(pot, sw=1.3, j=0.5)


def prop_window(s, x, y, w, sp):
    h = sp.get('hpx') or w * ASPECT['window']
    r = [(x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x + w / 2, y + h / 2), (x - w / 2, y + h / 2)]
    s.poly(r, sw=1.4, op=0.8, j=0.7); s.line(x, y - h / 2, x, y + h / 2, sw=1.0, op=0.6, passes=1); s.line(x - w / 2, y, x + w / 2, y, sw=1.0, op=0.6, passes=1)
    for i in range(3):
        s.line(x - w * 0.36 + i * w * 0.12, y - h * 0.36, x - w * 0.46 + i * w * 0.12, y - h * 0.12, sw=0.8, op=0.4, passes=1)


def prop_picture(s, x, y, w, sp):
    h = sp.get('hpx') or w * ASPECT['picture']
    r = [(x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x + w / 2, y + h / 2), (x - w / 2, y + h / 2)]
    s.poly(r, sw=1.3, op=0.8, j=0.6)
    if sp.get('label'):
        s.text(sp['label'], x, y, size=clamp(w * 0.2, 7.5, 18), maxw=w * 0.84, kind='label', maxlines=2, op=0.85)
    else:
        s.stroke([(x - w * 0.4, y + h * 0.3), (x - w * 0.12, y - h * 0.1), (x + w * 0.06, y + h * 0.14), (x + w * 0.2, y - h * 0.04), (x + w * 0.4, y + h * 0.3)], sw=0.9, op=0.6, j=0.5, passes=1)


def prop_lights(s, x, y, w, sp):
    s.line(x - w / 2, y, x + w / 2, y, sw=1.5)
    for dx in (-0.3, 0.02, 0.36):
        xx = x + w * dx; s.poly([(xx - 6 * s.K, y + 2), (xx + 6 * s.K, y + 2), (xx + 4 * s.K, y + 18 * s.K), (xx - 8 * s.K, y + 16 * s.K)], sw=1.1, j=0.6, passes=1)


def prop_softbox(s, x, y, w, sp):
    h = w * ASPECT['softbox']; t = y - h / 2
    box = [(x - w / 2, t), (x + w / 2, t), (x + w * 0.4, t + h * 0.34), (x - w * 0.4, t + h * 0.34)]
    s.fill(box, s.paper, smooth=False); s.hatch(box, ang=0.0, gap=4, op=0.25); s.poly(box, sw=1.5, j=0.6)
    s.line(x, t + h * 0.34, x, y + h / 2, sw=1.5)
    for dx in (-0.4, 0.4):
        s.line(x, y + h * 0.38, x + w * dx, y + h / 2, sw=1.2)


def prop_ringlight(s, x, y, w, sp):
    h = w * ASPECT['ringlight']; t = y - h / 2
    s.ellipse(x, t + w / 2, w / 2, w / 2, sw=1.8); s.ellipse(x, t + w / 2, w * 0.36, w * 0.36, sw=1.2, op=0.7)
    s.line(x, t + w, x, y + h / 2, sw=1.5)
    for dx in (-0.4, 0.4):
        s.line(x, y + h * 0.4, x + w * dx, y + h / 2, sw=1.2)


def prop_sofa(s, x, y, w, sp):
    h = w * ASPECT['sofa']
    s.rbox(x - w * 0.44, y - h / 2, x + w * 0.44, y + h * 0.2, w * 0.05, fillc=s.paper, sw=1.6, j=0.7)
    s.hatch(s.rrect(x - w * 0.44, y - h / 2, x + w * 0.44, y + h * 0.2, w * 0.05), ang=-0.6, gap=6, op=0.14, smooth=True)
    for sx in (-1, 1):
        s.rbox(x + sx * w * 0.44 - w * 0.07, y - h * 0.14, x + sx * w * 0.44 + w * 0.07, y + h / 2, w * 0.04, fillc=s.paper, sw=1.5, j=0.6)
    s.rbox(x - w * 0.38, y + h * 0.14, x + w * 0.38, y + h * 0.46, w * 0.03, fillc=s.paper, sw=1.4, j=0.6)


def prop_chair(s, x, y, w, sp):
    h = w * ASPECT['chair']
    s.rbox(x - w / 2, y - h / 2, x + w / 2, y + h / 2, w * 0.14, fillc=s.paper, sw=1.5, j=0.6)
    s.hatch(s.rrect(x - w / 2, y - h / 2, x + w / 2, y + h / 2, w * 0.14), ang=-0.6, gap=5, op=0.16, smooth=True)


def prop_door(s, x, y, w, sp):
    h = w * ASPECT['door']
    s.poly([(x - w / 2, y + h / 2), (x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x + w / 2, y + h / 2)], closed=False, sw=1.4, op=0.8, j=0.7)
    s.ellipse(x + w * 0.32, y + h * 0.05, w * 0.05, w * 0.05, sw=1.0, passes=1)


def prop_whiteboard(s, x, y, w, sp):
    h = sp.get('hpx') or w * ASPECT['whiteboard']
    r = [(x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x + w / 2, y + h / 2), (x - w / 2, y + h / 2)]
    s.fill(r, s.paper, smooth=False); s.poly(r, sw=1.7, j=0.7)
    screen_content(s, quad_map(r), sp.get('content') or ('label' if sp.get('label') else 'code'), sp.get('label'), w)


def prop_storefront(s, x, y, w, sp):
    h = sp.get('hpx') or w * ASPECT['storefront']; t = y - h / 2; b = y + h / 2
    s.poly([(x - w / 2, b), (x - w / 2, t), (x + w / 2, t), (x + w / 2, b)], closed=False, sw=1.6, j=0.8)
    sign = [(x - w * 0.44, t + h * 0.06), (x + w * 0.44, t + h * 0.06), (x + w * 0.44, t + h * 0.26), (x - w * 0.44, t + h * 0.26)]
    s.fill(sign, s.paper, smooth=False); s.poly(sign, sw=1.5, j=0.6)
    if sp.get('label'):
        s.text(sp['label'], x, t + h * 0.16, size=clamp(w * 0.1, 8.5, 24), maxw=w * 0.8, kind='label', maxlines=1)
    else:
        s.hatch(sign, ang=0.5, gap=4, op=0.25)
    aw = [(x - w * 0.48, t + h * 0.3), (x + w * 0.48, t + h * 0.3), (x + w * 0.52, t + h * 0.4), (x - w * 0.52, t + h * 0.4)]
    s.hatch(aw, ang=1.57, gap=7, op=0.4); s.poly(aw, sw=1.2, j=0.5)
    s.poly([(x + w * 0.12, b), (x + w * 0.12, t + h * 0.46), (x + w * 0.38, t + h * 0.46), (x + w * 0.38, b)], closed=False, sw=1.3, j=0.6)
    win = [(x - w * 0.4, t + h * 0.48), (x + w * 0.02, t + h * 0.48), (x + w * 0.02, t + h * 0.86), (x - w * 0.4, t + h * 0.86)]
    s.poly(win, sw=1.2, j=0.6); s.line(x - w * 0.34, t + h * 0.56, x - w * 0.2, t + h * 0.74, sw=0.8, op=0.4, passes=1)
    s.line(0, b, s.w, b, sw=1.2, op=0.6, passes=1)


def prop_car(s, x, y, w, sp):
    if sp.get('view') == 'front':
        h = w * 0.72; t = y - h / 2; b = y + h / 2
        for sx in (-1, 1):
            s.rbox(x + sx * w * 0.36 - w * 0.08, b - h * 0.2, x + sx * w * 0.36 + w * 0.08, b, w * 0.03, fillc=s.cur, fop=0.7, sw=1.3, j=0.4)
        body = s.rrect(x - w / 2, t + h * 0.42, x + w / 2, b - h * 0.1, w * 0.07)
        cab = [(x - w * 0.36, t + h * 0.44), (x - w * 0.27, t + h * 0.06), (x - w * 0.18, t), (x + w * 0.18, t), (x + w * 0.27, t + h * 0.06), (x + w * 0.36, t + h * 0.44)]
        s.fill(cab, s.paper); s.stroke(cab, sw=1.8, j=0.7)
        ws = [(x - w * 0.3, t + h * 0.4), (x - w * 0.22, t + h * 0.1), (x + w * 0.22, t + h * 0.1), (x + w * 0.3, t + h * 0.4)]
        s.hatch(ws, ang=0.8, gap=5, op=0.2); s.poly(ws, sw=1.2, j=0.5)
        s.fill(body, s.paper); s.stroke(body, sw=2.0, closed=True, j=0.7)
        for sx in (-1, 1):
            s.ellipse(x + sx * w * 0.34, t + h * 0.58, w * 0.08, h * 0.07, fillc=s.paper, sw=1.4)
        s.rbox(x - w * 0.2, t + h * 0.54, x + w * 0.2, t + h * 0.72, w * 0.02, sw=1.2, j=0.4); s.hatch(s.rrect(x - w * 0.2, t + h * 0.54, x + w * 0.2, t + h * 0.72, w * 0.02), ang=0, gap=3, op=0.4, smooth=True)
        if sp.get('label'):
            s.text(sp['label'], x, t + h * 0.82, size=clamp(w * 0.09, 7, 16), maxw=w * 0.4, kind='label', maxlines=1)
        return
    f = -1 if sp.get('flip') else 1; h = w * ASPECT['car']; X = lambda a: x + f * (a - 0.5) * w; Y = lambda b_: y - h / 2 + b_ * w
    body = [(0.02, 0.31), (0.03, 0.23), (0.1, 0.19), (0.22, 0.17), (0.33, 0.055), (0.45, 0.02), (0.62, 0.02), (0.74, 0.08), (0.82, 0.17), (0.93, 0.19), (0.98, 0.24), (0.98, 0.32), (0.5, 0.335)]
    P = [(X(a), Y(b_)) for a, b_ in body]
    s.fill(P, s.paper); s.hatch(P, ang=-0.4, gap=7, op=0.13, smooth=True); s.stroke(P, sw=2.0, closed=True, j=0.8)
    for wn in ([(0.35, 0.07), (0.47, 0.05), (0.47, 0.16), (0.26, 0.16)], [(0.5, 0.05), (0.62, 0.05), (0.72, 0.16), (0.5, 0.16)]):
        q = [(X(a), Y(b_)) for a, b_ in wn]; s.fill(q, s.paper, smooth=False); s.hatch(q, ang=0.8, gap=4, op=0.22); s.poly(q, sw=1.2, j=0.5)
    s.line(X(0.485), Y(0.17), X(0.485), Y(0.31), sw=0.9, op=0.5, passes=1); s.line(X(0.53), Y(0.2), X(0.58), Y(0.2), sw=1.2, passes=1)
    s.ellipse(X(0.05), Y(0.22), w * 0.025, w * 0.016, sw=1.0, passes=1)
    for a in (0.2, 0.79):
        s.ellipse(X(a), Y(0.33), w * 0.078, w * 0.078, fillc=s.cur, fop=0.72, sw=1.5); s.ellipse(X(a), Y(0.33), w * 0.036, w * 0.036, fillc=s.paper, sw=0.9, passes=1)
    s.line(x - w * 0.56, Y(0.41), x + w * 0.56, Y(0.41), sw=1.0, op=0.5, passes=1)
    if sp.get('label'):
        s.text(sp['label'], X(0.5), Y(0.25), size=clamp(w * 0.06, 7, 16), maxw=w * 0.4, kind='label', maxlines=1)


def prop_backdrop(s, x, y, w, sp):
    m = 12 * s.K; r = [(m, m * 1.4), (s.w - m, m * 1.4), (s.w - m, s.h * float(sp.get('to', 86)) / 100.0), (m, s.h * float(sp.get('to', 86)) / 100.0)]
    s.hatch(r, ang=-0.8, gap=8, op=0.2); s.poly(r, sw=1.4, op=0.7, j=1.0)
    if sp.get('label'):
        s.text(sp['label'], s.w / 2 if 'xpx' not in sp else sp['xpx'], m * 1.4 + 13 * s.K, size=11 * s.K, maxw=s.w * 0.6, kind='behind', maxlines=1, op=0.8)


def prop_car_interior(s, x, y, w, sp):
    """خلفية داخل السيارة: مسند الراس والشباك ورا الشخص (المقود والحزام ينرسمون قدام)."""
    W, H = s.w, s.h
    s.poly([(W * 0.04, H * 0.52), (W * 0.06, H * 0.2), (W * 0.3, H * 0.13), (W * 0.33, H * 0.5)], sw=1.4, op=0.8, j=0.8)
    s.hatch([(W * 0.04, H * 0.52), (W * 0.06, H * 0.2), (W * 0.3, H * 0.13), (W * 0.33, H * 0.5)], ang=0.8, gap=7, op=0.14)
    s.poly([(W * 0.67, H * 0.5), (W * 0.7, H * 0.13), (W * 0.94, H * 0.2), (W * 0.96, H * 0.52)], sw=1.4, op=0.8, j=0.8)
    s.hatch([(W * 0.67, H * 0.5), (W * 0.7, H * 0.13), (W * 0.94, H * 0.2), (W * 0.96, H * 0.52)], ang=0.8, gap=7, op=0.14)
    s.stroke([(W * 0.02, H * 0.1), (W * 0.3, H * 0.06), (W * 0.7, H * 0.06), (W * 0.98, H * 0.1)], sw=1.3, op=0.7)
    hr = s.rrect(x - w * 0.5, y - w * 0.78, x + w * 0.5, y + w * 0.5, w * 0.2)
    s.fill(hr, s.paper); s.hatch(hr, ang=-0.7, gap=4.5, op=0.22, smooth=True); s.stroke(hr, sw=1.5, closed=True)
    seat = s.rrect(x - w * 1.25, y + w * 0.62, x + w * 1.25, H + 20, w * 0.3)
    s.fill(seat, s.paper); s.hatch(seat, ang=-0.7, gap=5, op=0.16, smooth=True); s.stroke(seat, sw=1.5, closed=True)

    def front():
        side = -1 if sp.get('wheel', 'right') == 'left' else 1
        wx = W / 2 + side * W * 0.36; wy = H * 0.97; R = W * 0.3
        s.stroke(s.epts(wx, wy, R, R * 0.74, math.radians(170), math.radians(370), n=14), sw=5.5, op=0.9, j=0.6)
        s.stroke(s.epts(wx, wy, R * 0.86, R * 0.62, math.radians(180), math.radians(360), n=12), sw=1.0, op=0.5, passes=1)
        bx = x - side * w * 1.2
        s.stroke([(bx, y + w * 0.9), (x, y + w * 2.3), (x + side * w * 1.3, H * 0.94)], sw=5.0, op=0.5, j=0.5, passes=1)
    return front


PROPS = {'table': prop_table, 'laptop': prop_laptop, 'monitor': prop_monitor, 'tv': prop_monitor, 'phone': prop_phone, 'tablet': prop_phone, 'box': prop_box,
         'bottle': prop_bottle, 'perfume': prop_bottle, 'cup': prop_cup, 'can': prop_can, 'jar': prop_can, 'tube': prop_tube, 'bag': prop_bag, 'card': prop_card,
         'watch': prop_watch, 'book': prop_book, 'plate': prop_plate, 'burger': prop_burger, 'shoe': prop_shoe, 'mic': prop_mic, 'camera': prop_camera,
         'headphones': prop_headphones, 'keyboard': prop_keyboard, 'shape': prop_shape, 'shelf': prop_shelf, 'plant': prop_plant, 'window': prop_window,
         'picture': prop_picture, 'lights': prop_lights, 'softbox': prop_softbox, 'ringlight': prop_ringlight, 'sofa': prop_sofa, 'chair': prop_chair,
         'door': prop_door, 'whiteboard': prop_whiteboard, 'storefront': prop_storefront, 'car': prop_car, 'backdrop': prop_backdrop,
         'car-interior': prop_car_interior}


def draw_prop(s, sp, x, y, w):
    typ = alias(sp.get('type'))
    fn = PROPS.get(typ)
    if not fn:
        s.warn.append('نوع العنصر «%s» مو موجود بالمكتبة — انرسم مربع باسمه. الأنواع بـshot-language.md' % sp.get('type'))
        sp = dict(sp, type='shape', label=sp.get('label') or str(sp.get('type')))
        fn = prop_shape
    else:
        sp = dict(sp, type=typ if typ not in ('shape',) else sp.get('type'))
    rot = float(sp.get('rot', 0) or 0)
    hand = sp.get('hand')
    h = sp.get('hpx') or w * ASPECT.get(typ, 1.0)
    front = None
    if hand in ('bottom', 'left', 'right'):
        hs = clamp(w * 0.42, 9 * s.K, 34 * s.K)
        if hand == 'bottom':
            px, py = x + w * 0.1, y + h * 0.26
            s.tube([(x + w * 0.45, s.h + 10), (x + w * 0.3, y + h * 0.7), (px, py + hs * 0.4)], hs * 1.5, sw=1.6)
            s.ellipse(px, py, hs * 1.1, hs * 1.05, fillc=s.paper, sw=1.6)
        else:
            sx = -1 if hand == 'left' else 1
            px, py = x + sx * w * 0.2, y + h * 0.18
            s.tube([(-10 if sx < 0 else s.w + 10, y + h * 0.5), (x + sx * (w * 0.5 + hs * 1.6), y + h * 0.34), (px + sx * hs * 0.5, py)], hs * 1.5, sw=1.6)
            s.ellipse(px, py, hs * 1.1, hs * 1.05, fillc=s.paper, sw=1.6)
    with s.rot(rot, x, y):
        front = fn(s, x, y, w, sp)
    if hand in ('bottom', 'left', 'right'):
        if hand == 'bottom':
            draw_fingers(s, x + w / 2, y + h * 0.26, hs * 0.9, side=1, n=4)
            s.ellipse(x - w / 2 + hs * 0.25, y + h * 0.2, hs * 0.62, hs * 0.3, fillc=s.paper, sw=1.2, j=0.3, rot=0.5, passes=1)
        else:
            sx = -1 if hand == 'left' else 1
            draw_fingers(s, x + sx * w / 2, y + h * 0.18, hs * 0.9, side=sx, n=4)
    return front


# ───────────────────────────── عناصر المونتاج (تنرسم بلون مختلف ومنقّطة)
SIZES = {'huge': 54, 'big': 30, 'mid': 18, 'small': 13, 'tiny': 10.5}


def tsize(v, s, default='mid'):
    if isinstance(v, (int, float)):
        return float(v) * s.K
    return SIZES.get(str(v or default), SIZES[default]) * s.K


def ov_text(s, e, col):
    size = tsize(e.get('size'), s)
    maxw = e['wpx'] if e.get('wpx') else min(s.w - 14 * s.K, 2 * min(e['xpx'], s.w - e['xpx']) - 6 * s.K)
    style = e.get('style')
    if style == 'pill':
        lines, sz, ok = fit_text(e['text'], size, maxw - sz_pad(size))
        tw = max(text_w(ln, sz) for ln in lines); H = sz * 1.32 * len(lines)
        s.rbox(e['xpx'] - tw / 2 - sz * 0.7, e['ypx'] - H / 2 - sz * 0.35, e['xpx'] + tw / 2 + sz * 0.7, e['ypx'] + H / 2 + sz * 0.35, sz * 0.9,
               fillc=mix(s.paper, col, 0.14), sw=1.4, color=col, op=0.9, j=0.5, dash='')
        s.text(e['text'], e['xpx'], e['ypx'], size=sz, color=col, maxw=maxw - sz_pad(size), kind='behind' if e.get('behind') else 'overlay')
        b = s.texts[-1]['box']; s.texts[-1]['box'] = (b[0] - sz * 0.7, b[1] - sz * 0.3, b[2] + sz * 0.7, b[3] + sz * 0.3)
        return
    if style == 'blocks':
        s.cid += 1; pid = 'p%s_%d' % (s.uid, s.cid); lines, sz, ok = fit_text(e['text'], size, maxw, maxlines=1)
        s.o.append('<pattern id="%s" width="4.4" height="4.4" patternUnits="userSpaceOnUse"><path d="M1.2,0 L1.2,4.4" stroke="%s" stroke-width="2.2"></path><path d="M0,3.6 L4.4,3.6" stroke="%s" stroke-width="0.9"></path></pattern>' % (pid, col, s.paper))
        s.o.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="%.1f" data-fs="%.1f" data-mw="%.0f" font-weight="800" fill="url(#%s)" stroke="%s" stroke-width="1.2" text-anchor="middle" direction="%s">%s</text>'
                   % (e['xpx'], e['ypx'] + sz * 0.36, s.pal['page_font'], sz, min(size, sz * 1.16), maxw, pid, col, 'rtl' if is_ar(e['text']) else 'ltr', escape(lines[0])))
        tw = text_w(lines[0], sz)
        s.texts.append(dict(t=e['text'], box=(e['xpx'] - tw / 2, e['ypx'] - sz * 0.5, e['xpx'] + tw / 2, e['ypx'] + sz * 0.5), kind='behind' if e.get('behind') else 'overlay'))
        return
    s.text(e['text'], e['xpx'], e['ypx'], size=size, color=col, maxw=maxw, kind='behind' if e.get('behind') else 'overlay', op=e.get('op', 1))


def sz_pad(size):
    return size * 1.5


def ov_burst(s, e, col):
    x, y = e['xpx'], e['ypx']; r1 = e.get('r1px', 38 * s.K); r2 = e.get('r2px', 72 * s.K); n = int(e.get('rays', 12))
    for i in range(n):
        a = i * 2 * math.pi / n + 0.25; rr = r2 + (8 * s.K if i % 2 else 0)
        s.line(x + r1 * math.cos(a), y + r1 * math.sin(a), x + rr * math.cos(a), y + rr * math.sin(a), sw=7, color=col, op=0.5, j=0.8, passes=1, dash='')
    if e.get('text'):
        s.text(e['text'], x, y - r2 - 14 * s.K, size=11 * s.K, color=col, maxw=s.w * 0.7, kind='behind')


def ov_floor(s, e, col):
    W, H = s.w, s.h; y0 = H * float(e.get('y', 49)) / 100.0
    for i in range(-6, 7):
        s.line(W / 2 + i * W * 0.037, y0, W / 2 + i * W * 0.17, H - 8, sw=0.8, color=col, op=0.24, j=0.3, passes=1, dash='')
    for j in range(6):
        y = y0 + (j + 1) ** 1.7 * (H - y0) / 27.0
        s.line(8, y, W - 8, y, sw=0.8, color=col, op=0.24, j=0.3, passes=1, dash='')


def ov_panel(s, e, col):
    x, y, w = e['xpx'], e['ypx'], e['wpx']; h = e.get('hpx') or w * 0.62
    s.shapes.append(('إطار مونتاج', (x - w / 2, y - h / 2, x + w / 2, y + h / 2)))
    r = [(x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x + w / 2, y + h / 2), (x - w / 2, y + h / 2)]
    s.fill(r, s.paper, 0.9, smooth=False); s.hatch(r, ang=0.9, gap=6, color=col, op=0.2); s.poly(r, sw=1.5, color=col, op=0.9, j=0.6, dash='5 3', passes=1)
    with s.ink(col):
        screen_content(s, quad_map(r), e.get('content'), e.get('label') or e.get('text'), w * 0.9)


def ov_badge(s, e, col):
    x, y = e['xpx'], e['ypx']; w = e.get('wpx') or 52 * s.K
    s.shapes.append(('نجمة السعر', (x - w / 2, y - w / 2, x + w / 2, y + w / 2)))
    pts = []
    n = 14
    for i in range(n * 2):
        a = i * math.pi / n; rr = w / 2 * (1.0 if i % 2 == 0 else 0.86)
        pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
    if e.get('shape') == 'circle':
        pts = s.epts(x, y, w / 2, w / 2, n=18)[:-1]
    s.fill(pts, mix(s.paper, col, 0.16)); s.stroke(pts, sw=1.5, color=col, op=0.9, j=0.5, closed=True, dash='')
    s.text(e.get('text', ''), x, y, size=tsize(e.get('size'), s, 'mid'), color=col, maxw=w * 0.74, kind='overlay', maxlines=2)


def ov_list(s, e, col):
    x, y = e['xpx'], e['ypx']; items = e.get('items') or []; size = tsize(e.get('size'), s, 'small'); gap = size * 2.25
    maxw = e.get('wpx') or min(s.w * 0.62, 2 * min(x, s.w - x) - 8 * s.K)
    y0 = y - gap * (len(items) - 1) / 2
    for i, it in enumerate(items):
        yy = y0 + i * gap
        lines, sz, ok = fit_text(it, size, maxw - size * 1.6, maxlines=1)
        tw = text_w(lines[0], sz)
        s.rbox(x - tw / 2 - sz * 0.8, yy - sz * 0.95, x + tw / 2 + sz * 0.8, yy + sz * 0.95, sz * 0.9, fillc=mix(s.paper, col, 0.13), sw=1.3, color=col, op=0.9, j=0.5, dash='')
        s.text(it, x, yy, size=sz, color=col, maxw=maxw - size * 1.6, kind='overlay', maxlines=1)
        b = s.texts[-1]['box']; s.texts[-1]['box'] = (b[0] - sz * 0.8, b[1], b[2] + sz * 0.8, b[3])


def ov_arrow(s, e, col):
    a, b = e['frompx'], e['topx']
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2; dx, dy = b[0] - a[0], b[1] - a[1]; bend = float(e.get('bend', 0.14))
    s.arrow([a, (mx - dy * bend, my + dx * bend), b], color=col, sw=1.7, head=7, dash='5 4' if e.get('dash', True) else '')
    if e.get('text'):
        tx, ty = e.get('txpx', a[0]), e.get('typx', a[1] + (14 * s.K if a[1] > b[1] else -12 * s.K))
        tx = clamp(tx, 8 * s.K, s.w - 8 * s.K)
        s.text(e['text'], tx, ty, size=tsize(e.get('size'), s, 'small') * 0.9, color=col, maxw=min(s.w - 16 * s.K, 2 * min(tx, s.w - tx) - 4 * s.K), kind='overlay')


def ov_zoom(s, e, col):
    x, y, w = e['xpx'], e['ypx'], e['wpx']; h = e.get('hpx') or w * s.h / s.w
    s.zooms.append((x - w / 2, y - h / 2, x + w / 2, y + h / 2))
    s.rbox(x - w / 2, y - h / 2, x + w / 2, y + h / 2, 5 * s.K, sw=1.6, color=col, op=0.95, j=0.6, dash='6 4', passes=1)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx_, cy_ = x + sx * w / 2, y + sy * h / 2
            ox, oy = cx_ + sx * 18 * s.K, cy_ + sy * 18 * s.K
            if 4 < ox < s.w - 4 and 4 < oy < s.h - 4:
                s.arrow([(ox, oy), (cx_ + sx * 4 * s.K, cy_ + sy * 4 * s.K)], color=col, sw=1.4, head=5, dash='')
    if e.get('text'):
        ty = y - h / 2 - 11 * s.K if y - h / 2 > 30 * s.K else y + h / 2 + 12 * s.K
        tx_ = e.get('txpx', x); ty = e.get('typx', ty)
        s.text(e['text'], tx_, ty, size=tsize(e.get('size'), s, 'small') * 0.9, color=col, maxw=min(s.w - 16 * s.K, 2 * min(tx_, s.w - tx_) - 4 * s.K), kind='overlay')


def ov_caption(s, e, col):
    y = e['ypx']; w = e.get('wpx') or s.w * 0.7; x = e.get('xpx', s.w / 2)
    if e.get('text'):
        size = tsize(e.get('size'), s, 'small'); lines, sz, ok = fit_text(e['text'], size, w, maxlines=2)
        tw = max(text_w(ln, sz) for ln in lines); hh = sz * 1.32 * len(lines)
        s.rbox(x - tw / 2 - 7 * s.K, y - hh / 2 - 2 * s.K, x + tw / 2 + 7 * s.K, y + hh / 2 + 2 * s.K, 5 * s.K, fillc=s.paper, fop=0.92, sw=1.2, color=col, op=0.8, j=0.4, dash='4 3', passes=1)
        s.text(e['text'], x, y, size=size, color=col, maxw=w, kind='overlay', maxlines=2)
    else:
        s.rbox(x - w / 2, y - 9 * s.K, x + w / 2, y + 9 * s.K, 6 * s.K, sw=1.2, color=col, op=0.8, j=0.4, dash='4 3', passes=1)
        s.line(x - w * 0.36, y, x + w * 0.36, y, sw=2.2, color=col, op=0.5, j=0.3, passes=1, dash='')


def ov_logo(s, e, col):
    x, y = e['xpx'], e['ypx']; w = e.get('wpx') or 44 * s.K
    s.shapes.append(('مربع شعار', (x - w / 2, y - w / 2, x + w / 2, y + w / 2)))
    s.rbox(x - w / 2, y - w / 2, x + w / 2, y + w / 2, w * 0.24, fillc=mix(s.paper, col, 0.12), sw=1.5, color=col, op=0.9, j=0.5, dash='')
    s.text(e.get('text') or e.get('label') or '', x, y, size=clamp(w * 0.26, 8 * s.K, 22 * s.K), color=col, maxw=w * 0.82, kind='overlay', maxlines=2)


OVERLAYS = {'text': ov_text, 'burst': ov_burst, 'floor': ov_floor, 'panel': ov_panel, 'badge': ov_badge, 'list': ov_list, 'arrow': ov_arrow,
            'zoom': ov_zoom, 'caption': ov_caption, 'logo': ov_logo}


# ───────────────────────────── تركيب اللقطة + الفحص
NAMED_X = {'left': 24, 'center': 50, 'centre': 50, 'middle': 50, 'right': 76}
NAMED_Y = {'top': 13, 'upper': 28, 'middle': 50, 'center': 50, 'lower': 72, 'bottom': 88}
PSIZE = {'wide': 12.5, 'full': 12.5, 'medium': 23, 'waist': 23, 'mclose': 30, 'medium-close': 30, 'chest': 30, 'close': 44, 'xclose': 60}
PY = {'wide': 40, 'full': 40, 'medium': 34, 'waist': 34, 'mclose': 36, 'medium-close': 36, 'chest': 36, 'close': 42, 'xclose': 46}


def _num(v, named, default):
    if v is None:
        return float(default)
    if isinstance(v, (int, float)):
        return float(v)
    v = str(v).strip().lower()
    if v in named:
        return float(named[v])
    try:
        return float(v.rstrip('%'))
    except ValueError:
        return float(default)


def rects_hit(a, b, pad=0):
    return not (a[2] <= b[0] + pad or b[2] <= a[0] + pad or a[3] <= b[1] + pad or b[3] <= a[1] + pad)


def draw_shot(spec, idx, pal, W, H, character):
    fr = spec.get('frame') or {}
    seed = 1000 + idx * 101 + sum(ord(c) for c in str(spec.get('title', ''))) % 97
    s = Sk(seed, W, H, pal, 's%d' % idx)
    X = lambda v, d=50: _num(v, NAMED_X, d) / 100.0 * W
    Y = lambda v, d=50: _num(v, NAMED_Y, d) / 100.0 * H
    WP = lambda v: float(v) / 100.0 * W
    people = fr.get('people') or ([fr['person'] or {}] if 'person' in fr and fr['person'] is not None else [])
    props = [dict(p) for p in (fr.get('props') or [])]
    overlay = [dict(o) for o in (fr.get('overlay') or [])]
    notes = [dict(n) for n in (fr.get('notes') or [])]
    for pr in props:
        pr['_t'] = alias(pr.get('type'))
        pr['_layer'] = pr.get('layer') or ('back' if pr['_t'] in BACK_TYPES else 'front')
    desk = None
    for pr in props:
        if pr['_t'] == 'table' and pr['_layer'] == 'front':
            desk = Y(pr.get('y'), 68)
    fronts = []

    def place(pr):
        typ = pr['_t']
        dflt_w = {'table': 100, 'laptop': 60, 'monitor': 54, 'phone': 22, 'tablet': 34, 'car': 84, 'storefront': 92, 'sofa': 86, 'shelf': 24, 'plant': 14, 'window': 30,
                  'picture': 16, 'lights': 44, 'box': 26, 'bottle': 16, 'perfume': 20, 'cup': 18, 'bag': 30, 'card': 34, 'chair': 40, 'car-interior': 26, 'tv': 54,
                  'whiteboard': 60, 'mic': 12, 'camera': 22, 'softbox': 22, 'ringlight': 20, 'door': 26}.get(typ, 24)
        w = WP(pr.get('w', dflt_w))
        sp = dict(pr)
        if pr.get('h') is not None:
            sp['hpx'] = float(pr['h']) / 100.0 * H
        if typ == 'table':
            sp['x0px'] = WP(pr.get('x0', 0)); sp['x1px'] = WP(pr.get('x1', 100))
        x = X(pr.get('x')); y = Y(pr.get('y'), 68 if typ == 'table' else 50)
        if typ == 'car-interior' and people:
            p0 = people[0]; sz = p0.get('size', 'medium')
            u = (PSIZE.get(str(sz), 23) if not isinstance(sz, (int, float)) else float(sz) / 200.0 * 270) * s.K
            x = X(p0.get('x')); y = Y(p0.get('y'), PY.get(str(sz), 34)); w = u * 2.6
        f = draw_prop(s, sp, x, y, w)
        hgt = sp.get('hpx') or w * ASPECT.get(typ, 1.0)
        s.anchors['prop%d' % props.index(pr)] = (x, y, w, hgt)
        if typ == 'storefront':            # لوحة المحل واسمه: الكتابة ما تركب عليها
            s.objs.append(('لوحة المحل', (x - w * 0.44, y - hgt / 2 + hgt * 0.06, x + w * 0.44, y - hgt / 2 + hgt * 0.26), False))
        elif pr['_layer'] == 'back' and typ not in ('monitor', 'tv', 'laptop', 'backdrop', 'car-interior', 'table'):
            s.backs.append((str(pr.get('label') or pr.get('type')), (x - w / 2, y - hgt / 2, x + w / 2, y + hgt / 2)))
        if typ in ('monitor', 'tv', 'laptop') or (pr['_layer'] != 'back' and typ not in ('table', 'backdrop', 'car-interior')):
            s.objs.append((str(pr.get('label') or pr.get('type')), (x - w / 2, y - hgt / 2, x + w / 2, y + hgt / 2), pr['_layer'] != 'back'))
        if callable(f):
            fronts.append(f)

    for pr in props:
        if pr['_layer'] == 'back':
            place(pr)

    def colour(e):
        c = str(e.get('color', 1))
        if c.startswith('#'):                      # لون شعار معيّن (مثلاً برتقالي شعار البراند)
            return ensure(_hex(_rgb(c)), pal['paper'], 2.2)
        return pal['ov2'] if c in ('2', 'second') else pal['ov1']

    def draw_overlay(e):
        typ = alias(e.get('type') or ('text' if e.get('text') else 'shape'))
        col = colour(e)
        e['xpx'] = X(e.get('x')); e['ypx'] = Y(e.get('y'), 20)
        if e.get('w') is not None:
            e['wpx'] = WP(e['w'])
        if e.get('h') is not None:
            e['hpx'] = float(e['h']) / 100.0 * H
        if typ == 'zoom' and e.get('at'):
            e['txpx'] = X(e['at'][0]); e['typx'] = Y(e['at'][1])
        if typ == 'arrow':
            if not e.get('from') or not e.get('to'):
                raise ValueError('السهم يبي from و to كل واحد [x, y]')
            e['frompx'] = (X(e['from'][0]), Y(e['from'][1])); e['topx'] = (X(e['to'][0]), Y(e['to'][1]))
            if e.get('at'):
                e['txpx'] = X(e['at'][0]); e['typx'] = Y(e['at'][1])
        if typ == 'text' and not e.get('text'):
            raise ValueError('عنصر كتابة بلا text')
        if typ == 'burst':
            if e.get('r') is not None:
                e['r2px'] = WP(e['r']); e['r1px'] = e['r2px'] * 0.52
            if e.get('behind') is None:
                e['behind'] = True
        if typ in OVERLAYS:
            OVERLAYS[typ](s, e, col)
        else:
            with s.ink(col, '5 3'):
                sp = dict(e, type=typ)
                draw_prop(s, sp, e['xpx'], e['ypx'], e.get('wpx') or WP(24))

    # عناصر المونتاج اللي ورا الشخص
    for e in overlay:
        t = alias(e.get('type') or 'text')
        if e.get('behind') or t in ('floor',) or (t == 'burst' and e.get('behind') is None):
            draw_overlay(e); e['_done'] = True
    # الناس
    pinfo = []
    for p in people:
        sz = p.get('size', 'medium')
        u = (PSIZE.get(str(sz).lower(), 23) if not isinstance(sz, (int, float)) else float(sz) / 200.0 * 270) * s.K
        q = dict(p); q['cx'] = X(p.get('x')); q['cy'] = Y(p.get('y'), PY.get(str(sz).lower(), 34)); q['u'] = u
        t = p.get('turn', 0)
        q['turn'] = {'left': -1, 'right': 1, 'camera': 0}.get(t, t) if not isinstance(t, (int, float)) else t
        if p.get('point'):
            pt = p['point'] if isinstance(p['point'], (list, tuple)) else p['point'].get('to')
            arm = None if isinstance(p['point'], (list, tuple)) else p['point'].get('arm')
            q['point'] = {'to': (X(pt[0]), Y(pt[1])), 'arm': arm}
        if p.get('hold'):
            hd = dict(p['hold']); it = dict(hd.get('item') or {'type': 'box'})
            if it.get('w') is not None:
                it['wpx'] = WP(it['w'])
            if it.get('h') is not None:
                it['hpx'] = float(it['h']) / 100.0 * H
            hd['item'] = it; q['hold'] = hd
        ch = dict(character); ch.update(p.get('character') or {})
        d = desk if (desk is not None and p.get('behind_table', True) and desk > q['cy'] + 2.2 * u) else None
        info = draw_person(s, q, ch, d); pinfo.append(info)
        if info.get('held'):
            ix, iy, iw, ih = info['held']
            s.objs.append((str((q['hold'].get('item') or {}).get('label') or (q['hold'].get('item') or {}).get('type') or 'الغرض اللي بإيده'), (ix - iw / 2, iy - ih / 2, ix + iw / 2, iy + ih / 2), True))
        s.bodies.append((q['cx'] - 2.62 * u, q['cy'] + 1.76 * u, q['cx'] + 2.62 * u, min(H, q['cy'] + (8.2 * u if d is None else 0) + (0 if d is None else d - q['cy']))))
    for pr in sorted([q for q in props if q['_layer'] != 'back'], key=lambda q: 0 if q['_t'] == 'table' else 1):
        place(pr)
    for f in fronts:
        f()
    for e in overlay:
        if not e.get('_done'):
            draw_overlay(e)
    # ملاحظات المصوّر
    nc = pal['note']
    for n in notes:
        typ = n.get('type') or 'note'
        if typ == 'zoom':
            n['xpx'] = X(n.get('x')); n['ypx'] = Y(n.get('y')); n['wpx'] = WP(n.get('w', 50))
            if n.get('at'):
                n['txpx'] = X(n['at'][0]); n['typx'] = Y(n['at'][1])
            if n.get('h') is not None:
                n['hpx'] = float(n['h']) / 100.0 * H
            ov_zoom(s, n, nc); s.texts[-1]['kind'] = 'note' if n.get('text') else s.texts[-1]['kind']
            continue
        if typ == 'arrow':
            if not n.get('from') or not n.get('to'):
                raise ValueError('السهم يبي from و to كل واحد [x, y]')
            n['frompx'] = (X(n['from'][0]), Y(n['from'][1])); n['topx'] = (X(n['to'][0]), Y(n['to'][1]))
            if n.get('at'):
                n['txpx'] = X(n['at'][0]); n['typx'] = Y(n['at'][1])
            n.setdefault('dash', False)
            ov_arrow(s, n, nc)
            if n.get('text'):
                s.texts[-1]['kind'] = 'note'
            continue
        x = X(n.get('x')); y = Y(n.get('y'), 90); size = tsize(n.get('size'), s, 'small')
        maxw = WP(n['w']) if n.get('w') else min(W - 20 * s.K, 2 * min(x, W - x) - 8 * s.K)
        if n.get('box'):
            lines, sz, ok = fit_text(n.get('text', ''), size, maxw - 18 * s.K)
            tw = max(text_w(l, sz) for l in lines); hh = sz * 1.32 * len(lines)
            bx = (x - tw / 2 - 10 * s.K, y - hh / 2 - 6 * s.K, x + tw / 2 + 10 * s.K, y + hh / 2 + 6 * s.K)
            r = [(bx[0], bx[1]), (bx[2], bx[1]), (bx[2], bx[3]), (bx[0], bx[3])]
            s.fill(r, s.paper, smooth=False); s.poly(r, sw=1.2, color=nc, op=0.9, j=0.6, dash='5 4', passes=1)
            box = s.text(n.get('text', ''), x, y, size=size, color=nc, maxw=maxw - 18 * s.K, kind='note')
            box = bx
        else:
            box = s.text(n.get('text', ''), x, y, size=size, color=nc, maxw=maxw, kind='note')
        to = n.get('to')
        if to:
            T = (X(to[0]), Y(to[1]))
            cxn, cyn = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            dx, dy = T[0] - cxn, T[1] - cyn
            hw_, hh_ = (box[2] - box[0]) / 2 + 3 * s.K, (box[3] - box[1]) / 2 + 3 * s.K
            if abs(dx) * hh_ > abs(dy) * hw_:
                A = (cxn + math.copysign(hw_, dx), cyn + dy * hw_ / abs(dx) * 0.5)
            else:
                A = (cxn + dx * hh_ / (abs(dy) or 1) * 0.5, cyn + math.copysign(hh_, dy))
            L = math.hypot(T[0] - A[0], T[1] - A[1])
            if L > 10 * s.K:
                mx, my = (A[0] + T[0]) / 2, (A[1] + T[1]) / 2; bend = 0.16 if L > 40 * s.K else 0.05
                s.arrow([A, (mx - (T[1] - A[1]) * bend, my + (T[0] - A[0]) * bend), T], color=nc, sw=1.7, head=6.5)
    # الإطار
    s.poly([(4, 4), (W - 4, 4), (W - 4, H - 4), (4, H - 4)], sw=2.2, j=1.0, passes=2, color=pal['pen'])
    # ── الفحص: كتابة على راس أو منتج، كتابة على كتابة، كتابة برا حدود الأمان، غرض على الوجه
    def shrink(bx, f=0.84):
        mx, my = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2; hw_, hh_ = (bx[2] - bx[0]) / 2 * f, (bx[3] - bx[1]) / 2 * f
        return (mx - hw_, my - hh_, mx + hw_, my + hh_)
    issues = list(s.warn)
    mxs, mys = W * 0.025, H * 0.012
    for t in s.texts:
        b = t['box']
        if t['kind'] != 'label' and (b[0] < mxs or b[2] > W - mxs or b[1] < mys or b[3] > H - mys):
            issues.append('الكتابة «%s» %s — حرّكها لداخل أو قصّرها (خل أطرافها بين 6٪ و94٪ من العرض)'
                          % (t['t'][:36], 'طالعة برا الكادر' if (b[0] < 0 or b[2] > W or b[1] < 0 or b[3] > H) else 'لازقة بطرف الكادر'))
        if t['kind'] in ('overlay', 'note'):
            for f in s.faces:
                if rects_hit(b, f, pad=1.5):
                    issues.append('الكتابة «%s» راكبة على الوجه أو غطاء الراس — حرّكها فوق الراس أو على جنب (أو behind:true لو المقصود ورا الراس)' % t['t'][:36])
                    break
    for name, ob, front in s.objs:
        if front and any(rects_hit(shrink(ob, 0.8), f) for f in s.faces):
            issues.append('«%s» راكب على الوجه — صغّره (w) أو حرّكه أو بدّل مكان مسكته (at)' % name[:24])
    for t in s.texts:
        if t['kind'] not in ('overlay', 'note'):
            continue
        b = t['box']
        for name, ob, front in s.objs:
            if rects_hit(b, shrink(ob)):
                issues.append('الكتابة «%s» راكبة على «%s» — حرّكها عنه عشان العنصر يبين كامل' % (t['t'][:30], name[:20]))
                break
        for z in s.zooms:
            inside = b[0] >= z[0] and b[2] <= z[2] and b[1] >= z[1] and b[3] <= z[3]
            if rects_hit(b, z) and not inside:
                issues.append('إطار الزوم يقطع الكتابة «%s» — صغّر الإطار أو حرّك الكتابة' % t['t'][:30])
                break
    tx = [t for t in s.texts if t['kind'] in ('overlay', 'note', 'behind')]
    for i in range(len(tx)):
        for k in range(i + 1, len(tx)):
            if rects_hit(tx[i]['box'], tx[k]['box'], pad=-3 * s.K):
                issues.append('الكتابتين «%s» و«%s» راكبين على بعض — باعد بينهم' % (tx[i]['t'][:26], tx[k]['t'][:26]))
    nn = [n for n in notes if n.get('text')]
    if len(nn) > 2:
        issues.append('%d ملاحظات بلقطة وحدة — كثرتها تضيّع الرسمة. خل ملاحظتين بالكثير والباقي بقائمة «التوجيه»' % len(nn))
    if not people and not props and not overlay:
        issues.append('الكادر فاضي — حدد شنو ينشاف باللقطة (people / props / overlay)')
    return s, issues


# ───────────────────────────── الصفحة
FITJS = ("(function(){function f(){var t=document.querySelectorAll('text[data-mw]');for(var i=0;i<t.length;i++){var e=t[i],m=+e.getAttribute('data-mw'),"
         "z=+e.getAttribute('data-fs');e.setAttribute('font-size',z);var w=e.getComputedTextLength();if(w>m){e.setAttribute('font-size',(z*m/w).toFixed(2));}}}"
         "f();window.addEventListener('load',f);if(document.fonts&&document.fonts.ready){document.fonts.ready.then(f);}})();")
LABELS = {
    'ar': dict(board='ستوري بورد', script='السكربت الكامل', for_shoot='للتصوير',
               script_hint='مقسوم على اللقطات. كل جزء ينقال بلقطته، وبين الجمل سكتة قصيرة.',
               shot='لقطة', say='تقول', direction='التوجيه', before='قبل لا تصوّر', about='حوالي', sec='ث', seconds='ثانية',
               key_pen='بالرصاص: اللي ينصوّر', key_ov='ملوّن ومنقّط: اللي ينركّب بالمونتاج', key_note='بسهم: ملاحظة وقت التصوير',
               tall='طولي', wide='عرضي', square='مربع', no_speech='بلا كلام', sketch='سكتش اللقطة'),
    'en': dict(board='Storyboard', script='Full script', for_shoot='to shoot',
               script_hint='Split by shot. Say each part in its shot, with a short pause between sentences.',
               shot='Shot', say='Say', direction='Direction', before='Before you shoot', about='about', sec='s', seconds='seconds',
               key_pen='Pencil: what you film', key_ov='Colored & dashed: added in the edit', key_note='With an arrow: a note for the shoot',
               tall='Vertical', wide='Horizontal', square='Square', no_speech='No speech', sketch='Shot sketch'),
}
RATIOS = {'9:16': (270, 480), '16:9': (480, 270), '1:1': (360, 360), '4:5': (320, 400), '3:4': (300, 400)}


def shots_word(n, lang):
    if lang != 'ar':
        return '%d shot%s' % (n, '' if n == 1 else 's')
    if n == 1:
        return 'لقطة وحدة'
    if n == 2:
        return 'لقطتين'
    return '%d لقطات' % n if n <= 10 else '%d لقطة' % n


def words(t):
    t = re.sub('[\u064b-\u0652\u0670\u0640]', '', str(t))          # التشكيل والشدة ما يقسمون الكلمة
    return [w for w in re.split(r'\s+', re.sub(r'[^\w\s%$]', ' ', t, flags=re.UNICODE)) if w]


def norm_words(t):
    t = re.sub('[ً-ْٰـ]', '', str(t))
    t = re.sub('[أإآ]', 'ا', t).replace('ى', 'ي').replace('ة', 'ه')
    return [w.lower() for w in words(t)]


def check_script(spec, issues):
    """يتأكد إن ما انشالت ولا كلمة من سكربت المستخدم الأصلي."""
    src = spec.get('source_script')
    parts = spec.get('script') or []
    n = len(spec.get('shots') or [])
    for i, p in enumerate(parts, 1):
        sh = p.get('shot')
        ok = all(isinstance(v, int) and 1 <= v <= n for v in (sh if isinstance(sh, list) else [sh]))
        if not ok:
            issues.append('جزء السكربت %d («%s») رقم لقطته %r مو موجود — اللقطات من 1 إلى %d' % (i, p.get('part', ''), sh, n))
    if not src:
        return
    a = norm_words(src); b = norm_words(' '.join(str(p.get('text', '')) for p in parts))
    j = 0; missing = []
    for w in a:
        k = j
        while k < len(b) and b[k] != w:
            k += 1
        if k < len(b):
            j = k + 1
        else:
            missing.append(w)
    if missing:
        issues.append('كلمات من سكربت المستخدم مو موجودة بالتقسيم (%d): %s — رجّعها، السكربت ما ينقص منه شي' % (len(missing), ' '.join(missing[:14])))
    extra = len(b) - (len(a) - len(missing))
    if extra > max(3, len(a) * 0.06):
        issues.append('التقسيم فيه %d كلمة زيادة عن سكربت المستخدم — لا تعيد صياغة كلامه' % extra)


def build(spec):
    lang = spec.get('lang', 'ar'); L = dict(LABELS.get(lang, LABELS['ar'])); L.update(spec.get('labels') or {})
    brand = spec.get('brand') or {}
    try:
        pal = build_theme(brand)
    except ValueError as ex:
        raise SystemExit('هوية المستخدم (brand): %s' % ex)
    font = (brand.get('font') or '').strip()
    fstack = ("'%s'," % font if font else '') + "'Noto Sans Arabic','Segoe UI',Tahoma,system-ui,sans-serif"
    pal['page_font'] = fstack.replace('"', "'")
    pal['sketch_font'] = "'Playpen Sans Arabic'," + pal['page_font']
    ratio = str(spec.get('ratio', '9:16')).replace('x', ':').replace('×', ':')
    if ratio not in RATIOS:
        raise SystemExit('المقاس %r مو مدعوم — المتاح: %s' % (ratio, ' · '.join(RATIOS)))
    W, H = RATIOS[ratio]
    character = dict(spec.get('character') or {})
    shots = spec.get('shots') or []
    if not shots:
        raise SystemExit('ما فيه لقطات (shots) بالملف.')
    parts = spec.get('script') or []
    issues = []
    check_script(spec, issues)
    # الوقت التقريبي من عدد الكلمات
    pace = float(spec.get('pace', 2.2))
    said = []
    for i, sh in enumerate(shots, 1):
        mine = [p for p in parts if (i in p['shot'] if isinstance(p.get('shot'), list) else p.get('shot') == i)]
        txt = ' '.join(str(p.get('text', '')) for p in mine)
        said.append((mine, txt))
    t = 0.0; times = []
    for i, sh in enumerate(shots):
        n = len(words(said[i][1]))
        dur = float(sh['seconds']) if sh.get('seconds') is not None else (n / pace if n else 2.5)
        times.append((t, t + dur)); t += dur
    total = t
    svgs = []; cards = []; maps = []
    for i, sh in enumerate(shots, 1):
        try:
            s, iss = draw_shot(sh, i, pal, W, H, character)
        except SystemExit:
            raise
        except Exception as ex:      # وصف ناقص أو غلط بلقطة: رسالة واضحة بدل سطور خطأ
            raise SystemExit('اللقطة %d («%s»): وصف الكادر فيه شي ناقص أو غلط — %s: %s. راجع الحقول بـ references/shot-language.md'
                             % (i, sh.get('title', ''), type(ex).__name__, ex))
        issues += ['اللقطة %d: %s' % (i, m) for m in iss]
        pc = lambda bx: 'x %3d-%-3d  y %3d-%-3d' % (round(bx[0] / W * 100), round(bx[2] / W * 100), round(bx[1] / H * 100), round(bx[3] / H * 100))
        mp = ['اللقطة %d «%s»' % (i, sh.get('title', ''))]
        mp += ['  %-34s %s' % ('راس (مع غطاه)', pc(f)) for f in s.faces]
        mp += ['  %-34s %s' % ('جسم', pc(bd)) for bd in s.bodies]
        mp += ['  %-34s %s' % ('إيد', pc((hx - hr, hy - hr, hx + hr, hy + hr))) for hx, hy, hr in s.hands]
        mp += ['  %-34s %s' % ('عنصر «%s»' % nm[:20], pc(ob)) for nm, ob, fr_ in s.objs]
        mp += ['  %-34s %s' % ('خلفية «%s»' % nm[:20], pc(ob)) for nm, ob in s.backs]
        mp += ['  %-34s %s' % (nm, pc(ob)) for nm, ob in s.shapes]
        mp += ['  %-34s %s' % ('إطار زوم', pc(z)) for z in s.zooms]
        mp += ['  %-34s %s' % ({'note': 'ملاحظة', 'overlay': 'كتابة مونتاج', 'behind': 'كتابة خلفية', 'label': 'اسم على عنصر'}[t['kind']] + ' «%s»' % t['t'][:18].replace('\n', ' '), pc(t['box']))
               for t in s.texts if t['kind'] != 'label']
        maps.append('\n'.join(mp))
        label = '%s %d: %s' % (L['sketch'], i, sh.get('title', ''))
        svg = s.svg(label); svgs.append(svg)
        a, b = times[i - 1]
        tchip = sh.get('time') or ('%d-%d %s' % (int(round(a)), max(int(round(a)) + 1, int(round(b))), L['sec']))
        mine, txt = said[i - 1]
        say = sh.get('say')
        if say is None:
            say = '<br>'.join(escape(str(p.get('text', ''))).replace('\n', '<br>') for p in mine) or '<span class="mute">%s</span>' % L['no_speech']
        else:
            say = escape(str(say)).replace('\n', '<br>')
        dirs = ''.join('<li>%s</li>' % escape(str(d)) for d in (sh.get('direction') or []))
        if not dirs:
            issues.append('اللقطة %d: بلا «توجيه» — اكتب سطرين: وين يقعد/يوقف وشنو يسوي' % i)
        callout = '<div class="callout"><p>%s</p></div>' % escape(str(sh['callout'])) if sh.get('callout') else ''
        cards.append('<section class="card shot"><div class="shot-head"><span class="num">%02d</span><h2>%s</h2><span class="chip line">%s</span></div>'
                     '<div class="sketch">%s</div><div><h3>%s</h3><p class="say">%s</p></div><div><h3>%s</h3><ul>%s</ul></div>%s</section>'
                     % (i, escape(str(sh.get('title', ''))), escape(str(tchip)), svg, L['say'], say, L['direction'], dirs, callout))
    rows = ''
    for p in parts:
        sh = p.get('shot'); shl = ' · '.join(str(v) for v in sh) if isinstance(sh, list) else sh
        rows += ('<div class="row"><span class="chip line part">%s</span><div class="txt">%s</div><span class="chip soft">%s %s</span></div>'
                 % (escape(str(p.get('part', ''))), escape(str(p.get('text', ''))).replace('\n', '<br>'), L['shot'], shl))
    before = ''.join('<li>%s</li>' % escape(str(b)) for b in (spec.get('before') or []))
    if not before:
        issues.append('قسم «قبل لا تصوّر» فاضي — حط 3 إلى 5 نقاط من واقع اللقطات (شنو يجهّز، الإضاءة، الخصوصية بالشاشات)')
    approx = max(1, int(round(total)))
    dur_txt = spec.get('duration') or ('%s %d %s' % (L['about'], approx, L['seconds']))
    orient = L['tall'] if H > W else (L['wide'] if W > H else L['square'])
    name = (brand.get('name') or '').strip()
    kicker = spec.get('kicker') or (L['board'] + (' · ' + name if name else ''))
    title = spec.get('title') or L['board']
    gf = 'family=Playpen+Sans+Arabic:wght@500;700' + ('&family=%s:wght@400;500;700;800' % font.replace(' ', '+') if font else '')
    basis = {'9:16': 300, '4:5': 320, '3:4': 320, '1:1': 340, '16:9': 440}[ratio]
    css = '''
:root{--bg:%(bg)s;--ink:%(ink)s;--card:%(card)s;--paper:%(paper)s;--accent:%(accent)s;--muted:%(muted)s;--rule:%(rule)s;--soft:%(soft)s;--chip:%(chip)s;--pen:%(pen)s;--ov:%(ov1)s;--ov2:%(ov2)s;--note:%(note)s}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:%(font)s}
.wrap{max-width:1200px;margin:0 auto;padding:28px 16px 56px;display:flex;flex-direction:column;gap:24px}
header{display:flex;flex-direction:column;gap:12px}
.kicker{font-size:13px;font-weight:700;color:var(--accent)}
h1{margin:0;font-size:34px;line-height:1.25;font-weight:800}
h2{margin:0;font-size:20px;font-weight:800}
h3{margin:0 0 4px;font-size:14px;font-weight:800;color:var(--accent)}
.chips{display:flex;gap:8px;flex-wrap:wrap}
.chip{font-size:13px;font-weight:700;padding:4px 12px;border-radius:99px;white-space:nowrap}
.chip.line{border:1.5px solid var(--ink);background:var(--card)}
.chip.soft{background:var(--chip);color:var(--muted);font-size:12px;padding:3px 10px}
.chip.solid{background:var(--ink);color:var(--card);font-size:12px;padding:3px 10px}
.card{border:1.5px solid var(--ink);border-radius:14px;background:var(--card);padding:16px 18px}
.hint{margin:0 0 10px;font-size:14px;line-height:1.6;color:var(--muted)}
.row{display:flex;gap:10px 14px;flex-wrap:wrap;align-items:flex-start;padding:12px 0;border-top:1px solid var(--rule)}
.row .part{flex:0 0 auto;min-width:78px;text-align:center;font-size:12px;font-weight:800;padding:3px 10px}
.row .txt{flex:1 1 240px;min-width:0;font-size:17px;line-height:1.85;font-weight:700}
.head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.key{display:flex;gap:10px 22px;flex-wrap:wrap;align-items:center;padding:10px 14px;border:1.5px solid var(--ink);border-radius:12px;background:var(--card)}
.key div{display:flex;align-items:center;gap:8px;font-size:14px;font-weight:700}
.key i{display:inline-block;width:26px;height:4px;border-radius:2px}
.shots{display:flex;gap:18px;flex-wrap:wrap;align-items:stretch}
.shot{flex:1 1 %(basis)dpx;min-width:0;max-width:%(maxw)dpx;padding:14px;display:flex;flex-direction:column;gap:12px}
.shot-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.num{font-size:15px;font-weight:800;padding:3px 12px;border-radius:99px;background:var(--ink);color:var(--card)}
.shot-head .chip{font-size:12px;padding:3px 10px}
.sketch{border:1.5px solid var(--ink);border-radius:10px;overflow:hidden;background:var(--paper)}
.say{margin:0;font-size:17px;line-height:1.8;font-weight:700}
.mute{color:var(--muted);font-weight:500}
ul{margin:0;padding-inline-start:20px;font-size:15px;line-height:1.75}
.callout{border:1.5px dashed var(--accent);border-radius:10px;padding:10px 12px;background:var(--soft)}
.callout p{margin:0;font-size:15px;line-height:1.75;font-weight:700}
footer{font-size:12px;color:var(--muted);text-align:center}
@media (max-width:520px){h1{font-size:26px}.wrap{padding:20px 12px 40px}}
@media print{body{-webkit-print-color-adjust:exact;print-color-adjust:exact}.card,.key{break-inside:avoid}.wrap{padding:0}}
''' % dict(pal, font=pal['page_font'], basis=basis, maxw=basis * 2 if ratio != '16:9' else 900)
    fitjs = FITJS
    doc = ('<!doctype html>\n<html lang="%s" dir="%s">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>%s</title>\n'
           '<link rel="preconnect" href="https://fonts.googleapis.com">\n<link href="https://fonts.googleapis.com/css2?%s&amp;display=swap" rel="stylesheet">\n<style>%s</style>\n</head>\n<body>\n<div class="wrap">\n'
           % (lang, 'rtl' if lang == 'ar' else 'ltr', escape(title), gf, css))
    doc += ('<header><span class="kicker">%s</span><h1>%s</h1><div class="chips"><span class="chip line">%s</span><span class="chip line">%s</span><span class="chip line">%s %s</span></div></header>\n'
            % (escape(kicker), escape(title), shots_word(len(shots), lang), escape(dur_txt), orient, ratio))
    if rows:
        doc += ('<section class="card"><div class="head"><h2>%s</h2><span class="chip solid">%s</span></div><p class="hint">%s</p>%s</section>\n'
                % (L['script'], L['for_shoot'], escape(spec.get('script_hint') or L['script_hint']), rows))
    doc += ('<div class="key"><div><i style="background:var(--pen)"></i><span>%s</span></div><div><i style="background:linear-gradient(90deg,var(--ov) 50%%,var(--ov2) 50%%)"></i><span>%s</span></div>'
            '<div><i style="background:var(--note)"></i><span>%s</span></div></div>\n' % (L['key_pen'], L['key_ov'], L['key_note']))
    doc += '<div class="shots">\n' + '\n'.join(cards) + '\n</div>\n'
    if before:
        doc += '<section class="card"><h2 style="margin-bottom:8px">%s</h2><ul style="line-height:1.8">%s</ul></section>\n' % (L['before'], before)
    if name:
        doc += '<footer>%s</footer>\n' % escape(name)
    doc += '</div>\n<script>%s</script>\n</body>\n</html>\n' % fitjs
    return doc, svgs, issues, dict(shots=len(shots), seconds=approx, W=W, H=H, pal=pal, maps=maps)


def main():
    ap = argparse.ArgumentParser(description='ستوري بورد HTML من وصف اللقطات')
    ap.add_argument('spec'); ap.add_argument('-o', '--out', default='storyboard.html')
    ap.add_argument('--svgs', help='مجلد اختياري تنحفظ فيه كل رسمة ملف SVG لحالها')
    ap.add_argument('--strict', action='store_true', help='يرجّع خطأ لو فيه أي ملاحظة فحص')
    ap.add_argument('--map', action='store_true', help='يطبع مكان كل شي بكل لقطة بالنسبة المئوية (عينك لما ما تقدر تشوف الصفحة)')
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):          # طباعة العربي تشتغل بأي نظام
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    with open(a.spec, encoding='utf-8') as f:
        spec = json.load(f)
    doc, svgs, issues, info = build(spec)
    with open(a.out, 'w', encoding='utf-8') as f:
        f.write(doc)
    if a.svgs:
        os.makedirs(a.svgs, exist_ok=True)
        gf = 'https://fonts.googleapis.com/css2?family=Playpen+Sans+Arabic:wght@500;700&amp;display=swap'
        for i, sv in enumerate(svgs, 1):
            sv = sv.replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" ' % (info['W'] * 3, info['H'] * 3), 1)
            sv = sv.replace('>', '><style>@import url("%s");</style>' % gf, 1).replace('</svg>', '<script>%s</script></svg>' % FITJS.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
            with open(os.path.join(a.svgs, 'shot-%d.svg' % i), 'w', encoding='utf-8') as f:
                f.write(sv)
    print('تم: %s — %s، حوالي %d ثانية' % (a.out, shots_word(info['shots'], 'ar'), info['seconds']))
    if a.map:
        print('\nخريطة الكادر (x من يسار الكادر ليمينه، y من فوق لتحت، بالنسبة المئوية):')
        print('\n'.join(info['maps']))
    if issues:
        print('\nملاحظات الفحص (%d) — صلّحها بالملف وأعد التشغيل:' % len(issues))
        for m in issues:
            print(' - ' + m)
        if a.strict:
            sys.exit(2)
    else:
        print('\nالفحص نظيف: ما فيه كتابة على وجه ولا على منتج ولا برا الكادر، والسكربت كامل.')


if __name__ == '__main__':
    main()
