"""
FlashForge — AI Flashcard Software  (single-file edition)
Run:  python flashforge.py
Deps: pip install PyQt6
"""

# ── stdlib ───────────────────────────────────────────────────────────────────
import json, math, os, random, sqlite3, sys, time, threading, urllib.request, urllib.error
from contextlib import contextmanager
from html.parser import HTMLParser
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# ── PyQt6 ────────────────────────────────────────────────────────────────────
from PyQt6.QtCore import (
    QEasingCurve, QPropertyAnimation, QSettings, QThread, QTimer,
    Qt, pyqtSignal,
)
from PyQt6.QtGui import (
    QKeyEvent, QKeySequence, QPainter, QColor, QPen, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QGraphicsOpacityEffect,
    QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QSpinBox, QStackedWidget, QStatusBar, QTextEdit, QVBoxLayout, QWidget,
)


# ============================================================================
# CONFIG
# ============================================================================

APP_NAME           = "FlashForge"
VERSION            = "1.0.0"
DEFAULT_CARD_COUNT = 15
DEFAULT_DIFFICULTY = "Medium"
DB_NAME            = "flashforge.db"
DIFFICULTIES       = ["Easy", "Medium", "Hard"]

# "openrouter/free" auto-picks whichever free model is currently live on
# OpenRouter, so it's the default — the pinned IDs below rotate out of
# OpenRouter's free tier fairly often and are offered as manual fallbacks,
# not guaranteed to still exist. Verified against openrouter.ai as of Sep 2026.
FREE_MODELS = [
    "openrouter/free",
    "openai/gpt-oss-120b:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-3-27b-it:free",
    "deepseek/deepseek-r1:free",
]
DEFAULT_FREE_MODEL = FREE_MODELS[0]


def get_app_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_db_path() -> Path:
    return get_app_data_dir() / DB_NAME


# ============================================================================
# DATABASE
# ============================================================================

@contextmanager
def get_connection():
    conn = sqlite3.connect(str(get_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn; conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS decks (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                category      TEXT DEFAULT '',
                created_at    TEXT NOT NULL,
                last_studied  TEXT,
                total_cards   INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS cards (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                deck_id           INTEGER NOT NULL,
                question          TEXT NOT NULL,
                answer            TEXT NOT NULL,
                category          TEXT DEFAULT '',
                difficulty        TEXT DEFAULT 'Medium',
                created_at        TEXT NOT NULL,
                times_reviewed    INTEGER DEFAULT 0,
                times_correct     INTEGER DEFAULT 0,
                last_reviewed     TEXT,
                next_review       TEXT,
                difficulty_rating REAL DEFAULT 2.5,
                FOREIGN KEY (deck_id) REFERENCES decks(id) ON DELETE CASCADE
            );
        """)


def create_deck(name: str, category: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO decks (name,category,created_at) VALUES (?,?,?)",
            (name, category, datetime.now().isoformat()))
        return cur.lastrowid


def add_cards(deck_id: int, card_list: List[Dict]):
    with get_connection() as conn:
        now = datetime.now().isoformat()
        for c in card_list:
            conn.execute(
                "INSERT INTO cards (deck_id,question,answer,category,difficulty,created_at,next_review)"
                " VALUES (?,?,?,?,?,?,?)",
                (deck_id, c.get("question",""), c.get("answer",""),
                 c.get("category",""), c.get("difficulty","Medium"), now, now))
        conn.execute(
            "UPDATE decks SET total_cards=(SELECT COUNT(*) FROM cards WHERE deck_id=?) WHERE id=?",
            (deck_id, deck_id))


def get_all_decks() -> List[Dict]:
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM decks ORDER BY created_at DESC")]


def get_deck_cards(deck_id: int) -> List[Dict]:
    with get_connection() as conn:
        return [dict(r) for r in
                conn.execute("SELECT * FROM cards WHERE deck_id=? ORDER BY id", (deck_id,))]


def get_deck_by_id(deck_id: int) -> Optional[Dict]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM decks WHERE id=?", (deck_id,)).fetchone()
        return dict(row) if row else None


def update_card_review(card_id: int, correct: bool):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        if not row: return
        tr = row["times_reviewed"] + 1
        tc = row["times_correct"] + (1 if correct else 0)
        rating = min(row["difficulty_rating"]+0.1, 5.0) if correct else max(row["difficulty_rating"]-0.3, 1.3)
        days   = max(1, int(rating * max(tc, 1) * 0.4)) if correct else 1
        conn.execute(
            "UPDATE cards SET times_reviewed=?,times_correct=?,last_reviewed=?,"
            "next_review=?,difficulty_rating=? WHERE id=?",
            (tr, tc, datetime.now().isoformat(),
             (datetime.now()+timedelta(days=days)).isoformat(), rating, card_id))


def delete_deck(deck_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM decks WHERE id=?", (deck_id,))


def rename_deck(deck_id: int, new_name: str):
    with get_connection() as conn:
        conn.execute("UPDATE decks SET name=? WHERE id=?", (new_name, deck_id))


def update_deck_studied(deck_id: int):
    with get_connection() as conn:
        conn.execute("UPDATE decks SET last_studied=? WHERE id=?",
                     (datetime.now().isoformat(), deck_id))


def get_due_cards(deck_id: int, limit: int = 20) -> List[Dict]:
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM cards WHERE deck_id=? AND (next_review IS NULL OR next_review<=?)"
            " ORDER BY next_review ASC LIMIT ?",
            (deck_id, datetime.now().isoformat(), limit))]


# ============================================================================
# AI GENERATOR
# ============================================================================

CHUNK_SIZE                    = 80_000   # larger chunks = fewer API calls
SLEEP_BETWEEN_CHUNKS          = 8.0      # 8s between chunks to stay safely under free-tier limits
OPENROUTER_MIN_INTERVAL_SEC   = 4.5      # minimum seconds between OpenRouter API calls (20 req/min = 3s; 4.5s = safe margin)
_OPENROUTER_RATE_LOCK         = threading.Lock()
_LAST_OPENROUTER_REQUEST      = 0.0

_MOCK_CARDS: List[Dict] = [
    {"question": "What is photosynthesis?",
     "answer": "The process by which plants use sunlight, water, and CO₂ to produce glucose and oxygen.",
     "category": "Biology", "difficulty": "Easy"},
    {"question": "What is Newton's First Law of Motion?",
     "answer": "An object at rest stays at rest; an object in motion stays in motion — unless acted on by an external force.",
     "category": "Physics", "difficulty": "Medium"},
    {"question": "What is the Pythagorean theorem?",
     "answer": "In a right triangle: a² + b² = c², where c is the hypotenuse.",
     "category": "Math", "difficulty": "Easy"},
]


class FlashcardGenerationError(Exception):
    pass


def _get_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        try:
            key = (QSettings("FlashForge","FlashForge").value("openrouter_api_key") or "").strip()
        except Exception:
            pass
    return key


def _get_openrouter_model() -> str:
    model = os.environ.get("OPENROUTER_MODEL", "").strip()
    if model:
        return model
    try:
        model = (QSettings("FlashForge","FlashForge").value("openrouter_model") or "").strip()
        if model:
            return model
    except Exception:
        pass
    return DEFAULT_FREE_MODEL


def _strip_markdown(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _call_openrouter(prompt: str, api_key: str, strict: bool = False,
                       status_callback: Optional[Callable[[str], None]] = None) -> str:
    global _LAST_OPENROUTER_REQUEST
    model_name = _get_openrouter_model()
    endpoint = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://flashforge.local",
        "X-Title": "FlashForge",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 FlashForge/1.0",
    }
    with _OPENROUTER_RATE_LOCK:
        wait_for_next = OPENROUTER_MIN_INTERVAL_SEC - (time.time() - _LAST_OPENROUTER_REQUEST)
        if wait_for_next > 0:
            if status_callback:
                status_callback(f"Waiting {wait_for_next:.1f}s for OpenRouter rate-limit slot…")
            time.sleep(wait_for_next)
        if strict:
            prompt += "\n\nCRITICAL: Return ONLY a valid JSON array. No markdown, no explanation."
        body = json.dumps({
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 4096,
        }).encode("utf-8")
        req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", errors="replace")
            try:
                err_data = json.loads(msg)
                err_msg = err_data.get("error", {}).get("message", msg)
            except Exception:
                err_msg = msg
            raise FlashcardGenerationError(f"OpenRouter HTTP {e.code}: {err_msg}")
        except urllib.error.URLError as e:
            raise FlashcardGenerationError(f"OpenRouter request failed: {e.reason}")
        except Exception as e:
            raise FlashcardGenerationError(f"OpenRouter request error: {e}")
        _LAST_OPENROUTER_REQUEST = time.time()
    try:
        data = json.loads(raw)
        if "choices" not in data or not data["choices"]:
            raise KeyError("No choices in response")
        choice = data["choices"][0]
        if "message" in choice and "content" in choice["message"]:
            content = choice["message"]["content"]
        elif "text" in choice:
            content = choice["text"]
        else:
            raise KeyError("No content or text in response")
    except Exception as e:
        raise FlashcardGenerationError(f"Could not parse OpenRouter response: {e}\n{raw[:500]}")
    return content


def _extract_json_array(text: str) -> str:
    """Grab the first [...] block, tolerating stray prose/markdown around it
    (some free models ignore 'JSON only' instructions and add commentary)."""
    text = _strip_markdown(text)
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return text
    return text[start:end+1]


def _parse_cards(raw: str, deck_name: str, category: str, difficulty: str) -> List[Dict]:
    data = json.loads(_extract_json_array(raw))
    if not isinstance(data, list):
        raise ValueError("Not a JSON array")
    now, out = datetime.now().isoformat(), []
    for item in data:
        q = str(item.get("question","")).strip()
        a = str(item.get("answer","")).strip()
        if q and a:
            out.append({"question": q, "answer": a,
                        "category": str(item.get("category", category)).strip() or category,
                        "difficulty": difficulty,
                        "deck_name": deck_name, "created_at": now})
    return out


def _call_openrouter_with_backoff(prompt: str, api_key: str, retries: int = 3,
                                   strict: bool = False,
                                   status_callback: Optional[Callable[[str], None]] = None) -> str:
    """Call OpenRouter with model failover — tries the selected model first,
    then automatically falls through all 8 free models before giving up."""
    # Build the model list: selected model first, then the rest as fallbacks
    selected = _get_openrouter_model()
    fallback_chain = [selected] + [m for m in FREE_MODELS if m != selected]

    last_error = ""
    for model_idx, model in enumerate(fallback_chain):
        for attempt in range(retries):
            try:
                # Temporarily override the model for this call
                orig_env = os.environ.get("OPENROUTER_MODEL")
                os.environ["OPENROUTER_MODEL"] = model
                try:
                    result = _call_openrouter(prompt, api_key, strict=strict,
                                              status_callback=status_callback)
                finally:
                    if orig_env is None:
                        os.environ.pop("OPENROUTER_MODEL", None)
                    else:
                        os.environ["OPENROUTER_MODEL"] = orig_env
                return result
            except Exception as e:
                msg = str(e)
                last_error = msg
                is_rate_limit = "429" in msg or "quota" in msg.lower() or "rate" in msg.lower()
                is_model_error = any(x in msg.lower() for x in
                                     ["model", "not found", "unavailable", "overloaded",
                                      "503", "502", "404"])
                if is_rate_limit or is_model_error:
                    if attempt < retries - 1 and not is_model_error:
                        wait = 10 * (attempt + 1)
                        if status_callback:
                            status_callback(
                                f"Model '{model.split('/')[-1]}' rate limited, "
                                f"retrying in {wait}s…")
                        time.sleep(wait)
                    else:
                        # Move to next model
                        next_model = fallback_chain[model_idx + 1] if model_idx + 1 < len(fallback_chain) else None
                        if next_model and status_callback:
                            status_callback(
                                f"⚡ '{model.split('/')[-1]}' failed — "
                                f"switching to '{next_model.split('/')[-1]}'…")
                        break  # break retries loop → go to next model
                else:
                    raise FlashcardGenerationError(f"OpenRouter API error: {msg}")

    raise FlashcardGenerationError(
        f"All 8 free models failed or are rate-limited.\n"
        f"Wait ~60 seconds and try again. Last error: {last_error}"
    )


def _gen_chunk(chunk: str, count: int, category: str, difficulty: str,
               deck_name: str, api_key: str,
               status_callback: Optional[Callable[[str], None]] = None) -> List[Dict]:
    diff_guide = {
        "Easy":   "Simple recall questions. Short, direct answers. Beginner-friendly.",
        "Medium": "Conceptual understanding questions. Answers require explanation.",
        "Hard":   "Deep analysis, edge cases, 'why/how' questions. Complex multi-part answers.",
    }.get(difficulty, "")
    prompt = (
        f"You are an expert flashcard creator. Create exactly {count} Q&A flashcards "
        f"from the text below at {difficulty} difficulty.\n\n"
        f"Difficulty guide: {diff_guide}\n\n"
        f'Return ONLY a valid JSON array, no markdown, no explanation:\n'
        f'[{{"question":"...","answer":"...","category":"{category}"}}]\n\n'
        f"Each answer 1-3 sentences.\n\nTEXT:\n{chunk}"
    )
    try:
        raw = _call_openrouter_with_backoff(prompt, api_key, strict=True,
                                              status_callback=status_callback)
        return _parse_cards(raw, deck_name, category, difficulty)
    except FlashcardGenerationError:
        raise
    except (json.JSONDecodeError, ValueError) as e:
        raise FlashcardGenerationError(f"Could not parse AI response. Try again.\n{e}")
    except Exception as e:
        raise FlashcardGenerationError(f"Unexpected error: {e}")


def generate_flashcards(text: str, deck_name: str, category: str,
                        count: int, difficulty: str,
                        status_callback: Optional[Callable[[str], None]] = None) -> List[Dict]:
    api_key = _get_api_key()
    if not api_key:
        raise FlashcardGenerationError("NO_API_KEY")

    chunks, all_cards = [text[i:i+CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)], []
    for idx, chunk in enumerate(chunks):
        remaining = count - len(all_cards)
        chunk_count = remaining if idx == len(chunks)-1 else max(1, count//len(chunks))
        all_cards.extend(_gen_chunk(chunk, min(chunk_count, remaining),
                                    category, difficulty, deck_name, api_key,
                                    status_callback=status_callback))
        if idx < len(chunks)-1:
            if status_callback:
                status_callback("Waiting between OpenRouter requests to avoid rate limits…")
            time.sleep(SLEEP_BETWEEN_CHUNKS)
        if len(all_cards) >= count: break
    if not all_cards:
        raise FlashcardGenerationError("No cards generated. Try pasting more detailed text.")
    return all_cards[:count]


# ============================================================================
# DOCUMENT + URL READERS
# ============================================================================

class _TextExtractor(HTMLParser):
    """Strips HTML tags and collapses whitespace."""
    def __init__(self):
        super().__init__(); self._parts = []; self._skip = False
    def handle_starttag(self, tag, attrs):
        if tag in ("script","style","nav","header","footer","aside"): self._skip = True
    def handle_endtag(self, tag):
        if tag in ("script","style","nav","header","footer","aside"): self._skip = False
        if tag in ("p","div","br","li","h1","h2","h3","h4","h5","h6","tr","td"):
            self._parts.append("\n")
    def handle_data(self, data):
        if not self._skip: self._parts.append(data)
    def get_text(self):
        import re
        text = "".join(self._parts)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def fetch_url_text(url: str) -> str:
    """Fetch a URL and return its visible text content."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            charset = "utf-8"
            ct = resp.headers.get_content_charset()
            if ct: charset = ct
            html = raw.decode(charset, errors="replace")
    except urllib.error.URLError as e:
        raise FlashcardGenerationError(f"Could not fetch URL: {e.reason}")
    except Exception as e:
        raise FlashcardGenerationError(f"URL fetch error: {e}")
    p = _TextExtractor(); p.feed(html)
    text = p.get_text()
    if len(text) < 100:
        raise FlashcardGenerationError("Page had too little readable text. Try a different URL.")
    return text


def read_document(path: str) -> str:
    """Extract text from a PDF, DOCX, or TXT file."""
    ext = Path(path).suffix.lower()
    if ext == ".txt":
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception as e:
            raise FlashcardGenerationError(f"Could not read file: {e}")
    elif ext == ".pdf":
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise FlashcardGenerationError(
                "PyMuPDF is required for PDF reading.\nRun: pip install PyMuPDF")
        try:
            doc = fitz.open(path)
            pages = [page.get_text() for page in doc]
            doc.close()
            text = "\n\n".join(pages).strip()
            if not text:
                raise FlashcardGenerationError("PDF appears to be image-only or empty.")
            return text
        except FlashcardGenerationError: raise
        except Exception as e:
            raise FlashcardGenerationError(f"PDF read error: {e}")
    elif ext == ".doc":
        raise FlashcardGenerationError(
            "Legacy .doc files aren't supported (python-docx only reads .docx).\n"
            "Open it in Word/LibreOffice and re-save as .docx, then try again.")
    elif ext == ".docx":
        try:
            import docx as _docx
        except ImportError:
            raise FlashcardGenerationError(
                "python-docx is required for Word files.\nRun: pip install python-docx")
        try:
            doc = _docx.Document(path)
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            if not text:
                raise FlashcardGenerationError("Document appears to be empty.")
            return text
        except FlashcardGenerationError: raise
        except Exception as e:
            raise FlashcardGenerationError(f"DOCX read error: {e}")
    else:
        raise FlashcardGenerationError(f"Unsupported file type: {ext}.\nSupported: PDF, DOCX, TXT")


# ============================================================================
# EXPORT / IMPORT
# ============================================================================

def export_deck_to_json(deck_id: int, output_dir: Optional[str] = None) -> str:
    deck  = get_deck_by_id(deck_id)
    cards = get_deck_cards(deck_id)
    payload = {"flashforge_export": True, "version": "1.0",
               "exported_at": datetime.now().isoformat(),
               "decks": [{"name": deck["name"], "category": deck["category"],
                          "cards": [{"question": c["question"], "answer": c["answer"],
                                     "category": c["category"], "difficulty": c.get("difficulty","Medium")}
                                    for c in cards]}]}
    safe = "".join(ch if ch.isalnum() or ch in " _-" else "_" for ch in deck["name"])
    out  = Path(output_dir or ".") / f"{safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return str(out)


def export_all_to_json(output_dir: Optional[str] = None) -> str:
    payload = {"flashforge_export": True, "version": "1.0",
               "exported_at": datetime.now().isoformat(),
               "decks": [{"name": d["name"], "category": d["category"],
                          "cards": [{"question": c["question"], "answer": c["answer"],
                                     "category": c["category"], "difficulty": c.get("difficulty","Medium")}
                                    for c in get_deck_cards(d["id"])]}
                         for d in get_all_decks()]}
    out = Path(output_dir or ".") / f"FlashForge_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return str(out)


def import_from_json(file_path: str) -> Tuple[int, str]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e: return 0, f"Invalid JSON: {e}"
    except OSError as e:             return 0, f"Could not read file: {e}"
    if not isinstance(data, dict) or not isinstance(data.get("decks"), list):
        return 0, "No valid 'decks' array found."
    imported = 0
    for dd in data["decks"]:
        if not dd.get("name"): continue
        try:
            did = create_deck(dd["name"], dd.get("category",""))
            add_cards(did, [c for c in dd.get("cards",[])
                            if c.get("question") and c.get("answer")])
            imported += 1
        except Exception as e:
            return imported, f"DB error: {e}"
    return imported, ""


# ============================================================================
# SCORE RING WIDGET  (ported from React SVG version)
# ============================================================================

class ScoreRing(QWidget):
    """Animated circular progress ring — matches the React scoreRing SVG."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(120, 120)
        self._pct     = 0
        self._target  = 0
        self._timer   = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def set_score(self, pct: int):
        self._target = pct
        self._pct    = 0
        self._timer.start(12)   # ~80 fps animation

    def _tick(self):
        if self._pct < self._target:
            self._pct = min(self._pct + 2, self._target)
            self.update()
        else:
            self._timer.stop()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, r = 60, 60, 46
        # Track
        p.setPen(QPen(QColor("#2c2c28"), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawEllipse(cx-r, cy-r, r*2, r*2)
        # Arc
        if self._pct > 0:
            span = int(self._pct / 100 * 360 * 16)
            color = "#3dba7e" if self._pct >= 70 else "#e8c84a" if self._pct >= 50 else "#e05252"
            p.setPen(QPen(QColor(color), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(cx-r, cy-r, r*2, r*2, 90*16, -span)
        # Text
        p.setPen(QColor("#f2f0eb"))
        font = p.font(); font.setPointSize(18); font.setBold(True); p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"{self._pct}%")
        p.end()


# ============================================================================
# CONFETTI WIDGET  (ported from React canvas-confetti)
# ============================================================================

class ConfettiWidget(QWidget):
    """Simple confetti burst — auto-hides after 2.5s."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._particles = []
        self._timer = QTimer(self); self._timer.timeout.connect(self._tick)

    def burst(self):
        colors = ["#e8c84a","#3dba7e","#38bfbf","#e87d3e","#e05252","#a78bfa"]
        self._particles = [
            {"x": random.randint(100, self.width()-100),
             "y": random.randint(-20, 0),
             "vx": random.uniform(-3, 3),
             "vy": random.uniform(3, 8),
             "color": random.choice(colors),
             "size": random.randint(6, 12),
             "rot": random.uniform(0, 360),
             "spin": random.uniform(-5, 5),
             "life": 1.0}
            for _ in range(120)
        ]
        self.raise_(); self.show()
        self._timer.start(16)
        QTimer.singleShot(2500, self.hide)

    def _tick(self):
        alive = []
        for p in self._particles:
            p["x"] += p["vx"]; p["vy"] += 0.2; p["y"] += p["vy"]
            p["rot"] += p["spin"]; p["life"] -= 0.012
            if p["life"] > 0 and p["y"] < self.height() + 20:
                alive.append(p)
        self._particles = alive
        if not alive: self._timer.stop()
        self.update()

    def paintEvent(self, event):
        if not self._particles: return
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for pt in self._particles:
            p.save()
            p.translate(pt["x"], pt["y"]); p.rotate(pt["rot"])
            color = QColor(pt["color"])
            color.setAlphaF(min(pt["life"], 1.0))
            p.fillRect(-pt["size"]//2, -pt["size"]//4, pt["size"], pt["size"]//2, color)
            p.restore()
        p.end()


# ============================================================================
# STYLESHEET
# ============================================================================

STYLESHEET = """
QMainWindow, QDialog { background-color: #0e0e0c; }
QWidget { background-color: #0e0e0c; color: #f2f0eb; font-size: 13px; }
QScrollArea, QScrollArea > QWidget > QWidget { background-color: transparent; border: none; }

#sidebar { background-color: #141412; border-right: 1px solid rgba(255,255,255,0.06);
           min-width: 200px; max-width: 200px; }
#sidebarLogo { font-size: 22px; font-weight: 800; color: #f2f0eb;
               letter-spacing: -0.03em; padding: 28px 24px 20px 24px; background: transparent; }
#navBtn { background: transparent; color: #6b6860; border: none; border-radius: 10px;
          padding: 11px 18px; font-size: 13px; font-weight: 600; text-align: left; margin: 1px 10px; }
#navBtn:hover { background-color: rgba(255,255,255,0.05); color: #c8c4bc; }
#navBtnActive { background-color: rgba(232,200,74,0.1); color: #e8c84a; border: none;
                border-radius: 10px; padding: 11px 18px; font-size: 13px;
                font-weight: 700; text-align: left; margin: 1px 10px; }

#viewTitle { font-size: 26px; font-weight: 800; color: #f2f0eb; background: transparent; }
#viewSub { font-size: 13px; color: #7a766f; background: transparent; }
#sectionHeader { font-size: 11px; font-weight: 700; letter-spacing: 0.1em;
                 color: #5c5a55; background: transparent; padding-top: 4px; }

QLineEdit, QTextEdit, QSpinBox, QComboBox {
    background-color: #1a1a17; color: #f2f0eb;
    border: 1px solid rgba(255,255,255,0.08); border-radius: 10px;
    padding: 10px 14px; selection-background-color: rgba(232,200,74,0.3); }
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus { border-color: rgba(232,200,74,0.4); }
QComboBox:focus { border-color: rgba(232,200,74,0.4); }
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView { background-color: #242420; color: #f2f0eb;
    border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;
    selection-background-color: rgba(232,200,74,0.15); selection-color: #e8c84a; padding: 4px; }
QSpinBox::up-button, QSpinBox::down-button { width: 0; }
#textInput { font-size: 14px; border-radius: 14px; padding: 16px; }

QPushButton { background-color: #242420; color: #a8a49c;
    border: 1px solid rgba(255,255,255,0.07); border-radius: 10px;
    padding: 10px 18px; font-size: 13px; font-weight: 600; }
QPushButton:hover { background-color: #2e2e2a; color: #f2f0eb; border-color: rgba(255,255,255,0.13); }
QPushButton:pressed { background-color: #1e1e1b; }
QPushButton:disabled { opacity: 0.35; }

#generateBtn { background-color: rgba(232,200,74,0.12); color: #e8c84a;
    border: 1px solid rgba(232,200,74,0.25); border-radius: 12px;
    font-size: 14px; font-weight: 700; padding: 12px 24px; }
#generateBtn:hover { background-color: rgba(232,200,74,0.2); }

#saveBtn { background-color: rgba(61,186,126,0.12); color: #3dba7e;
    border: 1px solid rgba(61,186,126,0.25); border-radius: 10px; font-weight: 700; padding: 8px 18px; }
#saveBtn:hover { background-color: rgba(61,186,126,0.22); }

#saveKeyBtn { background-color: rgba(232,200,74,0.08); color: #e8c84a;
    border: 1px solid rgba(232,200,74,0.2); border-radius: 10px; font-weight: 600; }
#saveKeyBtn:hover { background-color: rgba(232,200,74,0.16); }

#headerBtn { background-color: #1e1e1b; color: #a8a49c;
    border: 1px solid rgba(255,255,255,0.08); border-radius: 9px; padding: 8px 16px; font-weight: 600; }
#headerBtn:hover { background-color: #2a2a26; color: #f2f0eb; }

#dangerBtn { background-color: rgba(224,82,82,0.08); color: #e05252;
    border: 1px solid rgba(224,82,82,0.2); border-radius: 10px; padding: 8px 16px; font-weight: 600; }
#dangerBtn:hover { background-color: rgba(224,82,82,0.16); }

#showBtn { background-color: #1e1e1b; color: #7a766f;
    border: 1px solid rgba(255,255,255,0.08); border-radius: 10px;
    padding: 10px 14px; font-weight: 600; max-width: 70px; }

#diffEasy   { background-color: rgba(61,186,126,0.12); color: #3dba7e;
    border: 1px solid rgba(61,186,126,0.25); border-radius: 10px; font-weight: 700; padding: 10px 20px; }
#diffEasy:hover   { background-color: rgba(61,186,126,0.22); }
#diffEasyOn { background-color: rgba(61,186,126,0.3);  color: #3dba7e;
    border: 2px solid #3dba7e; border-radius: 10px; font-weight: 700; padding: 9px 19px; }

#diffMedium   { background-color: rgba(232,200,74,0.1); color: #e8c84a;
    border: 1px solid rgba(232,200,74,0.25); border-radius: 10px; font-weight: 700; padding: 10px 20px; }
#diffMedium:hover { background-color: rgba(232,200,74,0.2); }
#diffMediumOn { background-color: rgba(232,200,74,0.28); color: #e8c84a;
    border: 2px solid #e8c84a; border-radius: 10px; font-weight: 700; padding: 9px 19px; }

#diffHard   { background-color: rgba(224,82,82,0.1); color: #e05252;
    border: 1px solid rgba(224,82,82,0.25); border-radius: 10px; font-weight: 700; padding: 10px 20px; }
#diffHard:hover   { background-color: rgba(224,82,82,0.2); }
#diffHardOn { background-color: rgba(224,82,82,0.28); color: #e05252;
    border: 2px solid #e05252; border-radius: 10px; font-weight: 700; padding: 9px 19px; }

QProgressBar { background-color: #2c2c28; border: none; border-radius: 2px; height: 4px; }
QProgressBar::chunk { background-color: #e8c84a; border-radius: 2px; }
QStatusBar { background-color: #0e0e0c; color: #5c5a55; font-size: 12px;
             border-top: 1px solid rgba(255,255,255,0.05); }

QScrollBar:vertical { background: transparent; width: 5px; margin: 0; }
QScrollBar::handle:vertical { background: #3a3a36; border-radius: 3px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QMenu { background-color: #242420; border: 1px solid rgba(255,255,255,0.1);
        border-radius: 10px; padding: 4px; color: #f2f0eb; }
QMenu::item { padding: 8px 20px; border-radius: 7px; }
QMenu::item:selected { background-color: rgba(255,255,255,0.07); }
QMenu::separator { background: rgba(255,255,255,0.07); height: 1px; margin: 3px 0; }

#settingLabel { color: #a8a49c; background: transparent; }
#statusLabel  { font-size: 13px; font-weight: 600; background: transparent; }
#previewFrame, #previewContainer { background: transparent; }
#previewTitle { font-size: 13px; font-weight: 700; color: #a8a49c; background: transparent; }
#previewScroll { border: none; background: transparent; }
#previewCard { background-color: #1a1a17; border: 1px solid rgba(255,255,255,0.07); border-radius: 10px; }
#previewNum { color: #5c5a55; font-size: 12px; font-weight: 700; background: transparent; }
#previewQ   { color: #f2f0eb; font-size: 12px; font-weight: 600; background: transparent; }
#previewA   { color: #7a766f; font-size: 12px; background: transparent; }
#previewArrow { color: #3a3a36; font-size: 14px; background: transparent; }
#previewMore  { color: #5c5a55; font-size: 12px; padding: 6px 0; background: transparent; }

#deckScroll, #deckGrid { background: transparent; }
#deckCard { background-color: #181816; border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; }
#deckCard:hover { background-color: #1e1e1a; border-color: rgba(255,255,255,0.14); }
#deckCardName { font-size: 15px; font-weight: 700; color: #f2f0eb; background: transparent; }
#deckCardCat  { background: transparent; }
#deckCardStat { font-size: 11px; color: #5c5a55; background: transparent; }
#deckStudyBtn { background-color: rgba(232,200,74,0.1); color: #e8c84a;
    border: 1px solid rgba(232,200,74,0.2); border-radius: 8px;
    padding: 7px 12px; font-size: 12px; font-weight: 700; }
#deckStudyBtn:hover { background-color: rgba(232,200,74,0.18); }
#deckDeleteBtn { background-color: rgba(224,82,82,0.08); color: #e05252;
    border: 1px solid rgba(224,82,82,0.15); border-radius: 8px; font-weight: 700; padding: 7px; }
#deckDeleteBtn:hover { background-color: rgba(224,82,82,0.18); }
#emptyMsg { font-size: 16px; color: #5c5a55; background: transparent; }

#studyDeckName { font-size: 16px; font-weight: 700; color: #f2f0eb; background: transparent; }
#studyScore    { font-size: 13px; color: #5c5a55; background: transparent; }
#studyDiff     { font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
                 background: transparent; padding: 3px 10px; border-radius: 6px; }
#progressLbl   { font-size: 12px; font-weight: 600; color: #5c5a55; background: transparent; letter-spacing: 0.04em; }
#endBtn { background: transparent; color: #5c5a55; border: 1px solid rgba(255,255,255,0.07);
          border-radius: 8px; padding: 6px 14px; font-size: 12px; }
#endBtn:hover { color: #e05252; border-color: rgba(224,82,82,0.3); }

#flipCard { background-color: #1c1c19; border: 1px solid rgba(255,255,255,0.1); border-radius: 20px; }
#flipCard:hover { border-color: rgba(255,255,255,0.16); }
#cardFace, #cardBack { background: transparent; }
#cardBadge { font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: #e8c84a; background: transparent; }
#cardFaceLabel     { font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: #3a3a36; background: transparent; }
#cardFaceLabelBack { font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: #2a4a38; background: transparent; }
#questionText { font-size: 20px; font-weight: 700; color: #f2f0eb; background: transparent; }
#answerText   { font-size: 16px; color: #d4d0c8; font-weight: 300; background: transparent; }
#flipHint     { font-size: 12px; color: #3a3a36; background: transparent; }

#knewBtn { background-color: rgba(61,186,126,0.12); color: #3dba7e;
    border: 1px solid rgba(61,186,126,0.2); border-radius: 12px; padding: 14px; font-size: 14px; font-weight: 700; }
#knewBtn:hover:!disabled { background-color: rgba(61,186,126,0.22); }
#missBtn { background-color: rgba(224,82,82,0.12); color: #e05252;
    border: 1px solid rgba(224,82,82,0.2); border-radius: 12px; padding: 14px; font-size: 14px; font-weight: 700; }
#missBtn:hover:!disabled { background-color: rgba(224,82,82,0.22); }
#skipBtn { background-color: #1a1a17; color: #7a766f;
    border: 1px solid rgba(255,255,255,0.07); border-radius: 12px; padding: 14px; font-size: 13px; font-weight: 600; }
#skipBtn:hover { background-color: #242420; color: #f2f0eb; }
#shortcutsHint { font-size: 11px; color: #3a3a36; background: transparent; }

#summaryGrade { font-size: 28px; font-weight: 800; color: #f2f0eb; background: transparent; }
#summarySub   { font-size: 14px; color: #7a766f; background: transparent; }
#statsFrame   { background-color: #181816; border: 1px solid rgba(255,255,255,0.07); border-radius: 14px; padding: 16px; }
#statNumGreen { font-size: 32px; font-weight: 800; color: #3dba7e; background: transparent; }
#statNumRed   { font-size: 32px; font-weight: 800; color: #e05252; background: transparent; }
#statNumGray  { font-size: 32px; font-weight: 800; color: #5c5a55; background: transparent; }
#statLbl      { font-size: 12px; color: #5c5a55; background: transparent; }
#missedTitle  { font-size: 11px; font-weight: 700; letter-spacing: 0.1em; color: #5c5a55; background: transparent; }
#missedScroll { border: none; }
#missedRow    { background-color: #181816; border: 1px solid rgba(255,255,255,0.06); border-radius: 10px; }
#missedCat { font-size: 10px; font-weight: 700; color: #e8c84a; background: transparent; min-width: 60px; letter-spacing: 0.06em; }
#missedQ   { font-size: 12px; color: #a8a49c; background: transparent; }
#retryBtn { background-color: rgba(232,200,74,0.1); color: #e8c84a;
    border: 1px solid rgba(232,200,74,0.2); border-radius: 10px; padding: 12px; font-size: 13px; font-weight: 700; }
#retryBtn:hover { background-color: rgba(232,200,74,0.18); }
#restartBtn { background-color: #1a1a17; color: #a8a49c;
    border: 1px solid rgba(255,255,255,0.07); border-radius: 10px; padding: 12px; font-size: 13px; font-weight: 600; }
#restartBtn:hover { background-color: #242420; color: #f2f0eb; }
#backBtn { background-color: transparent; color: #5c5a55;
    border: 1px solid rgba(255,255,255,0.06); border-radius: 10px; padding: 12px; font-size: 13px; }
#backBtn:hover { color: #f2f0eb; }

#settingDesc { font-size: 12px; color: #5c5a55; background: transparent; line-height: 1.6; }
#aboutFrame  { background-color: #181816; border: 1px solid rgba(255,255,255,0.07); border-radius: 14px; }
#aboutApp    { font-size: 14px; color: #f2f0eb; background: transparent; }
#aboutDesc   { font-size: 12px; color: #5c5a55; background: transparent; line-height: 1.6; }
"""


# ============================================================================
# VIEW — GENERATE
# ============================================================================

class GenerateWorker(QThread):
    finished = pyqtSignal(list)
    error    = pyqtSignal(str)
    status   = pyqtSignal(str)

    def __init__(self, text, deck_name, category, count, difficulty):
        super().__init__()
        self.text = text; self.deck_name = deck_name; self.category = category
        self.count = count; self.difficulty = difficulty

    def run(self):
        try:
            self.finished.emit(generate_flashcards(
                self.text, self.deck_name, self.category,
                self.count, self.difficulty,
                status_callback=self.status.emit))
        except Exception as e:
            self.error.emit(str(e))


class GenerateView(QWidget):
    cards_ready = pyqtSignal(str, str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._cards  = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 36, 40, 36)
        root.setSpacing(20)

        t = QLabel("Generate Flashcards"); t.setObjectName("viewTitle"); root.addWidget(t)
        s = QLabel("Paste text, upload a document (PDF/DOCX/TXT), or enter a URL — AI turns it into flashcards.")
        s.setObjectName("viewSub"); s.setWordWrap(True); root.addWidget(s)

        # ── No API key banner (hidden until needed) ───────────────────
        self.no_key_banner = QLabel(
            "⚠  No API key set — go to Settings → AI Configuration and save your OpenRouter key first.")
        self.no_key_banner.setWordWrap(True)
        self.no_key_banner.setStyleSheet(
            "color:#e8c84a;background:rgba(232,200,74,0.08);border:1px solid rgba(232,200,74,0.25);"
            "border-radius:10px;padding:10px 14px;font-size:13px;font-weight:600;")
        self.no_key_banner.setVisible(False)
        root.addWidget(self.no_key_banner)

        # ── URL row ───────────────────────────────────────────────────
        url_row = QHBoxLayout(); url_row.setSpacing(10)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Or enter a URL to fetch content from  (e.g. https://en.wikipedia.org/wiki/…)")
        url_row.addWidget(self.url_edit, 1)
        self.fetch_btn = QPushButton("⬇  Fetch URL"); self.fetch_btn.setObjectName("headerBtn")
        self.fetch_btn.setFixedHeight(40); self.fetch_btn.clicked.connect(self._on_fetch_url)
        url_row.addWidget(self.fetch_btn)
        root.addLayout(url_row)

        # ── Document upload row ───────────────────────────────────────
        doc_row = QHBoxLayout(); doc_row.setSpacing(10)
        self.upload_btn = QPushButton("📄  Upload Document"); self.upload_btn.setObjectName("headerBtn")
        self.upload_btn.setFixedHeight(40); self.upload_btn.clicked.connect(self._on_upload_doc)
        doc_row.addWidget(self.upload_btn)
        self.doc_label = QLabel(""); self.doc_label.setObjectName("settingLabel")
        doc_row.addWidget(self.doc_label); doc_row.addStretch()
        root.addLayout(doc_row)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText(
            "Paste your notes, article, or textbook chapter here…\n\n"
            "Tip: The more text you paste, the more varied and accurate your cards will be.")
        self.text_edit.setMinimumHeight(160); self.text_edit.setObjectName("textInput")
        root.addWidget(self.text_edit)

        row1 = QHBoxLayout(); row1.setSpacing(12)
        self.deck_name_edit = QLineEdit()
        self.deck_name_edit.setPlaceholderText("Deck name  (required)")
        row1.addWidget(self.deck_name_edit, 2)
        self.category_edit = QLineEdit()
        self.category_edit.setPlaceholderText("Category  (optional, e.g. Biology)")
        row1.addWidget(self.category_edit, 1)
        root.addLayout(row1)

        # ── Difficulty selector ────────────────────────────────────────
        diff_header = QLabel("DIFFICULTY"); diff_header.setObjectName("sectionHeader")
        root.addWidget(diff_header)

        diff_row = QHBoxLayout(); diff_row.setSpacing(10)
        self._diff_btns = {}
        for label, key in [("🟢  Easy","Easy"),("🟡  Medium","Medium"),("🔴  Hard","Hard")]:
            b = QPushButton(label)
            b.setObjectName(f"diff{key}")
            b.setFixedHeight(42)
            b.clicked.connect(lambda _, k=key: self._set_difficulty(k))
            diff_row.addWidget(b)
            self._diff_btns[key] = b

        diff_row.addStretch()
        root.addLayout(diff_row)
        self._difficulty = "Medium"
        self._set_difficulty("Medium")

        # ── Card count ────────────────────────────────────────────────
        count_row = QHBoxLayout(); count_row.setSpacing(12)
        lc = QLabel("Number of cards:"); lc.setObjectName("settingLabel"); count_row.addWidget(lc)
        self.count_spin = QSpinBox(); self.count_spin.setRange(3, 50)
        self.count_spin.setValue(DEFAULT_CARD_COUNT); self.count_spin.setFixedWidth(80)
        count_row.addWidget(self.count_spin); count_row.addStretch()
        root.addLayout(count_row)

        self.gen_btn = QPushButton("✦  Generate Flashcards")
        self.gen_btn.setObjectName("generateBtn"); self.gen_btn.setFixedHeight(48)
        self.gen_btn.clicked.connect(self._on_generate); root.addWidget(self.gen_btn)

        self.progress = QProgressBar(); self.progress.setRange(0, 0)
        self.progress.setFixedHeight(4); self.progress.setVisible(False)
        root.addWidget(self.progress)

        self.status_lbl = QLabel(""); self.status_lbl.setObjectName("statusLabel")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter); root.addWidget(self.status_lbl)

        # Preview
        self.preview_frame = QFrame(); self.preview_frame.setObjectName("previewFrame")
        self.preview_frame.setVisible(False)
        pfl = QVBoxLayout(self.preview_frame); pfl.setContentsMargins(0,0,0,0); pfl.setSpacing(12)
        ph = QHBoxLayout()
        self.preview_title = QLabel(""); self.preview_title.setObjectName("previewTitle")
        ph.addWidget(self.preview_title); ph.addStretch()
        self.save_btn = QPushButton("Save Deck →"); self.save_btn.setObjectName("saveBtn")
        self.save_btn.clicked.connect(self._on_save); ph.addWidget(self.save_btn)
        pfl.addLayout(ph)
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setFixedHeight(220)
        sc.setObjectName("previewScroll")
        self._pc = QWidget(); self._pc.setObjectName("previewContainer")
        self._pv = QVBoxLayout(self._pc); self._pv.setContentsMargins(0,0,0,0)
        self._pv.setSpacing(8); self._pv.addStretch(); sc.setWidget(self._pc)
        pfl.addWidget(sc); root.addWidget(self.preview_frame)
        root.addStretch()

    def _set_difficulty(self, key: str):
        self._difficulty = key
        for k, b in self._diff_btns.items():
            b.setObjectName(f"diff{k}On" if k == key else f"diff{k}")
            b.setStyle(b.style())

    def _on_fetch_url(self):
        url = self.url_edit.text().strip()
        if not url:
            self._setstatus("⚠  Please enter a URL first.", True); return
        if not url.startswith("http"):
            url = "https://" + url; self.url_edit.setText(url)
        self.fetch_btn.setEnabled(False); self.fetch_btn.setText("Fetching…")
        self._setstatus("Fetching page content…")
        try:
            text = fetch_url_text(url)
            self.text_edit.setPlainText(text)
            self._setstatus(f"✓  Fetched {len(text):,} characters from URL.")
        except FlashcardGenerationError as e:
            self._setstatus(f"✗  {e}", True)
        finally:
            self.fetch_btn.setEnabled(True); self.fetch_btn.setText("⬇  Fetch URL")

    def _on_upload_doc(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Document", "",
            "Documents (*.pdf *.docx *.txt);;All Files (*)")
        if not path: return
        self.doc_label.setText("Reading…")
        try:
            text = read_document(path)
            self.text_edit.setPlainText(text)
            fname = Path(path).name
            self.doc_label.setText(f"📄 {fname}  ({len(text):,} chars)")
            self._setstatus(f"✓  Loaded '{fname}' — {len(text):,} characters.")
            if not self.deck_name_edit.text().strip():
                self.deck_name_edit.setText(Path(path).stem)
        except FlashcardGenerationError as e:
            self.doc_label.setText("")
            self._setstatus(f"✗  {e}", True)

    def _on_generate(self):
        # Hard guard: never fire a second request while one is running
        if self._worker is not None and self._worker.isRunning():
            return
        text = self.text_edit.toPlainText().strip()
        name = self.deck_name_edit.text().strip()
        if not text: self._setstatus("⚠  Please paste some text first.", True); return
        if not name: self._setstatus("⚠  Please enter a deck name.", True);     return
        # Check API key early and show banner before even starting
        if not _get_api_key():
            self.no_key_banner.setVisible(True)
            self._setstatus("⚠  No API key — add one in Settings first.", True); return
        self.no_key_banner.setVisible(False)
        self.gen_btn.setEnabled(False); self.gen_btn.setText("Generating…")
        self.progress.setVisible(True); self.status_lbl.setText("")
        self._cards = []; self.preview_frame.setVisible(False)
        self._worker = GenerateWorker(text, name,
            self.category_edit.text().strip() or "General",
            self.count_spin.value(), self._difficulty)
        self._worker.finished.connect(self._on_ok)
        self._worker.error.connect(self._on_err)
        self._worker.status.connect(self._setstatus)
        self._worker.start()

    def _on_ok(self, cards):
        self._reset_btn(); self._cards = cards
        label = f"{self._difficulty} difficulty"
        self._setstatus(f"✓  {len(cards)} cards generated ({label})!")
        self._show_preview(cards)

    def _on_err(self, msg):
        self._reset_btn()
        if "NO_API_KEY" in msg:
            self.no_key_banner.setVisible(True)
            self._setstatus("⚠  No API key set. Go to Settings → AI Configuration.", True)
        else:
            self._setstatus(f"✗  {msg}", True)

    def _on_save(self):
        if self._cards:
            self.cards_ready.emit(self.deck_name_edit.text().strip(),
                                  self.category_edit.text().strip() or "General",
                                  self._cards)

    def _reset_btn(self):
        self.gen_btn.setEnabled(True); self.gen_btn.setText("✦  Generate Flashcards")
        self.progress.setVisible(False)

    def _setstatus(self, msg, error=False):
        self.status_lbl.setText(msg)
        self.status_lbl.setStyleSheet(f"color: {'#e05252' if error else '#3dba7e'};")

    def _show_preview(self, cards):
        while self._pv.count() > 1:
            w = self._pv.takeAt(0).widget()
            if w: w.deleteLater()
        for i, card in enumerate(cards[:8]):
            row = QFrame(); row.setObjectName("previewCard")
            rl  = QHBoxLayout(row); rl.setContentsMargins(14, 10, 14, 10)
            num = QLabel(f"{i+1}"); num.setObjectName("previewNum"); num.setFixedWidth(24); rl.addWidget(num)
            q   = QLabel(card["question"]); q.setObjectName("previewQ"); q.setWordWrap(True); rl.addWidget(q, 1)
            arr = QLabel("→"); arr.setObjectName("previewArrow"); rl.addWidget(arr)
            a   = QLabel(card["answer"]);   a.setObjectName("previewA"); a.setWordWrap(True); rl.addWidget(a, 1)
            self._pv.insertWidget(self._pv.count()-1, row)
        if len(cards) > 8:
            m = QLabel(f"  + {len(cards)-8} more cards…"); m.setObjectName("previewMore")
            self._pv.insertWidget(self._pv.count()-1, m)
        self.preview_title.setText(
            f"Preview — {len(cards)} card{'s' if len(cards)!=1 else ''}  ·  Difficulty: {self._difficulty}")
        self.preview_frame.setVisible(True)

    def reset(self):
        self.text_edit.clear(); self.deck_name_edit.clear(); self.category_edit.clear()
        self.count_spin.setValue(DEFAULT_CARD_COUNT); self._set_difficulty("Medium")
        self.status_lbl.setText(""); self.preview_frame.setVisible(False); self._cards = []


# ============================================================================
# VIEW — DECK MANAGER
# ============================================================================

def _fmt_date(iso: Optional[str]) -> str:
    if not iso: return "Never"
    try:    return datetime.fromisoformat(iso).strftime("%b %d, %Y")
    except Exception: return "—"


DECK_COLORS = ["#e8c84a","#3dba7e","#38bfbf","#e87d3e","#e05252","#a78bfa","#60a5fa","#f472b6"]


class DeckCard(QFrame):
    study_clicked  = pyqtSignal(int)
    study_due_clicked = pyqtSignal(int)
    delete_clicked = pyqtSignal(int)
    export_clicked = pyqtSignal(int)
    rename_clicked = pyqtSignal(int, str)

    def __init__(self, deck: dict, color_index: int = 0, parent=None):
        super().__init__(parent)
        self._id = deck["id"]; self._deck = deck
        self._color = DECK_COLORS[color_index % len(DECK_COLORS)]
        self.setObjectName("deckCard"); self.setFixedSize(240, 185)
        self._build()
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._ctx_menu)

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(18,16,18,14); lay.setSpacing(6)
        acc = QFrame(); acc.setFixedHeight(3)
        acc.setStyleSheet(f"background:{self._color};border-radius:2px;")
        lay.addWidget(acc); lay.addSpacing(4)
        n = QLabel(self._deck["name"]); n.setObjectName("deckCardName"); n.setWordWrap(True); lay.addWidget(n)
        cat = (self._deck.get("category") or "General").upper()
        cl = QLabel(cat); cl.setObjectName("deckCardCat")
        cl.setStyleSheet(f"color:{self._color};font-size:10px;font-weight:700;letter-spacing:0.08em;background:transparent;")
        lay.addWidget(cl); lay.addStretch()
        sr = QHBoxLayout(); sr.setSpacing(0)
        cards_lbl = QLabel(f"  {self._deck.get('total_cards',0)} cards"); cards_lbl.setObjectName("deckCardStat")
        sr.addWidget(cards_lbl); sr.addStretch()
        sl = QLabel(f"Studied {_fmt_date(self._deck.get('last_studied'))}  "); sl.setObjectName("deckCardStat")
        sr.addWidget(sl); lay.addLayout(sr); lay.addSpacing(6)
        br = QHBoxLayout(); br.setSpacing(8)
        sb = QPushButton("Study →"); sb.setObjectName("deckStudyBtn")
        sb.clicked.connect(lambda: self.study_clicked.emit(self._id)); br.addWidget(sb, 2)
        db = QPushButton("✕"); db.setObjectName("deckDeleteBtn"); db.setFixedWidth(34)
        db.clicked.connect(self._confirm_delete); br.addWidget(db)
        lay.addLayout(br)

    def _confirm_delete(self):
        if (QMessageBox.question(self,"Delete Deck",
                f"Delete '{self._deck['name']}'?\nThis cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
                == QMessageBox.StandardButton.Yes):
            self.delete_clicked.emit(self._id)

    def _ctx_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        m = QMenu(self)
        m.addAction("Study",  lambda: self.study_clicked.emit(self._id))
        m.addAction("Study Due Cards Only", lambda: self.study_due_clicked.emit(self._id))
        m.addAction("Rename", self._rename)
        m.addAction("Export", lambda: self.export_clicked.emit(self._id))
        m.addSeparator()
        m.addAction("Delete", self._confirm_delete)
        m.exec(self.mapToGlobal(pos))

    def _rename(self):
        name, ok = QInputDialog.getText(self,"Rename Deck","New name:",text=self._deck["name"])
        if ok and name.strip():
            self.rename_clicked.emit(self._id, name.strip())


class DeckManagerView(QWidget):
    study_deck = pyqtSignal(int)
    study_due_deck = pyqtSignal(int)
    status_msg = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent); self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(40,36,40,36); root.setSpacing(20)
        hdr = QHBoxLayout()
        t = QLabel("My Decks"); t.setObjectName("viewTitle"); hdr.addWidget(t); hdr.addStretch()
        for lbl, slot in [("⬆  Import",self._import),("⬇  Export All",self._export_all)]:
            b = QPushButton(lbl); b.setObjectName("headerBtn"); b.clicked.connect(slot); hdr.addWidget(b)
        root.addLayout(hdr)
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setObjectName("deckScroll")
        self._gw = QWidget(); self._gw.setObjectName("deckGrid")
        self._grid = QGridLayout(self._gw); self._grid.setSpacing(16)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        sc.setWidget(self._gw); root.addWidget(sc)
        self._empty = QWidget()
        ev = QVBoxLayout(self._empty); ev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ei = QLabel("📚"); ei.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ei.setStyleSheet("font-size:48px;"); ev.addWidget(ei)
        em = QLabel("No decks yet.\nGenerate your first one!")
        em.setObjectName("emptyMsg"); em.setAlignment(Qt.AlignmentFlag.AlignCenter); ev.addWidget(em)
        root.addWidget(self._empty)

    def load_decks(self, decks: list):
        while self._grid.count():
            w = self._grid.takeAt(0).widget()
            if w: w.deleteLater()
        if not decks:
            self._empty.setVisible(True); self._gw.setVisible(False); return
        self._empty.setVisible(False); self._gw.setVisible(True)
        for i, deck in enumerate(decks):
            card = DeckCard(deck, color_index=i)
            card.study_clicked.connect(self.study_deck)
            card.study_due_clicked.connect(self.study_due_deck)
            card.delete_clicked.connect(self._delete)
            card.export_clicked.connect(self._export_one)
            card.rename_clicked.connect(self._rename)
            self._grid.addWidget(card, i//3, i%3)

    def _delete(self, did):  delete_deck(did); self.status_msg.emit("Deck deleted."); self._refresh()
    def _rename(self, did, name): rename_deck(did,name); self.status_msg.emit(f"Renamed to '{name}'."); self._refresh()

    def _export_one(self, did):
        folder = QFileDialog.getExistingDirectory(self,"Choose save folder")
        if folder:
            try:   self.status_msg.emit(f"Exported → {export_deck_to_json(did, folder)}")
            except Exception as e: QMessageBox.critical(self,"Export Error",str(e))

    def _export_all(self):
        folder = QFileDialog.getExistingDirectory(self,"Choose save folder")
        if folder:
            try:   self.status_msg.emit(f"Exported → {export_all_to_json(folder)}")
            except Exception as e: QMessageBox.critical(self,"Export Error",str(e))

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self,"Import Decks","","JSON Files (*.json)")
        if not path: return
        n, err = import_from_json(path)
        if err: QMessageBox.warning(self,"Import Error",err)
        else:   self.status_msg.emit(f"Imported {n} deck(s).")
        self._refresh()

    def _refresh(self):
        self.load_decks(get_all_decks())


# ============================================================================
# VIEW — STUDY MODE
# ============================================================================

DIFF_STYLE = {
    "Easy":   ("🟢 EASY",   "color:#3dba7e;background:rgba(61,186,126,0.12);border-radius:6px;"),
    "Medium": ("🟡 MEDIUM", "color:#e8c84a;background:rgba(232,200,74,0.12);border-radius:6px;"),
    "Hard":   ("🔴 HARD",   "color:#e05252;background:rgba(224,82,82,0.12);border-radius:6px;"),
}


class FlipCard(QFrame):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("flipCard"); self.setMinimumHeight(280)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._flipped = False; self._animating = False

        self._stack = QStackedWidget(self)
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.addWidget(self._stack)

        # Front
        front = QWidget(); front.setObjectName("cardFace")
        fl = QVBoxLayout(front); fl.setContentsMargins(36,32,36,32); fl.setSpacing(14)
        self._front_badge = QLabel(""); self._front_badge.setObjectName("cardBadge"); fl.addWidget(self._front_badge)
        self._front_diff  = QLabel(""); self._front_diff.setObjectName("studyDiff"); fl.addWidget(self._front_diff)
        lbl = QLabel("QUESTION"); lbl.setObjectName("cardFaceLabel"); fl.addWidget(lbl)
        self._q_text = QLabel(""); self._q_text.setObjectName("questionText")
        self._q_text.setWordWrap(True); self._q_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fl.addWidget(self._q_text, 1)
        hint = QLabel("· · ·  tap to flip"); hint.setObjectName("flipHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter); fl.addWidget(hint)

        # Back
        back = QWidget(); back.setObjectName("cardBack")
        bl = QVBoxLayout(back); bl.setContentsMargins(36,32,36,32); bl.setSpacing(14)
        self._back_badge = QLabel(""); self._back_badge.setObjectName("cardBadge"); bl.addWidget(self._back_badge)
        blbl = QLabel("ANSWER"); blbl.setObjectName("cardFaceLabelBack"); bl.addWidget(blbl)
        self._a_text = QLabel(""); self._a_text.setObjectName("answerText")
        self._a_text.setWordWrap(True); self._a_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl.addWidget(self._a_text, 1)

        self._stack.addWidget(front); self._stack.addWidget(back)
        self._stack.setCurrentIndex(0)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton: self.clicked.emit()

    def load_card(self, card: dict):
        self._flipped = False
        self._q_text.setText(card.get("question",""))
        self._a_text.setText(card.get("answer",""))
        cat  = card.get("category","").upper()
        diff = card.get("difficulty","Medium")
        self._front_badge.setText(cat); self._back_badge.setText(cat)
        diff_label, diff_style = DIFF_STYLE.get(diff, DIFF_STYLE["Medium"])
        self._front_diff.setText(diff_label)
        self._front_diff.setStyleSheet(diff_style + "font-size:10px;font-weight:700;padding:3px 10px;background:transparent;")
        self._stack.setCurrentIndex(0)

    def flip(self):
        if self._animating: return
        self._animating = True
        fx = QGraphicsOpacityEffect(self); self.setGraphicsEffect(fx)
        fo = QPropertyAnimation(fx, b"opacity", self); fo.setDuration(130)
        fo.setStartValue(1.0); fo.setEndValue(0.0); fo.setEasingCurve(QEasingCurve.Type.InQuad)
        fo.finished.connect(self._swap); fo.start(); self._fo = fo

    def _swap(self):
        self._flipped = not self._flipped
        self._stack.setCurrentIndex(1 if self._flipped else 0)
        fx = self.graphicsEffect()
        fi = QPropertyAnimation(fx, b"opacity", self); fi.setDuration(130)
        fi.setStartValue(0.0); fi.setEndValue(1.0); fi.setEasingCurve(QEasingCurve.Type.OutQuad)
        fi.finished.connect(self._anim_done); fi.start(); self._fi = fi

    def _anim_done(self):
        self._animating = False; self.setGraphicsEffect(None)

    @property
    def is_flipped(self): return self._flipped


class SummaryScreen(QWidget):
    restart_study = pyqtSignal()
    retry_missed  = pyqtSignal(list)
    back_to_decks = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent); self._missed = []; self._build()

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(40,40,40,40)
        lay.setSpacing(20); lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Score ring + grade side by side (matches React layout)
        top_row = QHBoxLayout(); top_row.setSpacing(28)
        self._ring = ScoreRing(); top_row.addWidget(self._ring)
        text_col = QVBoxLayout(); text_col.setSpacing(8)
        self._grade = QLabel(""); self._grade.setObjectName("summaryGrade"); text_col.addWidget(self._grade)
        self._sub   = QLabel(""); self._sub.setObjectName("summarySub"); self._sub.setWordWrap(True); text_col.addWidget(self._sub)
        text_col.addStretch(); top_row.addLayout(text_col, 1)
        lay.addLayout(top_row)

        # Stats bar
        sf = QFrame(); sf.setObjectName("statsFrame")
        sr = QHBoxLayout(sf); sr.setSpacing(0)
        self._kn = QLabel("0"); self._kn.setObjectName("statNumGreen")
        self._ms = QLabel("0"); self._ms.setObjectName("statNumRed")
        self._sk = QLabel("0"); self._sk.setObjectName("statNumGray")
        for num, lbl in [(self._kn,"Knew it"),(self._ms,"Missed"),(self._sk,"Skipped")]:
            col = QWidget(); cl = QVBoxLayout(col); cl.setAlignment(Qt.AlignmentFlag.AlignCenter); cl.setSpacing(4)
            num.setAlignment(Qt.AlignmentFlag.AlignCenter); cl.addWidget(num)
            l = QLabel(lbl); l.setObjectName("statLbl"); l.setAlignment(Qt.AlignmentFlag.AlignCenter); cl.addWidget(l)
            sr.addWidget(col, 1)
        lay.addWidget(sf)

        # Missed cards list
        self._miss_sec = QWidget()
        ms = QVBoxLayout(self._miss_sec); ms.setSpacing(8); ms.setContentsMargins(0,0,0,0)
        mt = QLabel("REVIEW THESE"); mt.setObjectName("missedTitle"); ms.addWidget(mt)
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setFixedHeight(150); sc.setObjectName("missedScroll")
        self._mc = QWidget()
        self._mv = QVBoxLayout(self._mc); self._mv.setSpacing(6); self._mv.setContentsMargins(0,0,0,0)
        self._mv.addStretch(); sc.setWidget(self._mc); ms.addWidget(sc)
        lay.addWidget(self._miss_sec)

        br = QHBoxLayout(); br.setSpacing(10)
        self._retry_btn = QPushButton("Retry Missed"); self._retry_btn.setObjectName("retryBtn")
        self._retry_btn.clicked.connect(lambda: self.retry_missed.emit(self._missed)); br.addWidget(self._retry_btn)
        ra = QPushButton("Study Again"); ra.setObjectName("restartBtn"); ra.clicked.connect(self.restart_study); br.addWidget(ra)
        bk = QPushButton("← Back to Decks"); bk.setObjectName("backBtn"); bk.clicked.connect(self.back_to_decks); br.addWidget(bk)
        lay.addLayout(br)

    def show_results(self, knew, missed, skipped, total, missed_cards):
        self._missed = missed_cards
        pct = round((knew/total)*100) if total else 0
        grade = ("🏆 Excellent!" if pct>=90 else "👍 Good job!" if pct>=70
                 else "📈 Keep going!" if pct>=50 else "📖 Keep studying")
        self._grade.setText(grade)
        self._sub.setText(f"You answered {knew} of {total} cards correctly.")
        self._kn.setText(str(knew)); self._ms.setText(str(missed)); self._sk.setText(str(skipped))
        self._ring.set_score(pct)

        while self._mv.count() > 1:
            w = self._mv.takeAt(0).widget()
            if w: w.deleteLater()
        for card in missed_cards:
            row = QFrame(); row.setObjectName("missedRow")
            rl  = QHBoxLayout(row); rl.setContentsMargins(12,8,12,8)
            cat = QLabel(card.get("category","").upper()); cat.setObjectName("missedCat"); rl.addWidget(cat)
            q   = QLabel(card.get("question","")); q.setObjectName("missedQ"); q.setWordWrap(True); rl.addWidget(q,1)
            self._mv.insertWidget(self._mv.count()-1, row)
        self._miss_sec.setVisible(bool(missed_cards))
        self._retry_btn.setVisible(bool(missed_cards))
        return pct   # so caller can trigger confetti


class StudyModeView(QWidget):
    session_ended = pyqtSignal()
    back_to_decks = pyqtSignal()
    card_reviewed = pyqtSignal(int, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._deck = {}; self._cards = []; self._idx = 0
        self._knew = 0; self._missed = 0; self._skipped = 0; self._missed_cards = []
        self._build()

    def _build(self):
        self._stack = QStackedWidget(self)
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.addWidget(self._stack)

        # ── Study screen ─────────────────────────────────────────────
        study = QWidget()
        ss = QVBoxLayout(study); ss.setContentsMargins(40,28,40,28); ss.setSpacing(16)

        top = QHBoxLayout()
        self._deck_lbl  = QLabel(""); self._deck_lbl.setObjectName("studyDeckName"); top.addWidget(self._deck_lbl)
        self._diff_badge = QLabel(""); top.addWidget(self._diff_badge)
        top.addStretch()
        self._score_lbl = QLabel(""); self._score_lbl.setObjectName("studyScore"); top.addWidget(self._score_lbl)
        eb = QPushButton("End Session"); eb.setObjectName("endBtn"); eb.clicked.connect(self._end); top.addWidget(eb)
        ss.addLayout(top)

        self._prog_lbl = QLabel(""); self._prog_lbl.setObjectName("progressLbl"); ss.addWidget(self._prog_lbl)
        self._card = FlipCard(); self._card.clicked.connect(self._flip); ss.addWidget(self._card, 1)

        ctrl = QHBoxLayout(); ctrl.setSpacing(10)
        self._miss_btn = QPushButton("✕  Missed"); self._miss_btn.setObjectName("missBtn")
        self._miss_btn.setEnabled(False); self._miss_btn.clicked.connect(lambda: self._answer("miss")); ctrl.addWidget(self._miss_btn, 2)
        skip = QPushButton("→ Skip"); skip.setObjectName("skipBtn")
        skip.clicked.connect(lambda: self._answer("skip")); ctrl.addWidget(skip, 1)
        self._knew_btn = QPushButton("✓  Knew it"); self._knew_btn.setObjectName("knewBtn")
        self._knew_btn.setEnabled(False); self._knew_btn.clicked.connect(lambda: self._answer("knew")); ctrl.addWidget(self._knew_btn, 2)
        ss.addLayout(ctrl)

        hint = QLabel("Space — flip  ·  ↑ knew it  ·  ↓ missed  ·  → skip")
        hint.setObjectName("shortcutsHint"); hint.setAlignment(Qt.AlignmentFlag.AlignCenter); ss.addWidget(hint)

        # ── Summary screen ────────────────────────────────────────────
        self._summary = SummaryScreen()
        self._summary.restart_study.connect(self._restart)
        self._summary.retry_missed.connect(self._retry)
        self._summary.back_to_decks.connect(self.back_to_decks)

        # Confetti overlay on summary screen
        self._confetti = ConfettiWidget(self._summary)
        self._confetti.hide()

        self._stack.addWidget(study)
        self._stack.addWidget(self._summary)
        self._stack.setCurrentIndex(0)

    def resizeEvent(self, e):
        if self._confetti:
            self._confetti.setGeometry(self._summary.rect())
        super().resizeEvent(e)

    def start_session(self, deck: dict, cards: list, shuffle: bool = True):
        self._deck = deck
        self._cards = random.sample(cards, len(cards)) if shuffle else list(cards)
        self._idx = 0; self._knew = 0; self._missed = 0; self._skipped = 0; self._missed_cards = []
        self._stack.setCurrentIndex(0)
        self._deck_lbl.setText(deck.get("name","Study"))
        # Show difficulty badge based on most common difficulty in deck
        diffs = [c.get("difficulty","Medium") for c in cards]
        dominant = max(set(diffs), key=diffs.count)
        dl, ds = DIFF_STYLE.get(dominant, DIFF_STYLE["Medium"])
        self._diff_badge.setText(dl)
        self._diff_badge.setStyleSheet(ds + "font-size:10px;font-weight:700;padding:3px 10px;")
        self._load()

    def _load(self):
        if self._idx >= len(self._cards): self._end(); return
        self._card.load_card(self._cards[self._idx])
        self._prog_lbl.setText(f"Card {self._idx+1} of {len(self._cards)}")
        self._score_lbl.setText(f"  ✓ {self._knew}   ✗ {self._missed}  ")
        self._miss_btn.setEnabled(False); self._knew_btn.setEnabled(False)

    def _flip(self):
        self._card.flip(); QTimer.singleShot(280, self._unlock)

    def _unlock(self):
        if self._card.is_flipped:
            self._miss_btn.setEnabled(True); self._knew_btn.setEnabled(True)

    def _answer(self, kind: str):
        card = self._cards[self._idx]
        if   kind == "knew": self._knew   += 1; correct = True
        elif kind == "miss": self._missed += 1; self._missed_cards.append(card); correct = False
        else:                self._skipped += 1; self._idx += 1; self._load(); return
        if "id" in card: self.card_reviewed.emit(card["id"], correct)
        self._idx += 1; self._load()

    def _end(self):
        self.session_ended.emit()
        pct = self._summary.show_results(
            self._knew, self._missed, self._skipped,
            len(self._cards), self._missed_cards)
        self._stack.setCurrentIndex(1)
        self._confetti.setGeometry(self._summary.rect())
        if pct >= 70:                        # matches React's confetti threshold
            QTimer.singleShot(400, self._confetti.burst)

    def _restart(self): self.start_session(self._deck, self._cards)
    def _retry(self, missed):
        if missed: self.start_session(self._deck, missed)

    def keyPressEvent(self, e: QKeyEvent):
        if self._stack.currentIndex() != 0: return
        k = e.key()
        if   k == Qt.Key.Key_Space:                            self._flip()
        elif k == Qt.Key.Key_Up   and self._card.is_flipped:  self._answer("knew")
        elif k == Qt.Key.Key_Down and self._card.is_flipped:  self._answer("miss")
        elif k == Qt.Key.Key_Right:                            self._answer("skip")
        else: super().keyPressEvent(e)


# ============================================================================
# VIEW — SETTINGS
# ============================================================================

class SettingsView(QWidget):
    status_msg = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._s = QSettings("FlashForge","FlashForge")
        self._build(); self._load()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(40,36,40,36)
        root.setSpacing(28); root.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("Settings"); title.setObjectName("viewTitle"); root.addWidget(title)

        root.addWidget(self._sec("AI Configuration"))
        desc = QLabel(
            "Your OpenRouter API key is stored locally on your machine and never sent anywhere else.\n"
            "Get a free key at https://openrouter.ai/ (no credit card needed).")
        desc.setObjectName("settingDesc"); desc.setWordWrap(True); root.addWidget(desc)

        ar = QHBoxLayout(); ar.setSpacing(10)
        self.api_edit = QLineEdit(); self.api_edit.setPlaceholderText("sk-or-v1-...  (paste your OpenRouter API key)")
        self.api_edit.setEchoMode(QLineEdit.EchoMode.Password); ar.addWidget(self.api_edit, 1)
        show = QPushButton("Show"); show.setObjectName("showBtn"); show.setCheckable(True)
        show.toggled.connect(lambda c: self.api_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if c else QLineEdit.EchoMode.Password))
        ar.addWidget(show)
        sv = QPushButton("Save Key"); sv.setObjectName("saveKeyBtn"); sv.clicked.connect(self._save_key); ar.addWidget(sv)
        root.addLayout(ar)

        root.addWidget(self._sec("Default Generation Settings"))
        dr = QHBoxLayout(); dr.setSpacing(16)
        dr.addWidget(self._lbl("Default card count:"))
        self.count_spin = QSpinBox(); self.count_spin.setRange(3,50)
        self.count_spin.setValue(DEFAULT_CARD_COUNT); self.count_spin.setFixedWidth(80); dr.addWidget(self.count_spin)
        dr.addSpacing(20); dr.addWidget(self._lbl("Default difficulty:"))
        self.diff_combo = QComboBox(); self.diff_combo.addItems(DIFFICULTIES); self.diff_combo.setFixedWidth(120); dr.addWidget(self.diff_combo)
        dr.addStretch()
        sd = QPushButton("Save Defaults"); sd.setObjectName("saveKeyBtn"); sd.clicked.connect(self._save_defaults); dr.addWidget(sd)
        root.addLayout(dr)

        em = QHBoxLayout(); em.setSpacing(16)
        em.addWidget(self._lbl("OpenRouter model:"))
        self.model_combo = QComboBox(); self.model_combo.setEditable(True)
        self.model_combo.addItems(FREE_MODELS)
        self.model_combo.setFixedWidth(340)
        em.addWidget(self.model_combo)
        em.addStretch()
        root.addLayout(em)
        model_hint = QLabel(
            "'openrouter/free' auto-picks a live free model each request (recommended, most reliable). "
            "Pinned :free models can rotate out of OpenRouter's free tier without notice — "
            "custom model IDs also work.")
        model_hint.setObjectName("settingDesc"); root.addWidget(model_hint)

        root.addWidget(self._sec("Data Management"))
        dmr = QHBoxLayout(); dmr.setSpacing(10)
        for lbl, slot in [("⬇  Export All Decks",self._export),("⬆  Import Decks",self._import)]:
            b = QPushButton(lbl); b.setObjectName("headerBtn"); b.clicked.connect(slot); dmr.addWidget(b)
        dmr.addStretch()
        cl = QPushButton("⚠  Clear All Data"); cl.setObjectName("dangerBtn"); cl.clicked.connect(self._clear); dmr.addWidget(cl)
        root.addLayout(dmr)

        root.addWidget(self._sec("About"))
        af = QFrame(); af.setObjectName("aboutFrame")
        al = QVBoxLayout(af); al.setContentsMargins(18,14,18,14); al.setSpacing(4)
        an = QLabel(f"<b>{APP_NAME}</b>  v{VERSION}"); an.setObjectName("aboutApp"); al.addWidget(an)
        ad = QLabel("AI-powered flashcard software. Paste text → AI generates cards → study smarter.\n"
                    "Built with PyQt6 + OpenRouter (free-tier friendly).\n"
                    "Data stored locally in SQLite. No cloud, no account needed.")
        ad.setObjectName("aboutDesc"); ad.setWordWrap(True); al.addWidget(ad)
        root.addWidget(af); root.addStretch()

    @staticmethod
    def _sec(t):
        l = QLabel(t.upper()); l.setObjectName("sectionHeader"); return l
    @staticmethod
    def _lbl(t):
        l = QLabel(t); l.setObjectName("settingLabel"); return l

    def _save_key(self):
        key = self.api_edit.text().strip(); self._s.setValue("openrouter_api_key", key)
        if key:
            self.status_msg.emit("✓  API key saved. AI generation is now active.")
        else:
            self.status_msg.emit("API key cleared — running in mock mode.")

    def _save_defaults(self):
        self._s.setValue("default_card_count", self.count_spin.value())
        self._s.setValue("default_difficulty",  self.diff_combo.currentText())
        self._s.setValue("openrouter_model", self.model_combo.currentText().strip())
        self.status_msg.emit("Defaults saved.")

    def _export(self):
        folder = QFileDialog.getExistingDirectory(self,"Choose folder")
        if folder:
            try:   self.status_msg.emit(f"Exported → {export_all_to_json(folder)}")
            except Exception as e: QMessageBox.critical(self,"Export Error",str(e))

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self,"Import","","JSON Files (*.json)")
        if not path: return
        n, err = import_from_json(path)
        if err: QMessageBox.warning(self,"Import Error",err)
        else:   self.status_msg.emit(f"Imported {n} deck(s).")

    def _clear(self):
        if (QMessageBox.critical(self,"Clear All Data",
                "This will permanently delete ALL decks and cards.\n\nAre you absolutely sure?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
                != QMessageBox.StandardButton.Yes): return
        try:
            os.remove(get_db_path()); init_db(); self.status_msg.emit("All data cleared.")
        except Exception as e: QMessageBox.critical(self,"Error",str(e))

    def _load(self):
        self.api_edit.setText(self._s.value("openrouter_api_key",""))
        self.count_spin.setValue(self._s.value("default_card_count", DEFAULT_CARD_COUNT, type=int))
        idx = self.diff_combo.findText(self._s.value("default_difficulty","Medium"))
        if idx >= 0: self.diff_combo.setCurrentIndex(idx)
        saved_model = self._s.value("openrouter_model", DEFAULT_FREE_MODEL)
        idx = self.model_combo.findText(saved_model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        else:
            self.model_combo.setCurrentText(saved_model)


# ============================================================================
# SIDEBAR
# ============================================================================

NAV = [("✦  Generate","generate"),("⊞  My Decks","decks"),
       ("▷  Study Mode","study"),("⚙  Settings","settings")]


class Sidebar(QFrame):
    nav_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent); self.setObjectName("sidebar")
        self._btns = {}; self._active = None; self._build()

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,20); lay.setSpacing(2)
        logo = QLabel("flash<b style='color:#e8c84a;'>forge</b>")
        logo.setTextFormat(Qt.TextFormat.RichText); logo.setObjectName("sidebarLogo"); lay.addWidget(logo)
        lay.addSpacing(8)
        for label, key in NAV:
            b = QPushButton(label); b.setObjectName("navBtn"); b.setFixedHeight(42)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, k=key: self._click(k))
            lay.addWidget(b); self._btns[key] = b
        lay.addStretch()
        v = QLabel(f"v{VERSION}"); v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.setStyleSheet("color:#2e2e2a;font-size:11px;background:transparent;"); lay.addWidget(v)

    def _click(self, key):
        self.set_active(key); self.nav_changed.emit(key)

    def set_active(self, key):
        if self._active == key: return
        if self._active in self._btns:
            b = self._btns[self._active]; b.setObjectName("navBtn"); b.setStyle(b.style())
        self._active = key
        if key in self._btns:
            b = self._btns[key]; b.setObjectName("navBtnActive"); b.setStyle(b.style())


# ============================================================================
# MAIN WINDOW
# ============================================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}  —  AI Flashcard Software")
        self.setMinimumSize(1100, 720)
        scr = QApplication.primaryScreen().availableGeometry()
        self.move(max((scr.width()-1100)//2, 0), max((scr.height()-720)//2, 0))
        self._session_active = False
        self._build(); self._shortcuts(); self._reload()
        self._sidebar.set_active("generate")

    def _build(self):
        cw = QWidget(); self.setCentralWidget(cw)
        h  = QHBoxLayout(cw); h.setContentsMargins(0,0,0,0); h.setSpacing(0)

        self._sidebar = Sidebar(); self._sidebar.nav_changed.connect(self._nav); h.addWidget(self._sidebar)
        self._stack   = QStackedWidget(); h.addWidget(self._stack, 1)

        self._gen   = GenerateView()
        self._deck  = DeckManagerView()
        self._study = StudyModeView()
        self._sett  = SettingsView()

        self._pages = {"generate":self._gen,"decks":self._deck,
                       "study":self._study,"settings":self._sett}
        for w in self._pages.values(): self._stack.addWidget(w)

        self._sb = QStatusBar(); self.setStatusBar(self._sb)
        self._sb.showMessage(f"Welcome to {APP_NAME}  ·  No API key? Go to Settings → save your OpenRouter key.")

        self._gen.cards_ready.connect(self._save_deck)
        self._deck.study_deck.connect(self._start_study)
        self._deck.study_due_deck.connect(self._start_study_due)
        self._deck.status_msg.connect(self._sb.showMessage)
        self._sett.status_msg.connect(self._sb.showMessage)
        self._study.session_ended.connect(self._on_session_end)
        self._study.back_to_decks.connect(lambda: self._nav("decks"))
        self._study.card_reviewed.connect(lambda cid, ok: update_card_review(cid, ok))

    def _shortcuts(self):
        for key, page in [("Ctrl+1","generate"),("Ctrl+2","decks"),
                          ("Ctrl+3","study"),("Ctrl+4","settings")]:
            QShortcut(QKeySequence(key), self).activated.connect(
                lambda p=page: self._sidebar._click(p))

    def _nav(self, key: str):
        w = self._pages.get(key)
        if not w: return
        # Guard: don't allow jumping to study tab unless a session is active
        if key == "study" and not self._session_active:
            self._sb.showMessage("Pick a deck and hit 'Study →' to start a session.")
            self._nav("decks"); return
        self._stack.setCurrentWidget(w); self._sidebar.set_active(key)
        if key == "decks": self._reload()

    def _save_deck(self, name: str, category: str, cards: list):
        try:
            did = create_deck(name, category)
            add_cards(did, cards)
            self._sb.showMessage(f"✓  '{name}' saved — {len(cards)} cards ready to study.")
            self._gen.reset(); self._reload(); self._nav("decks")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def _start_study(self, deck_id: int):
        try:
            deck  = get_deck_by_id(deck_id)
            cards = get_deck_cards(deck_id)
            if not cards:
                self._sb.showMessage("This deck has no cards yet."); return
            update_deck_studied(deck_id)
            self._study.start_session(deck, cards)
            self._session_active = True          # FIX: set before _nav
            self._nav("study")
            self._study.setFocus()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _start_study_due(self, deck_id: int):
        try:
            deck = get_deck_by_id(deck_id)
            due  = get_due_cards(deck_id, limit=200)
            if not due:
                self._sb.showMessage("Nothing due in this deck right now — great job staying on top of it.")
                return
            update_deck_studied(deck_id)
            self._study.start_session(deck, due)
            self._session_active = True
            self._nav("study")
            self._study.setFocus()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_session_end(self):
        self._session_active = False             # FIX: reset so nav guard works again
        self._reload()

    def _reload(self):
        self._deck.load_decks(get_all_decks())


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    init_db()
    win = MainWindow()
    win.show()
    sys.exit(app.exec())