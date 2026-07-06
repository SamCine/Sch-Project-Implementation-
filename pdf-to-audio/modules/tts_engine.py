"""
TTS Engine Module — ElevenLabs
Converts text to speech using ElevenLabs API.
High-quality, realistic voices. Supports 30+ languages.
"""

import os
import uuid
import requests
import logging

logger = logging.getLogger(__name__)

ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"

# Character limit per request (ElevenLabs supports up to 5000 per call)
MAX_CHARS_PER_CHUNK = 4500

# Default fallback voices — only free-tier premade voices safe for API use
# Removed: Rachel, Domi, Elli, Josh, Sam — these trigger 402 on free tier
DEFAULT_VOICES = [
    {"voice_id": "pNInz6obpgDQGcFmaJgB", "name": "Adam (Male, American)"},
    {"voice_id": "ErXwobaYiN019PkySvjV", "name": "Antoni (Male, American)"},
    {"voice_id": "VR6AewLTigWG4xSOukaG", "name": "Arnold (Male, American)"},
    {"voice_id": "pNInz6obpgDQGcFmaJgB", "name": "Adam (Male, American)"},
]

# ElevenLabs supported model IDs — only free-tier compatible models
MODELS = {
    "eleven_multilingual_v2": "Multilingual v2 (Best Quality, 30+ languages)",
    "eleven_turbo_v2_5":      "Turbo v2.5 (Fast, low latency)",
}

DEFAULT_MODEL = "eleven_turbo_v2_5"


