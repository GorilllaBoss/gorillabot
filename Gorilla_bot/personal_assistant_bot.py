import asyncio
import random
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from openai import OpenAI

from personal_bot.config import (
    ACCESS_CODE,
    BOT_TOKEN,
    DATA_FILE,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    build_token_error,
)
from personal_bot.scheduler import (
    add_history_text,
    build_post_prompt,
    ensure_channel_defaults,
    hash_exists,
    is_due,
    mark_sent,
)
from personal_bot.services import ask_llm, fetch_crypto_snapshot
from personal_bot.states import (
    AccessCodeState,
    AssistantState,
    ChannelSetupState,
    CryptoState,
    EsotericState,
    LanguageState,
    NavigatorState,
    PsychologyState,
)
from personal_bot.storage import default_group_permissions, get_user_record, load_users, save_users, set_user_record, user_has_premium
from personal_bot.ui import (
    BTN_ACCESS,
    BTN_ADD_CHANNEL,
    BTN_AI,
    BTN_AUTOPOST,
    BTN_BACK,
    BTN_CRYPTO,
    BTN_ESOTERIC,
    BTN_GROUP,
    BTN_LANGUAGES,
    BTN_MODE_FIXED,
    BTN_MODE_INTERVAL,
    BTN_MODE_RANDOM,
    BTN_MY,
    BTN_NAVIGATOR,
    BTN_PSYCHOLOGY,
    autopost_menu_keyboard,
    back_menu,
    main_menu,
)

bot = None
dp = Dispatcher(storage=MemoryStorage())
dp.message.filter(F.chat.type == "private")
openai_client = OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")


async def run_llm_with_status(message: types.Message, statuses: list[str], llm_call):
    status_message = await message.answer(random.choice(statuses))
    task = asyncio.create_task(asyncio.to_thread(llm_call))

    while not task.done():
        await asyncio.sleep(2.2)
        if task.done():
            break
        next_text = random.choice(statuses)
        try:
            await status_message.edit_text(next_text)
        except Exception:
            pass

    answer = await task
    try:
        await status_message.delete()
    except Exception:
        pass
    return answer


def mode_alias_to_key(text: str) -> str | None:
    normalized = (text or "").strip().lower()
    mapping = {
        "интервал": "interval",
        "по интервалу": "interval",
        "⏱ интервал": "interval",
        "фикс": "fixed",
        "фикс время": "fixed",
        "фикс-время": "fixed",
        "🕒 фикс-время": "fixed",
        "рандом": "random",
        "рандомные": "random",
        "случайные": "random",
        "🎲 рандом": "random",
    }
    return mapping.get(normalized)


async def ask_mode_questions(message: types.Message, state: FSMContext, mode: str):
    await state.update_data(selected_mode=mode)
    if mode == "interval":
        await state.set_state(ChannelSetupState.waiting_interval)
        await message.answer("⏱ Введи интервал в часах (например 6):")
    elif mode == "fixed":
        await state.set_state(ChannelSetupState.waiting_fixed_times)
        await message.answer("🕒 Введи список времени через запятую, например: 09:00, 14:30, 21:10")
    else:
        await state.set_state(ChannelSetupState.waiting_random_window)
        await message.answer("🎲 Введи диапазон и количество: start,end,count (пример: 9,21,3)")


def group_permissions_kb(perms: dict) -> InlineKeyboardMarkup:
    def mark(val: bool) -> str:
        return "✅" if val else "❌"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{mark(perms.get('write'))} Писать", callback_data="gp:write")],
            [InlineKeyboardButton(text=f"{mark(perms.get('edit'))} Редактировать", callback_data="gp:edit")],
            [InlineKeyboardButton(text=f"{mark(perms.get('delete'))} Удалять", callback_data="gp:delete")],
            [InlineKeyboardButton(text=f"{mark(perms.get('ban'))} Банить", callback_data="gp:ban")],
            [InlineKeyboardButton(text=f"{mark(perms.get('posts'))} Автопостинг", callback_data="gp:posts")],
        ]
    )


def status_for_section(section: str) -> list[str]:
    mapping = {
        "assistant": [
            "🤔 Думаю...",
            "🧠 Собираю мысли...",
            "📚 Поднимаю знания...",
            "🛠️ Формирую полезный ответ...",
            "✨ Упаковываю красиво...",
            "✅ Почти готово...",
        ],
        "ask": [
            "🔎 Ищу лучший вариант...",
            "🧩 Склеиваю логику...",
            "🧠 Проверяю факты...",
            "✍️ Формулирую ответ...",
            "✨ Полирую подачу...",
            "✅ Ещё секунда...",
        ],
        "crypto": [
            "📈 Ищу голову и плечи...",
            "📊 Сверяю объёмы...",
            "🧮 Считаю динамику...",
            "🕵️ Проверяю рыночный фон...",
            "⚖️ Оцениваю риски...",
            "✨ Собираю вывод...",
            "✅ Почти готово...",
        ],
        "psychology": [
            "🧠 Настраиваюсь на диалог...",
            "💬 Подбираю бережные формулировки...",
            "📌 Ищу корень запроса...",
            "🌿 Готовлю поддерживающий ответ...",
            "🫶 Делаю рекомендации практичными...",
            "✨ Полирую тон общения...",
            "✅ Почти готово...",
        ],
        "esoteric": [
            "🔮 Настраиваю интуитивный канал...",
            "🪬 Считываю символические связи...",
            "📜 Анализирую выбранную систему...",
            "🧭 Ищу практичные ориентиры...",
            "✨ Собираю красивый разбор...",
            "🌙 Проверяю энергетический фон...",
            "✅ Почти готово...",
        ],
        "navigator": [
            "🧭 Сканирую вектор развития...",
            "🧠 Анализирую твой стиль мышления...",
            "🎯 Уточняю глубинные цели...",
            "🔍 Ищу ключевые блоки и страхи...",
            "🛠️ Собираю персональную карту...",
            "✨ Формирую конкретные шаги...",
            "✅ Почти готово...",
        ],
    }
    return mapping[section]


