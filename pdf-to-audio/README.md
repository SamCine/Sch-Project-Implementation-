# 📄➡️🔊 PDF to Audio Web App

A full-featured, browser-based system that converts PDF documents into natural speech using Python + Flask + Google TTS.

## ✨ Features

| Feature | Details |
|---|---|
| 📤 PDF Upload | Drag & drop or click to upload, up to 50MB |
| 🌍 Multi-language | 18+ languages — English (US/UK/AU/IN), Spanish, French, German, Chinese, Japanese, Arabic, Hindi, and more |
| ⚡ Speed Control | 0.5× to 3.0× playback speed |
| 🎵 Pitch Control | −6 to +6 semitones |
| 🐢 Slow Mode | Extra clear reading mode |
| 📑 Chapter Navigation | Auto-detects chapters/sections (via TOC or heuristic) |
| 🔊 In-browser Playback | HTML5 audio player with controls |
| ⬇️ Download MP3 | Download the generated audio |
| 🔗 Shareable Link | Copy direct link to audio |
| ⚙️ Async Conversion | Background processing with real-time progress bar |

## 🚀 Quick Start

```bash
# 1. Setup (first time only)
chmod +x setup.sh
./setup.sh

# 2. Run
source venv/bin/activate
python3 app.py

# 3. Open browser
# http://localhost:5000
```

## 📁 Project Structure

```
pdf-to-audio/
├── app.py                    # Flask backend (main entry point)
├── requirements.txt          # Python dependencies
├── setup.sh                  # One-command setup script
├── run.sh                    # Quick run script
├── modules/
│   ├── pdf_processor.py      # PDF text extraction + chapter detection
│   ├── tts_engine.py         # Google TTS wrapper (multi-lang, chunking)
│   └── audio_processor.py   # Speed, pitch, merge (pydub)
├── templates/
│   └── index.html            # Main UI
├── static/
│   ├── css/style.css         # Modern dark-theme styling
│   └── js/app.js             # Frontend logic
├── uploads/                  # Uploaded PDFs (auto-created)
└── audio_output/             # Generated MP3s (auto-created)
```

## 🔌 API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Main web UI |
| `/api/languages` | GET | List supported TTS languages |
| `/api/upload` | POST | Upload PDF, get file_id + chapters |
| `/api/convert` | POST | Start async conversion job |
| `/api/job/<job_id>` | GET | Poll job status + progress |
| `/api/audio/<filename>` | GET | Stream audio for playback |
| `/api/download/<filename>` | GET | Download MP3 |
| `/api/cleanup/<file_id>` | DELETE | Clean up uploaded files |

## 🛠️ Tech Stack

- **Backend:** Python 3 + Flask
- **PDF Processing:** PyMuPDF (fitz) + pdfplumber
- **TTS:** gTTS (Google Text-to-Speech)
- **Audio:** pydub (speed/pitch/merge)
- **Frontend:** HTML5 + CSS3 + Vanilla JS
