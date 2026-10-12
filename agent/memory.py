import json
import os
import time
import uuid


class Memory:
    """Self-learning store: logs every exchange, tracks feedback, and keeps
    concise 'learned notes' that get fed back into the system prompt."""

    def __init__(self, base_dir, history_turns=6):
        self.dir = os.path.join(base_dir, "memory")
        os.makedirs(self.dir, exist_ok=True)
        self.history_path = os.path.join(self.dir, "history.jsonl")
        self.notes_path = os.path.join(self.dir, "notes.md")
        self.report_path = os.path.join(self.dir, "report.md")
        self.history_turns = history_turns

    def _read_jsonl(self):
        items = []
        if os.path.exists(self.history_path):
            with open(self.history_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        items.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return items

    def _write_jsonl(self, items):
        tmp = self.history_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        os.replace(tmp, self.history_path)

    @staticmethod
    def _read_text(path):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
        return ""

    def log(self, question, reply, source="text", heard=None):
        item = {
            "id": uuid.uuid4().hex,
            "ts": time.time(),
            "source": source,
            "question": question,
            "heard": heard,
            "reply": reply,
            "rating": None,
            "rated_ts": None,
        }
        with open(self.history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return item["id"]

    def rate(self, item_id, rating):
        if rating not in ("up", "down", None):
            raise ValueError("rating must be 'up', 'down' or null")
        items = self._read_jsonl()
        found = False
        for it in items:
            if it.get("id") == item_id:
                it["rating"] = rating
                it["rated_ts"] = time.time() if rating else None
                found = True
        if found:
            self._write_jsonl(items)
            self.build_report()
        return found

    def all(self):
        return self._read_jsonl()

    def recent(self, n=20):
        return self._read_jsonl()[-n:]

    @staticmethod
    def _positive_pct(rated):
        if not rated:
            return None
        up = sum(1 for x in rated if x.get("rating") == "up")
        return round(100.0 * up / len(rated), 1)

    def stats(self):
        items = self._read_jsonl()
        rated = [it for it in items if it.get("rating") in ("up", "down")]
        up = sum(1 for it in rated if it["rating"] == "up")
        down = len(rated) - up
        result = {
            "total": len(items),
            "rated": len(rated),
            "up": up,
            "down": down,
            "positive_pct": self._positive_pct(rated),
            "trend": "not enough data",
            "trend_delta": None,
        }
        if len(rated) >= 6:
            half = len(rated) // 2
            older, newer = rated[:half], rated[half:]
            o, n = self._positive_pct(older), self._positive_pct(newer)
            delta = round(n - o, 1)
            result["trend_delta"] = delta
            if delta > 5:
                result["trend"] = "improving"
            elif delta < -5:
                result["trend"] = "declining"
            else:
                result["trend"] = "steady"
        return result

    def notes(self):
        return self._read_text(self.notes_path)

    def set_notes(self, text):
        with open(self.notes_path, "w", encoding="utf-8") as f:
            f.write((text or "").strip() + "\n")
        self.build_report()

    def prompt_context(self):
        """Compact text injected into the system prompt each reply."""
        parts = []
        notes = self.notes()
        if notes:
            parts.append("# Learned notes (from past feedback, apply these)\n" + notes)
        recent = self.recent(self.history_turns)
        if recent:
            lines = []
            for it in recent:
                q = (it.get("question") or "").strip().replace("\n", " ")
                a = (it.get("reply") or "").strip().replace("\n", " ")
                if len(a) > 220:
                    a = a[:220] + "..."
                mark = {"up": " [liked]", "down": " [disliked]"}.get(it.get("rating"), "")
                lines.append(f"- Earlier they asked: {q}\n  You replied{mark}: {a}")
            parts.append(
                "# Recent conversation memory (for continuity, do not repeat verbatim)\n"
                + "\n".join(lines)
            )
        return "\n\n".join(parts)

    def build_report(self):
        items = self._read_jsonl()
        stats = self.stats()
        notes = self.notes()
        lines = [
            "# Vikash Agent — Self-learning report",
            "",
            f"_Updated: {time.strftime('%Y-%m-%d %H:%M:%S')}_",
            "",
            "## Improvement signal",
            f"- Total exchanges logged: **{stats['total']}**",
            f"- Rated: {stats['rated']}  (👍 {stats['up']} / 👎 {stats['down']})",
            f"- Positive feedback: **{stats['positive_pct']}%**"
            if stats["positive_pct"] is not None
            else "- Positive feedback: n/a (rate some replies)",
            f"- Trend: **{stats['trend']}**"
            + (f" ({stats['trend_delta']:+} pts recent vs earlier)" if stats["trend_delta"] is not None else "")
            + "  (based on your 👍/👎 ratings, not an objective score)",
            "",
            "## Learned notes",
            notes or "_No notes yet — run a reflection to generate lessons._",
            "",
            "## Recent exchanges",
        ]
        for it in items[-15:]:
            mark = {"up": "👍", "down": "👎"}.get(it.get("rating"), "–")
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(it.get("ts", 0)))
            q = (it.get("question") or "").strip().replace("\n", " ")
            a = (it.get("reply") or "").strip().replace("\n", " ")
            lines.append(f"- {mark} [{ts}] **Q:** {q}")
            lines.append(f"  **A:** {a}")
        report = "\n".join(lines) + "\n"
        with open(self.report_path, "w", encoding="utf-8") as f:
            f.write(report)
        return report

    def report(self):
        return self._read_text(self.report_path) or self.build_report()
