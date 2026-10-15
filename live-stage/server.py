#!/usr/bin/env python3
# سيرفر العرض الحي: أمر واحد يشغّل كل شي.
#   - يعرض صفحة العرض على http://localhost:8000
#   - يمرر طلبات الفهم الذكي لكلود كود (اشتراكك) عبر جلسة واحدة شغالة طول الوقت، فما تنتظر تشغيل كلود مع كل جملة
#   - يستقبل تصويت الجمهور من جوالاتهم عبر الواي فاي (http://<ip>:8000/vote)
# شغّله:  python3 server.py
import json, os, queue, socket, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
MODEL = "claude-haiku-5-5"
ROOT = os.path.dirname(os.path.abspath(__file__))
# الملفات المسموح عرضها فقط، عشان أجهزة الشبكة ما تشوف باقي ملفاتك
PUBLIC = {"/": "live-stage.html", "/live-stage.html": "live-stage.html",
          "/deck.json": "deck.json", "/vote": "vote.html", "/vote.html": "vote.html"}
TYPES = {".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8",
         ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
         ".svg": "image/svg+xml", ".gif": "image/gif", ".mp4": "video/mp4"}


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # ما يرسل شي، بس يعرف أي شبكة نطلع منها
        ip = s.getsockname()[0]; s.close(); return ip
    except Exception:
        return "127.0.0.1"


