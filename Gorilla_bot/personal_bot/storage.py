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
    return {
        "id": "",
        "channel": "",
        "topic": "",
        "style": "expert",
        "formatting": {"emojis": True, "cta": True, "hashtags": False, "signature": ""},
        "frequency": {"mode": "interval", "value": 6},
        "sources": ["gpt"],
        "permissions": {"admins": [], "editors": []},
        "enabled": False,
        "history": [],
        "created_at": datetime.now().isoformat(),
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
        }
        save_users(data_file, users)
    users[key].setdefault("group_permissions", default_group_permissions())
    users[key].setdefault("projects", [])
    users[key].setdefault("user_life_profile", default_life_profile())
    return users[key]


def set_user_record(data_file: str, user_id: int, record: dict):
    users = load_users(data_file)
    users[str(user_id)] = record
    save_users(data_file, users)


def user_has_premium(data_file: str, user_id: int) -> bool:
    return get_user_record(data_file, user_id).get("premium", False)
