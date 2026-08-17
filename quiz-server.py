#!/usr/bin/env python3
"""
Onotsavam 2026 - Quiz buzzer server.

Standard library only, on purpose: on event day there may be no internet to
pip-install anything. Run it on the laptop that drives the projector, put every
phone on the same hotspot, and hand out the join URL it prints.

    python quiz-server.py

  phones (teams)   ->  http://<laptop-ip>:8000/
  projector        ->  http://localhost:8000/display
  quizmaster phone ->  http://<laptop-ip>:8000/admin   (PIN below)

Questions come from a Google Sheet the admin edits by hand. Only this server
ever sees the answer column - it is withheld from the broadcast until the
quizmaster reveals it, so it cannot reach the projector by accident.

Transport is Server-Sent Events: the server pushes state the instant it
changes, so a lockout lands on every phone without polling.
"""

import json
import mimetypes
import os
import queue
import secrets
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------- config ----

PORT = 8000
ADMIN_PIN = "onam26"        # keeps a bored participant off the scoring controls

# Google Sheet holding the questions. Share it as "anyone with the link can
# view", then paste the id from the sheet URL between /d/ and /edit. Leave it
# blank to fall back to quiz-questions.json. Can also be set from /admin.
SHEET_ID = ""
SHEET_TAB = "Quiz"

# Sheet columns, by header name. Anything unmatched falls back to this order:
#   Question | Option A | Option B | Option C | Option D | Answer
# The Answer cell may be a letter (A/B/C/D) or the full option text.

DEFAULT_TEAMS = [
    "Thiruvonam Titan's",
    "Gajaveerans",
    "Pulikali Panthers",
    "Onam Kombans",
    "Maveli Squad",
    "Chenda Champions",
    "Vallam Vikings",
    "Kerala Vibes",
]

POINTS_CORRECT = 10
POINTS_WRONG = 0            # set negative (e.g. -5) to punish speculative buzzing

# Every buzz landing within this window of the first one is judged together,
# and the earliest arrival wins. Absorbs thread-scheduling jitter; far too
# short for anyone in the hall to notice.
BUZZ_GRACE = 0.15

ROOT = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_FILE = os.path.join(ROOT, "quiz-questions.json")
SAVE_FILE = os.path.join(ROOT, "quiz-state.json")   # survives a mid-event restart

# ----------------------------------------------------------------- state ----

LOCK = threading.RLock()
SUBSCRIBERS = []            # list[queue.Queue] - one per open SSE stream

CODES = {}                  # team -> join code. Never broadcast.
TOKENS = {}                 # team -> secret token of the one signed-in phone
QUESTIONS = []              # [{q, options[], answer_index, answer_text}]

STATE = {
    "phase": "idle",        # idle | armed | buzzed
    "round": 0,             # bumped on every arm; clients drop stale rounds
    "question": "",
    "options": [],
    "answer": None,         # only populated once the quizmaster reveals it
    "q_index": -1,
    "q_total": 0,
    "winner": None,         # {"team": str, "ms": int}
    "order": [],            # full buzz order, for settling arguments
    "locked": [],           # teams that already answered wrong this round
    "scores": {},
    "teams": [],
    "active": {},           # team -> public session id of the signed-in phone
    "needs_code": {},       # team -> bool, so the phone knows whether to ask
    "source": "",           # where the questions came from, for the admin
    "join_url": "",
}

_armed_at = 0.0
_pending = []               # buzzes collected inside the grace window


# ------------------------------------------------------------ persistence ---

def save():
    """Team names, codes and scores survive a restart. Losing these mid-event
    would mean re-reading every code aloud again."""
    try:
        with open(SAVE_FILE, "w", encoding="utf-8") as fh:
            json.dump({
                "teams": STATE["teams"],
                "codes": CODES,
                "scores": STATE["scores"],
                "sheet_id": SHEET_ID,
                "sheet_tab": SHEET_TAB,
            }, fh, indent=2, ensure_ascii=False)
    except OSError as exc:
        print("  ! could not save state: %s" % exc)


