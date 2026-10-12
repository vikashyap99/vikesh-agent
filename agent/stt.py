import os

from openai import OpenAI


class STT:
    def __init__(self, base_url, model, api_key=None, api_key_env=None, language=None):
        key = api_key or os.environ.get(api_key_env or "", "")
        if not key:
            raise RuntimeError(
                f"missing STT API key: set {api_key_env} in .env or the environment"
            )
        self.client = OpenAI(base_url=base_url, api_key=key)
        self.model = model
        self.language = language

    def transcribe(self, audio_path):
        kwargs = {"model": self.model}
        if self.language:
            kwargs["language"] = self.language
        with open(audio_path, "rb") as f:
            result = self.client.audio.transcriptions.create(file=f, **kwargs)
        return (result.text or "").strip()