class TTSEngine:
    def __init__(self, output_dir, api_key=None):
        self.output_dir = output_dir
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        os.makedirs(output_dir, exist_ok=True)

    def set_api_key(self, api_key):
        self.api_key = api_key

    def _headers(self):
        return {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }

    # ── Voices ────────────────────────────────────────────────────────────

    def get_voices(self):
        """Fetch available voices from ElevenLabs API.
        Excludes paid/library voices and specific premade voices that
        return 402 errors on free-tier accounts.
        """
        if not self.api_key:
            return DEFAULT_VOICES

        # Voice IDs known to require paid plan even though listed as "premade"
        BLOCKED_VOICE_IDS = {
            "21m00Tcm4TlvDq8ikWAM",  # Adam (free-tier safe)
            "AZnzlk1XvdvUeBnXmlld",  # Domi
            "MF3mGyEYCl7XYWbV9V6O",  # Elli
            "TxGEqnHWrfWFTfGW9XjX",  # Josh
            "yoZ06aMxZJJ28mfd3POQ",  # Sam
        }

        try:
            res = requests.get(
                f"{ELEVENLABS_API_BASE}/voices",
                headers={"xi-api-key": self.api_key},
                timeout=10,
            )
            if res.status_code == 200:
                data = res.json()
                premade = []
                cloned  = []

                for v in data.get("voices", []):
                    voice_id = v["voice_id"]
                    category = v.get("category", "")

                    # Skip paid library/professional voices
                    if category == "professional":
                        continue
                    # Skip specifically blocked voices that cause 402
                    if voice_id in BLOCKED_VOICE_IDS:
                        continue

                    labels = v.get("labels", {})
                    accent = labels.get("accent", "")
                    gender = labels.get("gender", "")
                    desc = " ".join(filter(None, [gender.capitalize(), accent.capitalize()]))
                    name = v["name"]
                    if desc:
                        name = f"{name} ({desc})"

                    entry = {"voice_id": voice_id, "name": name}

                    if category == "cloned":
                        entry["name"] = f"⭐ {name} [Your Voice]"
                        cloned.append(entry)
                    else:
                        premade.append(entry)

                # User's own cloned voices first, then sorted premade voices
                voices = sorted(cloned, key=lambda x: x["name"]) + \
                         sorted(premade, key=lambda x: x["name"])

                if not voices:
                    logger.warning("No usable voices found, falling back to defaults.")
                    return DEFAULT_VOICES

                return voices
            else:
                logger.warning(f"ElevenLabs voices fetch failed: {res.status_code}")
                return DEFAULT_VOICES
        except Exception as e:
            logger.error(f"Error fetching voices: {e}")
            return DEFAULT_VOICES

    def get_models(self):
        """Return available TTS models."""
        return [{"model_id": k, "label": v} for k, v in MODELS.items()]

    def get_user_info(self):
        """Return API key usage info (character count, limit)."""
        if not self.api_key:
            return None
        try:
            res = requests.get(
                f"{ELEVENLABS_API_BASE}/user/subscription",
                headers={"xi-api-key": self.api_key},
                timeout=10,
            )
            if res.status_code == 200:
                data = res.json()
                return {
                    "character_count":  data.get("character_count", 0),
                    "character_limit":  data.get("character_limit", 10000),
                    "tier":             data.get("tier", "free"),
                }
        except Exception as e:
            logger.error(f"Error fetching user info: {e}")
        return None

    def validate_api_key(self):
        """Check if the API key is valid."""
        if not self.api_key:
            return False, "No API key provided."
        try:
            res = requests.get(
                f"{ELEVENLABS_API_BASE}/user",
                headers={"xi-api-key": self.api_key},
                timeout=10,
            )
            if res.status_code == 200:
                return True, "Valid"

            logger.warning(
                "ElevenLabs key validation failed: status=%s, body=%s",
                res.status_code,
                res.text,
            )

            try:
                payload = res.json()
            except Exception:
                payload = None

            if res.status_code == 401:
                if payload and isinstance(payload, dict):
                    detail = payload.get("detail") or {}
                    message = detail.get("message") or payload.get("message") or "Invalid API key."
                    return False, message
                return False, "Invalid API key."
            return False, payload.get("detail", {}).get("message", f"Unexpected status: {res.status_code}") if payload else f"Unexpected status: {res.status_code}"
        except Exception as e:
            logger.error("Error validating ElevenLabs API key: %s", e)
            return False, str(e)

    # ── Synthesis ─────────────────────────────────────────────────────────

    def synthesize(self, text, voice_id=None, model_id=None,
                   stability=0.5, similarity_boost=0.75,
                   style=0.0, output_filename=None):
        """
        Convert text to speech using ElevenLabs API.
        Returns path to generated MP3 file.
        Auto-chunks text that exceeds API limit.
        """
        if not self.api_key:
            raise ValueError("ElevenLabs API key is required.")

        if not text or not text.strip():
            raise ValueError("Text is empty — nothing to synthesize.")

        if voice_id is None:
            voice_id = DEFAULT_VOICES[0]["voice_id"]  # Adam (free-tier safe)

        if model_id is None:
            model_id = DEFAULT_MODEL

        if output_filename is None:
            output_filename = f"{uuid.uuid4().hex}.mp3"

        output_path = os.path.join(self.output_dir, output_filename)

        # Split into chunks if needed
        chunks = self._split_text(text)

        if len(chunks) == 1:
            self._call_api(chunks[0], voice_id, model_id,
                           stability, similarity_boost, style, output_path)
        else:
            from pydub import AudioSegment
            temp_files = []
            segments = []

            for i, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue
                tmp = os.path.join(self.output_dir, f"_chunk_{uuid.uuid4().hex}.mp3")
                self._call_api(chunk, voice_id, model_id,
                               stability, similarity_boost, style, tmp)
                segments.append(AudioSegment.from_mp3(tmp))
                temp_files.append(tmp)

            if not segments:
                raise RuntimeError("All TTS chunks failed.")

            combined = segments[0]
            silence = AudioSegment.silent(duration=300)
            for seg in segments[1:]:
                combined = combined + silence + seg
            combined.export(output_path, format="mp3")

            for f in temp_files:
                try:
                    os.remove(f)
                except Exception:
                    pass

        return output_path

    def _call_api(self, text, voice_id, model_id,
                  stability, similarity_boost, style, output_path):
        """Make a single ElevenLabs TTS API call and save MP3."""
        url = f"{ELEVENLABS_API_BASE}/text-to-speech/{voice_id}"

        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability":        stability,
                "similarity_boost": similarity_boost,
                "style":            style,
                "use_speaker_boost": True,
            },
        }

        res = requests.post(
            url,
            json=payload,
            headers=self._headers(),
            timeout=60,
            stream=True,
        )

        if res.status_code == 200:
            with open(output_path, "wb") as f:
                for chunk in res.iter_content(chunk_size=4096):
                    if chunk:
                        f.write(chunk)
        elif res.status_code == 401:
            raise PermissionError("Invalid ElevenLabs API key. Please re-validate your key.")
        elif res.status_code == 402:
            raise RuntimeError(
                "This voice requires a paid ElevenLabs plan. "
                "Please select a different voice and try again."
            )
        elif res.status_code == 422:
            raise ValueError(f"ElevenLabs request error: {res.text}")
        elif res.status_code == 429:
            raise RuntimeError("ElevenLabs rate limit exceeded. Please wait a moment and try again.")
        else:
            raise RuntimeError(f"ElevenLabs API error {res.status_code}: {res.text}")

    # ── Text Splitting ─────────────────────────────────────────────────────

    def _split_text(self, text):
        if len(text) <= MAX_CHARS_PER_CHUNK:
            return [text]

        chunks = []
        sentences = self._split_sentences(text)
        current = ""

        for sentence in sentences:
            if len(current) + len(sentence) + 1 <= MAX_CHARS_PER_CHUNK:
                current += (" " if current else "") + sentence
            else:
                if current:
                    chunks.append(current.strip())
                if len(sentence) > MAX_CHARS_PER_CHUNK:
                    word_chunks = self._split_by_words(sentence)
                    chunks.extend(word_chunks[:-1])
                    current = word_chunks[-1] if word_chunks else ""
                else:
                    current = sentence

        if current.strip():
            chunks.append(current.strip())

        return chunks

    def _split_sentences(self, text):
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s for s in sentences if s.strip()]

    def _split_by_words(self, text):
        words = text.split()
        chunks, current = [], ""
        for word in words:
            if len(current) + len(word) + 1 <= MAX_CHARS_PER_CHUNK:
                current += (" " if current else "") + word
            else:
                if current:
                    chunks.append(current)
                current = word
        if current:
            chunks.append(current)
        return chunks
