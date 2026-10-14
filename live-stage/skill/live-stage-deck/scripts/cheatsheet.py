#!/usr/bin/env python3
# ورقة المتحدث: كل مشهد، العبارات اللي تفتحه، وش يطلع، ونقاط الكلام. تنفتح على الجوال أو تنطبع.
# الاستخدام: python3 cheatsheet.py <deck.json> [out.html]
import html, json, os, sys

deck_path = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(deck_path)), "deck-cheatsheet.html")
deck = json.load(open(deck_path, encoding="utf-8"))
e = lambda s: html.escape(str(s or ""))

KIND = {"title": "عنوان", "keyword": "كلمة", "counter": "عداد", "list": "قائمة", "cards": "بطاقات", "bars": "مقارنة",
        "timeline": "خط زمني", "poll": "تصويت بالباركود", "image": "صورة", "sketch": "رسم", "map": "خريطة"}


def summary(sh):
    t = sh.get("t")
    if t in ("title", "keyword"): return sh.get("text", "")
    if t == "counter": return f'{sh.get("value")}{sh.get("suffix", "")} {sh.get("label", "")}'
    if t == "list": return (sh.get("title") or "") + ": " + "، ".join(sh.get("items") or [])
    if t == "cards": return "، ".join(c.get("title", "") for c in sh.get("cards") or [])
    if t in ("bars", "timeline"): return (sh.get("title") or "") + ": " + "، ".join(str(i.get("label", "")) for i in sh.get("items") or [])
    if t == "poll": return sh.get("question", "") + " (" + "، ".join(sh.get("options") or []) + ")"
    if t == "image": return sh.get("caption") or sh.get("src", "")
    return sh.get("title", "")


rows = []
for i, sc in enumerate(deck.get("scenes", [])):
    shows = sc["show"] if isinstance(sc.get("show"), list) else [sc.get("show") or {}]
    vis = "".join(f'<div class="vis"><b>{e(KIND.get(s.get("t"), s.get("t")))}</b> {e(summary(s))}</div>' for s in shows)
    say = "".join(f"<span>{e(p)}</span>" for p in sc.get("say", []))
    talk = "".join(f"<li>{e(t)}</li>" for t in sc.get("talk", []))
    src = f'<div class="src">المصدر: {e(sc["source"])}</div>' if sc.get("source") else ""
    rows.append(f'''<section><div class="n">{i + 1}</div><div class="b">
<div class="note">{e(sc.get("note") or sc.get("id"))}</div>
<div class="say">{say}</div>{vis}{f"<ul>{talk}</ul>" if talk else ""}{src}</div></section>''')

page = f'''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ورقة المتحدث</title><style>
:root{{--bg:#fff;--ink:#14141a;--mute:#6b6d7b;--line:#e3e4ea;--accent:#3E63DD;--chip:#eef1fd}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111216;--ink:#ecedf2;--mute:#9a9cab;--line:#2a2c35;--accent:#7b97f0;--chip:#1e2333}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,-apple-system,sans-serif;padding:20px 16px;line-height:1.6}}
main{{max-width:760px;margin:0 auto}}h1{{font-size:22px;margin:0 0 4px}}.top{{color:var(--mute);font-size:14px;margin-bottom:18px}}
section{{display:flex;gap:14px;padding:14px 0;border-top:1px solid var(--line);break-inside:avoid}}
.n{{flex:none;width:34px;height:34px;border-radius:50%;background:var(--accent);color:#fff;display:grid;place-items:center;font-weight:700}}
.b{{min-width:0;flex:1}}.note{{font-weight:700;font-size:17px}}
.say{{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}}.say span{{background:var(--chip);color:var(--accent);border-radius:999px;padding:2px 12px;font-weight:600}}
.vis{{color:var(--mute);font-size:14px}}.vis b{{color:var(--ink)}}ul{{margin:6px 0 0;padding-inline-start:18px;font-size:15px}}.src{{color:var(--mute);font-size:12px;margin-top:4px}}
@media print{{body{{padding:0}}}}
</style></head><body><main>
<h1>{e(deck.get("title") or "ورقة المتحدث")}</h1>
<div class="top">العبارات الملونة تفتح المشهد. لو المايك ما فهمك: السهم اليمين للي بعده، واليسار للي قبله. طقتين على المايك تمسح الشاشة.</div>
{"".join(rows)}
</main></body></html>'''
open(out, "w", encoding="utf-8").write(page)
print(out)