# ---------- كلود: جلسة واحدة شغالة ----------
class Claude:
    """يبقي عملية claude وحدة مفتوحة ويرسل لها الجمل سطر سطر. يعيد تشغيلها إذا تغير البرومبت أو كبرت المحادثة."""
    MAX_TURNS = 25

    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None; self.system = None; self.turns = 0; self.out = None

    def _start(self, system):
        self._stop()
        self.proc = subprocess.Popen(
            # safe-mode وما بعده: بدون إضافاتك (كونكترز، سكلز، تعليماتك العامة) وبدون تفكير، عشان الرد يكون خفيف وسريع
            ["claude", "-p", "--model", MODEL, "--system-prompt", system, "--tools", "",
             "--safe-mode", "--strict-mcp-config", "--disable-slash-commands",
             "--exclude-dynamic-system-prompt-sections", "--effort", "low",
             "--input-format", "stream-json", "--output-format", "stream-json", "--verbose"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1, cwd=ROOT)
        self.system = system; self.turns = 0
        self.out = queue.Queue()
        threading.Thread(target=self._reader, args=(self.proc, self.out), daemon=True).start()

    @staticmethod
    def _reader(proc, q):
        for line in proc.stdout:
            q.put(line)
        q.put(None)

    def _stop(self):
        if self.proc and self.proc.poll() is None:
            try: self.proc.kill()
            except Exception: pass
        self.proc = None

    def ask(self, system, user, timeout=30):
        with self.lock:
            if self.proc is None or self.proc.poll() is not None or system != self.system or self.turns >= self.MAX_TURNS:
                self._start(system)
            self.turns += 1
            msg = {"type": "user", "message": {"role": "user", "content": user}}
            self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n"); self.proc.stdin.flush()
            end = time.time() + timeout
            while time.time() < end:
                try: line = self.out.get(timeout=max(0.1, end - time.time()))
                except queue.Empty: break
                if line is None:
                    self._stop(); raise RuntimeError("claude stopped (سجّل دخول: claude ثم /login)")
                try: ev = json.loads(line)
                except ValueError: continue
                if ev.get("type") == "result":
                    if ev.get("is_error"):
                        self._stop(); raise RuntimeError(str(ev.get("result") or ev.get("subtype"))[:300])
                    return ev.get("result", "")
            self._stop(); raise RuntimeError("timeout")


CLAUDE = Claude()

# ---------- التصويت ----------
POLL = {"id": "", "question": "", "options": [], "counts": [], "texts": [], "free": False, "multi": False, "voters": 0, "open": False}
VOTERS = set()
PLOCK = threading.Lock()


def poll_public():
    return {k: POLL[k] for k in ("id", "question", "options", "counts", "texts", "free", "multi", "voters", "open")}


class H(BaseHTTPRequestHandler):
    def _local(self):
        return self.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def _body(self):
        n = min(int(self.headers.get("content-length", "0") or 0), 200_000)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/info":
            return self._json({"vote_url": f"http://{lan_ip()}:{PORT}/vote"})
        if path == "/poll":
            with PLOCK: return self._json(poll_public())
        name = PUBLIC.get(path)
        if name is None and path.startswith("/assets/") and ".." not in path:
            name = path.lstrip("/")
        f = os.path.join(ROOT, name) if name else None
        if not f or not os.path.isfile(f):
            return self._json({"error": "not found"}, 404)
        data = open(f, "rb").read()
        self.send_response(200)
        self.send_header("content-type", TYPES.get(os.path.splitext(f)[1].lower(), "application/octet-stream"))
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            body = self._body()
        except ValueError:
            return self._json({"error": "bad json"}, 400)

        if path == "/ai":
            # الفهم الذكي يستخدم اشتراكك، فمسموح بس من نفس الجهاز
            if not self._local():
                return self._json({"error": "forbidden"}, 403)
            try:
                t0 = time.time()
                txt = CLAUDE.ask(str(body.get("system", "")), str(body.get("user", "")))
                ms = int((time.time() - t0) * 1000)
                try:
                    u = json.loads(body.get("user", "{}"))
                    said = u.get("الجملة_الحالية") or (u.get("الجمل_الأخيرة") or [""])[-1]
                except Exception:
                    said = ""
                sys.stderr.write(f"[هايكو {ms}ms] قلت: {said[:70]}\n           رد: {txt[:160]}\n")
                return self._json({"content": [{"type": "text", "text": txt}], "ms": ms})
            except Exception as e:
                return self._json({"error": {"message": str(e)}}, 500)

        if path == "/poll/open":
            if not self._local():
                return self._json({"error": "forbidden"}, 403)
            opts = [str(o)[:60] for o in (body.get("options") or [])][:6]
            with PLOCK:
                POLL.update(id=str(body.get("id", time.time()))[:40], question=str(body.get("question", ""))[:200],
                            options=opts, counts=[0] * len(opts), texts=[], free=bool(body.get("free")),
                            multi=bool(body.get("multi")), voters=0, open=True)
                VOTERS.clear()
                return self._json(poll_public())

        if path == "/poll/close":
            if not self._local():
                return self._json({"error": "forbidden"}, 403)
            with PLOCK:
                POLL["open"] = False
                return self._json(poll_public())

        if path == "/poll/vote":
            with PLOCK:
                if not POLL["open"] or body.get("poll") != POLL["id"]:
                    return self._json({"error": "closed"}, 409)
                voter = str(body.get("voter", ""))[:64]
                if not voter or voter in VOTERS:
                    return self._json({"error": "already"}, 409)
                opt, text = body.get("option"), str(body.get("text") or "").strip()[:140]
                n = len(POLL["counts"])
                if POLL["multi"] and isinstance(body.get("options"), list):
                    # اختيار متعدد: كل شخص يختار أكثر من خيار، بس يصوّت مرة وحدة
                    picked = {o for o in body["options"] if type(o) is int and 0 <= o < n}
                else:
                    picked = {opt} if type(opt) is int and 0 <= opt < n else set()
                text = text if POLL["free"] else ""
                if not picked and not text:
                    return self._json({"error": "empty"}, 400)
                for o in picked:
                    POLL["counts"][o] += 1
                if text:
                    POLL["texts"] = (POLL["texts"] + [text])[-60:]
                VOTERS.add(voter)
                POLL["voters"] = len(VOTERS)
                return self._json({"ok": True})

        return self._json({"error": "not found"}, 404)

    def log_message(self, fmt, *args):
        line = str(args[0] if args else "")
        if not any(k in line for k in ("/poll", "/ai", "/info", "/deck.json", "favicon", "GET / ")):
            sys.stderr.write("[server] " + (fmt % args) + "\n")


if __name__ == "__main__":
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    except OSError:
        sys.exit(f"المنفذ {PORT} مشغول (غالباً سيرفر قديم). سكّره أو شغّل على منفذ ثاني:  python3 server.py 8010")
    print(f"العرض:   http://localhost:{PORT}")
    print(f"الجمهور: http://{lan_ip()}:{PORT}/vote   (لازم يكونون على نفس الواي فاي)")
    print("اضغط Ctrl+C للإيقاف")
    srv.serve_forever()