PSYCHOLOGY_PROMPT = """
Ты опытный, универсальный и этичный психолог-консультант.
Твоя задача: поддержать человека, помочь структурировать мысли и предложить практичные шаги.

Правила:
- Пиши тепло, бережно и без осуждения.
- Не ставь диагнозы и не назначай лечение.
- Объясняй простым языком.
- Давай конкретные техники самопомощи (1-3 упражнения), если уместно.
- Если есть признаки острого кризиса/самоповреждения — мягко советуй обратиться за срочной профессиональной помощью.

Формат:
- Короткое эмпатичное вступление.
- Анализ ситуации по пунктам.
- Практический план на ближайшие 24-72 часа.
"""


ESOTERIC_SYSTEMS = {
    "1": ("Таро", "Ты эксперт по Таро. Дай символический, психологичный и практичный разбор запроса через архетипы карт."),
    "2": ("Оракулы", "Ты эксперт по оракулам. Дай мягкий интуитивный разбор и практический совет."),
    "3": ("Руны", "Ты эксперт по рунам. Интерпретируй символы рун и дай прикладной вывод."),
    "4": ("И-цзин", "Ты эксперт по И-цзин. Дай структурный разбор через логику перемен и действий."),
    "5": ("Кофейная гуща / восковые отливки / маятник", "Ты эксперт по интуитивным методам гадания. Дай аккуратную трактовку и рекомендации."),
    "6": ("Западная астрология", "Ты эксперт по западной астрологии: натальная карта, транзиты, совместимость."),
    "7": ("Ведическая астрология (Джйотиш)", "Ты эксперт по Джйотиш. Дай разбор кармических акцентов и практических шагов."),
    "8": ("Китайская астрология", "Ты эксперт по китайской астрологии: животные года, элементы, циклы."),
    "9": ("Лунная астрология", "Ты эксперт по лунным циклам и их влиянию на решения и состояния."),
    "10": ("Классическая нумерология (Пифагор)", "Ты эксперт по пифагорейской нумерологии: число судьбы и личные циклы."),
    "11": ("Каббалистическая нумерология", "Ты эксперт по каббалистической нумерологии: буквы, числа, смыслы."),
    "12": ("Матрица судьбы (22 аркана)", "Ты эксперт по матрице судьбы 22 аркана. Дай разбор сильных и слабых сторон."),
    "13": ("Human Design", "Ты эксперт по Human Design. Объясни тип, стратегию, авторитет простым языком."),
    "14": ("Соционика", "Ты эксперт по соционике. Дай типологический разбор и рекомендации по коммуникации."),
    "15": ("MBTI", "Ты эксперт по MBTI. Дай структурный разбор типа и практичные советы."),
    "16": ("Эннеаграмма", "Ты эксперт по эннеаграмме. Опиши мотивации, триггеры и зоны роста."),
    "17": ("Чакровая система", "Ты эксперт по чакровой системе. Дай диагностику баланса и практики гармонизации."),
    "18": ("Рейки", "Ты эксперт по Рейки. Дай мягкие рекомендации по энергетическому восстановлению."),
    "19": ("Кармическая диагностика", "Ты эксперт по кармической диагностике. Дай бережный разбор уроков и векторов."),
    "20": ("Хиромантия", "Ты эксперт по хиромантии. Дай символический разбор линий и практичные выводы."),
    "21": ("Физиогномика", "Ты эксперт по физиогномике. Дай аккуратный и этичный разбор характера по чертам."),
    "22": ("Фэншуй", "Ты эксперт по фэншуй. Предложи практичные шаги по гармонизации пространства."),
    "23": ("Ба-цзы", "Ты эксперт по Ба-цзы. Дай разбор судьбы по дате и элементам."),
    "24": ("Цигун", "Ты эксперт по Цигун. Подбери безопасные энергетические практики для старта."),
}


def esoteric_catalog_text() -> str:
    groups = [
        "🪄 Гадательные и эзотерические системы\n"
        "1) Таро\n2) Оракулы\n3) Руны\n4) И-цзин\n5) Кофейная гуща / восковые отливки / маятник",
        "⭐ Астрологические системы\n"
        "6) Западная астрология\n7) Ведическая астрология (Джйотиш)\n8) Китайская астрология\n9) Лунная астрология",
        "🔢 Нумерологические направления\n"
        "10) Классическая нумерология\n11) Каббалистическая нумерология\n12) Матрица судьбы (22 аркана)",
        "🧠 Психо-типологии\n"
        "13) Human Design\n14) Соционика\n15) MBTI\n16) Эннеаграмма",
        "🧿 Энергетические и духовные системы\n"
        "17) Чакровая система\n18) Рейки\n19) Кармическая диагностика\n20) Хиромантия\n21) Физиогномика",
        "🌏 Восточные практики\n22) Фэншуй\n23) Ба-цзы\n24) Цигун",
    ]
    return "\n\n".join(groups)


