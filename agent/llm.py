import os
import re

from openai import OpenAI

_EMOJI = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF"
    "\U00002B00-\U00002BFF"
    "\uFE0F\u200d"
    "]+",
    flags=re.UNICODE,
)


def clean_for_speech(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"(?m)^\s*[-*\u2022]\s+", "", text)
    text = re.sub(r"(?m)^\s*\d+[.)]\s+", "", text)
    text = re.sub(r"(?m)^#{1,6}\s*", "", text)
    text = re.sub(r"[*_#>~|]+", "", text)
    text = _EMOJI.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class PersonaLLM:
    def __init__(
        self,
        base_url,
        model,
        api_key=None,
        api_key_env=None,
        context_file=None,
        profile_file=None,
        profile_summary_file=None,
        temperature=0.7,
        max_tokens=768,
        reasoning_effort=None,
        fallback_models=None,
        openrouter_reasoning=None,
        memory=None,
    ):
        key = api_key or os.environ.get(api_key_env or "", "")
        if not key:
            raise RuntimeError(
                f"missing LLM API key: set {api_key_env} in .env or the environment"
            )
        self.client = OpenAI(base_url=base_url, api_key=key)
        self.model = model
        self.context_file = context_file
        self.profile_file = profile_file
        self.profile_summary_file = profile_summary_file
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort
        self.fallback_models = list(fallback_models or [])
        self.openrouter_reasoning = openrouter_reasoning
        self.memory = memory
        self.system_prompt = self._build_system_prompt()

    @staticmethod
    def _read(path):
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
        return ""

    def _extra_body(self):
        extra = {}
        if self.reasoning_effort:
            extra["reasoning_effort"] = self.reasoning_effort
        if self.openrouter_reasoning is False:
            extra["reasoning"] = {"enabled": False}
        if self.fallback_models:
            extra["models"] = [self.model] + [
                m for m in self.fallback_models if m != self.model
            ]
        return extra or None

    def _build_system_prompt(self):
        parts = [
            "You are Vikash, a real person, chatting casually with someone. You are "
            "NOT an assistant. Never say you are an AI, a model, a bot, or a script.",
            "Speak in the first person in clear, natural Hindi (written in Roman "
            "script) with good English mixed in, the way Vikash actually talks. No "
            "Bhojpuri, no dialect, no added accent, no extra filler words.",
            "Reply like a normal chat message: conversational, 2 to 6 sentences, warm, "
            "lightly humorous, with a clear point of view. Do not write essays.",
            "Never use markdown or formatting: no headings, no asterisks, no dashes, "
            "no numbered or bullet lists, no emojis. Only plain spoken words.",
            "Use the background below only as facts to draw on. Do NOT summarize, "
            "recite, or narrate your biography unless asked about it directly.",
        ]
        context = self._read(self.context_file)
        profile = self._read(self.profile_summary_file) or self._read(self.profile_file)
        if context:
            parts.append("# How Vikash talks and behaves\n" + context)
        if profile:
            parts.append("# Vikash's background (facts only, do not recite)\n" + profile)
        if self.memory is not None:
            try:
                learned = self.memory.prompt_context()
            except Exception:
                learned = ""
            if learned:
                parts.append(learned)
        parts.append(
            "Reminder: you are Vikash. Begin every reply with the greeting "
            '"Hey everyone!" and end every reply with exactly "Bye, bye." — two byes '
            "only, never a third. In between, answer directly in clear, natural Hindi "
            "(Roman script) with good English mixed in, in your own casual voice. No "
            "Bhojpuri, no dialect, no added accent, no extra filler words. Keep it short "
            "unless asked for detail. Plain spoken words only, no lists or markdown."
        )
        return "\n\n".join(parts)

    def reply(self, text, history=None):
        self.system_prompt = self._build_system_prompt()
        messages = [{"role": "system", "content": self.system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": text})
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            extra_body=self._extra_body(),
        )
        return clean_for_speech(resp.choices[0].message.content or "")

    def reflect(self, prompt, max_tokens=600):
        """Plain completion (no persona) used for self-improvement notes."""
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a concise coach that improves a persona-based chat "
                        "agent. Output plain text notes only, no preamble."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=max_tokens,
            extra_body=self._extra_body(),
        )
        return (resp.choices[0].message.content or "").strip()

    def condense_profile(self):
        """Summarize the full profile into a compact, fact-complete reference."""
        full = self._read(self.profile_file)
        if not full:
            return ""
        prompt = (
            "Condense the biography below into a compact but complete reference of "
            "its key facts. Keep every concrete detail that matters: identity, dates, "
            "places, education, employers, job titles, projects, family, skills, "
            "opinions, favorites, milestones and numbers. Use short bullet lines "
            "under a few headings. Aim for roughly 1200-2000 tokens. Do not invent "
            "anything and do not add commentary.\n\n" + full
        )
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You faithfully compress background notes. Output plain text "
                        "only, no preamble."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=2200,
            extra_body=self._extra_body(),
        )
        return (resp.choices[0].message.content or "").strip()
