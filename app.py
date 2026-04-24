import os
import json
import re
import secrets
import markdown2
import anthropic
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, session, abort, jsonify
from dotenv import load_dotenv
from functools import wraps
from pathlib import Path

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "pbj-training-change-in-production")

CONTENT_DIR = Path(__file__).parent / "content"
PATHS_FILE = CONTENT_DIR / "paths.json"
TRAINING_PASSWORD = os.environ.get("TRAINING_PASSWORD", "pbj2024")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "pbjadmin2024")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

MARKDOWN_EXTRAS = ["fenced-code-blocks", "tables", "header-ids", "strike", "task_list"]


def load_modules() -> list:
    with open(CONTENT_DIR / "modules.json", encoding="utf-8") as f:
        return json.load(f)["modules"]


def load_paths() -> dict:
    if not PATHS_FILE.exists():
        return {}
    with open(PATHS_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_paths(paths: dict):
    with open(PATHS_FILE, "w", encoding="utf-8") as f:
        json.dump(paths, f, indent=2)


def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin_login", next=request.path))
        return f(*args, **kwargs)
    return decorated


def preprocess_content(text: str) -> str:
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


def render_lesson_content(lesson_meta: dict) -> str:
    content_path = CONTENT_DIR / lesson_meta["file"]
    if content_path.exists():
        raw = preprocess_content(content_path.read_text(encoding="utf-8"))
        return markdown2.markdown(raw, extras=MARKDOWN_EXTRAS)
    return "<p class='text-muted fst-italic'>Content coming soon — check back shortly.</p>"


# ── Public auth ───────────────────────────────────────────────────────────────

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


# ── Main training ─────────────────────────────────────────────────────────────

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

    content_html = render_lesson_content(lesson_meta)
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


# ── Learning Paths (token-gated, no login required) ───────────────────────────

@app.route("/path/<token>")
def path_landing(token):
    paths = load_paths()
    path = paths.get(token)
    if not path or not path["lessons"]:
        abort(404)
    first = path["lessons"][0]
    mid, lid = first.split("/")
    return redirect(url_for("path_lesson", token=token, module_id=mid, lesson_id=lid))


@app.route("/path/<token>/lesson/<module_id>/<lesson_id>")
def path_lesson(token, module_id, lesson_id):
    paths = load_paths()
    path = paths.get(token)
    if not path:
        abort(404)

    lesson_key = f"{module_id}/{lesson_id}"
    if lesson_key not in path["lessons"]:
        abort(403)

    modules = load_modules()
    module = next((m for m in modules if m["id"] == module_id), None)
    lesson_meta = next((l for l in (module["lessons"] if module else []) if l["id"] == lesson_id), None)
    if not module or not lesson_meta:
        abort(404)

    content_html = render_lesson_content(lesson_meta)

    # Build sidebar details for path lessons
    path_lesson_details = []
    last_mod_id = None
    for key in path["lessons"]:
        mid, lid = key.split("/")
        mod = next((m for m in modules if m["id"] == mid), None)
        les = next((l for l in mod["lessons"] if l["id"] == lid), None) if mod else None
        if mod and les:
            path_lesson_details.append({
                "module_id": mid,
                "lesson_id": lid,
                "module_title": mod["title"],
                "module_color": mod["color"],
                "lesson_title": les["title"],
                "duration": les["duration"],
                "key": key,
                "show_module_header": mid != last_mod_id,
            })
            last_mod_id = mid

    # Prev / next within path
    path_keys = path["lessons"]
    idx = next((i for i, k in enumerate(path_keys) if k == lesson_key), None)
    prev_key = path_keys[idx - 1] if idx and idx > 0 else None
    next_key = path_keys[idx + 1] if idx is not None and idx < len(path_keys) - 1 else None

    def key_to_url(k):
        if not k:
            return None
        m, l = k.split("/")
        return url_for("path_lesson", token=token, module_id=m, lesson_id=l)

    return render_template(
        "path_lesson.html",
        path=path,
        token=token,
        module=module,
        lesson=lesson_meta,
        content_html=content_html,
        path_lesson_details=path_lesson_details,
        prev_url=key_to_url(prev_key),
        next_url=key_to_url(next_key),
        current_key=lesson_key,
    )


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_authenticated"):
        return redirect(url_for("admin_dashboard"))
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin_authenticated"] = True
            return redirect(request.args.get("next") or url_for("admin_dashboard"))
        error = "Incorrect admin password."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_authenticated", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@require_admin
def admin_dashboard():
    paths = load_paths()
    modules = load_modules()
    # Annotate each path with lesson count and module summary
    for path in paths.values():
        path["lesson_count"] = len(path["lessons"])
    return render_template("admin.html", paths=paths, modules=modules)


@app.route("/admin/new", methods=["GET", "POST"])
@require_admin
def admin_new_path():
    modules = load_modules()
    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        assignee = request.form.get("assignee", "").strip()
        selected = request.form.getlist("lessons")
        if not name or not selected:
            error = "Please enter a path name and select at least one lesson."
        else:
            token = secrets.token_urlsafe(10)
            paths = load_paths()
            paths[token] = {
                "id": token,
                "name": name,
                "assignee": assignee,
                "created": str(date.today()),
                "lessons": selected,
            }
            save_paths(paths)
            return redirect(url_for("admin_dashboard"))
    return render_template("admin_new.html", modules=modules, error=error)


@app.route("/admin/delete/<token>", methods=["POST"])
@require_admin
def admin_delete_path(token):
    paths = load_paths()
    paths.pop(token, None)
    save_paths(paths)
    return redirect(url_for("admin_dashboard"))


# ── AI Chat API ───────────────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.json or {}
    path_token = data.get("path_token", "")

    # Allow regular users or valid path token holders
    if not session.get("authenticated") and not session.get("admin_authenticated"):
        if not path_token or path_token not in load_paths():
            return jsonify({"error": "Not authorized"}), 401

    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY not configured on server"}), 503

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
- If unsure about a version-specific detail, say so honestly"""

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