NAVIGATOR_PROMPT = """
ROLE:
Ты AI Life Navigator.
Ты живой собеседник, интервьюер, лайф-коуч и аналитик личности.

ЦЕЛЬ:
- Понять ценности, сильные стороны, страхи, мотивацию, мышление, цели.
- Вести уникальный диалог (не повторяй одинаковые вопросы).
- Минимум 7 и максимум 15 вопросов.

ПОВЕДЕНИЕ:
- Анализируй answers_json + insights + ai_analysis + последний ответ.
- На каждом шаге сам решай: уточнить, сменить тему, упростить вопрос или завершить сбор.
- Если ответ короткий/"не знаю"/"сложно" — упрости вопрос и дай 2-3 коротких примера ответов (до 5 слов каждый).
- Если ответ эмоциональный или про мечту/страх — копай глубже follow-up вопросом.
- Каждые 3 вопроса давай короткую поддержку: "Ты хорошо раскрываешься 👍" или "Спасибо за честность."

STOP CONDITION:
Когда данных достаточно, не задавай новый вопрос.
Напиши фразу: "Спасибо. Я понял тебя. Сейчас соберу твою карту развития."

АНАЛИЗ ПОСЛЕ STOP:
1) Архетип личности (1)
2) Сильные стороны (5)
3) Ограничения (3)
4) Основные ценности
5) Подходящие направления
6) План на 3 месяца
7) daily_action (1 действие)
8) weekly_focus (3 рекомендации)
9) monthly_focus (1 приоритет)

СТИЛЬ:
- Коротко, конкретно, без воды.
- Дружелюбно и умно, без заумных слов.
- Без эзотерики и философских монологов.
"""


LANGUAGE_LEARNING_CONTENT = {
    "english": {
        "title": "🇬🇧 English",
        "greeting": "Hello! How are you?",
        "greeting_ru": "Привет! Как дела?",
        "words": [
            ("today", "сегодня"),
            ("goal", "цель"),
            ("practice", "практика"),
            ("travel", "путешествие"),
            ("friend", "друг"),
        ],
        "quiz": {
            "question": "Как будет «цель» по-английски?",
            "answer": "goal",
            "hint": "Начинается на g",
        },
    },
    "spanish": {
        "title": "🇪🇸 Español",
        "greeting": "¡Hola! ¿Cómo estás?",
        "greeting_ru": "Привет! Как ты?",
        "words": [("gracias", "спасибо"), ("amigo", "друг"), ("viaje", "путешествие"), ("meta", "цель"), ("hoy", "сегодня")],
        "quiz": {"question": "Как будет «спасибо» по-испански?", "answer": "gracias", "hint": "Слово начинается на g"},
    },
    "french": {
        "title": "🇫🇷 Français",
        "greeting": "Salut! Comment ça va?",
        "greeting_ru": "Привет! Как дела?",
        "words": [("bonjour", "добрый день"), ("objectif", "цель"), ("ami", "друг"), ("voyage", "путешествие"), ("aujourd'hui", "сегодня")],
        "quiz": {"question": "Как по-французски «друг»?", "answer": "ami", "hint": "Короткое слово из 3 букв"},
    },
    "german": {
        "title": "🇩🇪 Deutsch",
        "greeting": "Hallo! Wie geht's?",
        "greeting_ru": "Привет! Как дела?",
        "words": [("danke", "спасибо"), ("ziel", "цель"), ("freund", "друг"), ("reise", "путешествие"), ("heute", "сегодня")],
        "quiz": {"question": "Как будет «спасибо» по-немецки?", "answer": "danke", "hint": "Начинается на d"},
    },
    "italian": {
        "title": "🇮🇹 Italiano",
        "greeting": "Ciao! Come stai?",
        "greeting_ru": "Привет! Как дела?",
        "words": [("grazie", "спасибо"), ("obiettivo", "цель"), ("amico", "друг"), ("viaggio", "путешествие"), ("oggi", "сегодня")],
        "quiz": {"question": "Как по-итальянски «друг»?", "answer": "amico", "hint": "Начинается на a"},
    },
    "portuguese": {
        "title": "🇵🇹 Português",
        "greeting": "Olá! Tudo bem?",
        "greeting_ru": "Привет! Всё хорошо?",
        "words": [("obrigado", "спасибо"), ("meta", "цель"), ("amigo", "друг"), ("viagem", "путешествие"), ("hoje", "сегодня")],
        "quiz": {"question": "Как по-португальски «сегодня»?", "answer": "hoje", "hint": "Начинается на h"},
    },
    "chinese": {
        "title": "🇨🇳 中文 (Mandarin)",
        "greeting": "你好！你好吗？ (Nǐ hǎo! Nǐ hǎo ma?)",
        "greeting_ru": "Привет! Как ты?",
        "words": [("谢谢 (xièxie)", "спасибо"), ("朋友 (péngyou)", "друг"), ("目标 (mùbiāo)", "цель"), ("今天 (jīntiān)", "сегодня"), ("旅行 (lǚxíng)", "путешествие")],
        "quiz": {"question": "Как по-китайски «спасибо» (пиньинь)?", "answer": "xiexie", "hint": "Звук «сье-сье»"},
    },
    "japanese": {
        "title": "🇯🇵 日本語",
        "greeting": "こんにちは！お元気ですか？",
        "greeting_ru": "Привет! Как дела?",
        "words": [("ありがとう (arigatou)", "спасибо"), ("友達 (tomodachi)", "друг"), ("目標 (mokuhyou)", "цель"), ("今日 (kyou)", "сегодня"), ("旅行 (ryokou)", "путешествие")],
        "quiz": {"question": "Как по-японски «друг» (ромадзи)?", "answer": "tomodachi", "hint": "Начинается на t"},
    },
    "korean": {
        "title": "🇰🇷 한국어",
        "greeting": "안녕하세요! 어떻게 지내요?",
        "greeting_ru": "Здравствуйте! Как поживаете?",
        "words": [("감사합니다 (gamsahamnida)", "спасибо"), ("친구 (chingu)", "друг"), ("목표 (mokpyo)", "цель"), ("오늘 (oneul)", "сегодня"), ("여행 (yeohaeng)", "путешествие")],
        "quiz": {"question": "Как по-корейски «друг» (латиницей)?", "answer": "chingu", "hint": "Слово начинается на ch"},
    },
    "arabic": {
        "title": "🇸🇦 العربية",
        "greeting": "مرحبًا! كيف حالك؟ (Marhaban! Kayfa haluk?)",
        "greeting_ru": "Привет! Как дела?",
        "words": [("شكرا (shukran)", "спасибо"), ("صديق (sadiq)", "друг"), ("هدف (hadaf)", "цель"), ("اليوم (alyawm)", "сегодня"), ("سفر (safar)", "путешествие")],
        "quiz": {"question": "Как по-арабски «спасибо» (латиницей)?", "answer": "shukran", "hint": "Начинается на sh"},
    },
}


