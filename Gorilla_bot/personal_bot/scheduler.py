import hashlib
import random
from datetime import datetime, timedelta


def ensure_channel_defaults(ch: dict):
    ch.setdefault("enabled", True)
    ch.setdefault("mode", "interval")
    ch.setdefault("interval_hours", 6)
    ch.setdefault("fixed_times", ["12:00"])
    ch.setdefault("random_window", {"start": 9, "end": 21, "posts_per_day": 2})
    ch.setdefault("next_run", (datetime.now() + timedelta(hours=1)).isoformat())
    ch.setdefault("last_plan_date", "")
    ch.setdefault("pending_today", [])
    ch.setdefault("history", [])
    ch.setdefault("sample_post", "")


def add_history_text(ch: dict, text: str):
    digest = hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()
    history = ch.get("history", [])
    history.append({"hash": digest, "text": text[:300], "time": datetime.now().isoformat()})
    ch["history"] = history[-80:]


def hash_exists(ch: dict, text: str) -> bool:
    digest = hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()
    return any(item.get("hash") == digest for item in ch.get("history", []))


def build_post_prompt(ch: dict) -> str:
    recent = "\n".join([f"- {h.get('text', '')}" for h in ch.get("history", [])[-10:]])
    if not recent:
        recent = "- пока нет"
    sample_post = (ch.get("sample_post") or "").strip()
    sample_block = ""
    if sample_post:
        sample_block = (
            "\nОриентир по стилю/оформлению (пример пользователя):\n"
            f"{sample_post}\n"
            "Сохрани похожую структуру, тон и подачу, но текст должен быть новым и уникальным.\n"
        )

    return (
        f"Тема канала: {ch['topic']}\n"
        "Сгенерируй пост для Telegram на русском языке.\n"
        "Требования: мощный заголовок, 1-2 смысловых блока, финальный CTA.\n"
        "До 900 символов, живой стиль, без воды.\n"
        f"{sample_block}"
        "Не повторяй эти тексты:\n"
        f"{recent}"
    )


def schedule_random_day(ch: dict, today: str):
    rw = ch.get("random_window", {})
    start = int(rw.get("start", 9))
    end = int(rw.get("end", 21))
    count = int(rw.get("posts_per_day", 2))
    start = max(0, min(23, start))
    end = max(start + 1, min(24, end))
    count = max(1, min(12, count))

    slots = set()
    while len(slots) < count:
        h = random.randint(start, end - 1)
        m = random.randint(0, 59)
        slots.add(f"{h:02d}:{m:02d}")

    ch["pending_today"] = sorted(slots)
    ch["last_plan_date"] = today


def is_due(ch: dict, now: datetime) -> bool:
    mode = ch.get("mode", "interval")
    now_str = now.strftime("%H:%M")
    today = now.date().isoformat()

    if mode == "interval":
        next_run = datetime.fromisoformat(ch.get("next_run"))
        return now >= next_run

    if mode == "fixed":
        times = ch.get("fixed_times", [])
        if ch.get("last_plan_date") != today:
            ch["pending_today"] = sorted(set(times))
            ch["last_plan_date"] = today
        return now_str in ch.get("pending_today", [])

    if mode == "random":
        if ch.get("last_plan_date") != today:
            schedule_random_day(ch, today)
        return now_str in ch.get("pending_today", [])

    return False


def mark_sent(ch: dict, now: datetime):
    mode = ch.get("mode", "interval")
    now_str = now.strftime("%H:%M")
    if mode == "interval":
        ch["next_run"] = (now + timedelta(hours=int(ch.get("interval_hours", 6)))).isoformat()
        return

    pending = ch.get("pending_today", [])
    ch["pending_today"] = [t for t in pending if t != now_str]
