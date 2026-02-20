import os
from pathlib import Path


def load_dotenv_file(path: Path) -> bool:
    if not path.exists():
        return False

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)
    return True


SCRIPT_DIR = Path(__file__).resolve().parent.parent
ENV_PATHS = [Path.cwd() / ".env", SCRIPT_DIR / ".env"]
LOADED_ENV_PATHS = [str(path) for path in ENV_PATHS if load_dotenv_file(path)]

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
ACCESS_CODE = os.getenv("BOT_ACCESS_CODE", "0000").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "").strip()
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "").strip()

DATA_FILE = "data/personal_bot_users.json"
os.makedirs("data", exist_ok=True)


def build_token_error() -> str:
    reasons = []
    if not BOT_TOKEN:
        reasons.append("переменная BOT_TOKEN пустая")
    elif ":" not in BOT_TOKEN:
        reasons.append("в токене нет символа ':'")
    elif "YOUR_TELEGRAM_BOT_TOKEN" in BOT_TOKEN:
        reasons.append("в BOT_TOKEN остался шаблон из .env.example")

    if not reasons:
        return ""

    env_info = "\n".join([f"- найден .env: {path}" for path in LOADED_ENV_PATHS])
    if not env_info:
        env_info = "- .env не найден (проверь, что файл лежит рядом со скриптом или в текущей папке запуска)"

    reason_info = "\n".join([f"- {reason}" for reason in reasons])
    return (
        "Ошибка запуска: BOT_TOKEN некорректный.\n"
        f"Причины:\n{reason_info}\n"
        "Что сделать:\n"
        "1) Открой .env и вставь реальный токен от @BotFather.\n"
        "2) Формат: BOT_TOKEN=123456789:AA...\n"
        "3) Перезапусти скрипт.\n"
        f"Проверка .env:\n{env_info}"
    )