def language_catalog_text() -> str:
    lines = ["🌍 Топ-10 языков для изучения:"]
    for idx, data in enumerate(LANGUAGE_LEARNING_CONTENT.values(), 1):
        lines.append(f"{idx}) {data['title']}")
    return "\n".join(lines)


def normalize_answer(text: str) -> str:
    cleaned = (text or "").strip().lower()
    return cleaned.replace("ё", "е").replace(" ", "")


def build_language_lesson(language_key: str) -> str:
    data = LANGUAGE_LEARNING_CONTENT[language_key]
    words = "\n".join([f"• {word} — {translation}" for word, translation in data["words"]])
    return (
        f"{data['title']}\n\n"
        f"Фраза дня: {data['greeting']}\n"
        f"Перевод: {data['greeting_ru']}\n\n"
        f"Мини-словарь:\n{words}\n\n"
        "Дальше выбери режим:\n"
        "1) lesson — еще мини-урок\n"
        "2) quiz — мини-тест"
    )



async def ensure_premium(message: types.Message) -> bool:
    if user_has_premium(DATA_FILE, message.from_user.id):
        return True
    await message.answer("🔐 Эта функция доступна только по коду. Нажми «🔐 Доступ по коду»", reply_markup=main_menu())
    return False


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "🚀 Добро пожаловать в личный AI-бот!\n\n"
        "Выбери раздел в меню ниже 👇\n"
        "• 🤖 AI ассистент (для всех)\n"
        "• 🌍 Изучение языков (10 популярных)\n"
        "• 🔐 Премиум функции по коду\n"
        "• 📣 Автопостинг с гибким расписанием\n"
        "• 📈 Крипто, 🧠 Психология и 🪄 Эзотерика",
        reply_markup=main_menu(),
    )


@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    await message.answer("🏠 Главное меню", reply_markup=main_menu())


@dp.message(F.text == BTN_BACK)
async def back_to_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("⬅️ Возврат в главное меню", reply_markup=main_menu())


@dp.message(F.text == BTN_ACCESS)
@dp.message(Command("access"))
async def cmd_access(message: types.Message, state: FSMContext):
    await state.set_state(AccessCodeState.waiting_code)
    await message.answer("🔑 Введи код доступа для приватных функций:", reply_markup=back_menu())


@dp.message(AccessCodeState.waiting_code)
async def process_access_code(message: types.Message, state: FSMContext):
    if message.text.strip() == ACCESS_CODE:
        record = get_user_record(DATA_FILE, message.from_user.id)
        record["premium"] = True
        set_user_record(DATA_FILE, message.from_user.id, record)
        await message.answer("✅ Доступ открыт! Премиум-функции активированы 🎉", reply_markup=main_menu())
    else:
        await message.answer("❌ Неверный код. Попробуй ещё раз или нажми «⬅️ Назад».", reply_markup=back_menu())
        return
    await state.clear()


@dp.message(F.text == BTN_AI)
async def assistant_menu(message: types.Message, state: FSMContext):
    await state.set_state(AssistantState.waiting_question)
    await message.answer(
        "🤖 *AI Ассистент*\n\n"
        "Что умеет:\n"
        "• отвечает на любые вопросы\n"
        "• объясняет сложные темы простым языком\n"
        "• помогает с идеями, текстами, планами\n\n"
        "✍️ Просто напиши свой вопрос следующим сообщением.",
        parse_mode="Markdown",
        reply_markup=back_menu(),
    )


@dp.message(AssistantState.waiting_question)
async def assistant_question(message: types.Message):
    q = (message.text or "").strip()
    if not q:
        await message.answer("⚠️ Напиши текстовый вопрос.")
        return
    answer = await run_llm_with_status(
        message,
        status_for_section("assistant"),
        lambda: ask_llm(
            openai_client,
            OPENROUTER_MODEL,
            OPENROUTER_API_KEY,
            "Ты полезный универсальный AI ассистент Telegram. Отвечай ясно, структурно и по делу.",
            q,
            max_tokens=700,
        ),
    )
    await message.answer(f"🤖 {answer}")


@dp.message(Command("ask"))
async def cmd_ask(message: types.Message):
    question = (message.text or "").replace("/ask", "", 1).strip()
    if not question:
        await message.answer("⚠️ Использование: /ask <вопрос>")
        return
    answer = await run_llm_with_status(
        message,
        status_for_section("ask"),
        lambda: ask_llm(openai_client, OPENROUTER_MODEL, OPENROUTER_API_KEY, "Ты полезный универсальный AI ассистент Telegram.", question),
    )
    await message.answer(f"🤖 {answer}")


@dp.message(F.text == BTN_AUTOPOST)
async def autopost_menu(message: types.Message):
    if not await ensure_premium(message):
        return

    await message.answer(
        "📣 *Автопостинг*\n\n"
        "Здесь ты можешь настроить публикации в свой канал:\n"
        "✅ Режим по интервалу (каждые N часов)\n"
        "✅ Режим по фиксированному времени (например 09:00, 18:30)\n"
        "✅ Режим рандомных постов в заданном диапазоне\n"
        "✅ Посты генерируются ИИ и не повторяются\n"
        "✅ Можно задать пример поста — бот будет держать похожий стиль",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
    await message.answer(
        "👇 Выбери действие кнопкой: добавить канал или сразу режим настройки.",
        reply_markup=autopost_menu_keyboard(),
    )




@dp.message(F.text == BTN_ADD_CHANNEL)
async def add_channel_button(message: types.Message, state: FSMContext):
    if not await ensure_premium(message):
        return
    await start_add_channel_flow(message, state)


@dp.message(F.text.in_([BTN_MODE_INTERVAL, BTN_MODE_FIXED, BTN_MODE_RANDOM]))
async def add_channel_mode_shortcut(message: types.Message, state: FSMContext):
    if not await ensure_premium(message):
        return

    selected_mode = {
        BTN_MODE_INTERVAL: "interval",
        BTN_MODE_FIXED: "fixed",
        BTN_MODE_RANDOM: "random",
    }[message.text]
    await start_add_channel_flow(message, state)
    await state.update_data(forced_mode=selected_mode)
    await message.answer("⚙️ Режим выбран заранее. Продолжим настройку канала 👇")


@dp.message(F.text.regexp(r"(?i)^(интервал|по интервалу|рандом|рандомные|фикс|фикс время|фикс-время)$"))
async def add_channel_mode_text_alias(message: types.Message, state: FSMContext):
    mode = mode_alias_to_key(message.text)
    if not mode:
        return
    if not await ensure_premium(message):
        return
    await start_add_channel_flow(message, state)
    await state.update_data(forced_mode=mode)
    await message.answer("🧭 Принял режим из текста. Дальше заполним канал.")

@dp.message(Command("add_channel"))
async def add_channel_command(message: types.Message, state: FSMContext):
    if not await ensure_premium(message):
        return
    await start_add_channel_flow(message, state)


async def start_add_channel_flow(message: types.Message, state: FSMContext):
    await state.set_state(ChannelSetupState.waiting_name)
    await message.answer("➕ Введи название канала (произвольное):", reply_markup=back_menu())


@dp.message(ChannelSetupState.waiting_name)
async def process_channel_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(ChannelSetupState.waiting_chat_id)
    await message.answer("🆔 Теперь отправь chat_id канала (пример: -1001234567890):")


@dp.message(ChannelSetupState.waiting_chat_id)
async def process_channel_chat_id(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text.startswith("-100"):
        await message.answer("⚠️ Это не похоже на chat_id канала. Формат: -100...")
        return
    await state.update_data(chat_id=text)
    await state.set_state(ChannelSetupState.waiting_topic)
    await message.answer("🧠 Тема канала для постинга (например: крипта, бизнес, новости):")


@dp.message(ChannelSetupState.waiting_topic)
async def process_channel_topic(message: types.Message, state: FSMContext):
    await state.update_data(topic=message.text.strip())
    await state.set_state(ChannelSetupState.waiting_sample)
    await message.answer(
        "🧩 Пришли пример поста (образец стиля), и будущие посты будут похожи по оформлению и подаче.\n"
        "Если без примера — отправь: -"
    )


@dp.message(ChannelSetupState.waiting_sample)
async def process_channel_sample(message: types.Message, state: FSMContext):
    sample_text = (message.text or "").strip()
    if sample_text == "-":
        sample_text = ""
    await state.update_data(sample_post=sample_text)

    data = await state.get_data()
    forced_mode = data.get("forced_mode")
    if forced_mode:
        await ask_mode_questions(message, state, forced_mode)
        return

    await state.set_state(ChannelSetupState.waiting_mode)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏱ Интервал", callback_data="pick_mode_interval")],
            [InlineKeyboardButton(text="🕒 Фикс время", callback_data="pick_mode_fixed")],
            [InlineKeyboardButton(text="🎲 Рандом", callback_data="pick_mode_random")],
        ]
    )
    await message.answer("⚙️ Выбери режим автопостинга:", reply_markup=kb)


@dp.callback_query(F.data.startswith("pick_mode_"))
async def pick_mode(callback: types.CallbackQuery, state: FSMContext):
    mode = callback.data.replace("pick_mode_", "")

    await ask_mode_questions(callback.message, state, mode)
    await callback.answer()


@dp.message(ChannelSetupState.waiting_interval)
async def process_interval(message: types.Message, state: FSMContext):
    try:
        interval = int((message.text or "").strip())
        if interval < 1:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Интервал должен быть целым числом >= 1")
        return

    await save_channel_from_state(message, state, mode="interval", interval_hours=interval)


@dp.message(ChannelSetupState.waiting_fixed_times)
async def process_fixed_times(message: types.Message, state: FSMContext):
    times = [x.strip() for x in (message.text or "").split(",") if x.strip()]
    valid = []
    for t in times:
        try:
            datetime.strptime(t, "%H:%M")
            valid.append(t)
        except ValueError:
            pass
    if not valid:
        await message.answer("⚠️ Нужен формат HH:MM, например: 08:30, 19:45")
        return

    await save_channel_from_state(message, state, mode="fixed", fixed_times=sorted(set(valid)))


@dp.message(ChannelSetupState.waiting_random_window)
async def process_random_window(message: types.Message, state: FSMContext):
    try:
        start, end, count = [int(x.strip()) for x in (message.text or "").split(",")]
        if start < 0 or start > 23 or end < 1 or end > 24 or end <= start or count < 1:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Формат: start,end,count. Пример: 9,21,3")
        return

    await save_channel_from_state(
        message,
        state,
        mode="random",
        random_window={"start": start, "end": end, "posts_per_day": min(count, 12)},
    )


async def save_channel_from_state(message: types.Message, state: FSMContext, **kwargs):
    data = await state.get_data()
    record = get_user_record(DATA_FILE, message.from_user.id)

    channel = {
        "name": data["name"],
        "chat_id": int(data["chat_id"]),
        "topic": data["topic"],
        "enabled": True,
        "mode": kwargs.get("mode", "interval"),
        "interval_hours": kwargs.get("interval_hours", 6),
        "fixed_times": kwargs.get("fixed_times", ["12:00"]),
        "random_window": kwargs.get("random_window", {"start": 9, "end": 21, "posts_per_day": 2}),
        "next_run": (datetime.now() + timedelta(minutes=2)).isoformat(),
        "last_plan_date": "",
        "pending_today": [],
        "history": [],
        "sample_post": data.get("sample_post", ""),
    }
    record["channels"].append(channel)
    set_user_record(DATA_FILE, message.from_user.id, record)
    await state.clear()

    await message.answer(f"✅ Канал добавлен! 📌 {channel['name']} | 🧠 {channel['topic']}", reply_markup=main_menu())


@dp.message(F.text == BTN_MY)
@dp.message(Command("my_channels"))
async def my_channels(message: types.Message):
    if not await ensure_premium(message):
        return

    record = get_user_record(DATA_FILE, message.from_user.id)
    channels = record.get("channels", [])
    if not channels:
        await message.answer("🗂 Каналов пока нет. Добавь через /add_channel", reply_markup=main_menu())
        return

    lines = ["🗂 *Твои каналы:*\n"]
    for idx, ch in enumerate(channels, start=1):
        ensure_channel_defaults(ch)
        if ch["mode"] == "interval":
            mode_label = f"⏱ {ch['interval_hours']}ч"
        elif ch["mode"] == "fixed":
            mode_label = f"🕒 {', '.join(ch.get('fixed_times', []))}"
        else:
            rw = ch.get("random_window", {})
            mode_label = f"🎲 {rw.get('start', 9)}-{rw.get('end', 21)}, {rw.get('posts_per_day', 2)}/день"

        lines.append(
            f"{idx}. 📣 {ch['name']}\n   🆔 {ch['chat_id']}\n   🧠 {ch['topic']}\n   ⚙️ {mode_label}\n"
            f"   🧩 Пример: {'есть' if (ch.get('sample_post') or '').strip() else 'нет'}\n"
            f"   {'✅ Включен' if ch.get('enabled') else '⛔ Выключен'}"
        )
    set_user_record(DATA_FILE, message.from_user.id, record)
    await message.answer("\n\n".join(lines), parse_mode="Markdown", reply_markup=main_menu())


@dp.message(F.text == BTN_GROUP)
async def group_permissions_menu(message: types.Message):
    if not await ensure_premium(message):
        return

    record = get_user_record(DATA_FILE, message.from_user.id)
    perms = record.get("group_permissions") or default_group_permissions()
    record["group_permissions"] = perms
    set_user_record(DATA_FILE, message.from_user.id, record)

    await message.answer(
        "🛡 Настройки поведения бота в группах\n\n"
        "Сейчас бот в группах не отвечает на чужие сообщения и не вмешивается в диалоги.\n"
        "Здесь ты можешь заранее включать/выключать допустимые действия.",
        reply_markup=main_menu(),
    )
    await message.answer("Выбери права для групп 👇", reply_markup=group_permissions_kb(perms))


@dp.callback_query(F.data.startswith("gp:"))
async def toggle_group_permission(callback: types.CallbackQuery):
    key = callback.data.split(":", 1)[1]
    if key not in {"write", "edit", "delete", "ban", "posts"}:
        await callback.answer("Неизвестная настройка", show_alert=True)
        return

    record = get_user_record(DATA_FILE, callback.from_user.id)
    perms = record.get("group_permissions") or default_group_permissions()
    perms[key] = not perms.get(key, False)
    record["group_permissions"] = perms
    set_user_record(DATA_FILE, callback.from_user.id, record)

    await callback.message.edit_text("🛡 Права в группах обновлены. Выбери дальше:", reply_markup=group_permissions_kb(perms))
    await callback.answer("Готово")



@dp.message(F.text == BTN_CRYPTO)
async def crypto_menu(message: types.Message, state: FSMContext):
    if not await ensure_premium(message):
        return
    await state.set_state(CryptoState.waiting_coin)
    await message.answer("📈 Введи coin id (bitcoin, ethereum, solana)", reply_markup=back_menu())


@dp.message(CryptoState.waiting_coin)
async def crypto_run(message: types.Message):
    coin = (message.text or "").strip().lower()
    if not coin:
        await message.answer("⚠️ Введи coin id, например: bitcoin")
        return

    try:
        snap = fetch_crypto_snapshot(coin)
        if not snap:
            await message.answer("❌ Монета не найдена. Попробуй: bitcoin / ethereum / solana")
            return

        prompt = (
            f"Монета: {coin}\nЦена USD: {snap.get('usd')}\n24h %: {snap.get('usd_24h_change')}\n"
            f"Market Cap: {snap.get('usd_market_cap')}\n24h Volume: {snap.get('usd_24h_vol')}\n"
            "Сделай понятный анализ: тренд, риски, нейтральный вывод."
        )
        answer = await run_llm_with_status(
            message,
            status_for_section("crypto"),
            lambda: ask_llm(openai_client, OPENROUTER_MODEL, OPENROUTER_API_KEY, "Ты аккуратный крипто-аналитик.", prompt, max_tokens=450),
        )
        await message.answer(f"📊 Анализ по {coin}\n\n{answer}")
    except Exception as e:
        await message.answer(f"⚠️ Ошибка анализа: {e}")




@dp.message(F.text == BTN_PSYCHOLOGY)
async def psychology_menu(message: types.Message, state: FSMContext):
    if not await ensure_premium(message):
        return
    await state.set_state(PsychologyState.waiting_mode)

    record = get_user_record(DATA_FILE, message.from_user.id)
    contact = (record.get("psychologist_contact") or "не указан").strip() or "не указан"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧠 ИИ-психолог", callback_data="psy:ai")],
            [InlineKeyboardButton(text="📞 Психолог онлайн (контакты)", callback_data="psy:contact")],
        ]
    )
    await message.answer(
        "🧠 Раздел Психология\n\n"
        "Выбери формат:\n"
        "• ИИ-психолог — поддержка и разбор ситуации\n"
        "• Психолог онлайн — контакт реального специалиста\n\n"
        f"Текущий контакт: {contact}",
        reply_markup=kb,
    )


