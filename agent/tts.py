import os

import requests

_MIME = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".mpeg": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/opus",
}


def _mime_for(path):
    return _MIME.get(os.path.splitext(path)[1].lower(), "audio/wav")


class FishTTS:
    def __init__(
        self,
        api_key=None,
        api_key_env=None,
        model="s2.1-pro-free",
        base_url="https://api.fish.audio",
        voice_api="https://api.fish.audio/model",
        reference_id=None,
        reference_text=None,
        audio_format="mp3",
    ):
        key = api_key or os.environ.get(api_key_env or "", "")
        if not key:
            raise RuntimeError(
                f"missing TTS API key: set {api_key_env} in .env or the environment"
            )
        self.api_key = key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.voice_api = voice_api
        self.reference_id = reference_id
        self.reference_text = reference_text
        self.audio_format = audio_format

    def create_voice(self, name, audio_path, reference_text=None):
        text = reference_text or self.reference_text
        if text and os.path.exists(text):
            with open(text, encoding="utf-8") as f:
                text = f.read().strip()
        return self.create_voice_multi(name, [{"audio": audio_path, "text": text}])

    def create_voice_multi(self, name, samples):
        """Create/train a voice model from 1-20 samples.

        samples: list of {"audio": <path>, "text": <transcript or "">}
        More samples (and matching transcripts) improve clone fidelity.
        """
        if not samples:
            raise ValueError("at least one voice sample is required")
        if len(samples) > 20:
            samples = samples[:20]
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = [
            ("title", name),
            ("type", "tts"),
            ("train_mode", "fast"),
            ("visibility", "private"),
            ("enhance_audio_quality", "true"),
        ]
        files = []
        handles = []
        try:
            for s in samples:
                path = s["audio"]
                text = (s.get("text") or "").strip()
                if not os.path.exists(path):
                    continue
                handle = open(path, "rb")
                handles.append(handle)
                files.append(
                    ("voices", (os.path.basename(path), handle, _mime_for(path)))
                )
                data.append(("texts", text))
            resp = requests.post(
                self.voice_api, headers=headers, data=data, files=files, timeout=600
            )
        finally:
            for handle in handles:
                handle.close()
        resp.raise_for_status()
        voice_id = resp.json()["_id"]
        self.reference_id = voice_id
        return voice_id

    def get_model(self, model_id=None):
        model_id = model_id or self.reference_id
        if not model_id:
            return None
        resp = requests.get(
            f"{self.voice_api}/{model_id}",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def synthesize(self, text, out_path, reference_id=None):
        ref = reference_id or self.reference_id
        if not ref:
            raise ValueError(
                "no reference_id set. Enroll your voice first: python cli.py --enroll"
            )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "model": self.model,
        }
        body = {"text": text, "reference_id": ref, "format": self.audio_format}
        resp = requests.post(
            f"{self.base_url}/v1/tts", headers=headers, json=body, timeout=600
        )
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(resp.content)
        return out_path
