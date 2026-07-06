"""
PDF to Audio Web App — Flask Backend
Full-featured: upload PDF, extract text, ElevenLabs TTS, speed/pitch control,
chapter navigation, multi-language, streaming audio.
"""

import os
import uuid
import json
import threading
import logging
import time
from pathlib import Path
from flask import (
    Flask, request, jsonify, render_template,
    send_from_directory, Response, stream_with_context, session
)
from flask_cors import CORS
from werkzeug.utils import secure_filename

from modules.pdf_processor import PDFProcessor
from modules.tts_engine import TTSEngine
from modules.audio_processor import AudioProcessor

# ──────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────
BASE_DIR = Path(__file__).parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
AUDIO_FOLDER  = BASE_DIR / "audio_output"
ALLOWED_EXTENSIONS   = {"pdf"}
MAX_CONTENT_LENGTH   = 50 * 1024 * 1024  # 50 MB

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(AUDIO_FOLDER,  exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))
app.config["UPLOAD_FOLDER"]      = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
CORS(app)

# TTS engine — API key can be supplied per-request or via env var
tts_engine      = TTSEngine(str(AUDIO_FOLDER))
audio_processor = AudioProcessor(str(AUDIO_FOLDER))

# In-memory job tracker
jobs      = {}
jobs_lock = threading.Lock()

# ──────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def update_job(job_id, **kwargs):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(kwargs)

def get_job(job_id):
    with jobs_lock:
        return jobs.get(job_id, {}).copy()

# ──────────────────────────────────────────
# Routes — General
# ──────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── ElevenLabs API key validation ─────────
@app.route("/api/validate-key", methods=["POST"])
def validate_key():
    """Validate an ElevenLabs API key and return user info."""
    data = request.get_json() or {}
    api_key = data.get("api_key", "").strip()
    if not api_key:
        return jsonify({"valid": False, "message": "No API key provided."}), 400

    engine = TTSEngine(str(AUDIO_FOLDER), api_key=api_key)
    valid, message = engine.validate_api_key()

    if valid:
        session["api_key"] = api_key
        info = engine.get_user_info()
        return jsonify({"valid": True, "message": message, "user_info": info})
    return jsonify({"valid": False, "message": message}), 401


# ── Voices ────────────────────────────────
@app.route("/api/voices", methods=["POST"])
def get_voices():
    """Fetch available voices for the given API key."""
    data    = request.get_json() or {}
    api_key = session.get("api_key", "") or data.get("api_key", "").strip()

    engine = TTSEngine(str(AUDIO_FOLDER), api_key=api_key)
    voices = engine.get_voices()
    models = engine.get_models()
    return jsonify({"voices": voices, "models": models})