@dp.callback_query(F.data.startswith("psy:"))
async def psychology_choice(callback: types.CallbackQuery, state: FSMContext):
    mode = callback.data.split(":", 1)[1]
    if mode == "ai":
        await state.set_state(PsychologyState.waiting_question)
        await callback.message.answer("🫶 Напиши, что тебя беспокоит. Я отвечу как бережный ИИ-психолог.")
    else:
        await state.set_state(PsychologyState.waiting_contact)
        await callback.message.answer("📞 Пришли контакт реального психолога (телефон/telegram/сайт).")
    await callback.answer()


@dp.message(PsychologyState.waiting_contact)
async def psychology_save_contact(message: types.Message, state: FSMContext):
    contact = (message.text or "").strip()
    if not contact:
        await message.answer("⚠️ Контакт пустой. Отправь телефон/telegram/сайт.")
        return

    record = get_user_record(DATA_FILE, message.from_user.id)
    record["psychologist_contact"] = contact
    set_user_record(DATA_FILE, message.from_user.id, record)
    await state.clear()
    await message.answer(f"✅ Контакт сохранен: {contact}", reply_markup=main_menu())


@dp.message(PsychologyState.waiting_question)
async def psychology_ai_run(message: types.Message):
    user_text = (message.text or "").strip()
    if not user_text:
        await message.answer("⚠️ Напиши сообщение для ИИ-психолога.")
        return

    answer = await run_llm_with_status(
        message,
        status_for_section("psychology"),
        lambda: ask_llm(
            openai_client,
            OPENROUTER_MODEL,
            OPENROUTER_API_KEY,
            PSYCHOLOGY_PROMPT,
            user_text,
            max_tokens=800,
        ),
    )
    await message.answer(f"🧠 {answer}")


@dp.message(F.text == BTN_LANGUAGES)
async def languages_menu(message: types.Message, state: FSMContext):
    await state.set_state(LanguageState.waiting_language)
    await message.answer(
        "🌍 Режим изучения языков\n\n"
        "Я помогу учить 10 самых популярных языков:"
        " мини-уроки + мини-квиз.\n\n"
        f"{language_catalog_text()}\n\n"
        "Отправь номер языка (1-10).",
        reply_markup=back_menu(),
    )


@dp.message(LanguageState.waiting_language)
async def languages_choose(message: types.Message, state: FSMContext):
    raw = (message.text or "").strip()
    if not raw.isdigit() or not (1 <= int(raw) <= 10):
        await message.answer("⚠️ Введи номер языка от 1 до 10.")
        return

    key = list(LANGUAGE_LEARNING_CONTENT.keys())[int(raw) - 1]
    await state.update_data(language_key=key)
    await state.set_state(LanguageState.waiting_mode)
    await message.answer(build_language_lesson(key))


@dp.message(LanguageState.waiting_mode)
async def languages_mode(message: types.Message, state: FSMContext):
    mode = (message.text or "").strip().lower()
    data = await state.get_data()
    language_key = data.get("language_key")
    if not language_key:
        await state.set_state(LanguageState.waiting_language)
        await message.answer("⚠️ Язык не выбран. Сначала отправь номер языка (1-10).")
        return

    language_data = LANGUAGE_LEARNING_CONTENT[language_key]
    if mode in {"lesson", "урок", "1"}:
        await message.answer(build_language_lesson(language_key))
        return

    if mode in {"quiz", "тест", "2"}:
        await state.set_state(LanguageState.waiting_answer)
        quiz = language_data["quiz"]
        await message.answer(
            f"📝 Мини-квиз: {quiz['question']}\n"
            f"Подсказка: {quiz['hint']}\n\n"
            "Напиши свой ответ одним словом."
        )
        return

    await message.answer("⚠️ Напиши `lesson` или `quiz` (или 1/2).")


@dp.message(LanguageState.waiting_answer)
async def languages_quiz_check(message: types.Message, state: FSMContext):
    user_answer = normalize_answer(message.text or "")
    data = await state.get_data()
    language_key = data.get("language_key")
    if not language_key:
        await state.set_state(LanguageState.waiting_language)
        await message.answer("⚠️ Давай начнем заново. Выбери язык номером от 1 до 10.")
        return

    language_data = LANGUAGE_LEARNING_CONTENT[language_key]
    correct = normalize_answer(language_data["quiz"]["answer"])

    if user_answer == correct:
        record = get_user_record(DATA_FILE, message.from_user.id)
        progress = record.get("language_progress", {})
        progress[language_key] = int(progress.get(language_key, 0)) + 1
        record["language_progress"] = progress
        set_user_record(DATA_FILE, message.from_user.id, record)
        await state.set_state(LanguageState.waiting_mode)
        await message.answer(
            f"✅ Верно! +1 очко в {language_data['title']}\n"
            f"Твой прогресс: {progress[language_key]}\n\n"
            "Продолжим? Напиши `lesson` или `quiz`."
        )
        return

    await message.answer(
        f"❌ Пока неверно. Правильный ответ: {language_data['quiz']['answer']}\n"
        "Попробуй еще раз: напиши `quiz` для нового вопроса или `lesson` для повторения."
    )
    await state.set_state(LanguageState.waiting_mode)


@dp.message(F.text == BTN_ESOTERIC)
async def esoteric_menu(message: types.Message, state: FSMContext):
    if not await ensure_premium(message):
        return
    await state.set_state(EsotericState.waiting_system)
    await message.answer(
        "🪄 Раздел Эзотерика\n\n"
        "Здесь собраны системы по направлениям.\n"
        "Выбери номер направления (1-24):\n\n"
        f"{esoteric_catalog_text()}"
    )


