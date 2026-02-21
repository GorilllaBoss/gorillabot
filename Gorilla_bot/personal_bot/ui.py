from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_AI = "🤖 AI Ассистент"
BTN_ACCESS = "🔐 Доступ по коду"
BTN_AUTOPOST = "📣 Автопостинг"
BTN_CRYPTO = "📈 Крипто анализ"
BTN_ESOTERIC = "🪄 Эзотерика"
BTN_PSYCHOLOGY = "🧠 Психология"
BTN_NAVIGATOR = "🧭 Тебе точно сюда"
BTN_LANGUAGES = "🌍 Изучение языков"
BTN_MY = "🗂 Мои каналы"
BTN_GROUP = "🛡 Группы и права"
BTN_BACK = "⬅️ Назад"

BTN_ADD_CHANNEL = "➕ Добавить канал"
BTN_MODE_INTERVAL = "⏱ Интервал"
BTN_MODE_FIXED = "🕒 Фикс-время"
BTN_MODE_RANDOM = "🎲 Рандом"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_AI), KeyboardButton(text=BTN_ACCESS)],
            [KeyboardButton(text=BTN_AUTOPOST), KeyboardButton(text=BTN_MY)],
            [KeyboardButton(text=BTN_GROUP)],
            [KeyboardButton(text=BTN_CRYPTO), KeyboardButton(text=BTN_PSYCHOLOGY)],
            [KeyboardButton(text=BTN_LANGUAGES)],
            [KeyboardButton(text=BTN_NAVIGATOR)],
            [KeyboardButton(text=BTN_ESOTERIC)],
        ],
        resize_keyboard=True,
    )


def back_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_BACK)]],
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
