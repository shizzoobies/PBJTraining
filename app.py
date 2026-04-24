import os
import json
import re
import markdown2
import anthropic
from flask import Flask, render_template, request, redirect, url_for, session, abort, jsonify
from dotenv import load_dotenv
from functools import wraps
from pathlib import Path

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "pbj-training-change-in-production")

CONTENT_DIR = Path(__file__).parent / "content"
TRAINING_PASSWORD = os.environ.get("TRAINING_PASSWORD", "pbj2024")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

MARKDOWN_EXTRAS = ["fenced-code-blocks", "tables", "header-ids", "strike", "task_list"]


def load_modules() -> list:
    with open(CONTENT_DIR / "modules.json", encoding="utf-8") as f:
        return json.load(f)["modules"]


def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


def preprocess_content(text: str) -> str:
    """Replace [IMAGE: desc] and [VIDEO: desc] markers with styled placeholder HTML."""
    text = re.sub(
        r'\[IMAGE:\s*([^\]]+)\]',
        lambda m: (
            '<div class="media-placeholder img-ph">'
            '<i class="bi bi-image"></i>'
            f'<strong>{m.group(1).strip()}</strong>'
            '<span>Screenshot placeholder — replace with actual QuickBooks image</span>'
            '</div>'
        ),
        text,
    )
    text = re.sub(
        r'\[VIDEO:\s*([^\]]+)\]',
        lambda m: (
            '<div class="media-placeholder vid-ph">'
            '<i class="bi bi-play-circle-fill"></i>'
            f'<strong>{m.group(1).strip()}</strong>'
            '<span>Video placeholder — add YouTube or Vimeo embed URL here</span>'
            '</div>'
        ),
        text,
    )
    return text


@app.route("/")
def index():
    return redirect(url_for("dashboard") if session.get("authenticated") else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        if request.form.get("password") == TRAINING_PASSWORD:
            session["authenticated"] = True
            return redirect(request.args.get("next") or url_for("dashboard"))
        error = "Incorrect password. Please try again."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@require_login
def dashboard():
    return render_template(
        "dashboard.html",
        modules=load_modules(),
        current_module_id=None,
        current_lesson_id=None,
    )


@app.route("/module/<module_id>/lesson/<lesson_id>")
@require_login
def lesson(module_id, lesson_id):
    modules = load_modules()
    module = next((m for m in modules if m["id"] == module_id), None)
    if not module:
        abort(404)
    lesson_meta = next((l for l in module["lessons"] if l["id"] == lesson_id), None)
    if not lesson_meta:
        abort(404)

    content_path = CONTENT_DIR / lesson_meta["file"]
    if content_path.exists():
        raw = preprocess_content(content_path.read_text(encoding="utf-8"))
        content_html = markdown2.markdown(raw, extras=MARKDOWN_EXTRAS)
    else:
        content_html = "<p class='text-muted fst-italic'>Content coming soon — check back shortly.</p>"

    all_lessons = [(m["id"], l["id"]) for m in modules for l in m["lessons"]]
    idx = next((i for i, x in enumerate(all_lessons) if x == (module_id, lesson_id)), None)
    prev_lesson = all_lessons[idx - 1] if idx and idx > 0 else None
    next_lesson = all_lessons[idx + 1] if idx is not None and idx < len(all_lessons) - 1 else None

    return render_template(
        "lesson.html",
        modules=modules,
        module=module,
        lesson=lesson_meta,
        content_html=content_html,
        prev_lesson=prev_lesson,
        next_lesson=next_lesson,
        current_module_id=module_id,
        current_lesson_id=lesson_id,
    )


@app.route("/api/chat", methods=["POST"])
@require_login
def api_chat():
    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY not set in .env"}), 503

    data = request.json or {}
    messages = data.get("messages", [])
    lesson_title = data.get("lesson_title", "")
    module_title = data.get("module_title", "")

    system = f"""You are a friendly, knowledgeable QuickBooks training assistant helping a student work through an online course.

Current context: Module "{module_title}" — Lesson "{lesson_title}"

Your role:
- Answer QuickBooks questions clearly and practically
- Use numbered steps when explaining processes
- Reference the current lesson topic when relevant
- Keep answers concise but complete (2–4 short paragraphs max)
- Use plain language — explain any accounting terms you use
- If you are unsure about a detail specific to the user's QB version, say so honestly and suggest they verify in QB's help docs"""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            system=system,
            messages=messages,
        )
        return jsonify({"reply": response.content[0].text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