def load_saved():
    global SHEET_ID, SHEET_TAB
    try:
        with open(SAVE_FILE, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, json.JSONDecodeError):
        set_teams(DEFAULT_TEAMS, {})
        return
    teams = d.get("teams") or DEFAULT_TEAMS
    set_teams(teams, d.get("codes") or {}, d.get("scores") or {})
    SHEET_ID = d.get("sheet_id", SHEET_ID)
    SHEET_TAB = d.get("sheet_tab", SHEET_TAB)


def set_teams(names, codes, scores=None):
    """Rename/replace the roster. Scores follow a team across a rename only if
    the name is unchanged; anything new starts at zero."""
    names = [str(n).strip() for n in names if str(n).strip()]
    if not names:
        names = list(DEFAULT_TEAMS)
    old = scores if scores is not None else STATE["scores"]
    with LOCK:
        STATE["teams"] = names
        STATE["scores"] = {n: int(old.get(n, 0)) for n in names}
        CODES.clear()
        CODES.update({n: str(codes.get(n, "")).strip() for n in names})
        STATE["needs_code"] = {n: bool(CODES[n]) for n in names}
        for t in list(TOKENS):
            if t not in names:
                TOKENS.pop(t, None)
                STATE["active"].pop(t, None)
        STATE["locked"] = [t for t in STATE["locked"] if t in names]


# ------------------------------------------------------------- questions ----

def _norm(s):
    return "".join(ch for ch in str(s).strip().lower() if ch.isalnum())


def _pick_col(cols, wanted, fallback):
    """Find a column by header, tolerating 'Option A' / 'OptionA' / 'A'."""
    for i, c in enumerate(cols):
        if _norm(c) in wanted:
            return i
    return fallback


def parse_sheet(text):
    """gviz wraps its JSON in a JS callback; unwrap it, then map the columns."""
    body = text[text.index("{"): text.rindex("}") + 1]
    table = json.loads(body).get("table", {})
    cols = [(c.get("label") or "") for c in table.get("cols", [])]

    iq = _pick_col(cols, {"question", "q", "questions"}, 0)
    ia = _pick_col(cols, {"optiona", "a", "option1", "1"}, 1)
    ib = _pick_col(cols, {"optionb", "b", "option2", "2"}, 2)
    ic = _pick_col(cols, {"optionc", "c", "option3", "3"}, 3)
    idd = _pick_col(cols, {"optiond", "d", "option4", "4"}, 4)
    ians = _pick_col(cols, {"answer", "ans", "correct", "correctanswer", "key"}, 5)

    out = []
    for row in table.get("rows", []):
        cells = row.get("c") or []

        def val(i):
            if i is None or i >= len(cells) or not cells[i]:
                return ""
            v = cells[i].get("v")
            return "" if v is None else str(v).strip()

        q = val(iq)
        if not q:
            continue
        opts = [val(ia), val(ib), val(ic), val(idd)]
        if not any(opts):
            opts = []
        out.append(_build(q, opts, val(ians)))
    return out


def _build(q, opts, ans):
    """Answer may be a letter or the option text; accept either."""
    idx, text = None, ans
    if opts:
        letter = _norm(ans)
        if letter in ("a", "b", "c", "d"):
            idx = "abcd".index(letter)
            text = opts[idx]
        else:
            for i, o in enumerate(opts):
                if o and _norm(o) == _norm(ans):
                    idx, text = i, o
                    break
    return {"q": q, "options": opts, "answer_index": idx, "answer_text": text}


def fetch_sheet():
    url = ("https://docs.google.com/spreadsheets/d/%s/gviz/tq"
           "?tqx=out:json&headers=1&sheet=%s&t=%d"
           % (SHEET_ID, urllib.parse.quote(SHEET_TAB), int(time.time())))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return parse_sheet(r.read().decode("utf-8", "replace"))


