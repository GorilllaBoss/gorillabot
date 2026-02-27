import json
import os
from datetime import datetime


def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def default_group_permissions() -> dict:
    return {
        "read": False,
        "write": False,
        "delete": False,
        "ban": False,
        "edit": False,
        "posts": True,
    }


def default_life_profile() -> dict:
    now = datetime.now().isoformat()
    return {
        "answers_json": [],
        "ai_analysis": "",
        "archetype": "",
        "goals": [],
        "daily_plan": "",
        "weekly_plan": "",
        "monthly_plan": "",
        "reminder_settings": {"mode": "off", "last_sent": ""},
        "history": [],
        "created_at": now,
        "last_update": now,
        "onboarding_topics": [],
        "update_answers": [],
    }


def default_project() -> dict:
    now = datetime.now().isoformat()
    return {
        "id": "",
        "project_id": "",
        "user_id": 0,
        "channel_username": "",
        "channel_id": "",
        "theme": "AI",
        "custom_theme": "",
        "post_style": "короткие посты",
        "posting_frequency": "1_post_day",
        "posting_time": "09:00",
        "content_sources": ["AI генерация"],
        "is_autopost_enabled": False,
        "example_posts": [],
        "scheduler_settings": {"daily_posts": 1, "weekly_mode": False, "random_mode": False, "timezone": "Europe/Moscow"},
        "enabled": False,
        "history": [],
        "created_at": now,
        "updated_at": now,
        # backward-compatible aliases
        "channel": "",
        "topic": "AI",
        "style": "short",
        "formatting": {"emojis": True, "cta": True, "hashtags": False, "signature": ""},
        "frequency": {"mode": "daily", "value": "09:00"},
        "sources": ["gpt"],
        "permissions": {"admins": [], "editors": []},
    }


def load_users(data_file: str):
    return load_json(data_file, {})


def save_users(data_file: str, data):
    save_json(data_file, data)


def get_user_record(data_file: str, user_id: int):
    users = load_users(data_file)
    key = str(user_id)
    if key not in users:
        users[key] = {
            "premium": False,
            "channels": [],
            "projects": [],
            "group_permissions": default_group_permissions(),
            "user_life_profile": default_life_profile(),
            "flow_memory": {},
        }
        save_users(data_file, users)
    users[key].setdefault("group_permissions", default_group_permissions())
    users[key].setdefault("projects", [])
    users[key].setdefault("user_life_profile", default_life_profile())
    users[key].setdefault("flow_memory", {})
    return users[key]


def set_user_record(data_file: str, user_id: int, record: dict):
    users = load_users(data_file)
    users[str(user_id)] = record
    save_users(data_file, users)


def user_has_premium(data_file: str, user_id: int) -> bool:
    return get_user_record(data_file, user_id).get("premium", False)