# ── PDF Upload ────────────────────────────
@app.route("/api/upload", methods=["POST"])
def upload_pdf():
    if "file" not in request.files:
        return jsonify({"error": "No file provided."}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Only PDF files are supported."}), 400

    file_id  = uuid.uuid4().hex
    filename = secure_filename(f"{file_id}.pdf")
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    try:
        processor  = PDFProcessor(filepath)
        metadata   = processor.get_metadata()
        processor.close()

        # Start chapter detection in background to avoid blocking upload
        def _detect_chapters_bg():
            try:
                p = PDFProcessor(filepath)
                chapters = p.detect_chapters()
                p.close()
                cache_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{file_id}_chapters.json")
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(chapters, f, ensure_ascii=False)
                logger.info(f"Chapter detection done: {file_id}, {len(chapters)} chapters")
            except Exception as e:
                logger.error(f"Background chapter detection error for {file_id}: {e}")

        threading.Thread(target=_detect_chapters_bg, daemon=True).start()

        logger.info(f"Uploaded: {metadata['title']}, {metadata['total_pages']} pages (chapters detecting in background)")
        return jsonify({"file_id": file_id, "metadata": metadata, "chapters": []})

    except Exception as e:
        logger.error(f"PDF processing error: {e}")
        return jsonify({"error": f"Failed to process PDF: {str(e)}"}), 500


# ── Get Chapters (for background detection) ────────────────────────────────
@app.route("/api/chapters/<file_id>", methods=["GET"])
def get_chapters(file_id):
    """Fetch chapters for a file (waits for background detection if needed)."""
    cache_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{file_id}_chapters.json")
    
    # Wait up to 30 seconds for chapters to be detected
    for _ in range(60):
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                chapters = json.load(f)
            chapter_list = [
                {
                    "index":      i,
                    "title":      ch["title"],
                    "start_page": ch["start_page"],
                    "end_page":   ch["end_page"],
                }
                for i, ch in enumerate(chapters)
            ]
            return jsonify({"chapters": chapter_list, "ready": True})
        time.sleep(0.5)
    
    # Timeout - still detecting
    return jsonify({"chapters": [], "ready": False}), 202


# ── Conversion ────────────────────────────
@app.route("/api/convert", methods=["POST"])
def convert_to_audio():
    """
    Start async conversion job.
    Body: {
      file_id, api_key,
      voice_id, model_id,
      stability, similarity_boost, style,
      speed, pitch,
      chapter_index   (-1 = all)
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body."}), 400

    file_id   = data.get("file_id")
    # Use server-side session key as primary (set during validation)
    # Fall back to request body key only if session has none
    api_key = session.get("api_key", "") or data.get("api_key", "").strip()

    if not api_key:
        return jsonify({"error": "ElevenLabs API key required. Please validate your key in Step 1."}), 400

    # ── Voice preview (no PDF needed) ──────────────────────────────────────
    if data.get("preview"):
        preview_text = data.get("preview_text", "Hello! This is a voice preview.")
        job_id = uuid.uuid4().hex
        with jobs_lock:
            jobs[job_id] = {
                "status": "queued", "progress": 0,
                "message": "Generating preview...",
                "output_path": None, "duration": None, "error": None,
            }
        voice_id         = data.get("voice_id",         "pNInz6obpgDQGcFmaJgB")
        model_id         = data.get("model_id",         "eleven_turbo_v2_5")
        stability        = float(data.get("stability",        0.5))
        similarity_boost = float(data.get("similarity_boost", 0.75))
        style            = float(data.get("style",            0.0))

        def _preview():
            try:
                update_job(job_id, status="processing", progress=50, message="Generating preview...")
                engine = TTSEngine(str(AUDIO_FOLDER), api_key=api_key)
                out = engine.synthesize(
                    text=preview_text, voice_id=voice_id, model_id=model_id,
                    stability=stability, similarity_boost=similarity_boost, style=style,
                    output_filename=f"preview_{job_id}.mp3"
                )
                duration = audio_processor.get_duration(out)
                update_job(job_id, status="done", progress=100, message="Done!",
                           output_path=f"preview_{job_id}.mp3", duration=round(duration, 1))
            except Exception as e:
                update_job(job_id, status="failed", error=str(e))

        threading.Thread(target=_preview, daemon=True).start()
        return jsonify({"job_id": job_id})
    # ───────────────────────────────────────────────────────────────────────

    if not file_id:
        return jsonify({"error": "file_id required."}), 400

    voice_id         = data.get("voice_id",         "pNInz6obpgDQGcFmaJgB")
    model_id         = data.get("model_id",         "eleven_turbo_v2_5")
    stability        = float(data.get("stability",        0.5))
    similarity_boost = float(data.get("similarity_boost", 0.75))
    style            = float(data.get("style",            0.0))
    speed            = float(data.get("speed",            1.0))
    pitch            = int(data.get("pitch",              0))
    chapter_index    = data.get("chapter_index",    -1)

    speed = max(0.5, min(3.0, speed))
    pitch = max(-6,  min(6,   pitch))

    pdf_path       = os.path.join(app.config["UPLOAD_FOLDER"], f"{file_id}.pdf")
    chapters_cache = os.path.join(app.config["UPLOAD_FOLDER"], f"{file_id}_chapters.json")

    if not os.path.exists(pdf_path):
        return jsonify({"error": "PDF not found. Please upload again."}), 404

    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {
            "status":      "queued",
            "progress":    0,
            "message":     "Queued...",
            "output_path": None,
            "duration":    None,
            "error":       None,
        }

    thread = threading.Thread(
        target=_run_conversion,
        args=(job_id, pdf_path, chapters_cache,
              api_key, voice_id, model_id,
              stability, similarity_boost, style,
              speed, pitch, chapter_index),
        daemon=True
    )
    thread.start()
    return jsonify({"job_id": job_id})


def _run_conversion(job_id, pdf_path, chapters_cache,
                    api_key, voice_id, model_id,
                    stability, similarity_boost, style,
                    speed, pitch, chapter_index):
    """Background worker: extract → ElevenLabs TTS → adjust audio → save."""
    try:
        update_job(job_id, status="processing", progress=5, message="Loading PDF...")

        engine = TTSEngine(str(AUDIO_FOLDER), api_key=api_key)

        # ── "Convert entire document" path ────────────────────────────────
        # Bypass chapter detection completely — extract ALL text in page order
        if chapter_index == -1:
            processor = PDFProcessor(pdf_path)
            full_text = processor.extract_all_text()
            processor.close()

            if not full_text.strip():
                update_job(job_id, status="failed", error="PDF has no readable text.")
                return

            update_job(job_id, progress=20, message="Converting full document to audio...")


            logger.info(f"Text length: {len(full_text)}")
            logger.info(f"First 200 characters: {repr(full_text[:200])}")

            raw_path = engine.synthesize(
                text=full_text,
                voice_id=voice_id,
                model_id=model_id,
                stability=stability,
                similarity_boost=similarity_boost,
                style=style,
                output_filename=f"raw_{job_id}_full.mp3"
            )

            output_filename = f"output_{job_id}.mp3"
            output_path     = os.path.join(str(AUDIO_FOLDER), output_filename)

            if speed != 1.0 or pitch != 0:
                update_job(job_id, progress=88, message="Adjusting speed/pitch...")
                output_path = audio_processor.adjust_speed_and_pitch(
                    raw_path, speed=speed, semitones=pitch,
                    output_path=output_path
                )
                try:
                    os.remove(raw_path)
                except Exception:
                    pass
            else:
                import shutil
                shutil.move(raw_path, output_path)

            duration = audio_processor.get_duration(output_path)
            update_job(
                job_id,
                status="done", progress=100, message="Done!",
                output_path=output_filename,
                duration=round(duration, 1)
            )
            logger.info(f"Job {job_id} done (full doc): {output_filename} ({duration:.1f}s)")
            return
        # ──────────────────────────────────────────────────────────────────

        # ── Chapter-specific path ─────────────────────────────────────────
        if os.path.exists(chapters_cache):
            with open(chapters_cache, "r", encoding="utf-8") as f:
                chapters = json.load(f)
        else:
            processor = PDFProcessor(pdf_path)
            chapters  = processor.detect_chapters()
            processor.close()

        idx = int(chapter_index)
        if idx < 0 or idx >= len(chapters):
            update_job(job_id, status="failed", error="Invalid chapter index.")
            return
        selected = [chapters[idx]]

        total = len(selected)
        chapter_audio_files = []
        temp_files = []

        for i, chapter in enumerate(selected):
            progress = int(10 + (i / total) * 70)
            update_job(
                job_id,
                progress=progress,
                message=f"Converting {i+1}/{total}: {chapter['title'][:40]}..."
            )

            text = chapter.get("text", "")
            if not text.strip():
                logger.warning(f"Chapter {i+1} has no text, skipping.")
                continue
            

            raw_path = engine.synthesize(
                text=text,
                voice_id=voice_id,
                model_id=model_id,
                stability=stability,
                similarity_boost=similarity_boost,
                style=style,
                output_filename=f"raw_{job_id}_{i}.mp3"
            )
            temp_files.append(raw_path)

            if speed != 1.0 or pitch != 0:
                processed = audio_processor.adjust_speed_and_pitch(
                    raw_path, speed=speed, semitones=pitch,
                    output_path=os.path.join(str(AUDIO_FOLDER), f"proc_{job_id}_{i}.mp3")
                )
                temp_files.append(processed)
                chapter_audio_files.append(processed)
            else:
                chapter_audio_files.append(raw_path)

        if not chapter_audio_files:
            update_job(job_id, status="failed", error="No audio generated (empty text).")
            return

        update_job(job_id, progress=88, message="Merging audio...")

        output_filename = f"output_{job_id}.mp3"
        output_path     = os.path.join(str(AUDIO_FOLDER), output_filename)

        if len(chapter_audio_files) == 1:
            import shutil
            shutil.copy(chapter_audio_files[0], output_path)
        else:
            audio_processor.merge_audio_files(chapter_audio_files, output_path)

        duration = audio_processor.get_duration(output_path)
        audio_processor.cleanup_temp_files(
            [f for f in temp_files if f != output_path]
        )

        update_job(
            job_id,
            status="done",
            progress=100,
            message="Done!",
            output_path=output_filename,
            duration=round(duration, 1)
        )
        logger.info(f"Job {job_id} done: {output_filename} ({duration:.1f}s)")

    except PermissionError as e:
        update_job(job_id, status="failed", error=str(e), message="Invalid API key.")
    except RuntimeError as e:
        err = str(e)
        if "paid ElevenLabs plan" in err or "payment_required" in err:
            update_job(job_id, status="failed", error=err,
                       message="⚠️ This voice requires a paid plan. Please select a different voice.")
        else:
            update_job(job_id, status="failed", error=err, message="Conversion failed.")
    except Exception as e:
        logger.exception(e)
        update_job(
            job_id,
            status="failed",
            error=str(e),
            message="Conversion failed."
      )
    

# ── Status / Serve / Download ─────────────
@app.route("/api/job/<job_id>")
def job_status(job_id):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    return jsonify(job)


@app.route("/api/audio/<filename>")
def serve_audio(filename):
    return send_from_directory(str(AUDIO_FOLDER), filename, as_attachment=False)


@app.route("/api/download/<filename>")
def download_audio(filename):
    return send_from_directory(str(AUDIO_FOLDER), filename, as_attachment=True)


@app.route("/api/stream/<job_id>")
def stream_audio(job_id):
    job = get_job(job_id)
    if not job or job.get("status") != "done":
        return jsonify({"error": "Audio not ready."}), 404

    filepath = os.path.join(str(AUDIO_FOLDER), job["output_path"])
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found."}), 404

    def generate():
        with open(filepath, "rb") as f:
            while chunk := f.read(8192):
                yield chunk

    return Response(
        stream_with_context(generate()),
        mimetype="audio/mpeg",
        headers={"Accept-Ranges": "bytes"}
    )


@app.route("/api/cleanup/<file_id>", methods=["DELETE"])
def cleanup(file_id):
    count = 0
    for pattern in [f"{file_id}.pdf", f"{file_id}_chapters.json"]:
        path = os.path.join(app.config["UPLOAD_FOLDER"], pattern)
        if os.path.exists(path):
            os.remove(path)
            count += 1
    return jsonify({"deleted": count})


# ──────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 50)
    print("  PDF to Audio  —  ElevenLabs Edition")
    print(f"  Running at: http://localhost:{port}")
    print("=" * 50)
    app.run(debug=False, host="0.0.0.0", port=port)
