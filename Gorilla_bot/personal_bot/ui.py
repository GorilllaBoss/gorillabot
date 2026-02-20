from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_AI = "🤖 GorillaAI"
BTN_ACCESS = "🔐 Премиум услуги"
BTN_AUTOPOST = "📣 Автопостинг"
BTN_CRYPTO = "📈 Крипто анализ"
BTN_ESOTERIC = "🪄 Глубокая эзотерика"
BTN_PSYCHOLOGY = "🧠 Психолог"
BTN_NAVIGATOR = "🧭 Тебе точно сюда"
BTN_MY = "🗂 Мои каналы"
BTN_GROUP = "🛡 Группы и права"
BTN_BACK = "⬅️ Назад"
BTN_PROJECTS = "📁 Мои проекты"
BTN_CREATE_PROJECT = "🚀 Создать проект"
BTN_PROJECT_WIZARD = "✨ Начать"
BTN_ACCOUNT = "⚙️ Аккаунт"

BTN_ADD_CHANNEL = "➕ Добавить канал"
BTN_MODE_INTERVAL = "⏱ Интервал"
BTN_MODE_FIXED = "🕒 Фикс-время"
BTN_MODE_RANDOM = "🎲 Рандом"


def main_menu(is_premium: bool = False) -> ReplyKeyboardMarkup:
    if not is_premium:
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=BTN_ACCESS)],
            ],
            resize_keyboard=True,
        )

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_AI), KeyboardButton(text=BTN_ACCESS)],
            [KeyboardButton(text=BTN_NAVIGATOR), KeyboardButton(text=BTN_PSYCHOLOGY)],
            [KeyboardButton(text=BTN_ESOTERIC), KeyboardButton(text=BTN_CRYPTO)],
            [KeyboardButton(text=BTN_CREATE_PROJECT)],
        ],
        resize_keyboard=True,
    )


def back_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_BACK)]],
        resize_keyboard=True,
    )


def project_hub_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_PROJECT_WIZARD)],
            [KeyboardButton(text=BTN_PROJECTS), KeyboardButton(text=BTN_AUTOPOST)],
            [KeyboardButton(text=BTN_GROUP)],
            [KeyboardButton(text=BTN_ACCOUNT)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def autopost_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ADD_CHANNEL), KeyboardButton(text=BTN_MY)],
            [KeyboardButton(text=BTN_MODE_INTERVAL), KeyboardButton(text=BTN_MODE_FIXED), KeyboardButton(text=BTN_MODE_RANDOM)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )
