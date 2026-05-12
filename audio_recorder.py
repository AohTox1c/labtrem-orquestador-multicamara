"""
audio_recorder.py
Grabación de audio en segundo plano durante la sesión de video.

Requiere: pip install sounddevice
Para muxing de audio+video: ffmpeg debe estar en el PATH del sistema.
"""
import os
import shutil
import subprocess
import tempfile
import wave

try:
    import numpy as np
    import sounddevice as sd
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

SAMPLE_RATE = 44100
_FALLBACK_RATES = [44100, 48000, 22050, 16000]
CHANNELS = 1  # mono


class AudioRecorder:
    """
    Graba el micrófono predeterminado mientras dure la sesión de grabación.
    Si sounddevice no está instalado, todas las operaciones son no-op silenciosas.
    """

    def __init__(self):
        self.available = _AVAILABLE
        self._frames: list = []
        self._stream = None
        self._wav_path: str | None = None
        self._sample_rate: int = SAMPLE_RATE

    def start(self) -> None:
        """Inicia la captura de audio."""
        if not self.available:
            return
        self._frames = []
        fd, self._wav_path = tempfile.mkstemp(suffix="_labtrem_audio.wav")
        os.close(fd)

        last_err = None
        for rate in _FALLBACK_RATES:
            try:
                self._stream = sd.InputStream(
                    samplerate=rate,
                    channels=CHANNELS,
                    dtype="int16",
                    callback=self._callback,
                )
                self._stream.start()
                self._sample_rate = rate
                return
            except Exception as e:
                last_err = e
                self._stream = None
                continue

        # No supported rate found — disable audio silently
        self.available = False
        print(f"[AudioRecorder] No supported sample rate found, audio disabled. Last error: {last_err}")

    def _callback(self, indata, frames, time_info, status) -> None:
        self._frames.append(indata.copy())

    def stop(self) -> "str | None":
        """
        Detiene la grabación, guarda el .wav temporal y devuelve su ruta.
        Devuelve None si no hay audio disponible.
        """
        if not self.available or self._stream is None:
            return None
        self._stream.stop()
        self._stream.close()
        self._stream = None
        if not self._frames:
            return None
        data = np.concatenate(self._frames, axis=0)
        with wave.open(self._wav_path, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)          # int16 = 2 bytes por muestra
            wf.setframerate(self._sample_rate)
            wf.writeframes(data.tobytes())
        return self._wav_path


def mux_audio_into_video(video_path: str, wav_path: str) -> bool:
    """
    Mezcla el audio .wav dentro del archivo .mp4 usando el ffmpeg de PyAV.
    """
    try:
        import av as _av
        ffmpeg = _av.datasets.curated  # solo para verificar que av está disponible
        import shutil as _sh
        # PyAV no expone el exe directamente; intentar imageio-ffmpeg o sistema
        try:
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_exe = _sh.which("ffmpeg")
    except Exception:
        ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        return False

    tmp_out = video_path + ".mux_tmp.mp4"
    try:
        result = subprocess.run(
            [
                ffmpeg_exe, "-y",
                "-i", video_path,
                "-i", wav_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                tmp_out,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
        if result.returncode == 0 and os.path.exists(tmp_out):
            os.replace(tmp_out, video_path)
            return True
    except Exception:
        pass
    finally:
        if os.path.exists(tmp_out):
            try:
                os.remove(tmp_out)
            except OSError:
                pass
    return False