def load_questions():
    """Sheet first, local file as the safety net. The cached list is only
    replaced on success, so a dead connection mid-event changes nothing."""
    global QUESTIONS
    if SHEET_ID:
        try:
            rows = fetch_sheet()
            if rows:
                QUESTIONS = rows
                STATE["q_total"] = len(rows)
                STATE["source"] = "Google Sheet - %s (%d questions)" % (SHEET_TAB, len(rows))
                print("  loaded %d questions from the sheet" % len(rows))
                return True
            STATE["source"] = "Sheet '%s' had no usable rows" % SHEET_TAB
        except Exception as exc:                      # noqa: BLE001 - any failure falls back
            STATE["source"] = "Sheet unreachable (%s)" % type(exc).__name__
            print("  ! sheet fetch failed: %s" % exc)
        if QUESTIONS:
            return False                              # keep what we already had

    try:
        with open(QUESTIONS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        QUESTIONS = [_build(d.get("q", ""), d.get("options") or [], d.get("a", ""))
                     for d in data if d.get("q")]
        STATE["source"] = (STATE["source"] + " - using quiz-questions.json"
                           if SHEET_ID else "quiz-questions.json (%d questions)" % len(QUESTIONS))
    except (OSError, json.JSONDecodeError) as exc:
        print("  ! no questions available: %s" % exc)
        QUESTIONS = []
        STATE["source"] = "No questions loaded"
    STATE["q_total"] = len(QUESTIONS)
    return False


# ------------------------------------------------------------- broadcast ----

def public_state():
    """Safe for the projector and every phone - codes and unrevealed answers
    are not in here at all."""
    with LOCK:
        return dict(STATE)


def broadcast():
    payload = "data: " + json.dumps(public_state()) + "\n\n"
    for q in list(SUBSCRIBERS):
        try:
            q.put_nowait(payload)
        except queue.Full:
            pass


# ------------------------------------------------------------------ join -----

def do_join(team, code):
    """One phone per team. A later sign-in takes over and the earlier phone is
    told so - a dead battery must not lock a team out of the rest of the quiz."""
    with LOCK:
        if team not in STATE["scores"]:
            return {"ok": False, "reason": "unknown_team"}
        want = CODES.get(team, "")
        if want and str(code).strip() != want:
            return {"ok": False, "reason": "bad_code"}
        token = secrets.token_urlsafe(16)
        sid = secrets.token_hex(3)
        TOKENS[team] = token
        STATE["active"][team] = sid
    broadcast()
    return {"ok": True, "token": token, "sid": sid, "team": team}


# ----------------------------------------------------------------- buzzer ---

def resolve_buzz(round_id):
    """Pick the winner once the grace window closes."""
    with LOCK:
        if STATE["round"] != round_id or STATE["phase"] != "armed" or not _pending:
            return
        ordered = sorted(_pending, key=lambda b: b["t"])
        STATE["order"] = [
            {"team": b["team"], "ms": int((b["t"] - _armed_at) * 1000)}
            for b in ordered
        ]
        STATE["winner"] = STATE["order"][0]
        STATE["phase"] = "buzzed"
        _pending.clear()
    broadcast()


def do_buzz(team, token):
    t = time.monotonic()            # stamp arrival before touching the lock
    with LOCK:
        if team not in STATE["scores"]:
            return {"ok": False, "reason": "unknown_team"}
        if TOKENS.get(team) != token:
            return {"ok": False, "reason": "signed_out"}
        if STATE["phase"] != "armed":
            return {"ok": False, "reason": "not_armed"}
        if team in STATE["locked"]:
            return {"ok": False, "reason": "locked_out"}
        if any(b["team"] == team for b in _pending):
            return {"ok": True, "reason": "already_in"}
        _pending.append({"team": team, "t": t})
        if len(_pending) == 1:
            threading.Timer(BUZZ_GRACE, resolve_buzz, args=(STATE["round"],)).start()
    return {"ok": True}


# ------------------------------------------------------------------ admin ---

def set_question(index):
    global _armed_at
    with LOCK:
        if not QUESTIONS:
            return
        index = max(0, min(index, len(QUESTIONS) - 1))
        rec = QUESTIONS[index]
        STATE["q_index"] = index
        STATE["question"] = rec["q"]
        STATE["options"] = list(rec["options"])
        STATE["answer"] = None                 # withheld until reveal
        STATE["phase"] = "idle"
        STATE["winner"] = None
        STATE["order"] = []
        STATE["locked"] = []
        _pending.clear()
        _armed_at = 0.0


def do_admin(action, body):
    global _armed_at, SHEET_ID, SHEET_TAB
    with LOCK:
        if action == "arm":
            STATE["phase"] = "armed"
            STATE["round"] += 1
            STATE["winner"] = None
            STATE["order"] = []
            _pending.clear()
            _armed_at = time.monotonic()

        elif action == "reset":
            STATE["phase"] = "idle"
            STATE["winner"] = None
            STATE["order"] = []
            STATE["locked"] = []
            _pending.clear()

        elif action == "wrong":
            w = STATE["winner"]
            if w:
                if w["team"] not in STATE["locked"]:
                    STATE["locked"].append(w["team"])
                if POINTS_WRONG:
                    STATE["scores"][w["team"]] = STATE["scores"].get(w["team"], 0) + POINTS_WRONG
            STATE["winner"] = None
            STATE["order"] = []
            _pending.clear()
            if len(STATE["locked"]) >= len(STATE["teams"]):
                STATE["phase"] = "idle"
            else:
                STATE["phase"] = "armed"
                STATE["round"] += 1
                _armed_at = time.monotonic()
            save()

        elif action == "correct":
            w = STATE["winner"]
            if w:
                pts = int(body.get("points", POINTS_CORRECT))
                STATE["scores"][w["team"]] = STATE["scores"].get(w["team"], 0) + pts
            STATE["phase"] = "idle"
            save()

        elif action == "reveal":
            i = STATE["q_index"]
            if 0 <= i < len(QUESTIONS):
                rec = QUESTIONS[i]
                STATE["answer"] = {"index": rec["answer_index"], "text": rec["answer_text"]}

        elif action == "hide":
            STATE["answer"] = None

        elif action == "adjust":
            team, delta = body.get("team"), int(body.get("delta", 0))
            if team in STATE["scores"]:
                STATE["scores"][team] = STATE["scores"][team] + delta
                save()

        elif action == "question":
            if "index" in body:
                set_question(int(body["index"]))
            elif "text" in body:
                STATE["question"] = str(body["text"])
                STATE["options"] = []
                STATE["answer"] = None
                STATE["q_index"] = -1
                STATE["phase"] = "idle"
                STATE["winner"] = None
                STATE["order"] = []
                STATE["locked"] = []

        elif action == "teams":
            set_teams(body.get("names") or [], body.get("codes") or {})
            save()

        elif action == "sign_out":
            team = body.get("team")
            TOKENS.pop(team, None)
            STATE["active"].pop(team, None)

        elif action == "reset_scores":
            for t in STATE["scores"]:
                STATE["scores"][t] = 0
            save()

        elif action == "sheet":
            SHEET_ID = str(body.get("sheet_id", "")).strip()
            SHEET_TAB = str(body.get("sheet_tab", "") or "Quiz").strip()
            save()

    if action in ("reload", "sheet"):
        load_questions()                       # network call - outside the lock
        with LOCK:
            if QUESTIONS and STATE["q_index"] >= 0:
                set_question(min(STATE["q_index"], len(QUESTIONS) - 1))
            elif QUESTIONS:
                set_question(0)

    broadcast()
    return {"ok": True, "source": STATE["source"]}


# ------------------------------------------------------------------ HTTP -----

PAGES = {
    "/": "quiz-buzzer.html",
    "/display": "quiz-display.html",
    "/admin": "quiz-admin.html",
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"       # keep-alive, so a buzz reuses a warm socket
    server_version = "OnotsavamQuiz/1.0"

    def log_message(self, fmt, *args):
        pass                            # the console is for the join URL, not a log

    # -- helpers --

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj))

    def _read_body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or "{}")
        except (ValueError, json.JSONDecodeError):
            return {}

    # -- routes --

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/events":
            return self.sse()

        if path == "/api/teams":
            # Codes live here, behind the PIN, so they never reach a phone.
            if self.headers.get("X-Pin") != ADMIN_PIN:
                return self._json({"ok": False, "reason": "bad_pin"}, 403)
            return self._json({
                "ok": True,
                "teams": STATE["teams"],
                "codes": CODES,
                "sheet_id": SHEET_ID,
                "sheet_tab": SHEET_TAB,
                "source": STATE["source"],
                "questions": [{"q": q["q"], "options": q["options"],
                               "answer_index": q["answer_index"],
                               "answer_text": q["answer_text"]} for q in QUESTIONS],
            })

        if path in PAGES:
            return self.serve_file(PAGES[path])

        return self.serve_file(path.lstrip("/"))

    def do_POST(self):
        path = self.path.split("?")[0]
        body = self._read_body()

        if path == "/api/join":
            return self._json(do_join(body.get("team", ""), body.get("code", "")))

        if path == "/api/buzz":
            return self._json(do_buzz(body.get("team", ""), body.get("token", "")))

        if path == "/api/ping":
            return self._json({"ok": True})       # opens the socket before it matters

        if path == "/api/admin":
            if body.get("pin") != ADMIN_PIN:
                return self._json({"ok": False, "reason": "bad_pin"}, 403)
            return self._json(do_admin(body.get("action", ""), body))

        return self._json({"ok": False, "reason": "not_found"}, 404)

    # -- static --

    def serve_file(self, rel):
        rel = rel or "quiz-buzzer.html"
        full = os.path.abspath(os.path.join(ROOT, rel.replace("/", os.sep)))
        if not full.startswith(ROOT) or not os.path.isfile(full):
            return self._send(404, "Not found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as fh:
            self._send(200, fh.read(), ctype)

    # -- SSE --

    def sse(self):
        q = queue.Queue(maxsize=64)
        SUBSCRIBERS.append(q)
        self.close_connection = True          # stream is close-delimited
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self.wfile.write(("data: " + json.dumps(public_state()) + "\n\n").encode("utf-8"))
            self.wfile.flush()
            while True:
                try:
                    msg = q.get(timeout=15)
                except queue.Empty:
                    msg = ": ping\n\n"        # keeps dozing phones attached
                self.wfile.write(msg.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            if q in SUBSCRIBERS:
                SUBSCRIBERS.remove(q)


# ------------------------------------------------------------------ boot -----

class QuizServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        """Phones close tabs, sleep and roam constantly, and each dropped SSE
        stream would otherwise dump a traceback over the join URL. Only real
        faults get printed."""
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))            # no packets leave; just picks a route
        return s.getsockname()[0]
    except OSError:
        pass
    finally:
        s.close()
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if not ip.startswith("127."):
                return ip
    except OSError:
        pass
    return "127.0.0.1"


def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)   # the join URL must never sit in a buffer
    except (AttributeError, OSError):
        pass
    load_saved()
    load_questions()
    if QUESTIONS:
        set_question(0)

    ip = lan_ip()
    STATE["join_url"] = "http://%s:%d/" % (ip, PORT)

    print("")
    print("  Onotsavam Quiz Buzzer")
    print("  " + "=" * 54)
    print("  Questions   %s" % STATE["source"])
    print("  Teams       %d" % len(STATE["teams"]))
    print("")
    print("  Teams join  http://%s:%d/" % (ip, PORT))
    print("  Projector   http://localhost:%d/display" % PORT)
    print("  Quizmaster  http://%s:%d/admin   PIN %s" % (ip, PORT, ADMIN_PIN))
    print("  " + "=" * 54)
    print("  If phones cannot reach it, allow Python through the Windows")
    print("  firewall on private networks, and check everyone is on the")
    print("  same hotspot. Ctrl-C to stop.")
    print("")

    srv = QuizServer(("0.0.0.0", PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
