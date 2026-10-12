import os
import shutil
import uuid

import yaml
from dotenv import load_dotenv

from .llm import PersonaLLM
from .memory import Memory
from .stt import STT
from .tts import FishTTS

AUDIO_EXTS = {".wav", ".mp3", ".mpeg", ".m4a", ".mp4", ".aac", ".flac", ".webm", ".ogg", ".oga", ".opus"}


class Pipeline:
    def __init__(self, config_path="config.yaml"):
        load_dotenv()
        self.config_path = os.path.abspath(config_path)
        self.base_dir = os.path.dirname(self.config_path)
        with open(self.config_path, encoding="utf-8") as f:
            self.cfg = yaml.safe_load(f) or {}
        self.data_dir = self._resolve_data_dir()
        os.makedirs(os.path.join(self.data_dir, "voice"), exist_ok=True)
        self.memory = Memory(self.data_dir)
        self._stt = None
        self._llm = None
        self._tts = None

    def _resolve_data_dir(self):
        root = self.cfg.get("data_dir") or os.environ.get("VIK_DATA_DIR")
        if not root:
            return self.base_dir
        return root if os.path.isabs(root) else os.path.join(self.base_dir, root)

    def _path(self, p):
        if not p:
            return p
        return p if os.path.isabs(p) else os.path.join(self.base_dir, p)

    def _data_path(self, p):
        if not p:
            return p
        return p if os.path.isabs(p) else os.path.join(self.data_dir, p)

    def _voice_id(self, cfg):
        if cfg.get("reference_id"):
            return cfg["reference_id"]
        id_file = self._data_path("voice/voice_id.txt")
        if os.path.exists(id_file):
            with open(id_file, encoding="utf-8") as f:
                return f.read().strip()
        return None

    @property
    def stt(self):
        if self._stt is None:
            cfg = self.cfg.get("stt", {})
            self._stt = STT(
                base_url=cfg["base_url"],
                model=cfg["model"],
                api_key_env=cfg.get("api_key_env"),
                language=cfg.get("language"),
            )
        return self._stt

    @property
    def llm(self):
        if self._llm is None:
            persona = self.cfg.get("persona", {})
            cfg = self.cfg.get("llm", {})
            summary_file = None
            if persona.get("profile_mode", "auto") != "full":
                summary_file = self._path(
                    persona.get("profile_summary_file", "profile_summary.md")
                )
            self._llm = PersonaLLM(
                base_url=cfg["base_url"],
                model=cfg["model"],
                api_key_env=cfg.get("api_key_env"),
                context_file=self._path(persona.get("context_file", "context.md")),
                profile_file=self._path(persona.get("profile_file", "profile.md")),
                profile_summary_file=summary_file,
                temperature=cfg.get("temperature", 0.7),
                max_tokens=cfg.get("max_tokens", 768),
                reasoning_effort=cfg.get("reasoning_effort"),
                fallback_models=cfg.get("fallback_models"),
                openrouter_reasoning=cfg.get("openrouter_reasoning"),
                memory=self.memory,
            )
        return self._llm

    @property
    def tts(self):
        if self._tts is None:
            cfg = self.cfg.get("tts", {})
            self._tts = FishTTS(
                api_key_env=cfg.get("api_key_env"),
                model=cfg.get("model", "s2.1-pro-free"),
                base_url=cfg.get("base_url", "https://api.fish.audio"),
                voice_api=cfg.get(
                    "voice_api", "https://api.fish.audio/model"
                ),
                reference_id=self._voice_id(cfg),
                reference_text=self._data_path(cfg.get("reference_text")),
                audio_format=cfg.get("format", "mp3"),
            )
        return self._tts

    def enroll(self, name="Vikash", audio=None):
        cfg = self.cfg.get("tts", {})
        audio = audio or cfg.get("reference_audio", "voice/ref.wav")
        voice_id = self.tts.create_voice(
            name=name,
            audio_path=self._data_path(audio),
            reference_text=self._data_path(cfg.get("reference_text")),
        )
        id_file = self._data_path("voice/voice_id.txt")
        os.makedirs(os.path.dirname(id_file), exist_ok=True)
        with open(id_file, "w", encoding="utf-8") as f:
            f.write(voice_id)
        return voice_id

    def samples_dir(self):
        path = self._data_path("voice/samples")
        os.makedirs(path, exist_ok=True)
        return path

    def save_voice_sample(self, src_path, transcript, ext=None):
        ext = (ext or os.path.splitext(src_path)[1] or ".wav").lower()
        if ext not in AUDIO_EXTS:
            ext = ".wav"
        sid = uuid.uuid4().hex[:10]
        dst = os.path.join(self.samples_dir(), sid + ext)
        shutil.copyfile(src_path, dst)
        with open(os.path.splitext(dst)[0] + ".txt", "w", encoding="utf-8") as f:
            f.write((transcript or "").strip())
        return sid

    def list_voice_samples(self):
        sdir = self.samples_dir()
        out = []
        for name in sorted(os.listdir(sdir)):
            if os.path.splitext(name)[1].lower() not in AUDIO_EXTS:
                continue
            path = os.path.join(sdir, name)
            text_path = os.path.splitext(path)[0] + ".txt"
            transcript = ""
            if os.path.exists(text_path):
                with open(text_path, encoding="utf-8") as f:
                    transcript = f.read().strip()
            out.append(
                {
                    "id": os.path.splitext(name)[0],
                    "ext": os.path.splitext(name)[1].lower(),
                    "transcript": transcript,
                    "bytes": os.path.getsize(path),
                    "ts": os.path.getmtime(path),
                }
            )
        return out

    def delete_voice_sample(self, sid):
        sdir = self.samples_dir()
        removed = False
        for name in os.listdir(sdir):
            if os.path.splitext(name)[0] == sid:
                os.remove(os.path.join(sdir, name))
                removed = True
        return removed

    def _collected_samples(self):
        cfg = self.cfg.get("tts", {})
        samples = []
        ref_audio = self._data_path(cfg.get("reference_audio", "voice/ref.wav"))
        ref_text = self._data_path(cfg.get("reference_text", "voice/ref.txt"))
        if os.path.exists(ref_audio):
            transcript = ""
            if os.path.exists(ref_text):
                with open(ref_text, encoding="utf-8") as f:
                    transcript = f.read().strip()
            samples.append({"audio": ref_audio, "text": transcript})
        for s in self.list_voice_samples():
            samples.append(
                {"audio": os.path.join(self.samples_dir(), s["id"] + s["ext"]), "text": s["transcript"]}
            )
        return samples[:20]

    def train_voice(self, name="Vikash"):
        samples = self._collected_samples()
        if not len(samples):
            raise ValueError("no voice samples found — record at least one first")
        voice_id = self.tts.create_voice_multi(name, samples)
        id_file = self._data_path("voice/voice_id.txt")
        os.makedirs(os.path.dirname(id_file), exist_ok=True)
        with open(id_file, "w", encoding="utf-8") as f:
            f.write(voice_id)
        self._tts = None
        return voice_id, len(samples)

    def ensure_profile_summary(self, force=False):
        persona = self.cfg.get("persona", {})
        if persona.get("profile_mode", "auto") == "full":
            return None
        src = self._path(persona.get("profile_file", "profile.md"))
        dst = self._path(persona.get("profile_summary_file", "profile_summary.md"))
        if not os.path.exists(src):
            return None
        if (
            not force
            and os.path.exists(dst)
            and os.path.getmtime(dst) >= os.path.getmtime(src)
        ):
            return dst
        text = self.llm.condense_profile()
        if not text:
            return None
        with open(dst, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        return dst

    def run(self, text=None, audio=None, out=None, language=None, history=None):
        heard = None
        if audio:
            heard = self.stt.transcribe(self._path(audio))
            text = heard
        if not text:
            raise ValueError("provide text or audio input")
        reply = self.llm.reply(text, history=history)
        out_dir = self._data_path(self.cfg.get("output_dir", "output"))
        os.makedirs(out_dir, exist_ok=True)
        ext = self.cfg.get("tts", {}).get("format", "mp3")
        out_path = out or os.path.join(out_dir, f"reply.{ext}")
        self.tts.synthesize(reply, out_path)
        return heard, reply, out_path
