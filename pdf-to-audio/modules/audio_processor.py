"""
Audio Processor Module
Handles speed adjustment, pitch shifting, and audio merging using pydub.
"""

import os
import uuid
from pydub import AudioSegment
from pydub.effects import normalize
import logging

logger = logging.getLogger(__name__)


class AudioProcessor:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def adjust_speed(self, input_path, speed=1.0, output_path=None):
        """
        Adjust playback speed of an MP3 file.
        speed: 0.5 = half speed, 1.0 = normal, 2.0 = double speed
        Returns path to the processed file.
        """
        if speed == 1.0:
            return input_path  # No processing needed

        if output_path is None:
            output_path = os.path.join(
                self.output_dir, f"speed_{uuid.uuid4().hex}.mp3"
            )

        audio = AudioSegment.from_mp3(input_path)

        # Speed change by overriding frame_rate then resampling
        new_frame_rate = int(audio.frame_rate * speed)
        faster = audio._spawn(audio.raw_data, overrides={"frame_rate": new_frame_rate})
        faster = faster.set_frame_rate(44100)

        faster.export(output_path, format="mp3")
        return output_path

    def adjust_pitch(self, input_path, semitones=0, output_path=None):
        """
        Adjust pitch of an MP3 file.
        semitones: negative = lower pitch, positive = higher pitch
        Returns path to the processed file.
        """
        if semitones == 0:
            return input_path

        if output_path is None:
            output_path = os.path.join(
                self.output_dir, f"pitch_{uuid.uuid4().hex}.mp3"
            )

        audio = AudioSegment.from_mp3(input_path)

        # Pitch shift by changing frame rate (simple but effective)
        import math
        factor = math.pow(2, semitones / 12.0)
        new_frame_rate = int(audio.frame_rate * factor)
        shifted = audio._spawn(audio.raw_data, overrides={"frame_rate": new_frame_rate})
        shifted = shifted.set_frame_rate(audio.frame_rate)

        shifted.export(output_path, format="mp3")
        return output_path

    def adjust_speed_and_pitch(self, input_path, speed=1.0, semitones=0, output_path=None):
        """Apply both speed and pitch adjustments."""
        if output_path is None:
            output_path = os.path.join(
                self.output_dir, f"processed_{uuid.uuid4().hex}.mp3"
            )

        audio = AudioSegment.from_mp3(input_path)

        import math

        # Apply pitch shift
        if semitones != 0:
            factor = math.pow(2, semitones / 12.0)
            new_fr = int(audio.frame_rate * factor)
            audio = audio._spawn(audio.raw_data, overrides={"frame_rate": new_fr})
            audio = audio.set_frame_rate(44100)

        # Apply speed change
        if speed != 1.0:
            new_fr = int(audio.frame_rate * speed)
            audio = audio._spawn(audio.raw_data, overrides={"frame_rate": new_fr})
            audio = audio.set_frame_rate(44100)

        # Normalize to prevent clipping
        audio = normalize(audio)

        audio.export(output_path, format="mp3")
        return output_path

    def merge_audio_files(self, file_paths, output_path=None, silence_ms=500):
        """
        Merge multiple MP3 files into one, with optional silence between them.
        Returns path to merged file.
        """
        if not file_paths:
            raise ValueError("No files to merge.")

        if output_path is None:
            output_path = os.path.join(
                self.output_dir, f"merged_{uuid.uuid4().hex}.mp3"
            )

        combined = None
        silence = AudioSegment.silent(duration=silence_ms)

        for path in file_paths:
            if not os.path.exists(path):
                logger.warning(f"File not found, skipping: {path}")
                continue
            seg = AudioSegment.from_mp3(path)
            if combined is None:
                combined = seg
            else:
                combined = combined + silence + seg

        if combined is None:
            raise RuntimeError("No valid audio files to merge.")

        combined.export(output_path, format="mp3")
        return output_path

    def get_duration(self, file_path):
        """Return duration of audio file in seconds."""
        audio = AudioSegment.from_mp3(file_path)
        return len(audio) / 1000.0

    def cleanup_temp_files(self, file_paths):
        """Delete temporary audio files."""
        for path in file_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.warning(f"Could not delete {path}: {e}")