@dp.message(EsotericState.waiting_system)
async def esoteric_pick_system(message: types.Message, state: FSMContext):
    key = (message.text or "").strip()
    if key not in ESOTERIC_SYSTEMS:
        await message.answer("⚠️ Введи номер системы от 1 до 24.")
        return

    name, prompt = ESOTERIC_SYSTEMS[key]
    await state.update_data(esoteric_prompt=prompt, esoteric_name=name)
    await state.set_state(EsotericState.waiting_question)
    await message.answer(f"✅ Выбрано: {name}\nТеперь отправь данные/вопрос для разбора.")


@dp.message(EsotericState.waiting_question)
async def esoteric_run(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prompt = data.get("esoteric_prompt")
    name = data.get("esoteric_name", "Система")
    user_text = (message.text or "").strip()

    if not prompt or not user_text:
        await message.answer("⚠️ Не хватает данных. Выбери раздел заново через 🪄 Эзотерика.")
        return

    answer = await run_llm_with_status(
        message,
        status_for_section("esoteric"),
        lambda: ask_llm(
            openai_client,
            OPENROUTER_MODEL,
            OPENROUTER_API_KEY,
            prompt,
            user_text,
            max_tokens=850,
        ),
    )
    await message.answer(f"🪄 {name}\n\n{answer}")


@dp.message(F.text == BTN_NAVIGATOR)
async def navigator_menu(message: types.Message, state: FSMContext):
    if not await ensure_premium(message):
        return

    await state.set_state(NavigatorState.waiting_message)
    record = get_user_record(DATA_FILE, message.from_user.id)
    nav = record.get("navigator_profile") or {
        "q_count": 0,
        "answers_json": [],
        "insights": "",
        "ai_analysis": "",
        "done": False,
    }
    record["navigator_profile"] = nav
    set_user_record(DATA_FILE, message.from_user.id, record)

    await message.answer(
        "🧭 Тебе точно сюда\n\n"
        "Я проведу персональную навигацию: вопросы → анализ → план на 3 месяца.\n"
        "Отвечай свободно, можно коротко или подробно.\n\n"
        "Стартовый вопрос:\n"
        "Что сейчас для тебя важнее всего: деньги, свобода, спокойствие или самореализация?"
    )


@dp.message(NavigatorState.waiting_message)
async def navigator_run(message: types.Message):
    user_text = (message.text or "").strip()
    if not user_text:
        await message.answer("⚠️ Напиши ответ, чтобы я продолжил навигацию.")
        return

    record = get_user_record(DATA_FILE, message.from_user.id)
    nav = record.get("navigator_profile") or {
        "q_count": 0,
        "answers_json": [],
        "insights": "",
        "ai_analysis": "",
        "done": False,
    }

    nav["answers_json"].append({"user": user_text})
    nav["q_count"] = int(nav.get("q_count", 0)) + 1

    context_payload = {
        "answers_json": nav.get("answers_json", []),
        "insights": nav.get("insights", ""),
        "ai_analysis": nav.get("ai_analysis", ""),
        "q_count": nav.get("q_count", 0),
        "last_user_answer": user_text,
    }

    answer = await run_llm_with_status(
        message,
        status_for_section("navigator"),
        lambda: ask_llm(
            openai_client,
            OPENROUTER_MODEL,
            OPENROUTER_API_KEY,
            NAVIGATOR_PROMPT,
            f"Текущий профиль: {context_payload}",
            max_tokens=1000,
        ),
    )

    nav["answers_json"].append({"ai": answer})
    if "Сейчас соберу твою карту развития" in answer:
        nav["done"] = True
        nav["ai_analysis"] = answer

    record["navigator_profile"] = nav
    set_user_record(DATA_FILE, message.from_user.id, record)
    await message.answer(f"🧭 {answer}")


async def autopost_loop():
    while True:
        try:
            users = load_users(DATA_FILE)
            now = datetime.now()

            for user_id, record in users.items():
                perms = record.get("group_permissions") or default_group_permissions()
                if not perms.get("posts", True):
                    continue

                channels = record.get("channels", [])
                for ch in channels:
                    ensure_channel_defaults(ch)
                    if not ch.get("enabled") or not is_due(ch, now):
                        continue

                    prompt = build_post_prompt(ch)
                    post_text = ""
                    for _ in range(4):
                        candidate = ask_llm(
                            openai_client,
                            OPENROUTER_MODEL,
                            OPENROUTER_API_KEY,
                            "Ты сильный редактор Telegram-каналов. Пиши ярко, полезно, без воды.",
                            prompt,
                            max_tokens=500,
                        )
                        if candidate and not hash_exists(ch, candidate):
                            post_text = candidate
                            break

                    if post_text.startswith("⚠️ Ошибка авторизации OpenRouter") or post_text.startswith("⚠️ OPENROUTER_API_KEY"):
                        mark_sent(ch, now)
                        continue

                    if not post_text:
                        post_text = "⚠️ Не удалось сгенерировать уникальный пост. Проверь ключ ИИ и попробуй позже."

                    if bot is not None:
                        await bot.send_message(ch["chat_id"], f"📣 {post_text}")

                    add_history_text(ch, post_text)
                    mark_sent(ch, now)

                record["channels"] = channels
                users[user_id] = record

            save_users(DATA_FILE, users)
        except Exception as e:
            print("AUTPOST ERROR:", e)

        await asyncio.sleep(30)


@dp.message()
async def fallback(message: types.Message):
    await message.answer("🤝 Я не понял команду. Используй кнопки меню ниже или /start", reply_markup=main_menu())


async def main():
    global bot
    token_error = build_token_error()
    if token_error:
        raise RuntimeError(token_error)

    bot = Bot(BOT_TOKEN)
    asyncio.create_task(autopost_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
