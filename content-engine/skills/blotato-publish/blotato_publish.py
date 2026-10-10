#!/usr/bin/env python3
"""
انشر كاروسيل على حساباتك عبر بلوتاتو — بلا منصة وبلا موقع.

الاستخدام:
    python3 blotato_publish.py <مجلد-الصور> --caption "نص المنشور" --platforms instagram,threads
    python3 blotato_publish.py slides/ --caption-file caption.txt --when best --time "2026-08-25T15:00:00Z"

يقرأ المفتاح والأرقام من ملف accounts.json جنبه (انسخ accounts.example.json وعبّيه).
الصور تُرفع من جهازك مباشرة — ما تحتاج استضافة.
"""
import argparse, base64, json, mimetypes, os, sys, urllib.request

API = "https://backend.blotato.com/v2"
HERE = os.path.dirname(os.path.abspath(__file__))
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
VID_EXT = (".mp4", ".mov")


def die(msg):
    print("❌ " + msg)
    sys.exit(1)


def load_conf():
    p = os.path.join(HERE, "accounts.json")
    if not os.path.exists(p):
        die("ما لقيت accounts.json — انسخ accounts.example.json باسم accounts.json وعبّيه")
    c = json.load(open(p, encoding="utf-8"))
    if not c.get("api_key"):
        die("api_key فاضي في accounts.json")
    return c


def call(path, payload, key, timeout=180):
    req = urllib.request.Request(API + path, data=json.dumps(payload, ensure_ascii=False).encode(),
                                 headers={"blotato-api-key": key, "Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        die("بلوتاتو رفض (%s): %s" % (e.code, e.read().decode()[:300]))
    except Exception as e:
        die("ما وصلنا بلوتاتو: %s" % str(e)[:200])


def upload(path, key):
    """يرفع ملفاً من جهازك ويرجّع رابطه عند بلوتاتو."""
    mime = mimetypes.guess_type(path)[0] or "image/png"
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    size = os.path.getsize(path) / 1024 / 1024
    print("   ↑ %-28s %5.1f ميقا" % (os.path.basename(path)[:28], size))
    return call("/media", {"url": "data:%s;base64,%s" % (mime, b64)}, key)["url"]


def target_for(platform, conf, title):
    p = "".join(ch for ch in platform if not ch.isdigit())      # instagram2 → instagram
    if p == "instagram":
        return {"targetType": "instagram"}
    if p == "tiktok":
        return {"targetType": "tiktok", "privacyLevel": "PUBLIC_TO_EVERYONE",
                "disabledComments": False, "disabledDuet": False, "disabledStitch": False,
                "isBrandedContent": False, "isYourBrand": False, "isAiGenerated": False}
    if p == "pinterest":
        board = str(conf.get("pinterest_board_id") or "")
        if not board:
            die("بنترست يحتاج pinterest_board_id في accounts.json")
        return {"targetType": "pinterest", "boardId": board, "title": (title or "منشور جديد")[:95]}
    if p == "youtube":
        return {"targetType": "youtube", "title": (title or "فيديو جديد")[:95],
                "privacyStatus": "public", "shouldNotifySubscribers": True}
    return {"targetType": p}


def content_for(platform, text, media, tags):
    p = "".join(ch for ch in platform if not ch.isdigit())
    if p == "twitter":                       # X: حد الحروف + ٤ صور
        first = text.split("\n")[0][:240]
        return {"text": (first + ("\n\n" + tags if tags else ""))[:275],
                "platform": "twitter", "mediaUrls": media[:4]}
    if p == "threads":                       # ثريدز: عنصر واحد بس
        return {"text": text[:480], "platform": "threads", "mediaUrls": media[:1]}
    return {"text": text[:2000], "platform": p, "mediaUrls": media}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", help="مجلد فيه صور الشرائح (وفيديو اختياري)")
    ap.add_argument("--caption", default="")
    ap.add_argument("--caption-file", default="")
    ap.add_argument("--hashtags", default="", help="مفصولة بمسافة، مثال: '#كلود #ذكاء'")
    ap.add_argument("--platforms", default="instagram")
    ap.add_argument("--when", default="now", choices=["now", "time", "slot"])
    ap.add_argument("--time", default="", help="مع when=time، بصيغة 2026-08-25T15:00:00Z")
    ap.add_argument("--title", default="", help="لبنترست ويوتيوب")
    ap.add_argument("--dry-run", action="store_true", help="يعرض شنو بيصير بلا نشر")
    a = ap.parse_args()

    conf = load_conf()
    accounts = conf.get("accounts") or {}
    text = a.caption
    if a.caption_file:
        text = open(a.caption_file, encoding="utf-8").read().strip()
    if not text.strip():
        die("ما فيه نص للمنشور — استخدم --caption أو --caption-file")
    if a.hashtags:
        text = (text + "\n\n" + a.hashtags).strip()

    files = sorted(os.listdir(a.folder))
    imgs = [os.path.join(a.folder, f) for f in files if f.lower().endswith(IMG_EXT)]
    vids = [os.path.join(a.folder, f) for f in files if f.lower().endswith(VID_EXT)]
    if not imgs and not vids:
        die("ما لقيت صوراً ولا فيديو في: " + a.folder)
    if len(imgs) + len(vids) > 10:
        print("⚠️ عندك %d عنصراً — انستقرام يقبل ١٠، بيتقصّون" % (len(imgs) + len(vids)))

    wanted = [p.strip() for p in a.platforms.split(",") if p.strip()]
    missing = [p for p in wanted if p not in accounts]
    if missing:
        die("هذي المنصات ما لها أرقام في accounts.json: " + "، ".join(missing))
    if a.when == "time" and not a.time:
        die("مع --when time لازم --time")

    print("📦 %d صورة · %d فيديو → %s" % (len(imgs), len(vids), "، ".join(wanted)))
    if a.dry_run:
        for p in wanted:
            print("   %s (حساب %s) → %s" % (p, accounts[p], json.dumps(target_for(p, conf, a.title), ensure_ascii=False)))
        print("🔍 تجربة فقط — ما انرسل شي")
        return

    print("⬆️ نرفع الملفات...")
    media = [upload(v, conf["api_key"]) for v in vids[:1]]      # الفيديو أول عنصر لو موجود
    media += [upload(i, conf["api_key"]) for i in imgs]
    media = media[:10]

    ok, fail = [], []
    for p in wanted:
        post = {"post": {"accountId": str(accounts[p]),
                         "content": content_for(p, text, media, a.hashtags),
                         "target": target_for(p, conf, a.title)}}
        if a.when == "time":
            post["scheduledTime"] = a.time
        elif a.when == "slot":
            post["useNextFreeSlot"] = True
        try:
            r = call("/posts", post, conf["api_key"])
            ok.append(p)
            print("✅ %-12s %s" % (p, r.get("postSubmissionId", "")))
        except SystemExit:
            fail.append(p)
    print("\nالخلاصة: نجح %s%s" % ("، ".join(ok) or "لا شي",
                                   (" · فشل " + "، ".join(fail)) if fail else ""))


if __name__ == "__main__":
    main()
