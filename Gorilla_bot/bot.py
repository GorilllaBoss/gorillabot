import asyncio
import random
import uuid
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from openai import OpenAI

from personal_bot.config import ACCESS_CODE, BINANCE_API_KEY, BOT_TOKEN, DATA_FILE, OPENROUTER_API_KEY, OPENROUTER_MODEL, build_token_error
from personal_bot.scheduler import add_history_text, build_post_prompt, ensure_channel_defaults, hash_exists, is_due, mark_sent
from personal_bot.services import analyze_binance_pair, ask_llm, fetch_crypto_snapshot, resolve_binance_pair_input
from personal_bot.states import AccessCodeState, AssistantState, ChannelSetupState, CryptoState, EsotericState, NavigatorState, ProjectState, PsychologyState
from personal_bot.storage import default_group_permissions, default_life_profile, default_project, get_user_record, load_users, save_users, set_user_record, user_has_premium
from personal_bot.ui import (
    BTN_ACCESS,
    BTN_ACCOUNT,
    BTN_ADD_CHANNEL,
    BTN_AI,
    BTN_PSYCHOLOGY,
    BTN_AUTOPOST,
    BTN_BACK,
    BTN_CREATE_PROJECT,
    BTN_PROJECT_WIZARD,
    BTN_CRYPTO,
    BTN_ESOTERIC,
    BTN_GROUP,
    BTN_MY,
    BTN_NAVIGATOR,
    BTN_PROJECTS,
    autopost_menu_keyboard,
    back_menu,
    main_menu,
    project_hub_keyboard,
)

bot = None
dp = Dispatcher(storage=MemoryStorage())
dp.message.filter(F.chat.type == "private")
openai_client = OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")

NAV_BTN_ADVICE = "🧠 Спросить совет"
NAV_BTN_GOALS = "🎯 Мои цели"
NAV_BTN_PROFILE = "📊 Мой профиль"
NAV_BTN_TODAY = "📅 План сегодня"
NAV_BTN_REMIND = "⏰ Напоминания"
NAV_BTN_UPDATE = "🔄 Обновить анализ"

TOPIC_QUESTIONS = {
    "identity": "Как ты себя описываешь в 3 словах? Примеры: 'спокойный стратег', 'энергичный практик'.",
    "values": "Что важнее в решениях: свобода, деньги, влияние или стабильность?",
    "career": "Какая работа даёт ощущение силы? Примеры: запуск проектов / переговоры / аналитика.",
    "money": "Какую финансовую цель хочешь закрыть за 6 месяцев?",
    "dreams": "Если ограничений нет — какой проект ты бы начал завтра?",
    "fears": "Что тормозит твой рост сейчас? Примеры: страх ошибки / дисциплина / окружение.",
    "skills": "Какие 2 навыка дают тебе лучший результат?",
    "habits": "Какая привычка стабильно тянет тебя вниз?",
    "lifestyle": "Какой режим лучше: спринты или марафон?",
    "energy": "Когда пик энергии: утром, днём или вечером?",
    "risk tolerance": "Насколько ты готов рисковать от 1 до 10 и почему?",
}

SPICY_QUESTIONS = [
    "Можно странный вопрос? Если деньги не проблема — чем займёшься в ближайший год?",
    "Если бы у тебя был 1 свободный год, какой навык ты бы прокачал до уровня топ-1%?",
    "Какой выбор ты откладываешь уже месяц, хотя знаешь правильный шаг?",
]

MICRO_INSIGHTS = [
    "⚡ Считываю тебя как человека действия: лучше короткий рывок, чем бесконечная теория.",
    "⚡ У тебя сильный фокус на результате — это хороший фундамент для роста.",
    "⚡ Вижу дисциплинарный запрос: ты хочешь не просто мотивацию, а рабочую систему.",
    "⚡ Ты честно смотришь на ограничения — это ускоряет прогресс сильнее любой техники.",
]

ESOTERIC_MENU = {
    "🃏 Таро": {
        "description": "Архетипический разбор ситуации через символы карт и практический вектор действий.",
        "input": "Введи: ситуация + вопрос + горизонт (дни/недели)",
    },
    "🔮 Оракулы": {
        "description": "Мягкая интуитивная трактовка для текущего запроса и выбора следующего шага.",
        "input": "Введи: запрос + что хочешь получить на выходе",
    },
    "ᚱ Руны": {
        "description": "Символьный разбор конфликта/цели через рунические смыслы и рекомендации.",
        "input": "Введи: контекст + цель на 30 дней",
    },
    "☯️ И-цзин": {
        "description": "Стратегический анализ через логику перемен и сценарий выбора А/Б.",
        "input": "Введи: ситуация / выбор А / выбор Б",
    },
    "☕ Интуитивные методы": {
        "description": "Разбор эмоционального фона и скрытых сигналов для принятия решения.",
        "input": "Введи: эмоция дня + главный вопрос",
    },
    "⭐ Классическая астрология": {
        "description": "Базовый разбор натальных акцентов: характер, сильные стороны, риски.",
        "input": "Введи: ДД.ММ.ГГГГ ЧЧ:ММ Город",
    },
    "🌞 Классическая западная астрология": {
        "description": "Подробный разбор транзитов, совместимости и текущего периода.",
        "input": "Введи: ДД.ММ.ГГГГ ЧЧ:ММ Город",
    },
    "🪐 Джйотиш": {
        "description": "Ведический взгляд на кармические уроки, периоды и практичные решения.",
        "input": "Введи: ДД.ММ.ГГГГ ЧЧ:ММ Город",
    },
    "🐉 Китайская астрология": {
        "description": "Разбор по знаку/элементу и циклам для карьеры, денег и отношений.",
        "input": "Введи: ДД.ММ.ГГГГ Пол + вопрос",
    },
    "🌙 Лунная астрология": {
        "description": "Анализ лунного ритма для режима, эмоций и тайминга решений.",
        "input": "Введи: дата + цель месяца + вопрос",
    },
    "🔢 Классическая нумерология": {
        "description": "Число пути, таланты и уязвимости в классической школе нумерологии.",
        "input": "Введи: ДД.ММ.ГГГГ",
    },
    "🔢 Пифагор": {
        "description": "Квадрат Пифагора: характер, энергия, дисциплина, интеллект, призвание.",
        "input": "Введи: ДД.ММ.ГГГГ",
    },
    "🧾 Каббалистическая": {
        "description": "Числовые и буквенные коды имени/даты для глубинных паттернов.",
        "input": "Введи: ФИО + ДД.ММ.ГГГГ",
    },
    "🧩 Матрица судьбы": {
        "description": "Разбор архетипов 22 арканов: ресурсы, блоки, вектор роста.",
        "input": "Введи: ДД.ММ.ГГГГ + ключевой вопрос",
    },
    "🧠 Human Design": {
        "description": "Тип, стратегия и авторитет для верных решений и меньшего стресса.",
        "input": "Введи: ДД.ММ.ГГГГ ЧЧ:ММ Город",
    },
    "🧠 Соционика": {
        "description": "Коммуникационный профиль, сильные роли и зоны конфликтов.",
        "input": "Введи: 3 типичных сценария общения",
    },
    "🧠 MBTI": {
        "description": "Когнитивный профиль и практичные рекомендации по работе/общению.",
        "input": "Введи: как принимаешь решения + что заряжает",
    },
    "🧠 Эннеаграмма": {
        "description": "Базовые мотивации и защитные стратегии, которые мешают росту.",
        "input": "Введи: мотивация + главный страх",
    },
    "🌀 Чакры": {
        "description": "Оценка баланса энергии и мягкий план восстановления ресурса.",
        "input": "Введи: самочувствие + эмоции + запрос",
    },
    "✨ Рейки": {
        "description": "Рекомендации по энергетической гигиене и восстановлению через практики.",
        "input": "Введи: энергия (1-10) + стресс + цель",
    },
    "🧿 Карма": {
        "description": "Повторяющиеся жизненные сценарии и как выйти из цикла.",
        "input": "Введи: повторяющийся сценарий + желаемый сдвиг",
    },
    "✋ Хиромантия": {
        "description": "Символьная трактовка линий ладони и характера решений.",
        "input": "Введи: описание ладони + вопрос",
    },
    "🙂 Физиогномика": {
        "description": "Этичный разбор поведенческих склонностей по описанию черт лица.",
        "input": "Введи: черты лица + вопрос",
    },
    "🏡 Фэншуй": {
        "description": "Практичные изменения пространства для фокуса, денег и спокойствия.",
        "input": "Введи: тип пространства + проблема + цель",
    },
    "📆 Ба-цзы": {
        "description": "Карта элементов, циклы удачи и выбор оптимальной стратегии.",
        "input": "Введи: ДД.ММ.ГГГГ ЧЧ:ММ Пол",
    },
    "🥋 Цигун": {
        "description": "Подбор безопасных практик для энергии, концентрации и восстановления.",
        "input": "Введи: уровень подготовки + цель + ограничения",
    },
}



def user_menu(user_id: int):
    return main_menu(user_has_premium(DATA_FILE, user_id))


def is_premium_only_module(text: str) -> bool:
    premium_buttons = {
        BTN_PSYCHOLOGY,
        BTN_NAVIGATOR,
        BTN_ESOTERIC,
        BTN_CRYPTO,
        BTN_CREATE_PROJECT,
        BTN_PROJECT_WIZARD,
        BTN_PROJECTS,
        BTN_AUTOPOST,
        BTN_MY,
        BTN_GROUP,
        BTN_ACCOUNT,
    }
    return text in premium_buttons


def current_module_from_text(text: str) -> str:
    mapping = {
        BTN_AI: "assistant",
        BTN_ACCESS: "access",
        BTN_PSYCHOLOGY: "psychology",
        BTN_NAVIGATOR: "navigator",
        BTN_ESOTERIC: "esoteric",
        BTN_CRYPTO: "crypto",
        BTN_CREATE_PROJECT: "project_hub",
        BTN_PROJECT_WIZARD: "project_wizard",
        BTN_PROJECTS: "project_list",
        BTN_AUTOPOST: "autopost",
        BTN_MY: "channels",
        BTN_GROUP: "groups",
        BTN_ACCOUNT: "account",
    }
    return mapping.get(text, "unknown")


async def persist_flow_snapshot(message: types.Message, state: FSMContext, target_module: str):
    current_state = await state.get_state()
    if not current_state:
        return
    payload = await state.get_data()
    record = get_user_record(DATA_FILE, message.from_user.id)
    memory = record.get("flow_memory", {})
    memory[current_state] = {
        "state": current_state,
        "data": payload,
        "target_module": target_module,
        "saved_at": datetime.now().isoformat(),
    }
    record["flow_memory"] = memory
    set_user_record(DATA_FILE, message.from_user.id, record)


def dashboard_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=NAV_BTN_ADVICE), KeyboardButton(text=NAV_BTN_GOALS)],
            [KeyboardButton(text=NAV_BTN_PROFILE), KeyboardButton(text=NAV_BTN_TODAY)],
            [KeyboardButton(text=NAV_BTN_REMIND), KeyboardButton(text=NAV_BTN_UPDATE)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def profile_ready(profile: dict) -> bool:
    return bool(profile.get("ai_analysis")) and bool(profile.get("answers_json"))


def format_freq_label(raw: str) -> str:
    val = str(raw or "1")
    mapping = {"1": "1 пост/день", "3": "3 поста/день", "5": "5 постов/день", "random": "Random"}
    return mapping.get(val, val)


def next_project_interval_minutes(project: dict) -> int:
    freq = str(project.get("posting_frequency", "1"))
    if freq == "random":
        return random.randint(180, 480)
    if freq.isdigit() and int(freq) > 0:
        return max(30, int(1440 / int(freq)))
    return 1440


def parse_analysis(text: str) -> dict:
    lines = [x.strip("-• ") for x in text.splitlines() if x.strip()]
    return {
        "archetype": lines[0] if lines else "Стратег-практик",
        "goals": lines[1:4] if len(lines) >= 4 else ["Усилить фокус", "Дожать ключевую цель", "Стабилизировать ритм"],
        "daily_plan": lines[4] if len(lines) > 4 else "1 ключевая задача + итог дня",
        "weekly_plan": lines[5] if len(lines) > 5 else "3 шага на неделю",
        "monthly_plan": lines[6] if len(lines) > 6 else "1 главный результат месяца",
    }


def next_onboarding_question(profile: dict, last_user: str = "") -> str:
    if last_user.lower().strip() in {"не знаю", "сложно", "хз"}:
        return "Окей, упростим: тебе ближе контент, продажи или продукт?"

    spicy_seen = profile.setdefault("onboarding_spicy_seen", [])
    spicy_available = [q for q in SPICY_QUESTIONS if q not in spicy_seen]
    if spicy_available and random.random() < 0.2:
        q = random.choice(spicy_available)
        spicy_seen.append(q)
        profile["last_onboarding_question"] = q
        return q

    seen = profile.get("onboarding_topics", [])
    available = [x for x in TOPIC_QUESTIONS if x not in seen] or list(TOPIC_QUESTIONS)
    topic = random.choice(available)
    seen.append(topic)
    profile["onboarding_topics"] = seen
    q = TOPIC_QUESTIONS[topic]
    profile["last_onboarding_question"] = q
    return q


def onboarding_micro_insight(user_text: str, user_count: int) -> str:
    text = (user_text or "").lower()
    if any(x in text for x in ["дисцип", "фокус", "привыч"]):
        return "⚡ Фокус на дисциплине — это сильный сигнал. Из этого обычно рождается стабильный рост."
    if any(x in text for x in ["страх", "ошиб", "сомнен"]):
        return "⚡ Ты честно называешь внутренние стоп-факторы. Это уже половина решения."
    return MICRO_INSIGHTS[(user_count // 3) % len(MICRO_INSIGHTS)]


async def run_llm_with_status(message: types.Message, statuses: list[str], llm_call):
    status_message = await message.answer(random.choice(statuses))
    task = asyncio.create_task(asyncio.to_thread(llm_call))
    while not task.done():
        await asyncio.sleep(2.2)
        if task.done():
            break
        try:
            await status_message.edit_text(random.choice(statuses))
        except Exception:
            pass
    answer = await task
    try:
        await status_message.delete()
    except Exception:
        pass
    return answer


def status_for(section: str):
    return {
        "assistant": ["🤔 Думаю...", "🧠 Сверяю контекст...", "✅ Почти готово..."],
        "navigator": ["🧭 Ищу вектор...", "🎯 Собираю план...", "✅ Уже готово..."],
        "crypto": ["📈 Смотрю рынок...", "🧮 Считаю...", "✅ Финализирую..."],
    }[section]


def crypto_suggestions_kb(base_pair: str = "BTC/USDT") -> InlineKeyboardMarkup:
    base = (base_pair or "BTC/USDT").upper().replace(" ", "")
    second = "ETH/USDT" if not base.startswith("ETH") else "BTC/USDT"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Анализ {second.split('/')[0]}", callback_data=f"crypto:pair:{second}")],
            [InlineKeyboardButton(text=f"Сетап на {base.split('/')[0]}", callback_data=f"crypto:setup:{base}")],
            [InlineKeyboardButton(text=f"Куда может пойти {base.split('/')[0]}?", callback_data=f"crypto:where:{base}")],
            [InlineKeyboardButton(text="Что купить?", callback_data=f"crypto:buy:{base}")],
            [InlineKeyboardButton(text="Мои позиции", callback_data=f"crypto:positions:{base}")],
        ]
    )


async def ensure_premium(message: types.Message) -> bool:
    if user_has_premium(DATA_FILE, message.from_user.id):
        return True
    await message.answer("🔐 Функция доступна после кода. Нажми «🔐 Премиум услуги».", reply_markup=user_menu(message.from_user.id))
    return False


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if user_has_premium(DATA_FILE, message.from_user.id):
        await message.answer("🚀 GorillaAI. Выбери раздел.", reply_markup=user_menu(message.from_user.id))
    else:
        await message.answer("🤖 GorillaAI Premium.\n\nТребуется код доступа.", reply_markup=user_menu(message.from_user.id))


@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    await message.answer("🏠 Главное меню", reply_markup=user_menu(message.from_user.id))


@dp.message(F.text.in_([
    BTN_AI,
    BTN_ACCESS,
    BTN_PSYCHOLOGY,
    BTN_NAVIGATOR,
    BTN_ESOTERIC,
    BTN_CRYPTO,
    BTN_CREATE_PROJECT,
    BTN_PROJECT_WIZARD,
    BTN_PROJECTS,
    BTN_AUTOPOST,
    BTN_MY,
    BTN_GROUP,
    BTN_ACCOUNT,
]))
async def route_menu_buttons(message: types.Message, state: FSMContext):
    text = message.text
    if not user_has_premium(DATA_FILE, message.from_user.id) and is_premium_only_module(text):
        await message.answer("🔐 Сначала активируй премиум-доступ по коду.", reply_markup=user_menu(message.from_user.id))
        return

    await persist_flow_snapshot(message, state, current_module_from_text(text))
    if await state.get_state():
        await state.clear()

    if text == BTN_AI:
        await ask_ai(message, state)
    elif text == BTN_ACCESS:
        await cmd_access(message, state)
    elif text == BTN_PSYCHOLOGY:
        await psychology_menu(message, state)
    elif text == BTN_NAVIGATOR:
        await navigator_entry(message, state)
    elif text == BTN_ESOTERIC:
        await esoteric_menu(message, state)
    elif text == BTN_CRYPTO:
        await crypto_menu(message, state)
    elif text == BTN_CREATE_PROJECT:
        await open_project_hub(message, state)
    elif text == BTN_PROJECT_WIZARD:
        await start_project_wizard(message, state)
    elif text == BTN_PROJECTS:
        await my_projects(message)
    elif text == BTN_AUTOPOST:
        await autopost_menu(message)
    elif text == BTN_MY:
        await my_channels(message)
    elif text == BTN_GROUP:
        await group_menu(message)
    elif text == BTN_ACCOUNT:
        await account(message)


@dp.message(F.text == BTN_BACK)
async def back_to_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("⬅️ Возврат в меню", reply_markup=user_menu(message.from_user.id))


@dp.message(F.text == BTN_ACCESS)
@dp.message(Command("access"))
async def cmd_access(message: types.Message, state: FSMContext):
    if user_has_premium(DATA_FILE, message.from_user.id):
        await message.answer("✅ Премиум уже активирован", reply_markup=user_menu(message.from_user.id))
        return
    await state.set_state(AccessCodeState.waiting_code)
    await message.answer("🔑 Введи код доступа", reply_markup=back_menu())


@dp.message(AccessCodeState.waiting_code)
async def process_access_code(message: types.Message, state: FSMContext):
    if (message.text or "").strip() == ACCESS_CODE:
        record = get_user_record(DATA_FILE, message.from_user.id)
        record["premium"] = True
        set_user_record(DATA_FILE, message.from_user.id, record)
        await state.clear()
        await message.answer("✅ Премиум открыт", reply_markup=user_menu(message.from_user.id))
    else:
        await message.answer("❌ Неверный код")


@dp.message(F.text == BTN_AI)
@dp.message(Command("ask"))
async def ask_ai(message: types.Message, state: FSMContext):
    text = (message.text or "").replace("/ask", "", 1).strip()
    if not text:
        await state.set_state(AssistantState.waiting_question)
        await message.answer("Напиши вопрос", reply_markup=back_menu())
        return
    answer = await run_llm_with_status(
        message,
        status_for("assistant"),
        lambda: ask_llm(openai_client, OPENROUTER_MODEL, OPENROUTER_API_KEY, "Ты полезный AI ассистент Telegram", text, max_tokens=700),
    )
    await message.answer(f"🤖 {answer}", reply_markup=user_menu(message.from_user.id))


@dp.message(AssistantState.waiting_question)
async def ask_ai_state(message: types.Message, state: FSMContext):
    await state.clear()
    await ask_ai(message, state)


@dp.message(F.text == BTN_PSYCHOLOGY)
async def psychology_menu(message: types.Message, state: FSMContext):
    if not await ensure_premium(message):
        return
    await state.set_state(PsychologyState.waiting_mode)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧠 Психолог ИИ", callback_data="help:ai")],
            [InlineKeyboardButton(text="📞 Психолог онлайн", callback_data="help:online")],
        ]
    )
    await message.answer("Выбери формат психологической помощи", reply_markup=kb)


@dp.callback_query(F.data.startswith("help:"))
async def psychology_mode(callback: types.CallbackQuery, state: FSMContext):
    mode = callback.data.split(":", 1)[1]
    if mode == "online":
        await state.clear()
        await callback.message.answer("Психолог онлайн: @aggressive_chik")
    else:
        await state.set_state(PsychologyState.waiting_question)
        await callback.message.answer("Опиши ситуацию")
    await callback.answer()


@dp.message(PsychologyState.waiting_question)
async def psychology_ai_run(message: types.Message):
    answer = await run_llm_with_status(
        message,
        status_for("assistant"),
        lambda: ask_llm(openai_client, OPENROUTER_MODEL, OPENROUTER_API_KEY, "Ты ИИ-психолог: поддерживающий, бережный и практичный. Дай 3 понятных шага.", (message.text or ""), max_tokens=700),
    )
    await message.answer(f"🧠 {answer}")


@dp.message(F.text == BTN_NAVIGATOR)
async def navigator_entry(message: types.Message, state: FSMContext):
    if not await ensure_premium(message):
        return
    await state.clear()
    record = get_user_record(DATA_FILE, message.from_user.id)
    profile = record.get("user_life_profile") or default_life_profile()
    if not profile_ready(profile):
        record["user_life_profile"] = profile
        set_user_record(DATA_FILE, message.from_user.id, record)
        await state.set_state(NavigatorState.onboarding)
        await message.answer("🧭 Стартуем onboarding.\n" + next_onboarding_question(profile), reply_markup=back_menu())
        return
    await state.set_state(NavigatorState.coach)
    goals = "\n".join(f"• {g}" for g in profile.get("goals", []))
    await message.answer(f"Привет снова.\n\nЯ помню твои цели:\n\n{goals}\n\nСегодняшний фокус:\n\n{profile.get('daily_plan')}", reply_markup=dashboard_kb())


@dp.message(NavigatorState.onboarding)
async def navigator_onboarding(message: types.Message, state: FSMContext):
    user_text = (message.text or "").strip()
    if not user_text:
        await message.answer("Нужен ответ текстом")
        return
    record = get_user_record(DATA_FILE, message.from_user.id)
    profile = record.get("user_life_profile") or default_life_profile()
    profile["answers_json"].append({"user": user_text, "time": datetime.now().isoformat()})
    user_count = len([x for x in profile["answers_json"] if x.get("user")])

    if user_count >= 12:
        analysis = await run_llm_with_status(
            message,
            status_for("navigator"),
            lambda: ask_llm(
                openai_client,
                OPENROUTER_MODEL,
                OPENROUTER_API_KEY,
                "Ты AI Life Navigator. На основе ответов дай уникальный архетип, сильные стороны, ограничения, ценности, направления и план на 3 месяца + daily/weekly/monthly.",
                str(profile["answers_json"][-20:]),
                max_tokens=950,
            ),
        )
        profile["ai_analysis"] = analysis
        profile.update(parse_analysis(analysis))
        profile["last_update"] = datetime.now().isoformat()
        record["user_life_profile"] = profile
        set_user_record(DATA_FILE, message.from_user.id, record)
        await state.set_state(NavigatorState.coach)
        await message.answer("🎉 Навигация завершена.\nТеперь я твой персональный ассистент.", reply_markup=dashboard_kb())
        await message.answer(
            "Чтобы напоминания были точными, уточни:\n"
            "• 🎯 Мои цели\n"
            "• 📅 План сегодня\n"
            "• ⏰ Напоминания"
        )
        return

    if user_count % 3 == 0:
        await message.answer(onboarding_micro_insight(user_text, user_count))
    q = next_onboarding_question(profile, user_text)
    record["user_life_profile"] = profile
    set_user_record(DATA_FILE, message.from_user.id, record)
    await message.answer(q)


@dp.message(F.text.in_([NAV_BTN_ADVICE, NAV_BTN_GOALS, NAV_BTN_PROFILE, NAV_BTN_TODAY, NAV_BTN_REMIND, NAV_BTN_UPDATE]))
async def navigator_dashboard_actions(message: types.Message, state: FSMContext):
    if not await ensure_premium(message):
        return
    record = get_user_record(DATA_FILE, message.from_user.id)
    profile = record.get("user_life_profile") or default_life_profile()

    if message.text == NAV_BTN_GOALS:
        goals = profile.get("goals", [])
        await state.set_state(NavigatorState.edit_goals)
        await message.answer(
            "🎯 Мои цели:\n" + "\n".join(f"• {x}" for x in goals) + "\n\n"
            "Отправь новые цели одним сообщением (через запятую или с новой строки)."
        )
    elif message.text == NAV_BTN_PROFILE:
        await message.answer(f"📊 Архетип: {profile.get('archetype')}\n\n{profile.get('ai_analysis','')[:3500]}")
    elif message.text == NAV_BTN_TODAY:
        await state.set_state(NavigatorState.edit_today)
        await message.answer(
            f"📅 План сегодня:\n{profile.get('daily_plan')}\n\n"
            "Отправь обновлённый фокус на сегодня (1-3 конкретных шага)."
        )
    elif message.text == NAV_BTN_REMIND:
        await state.set_state(NavigatorState.reminders)
        await message.answer("Режим напоминаний: ежедневно / еженедельно / ежемесячно / off")
    elif message.text == NAV_BTN_UPDATE:
        await state.set_state(NavigatorState.update)
        profile["update_answers"] = []
        record["user_life_profile"] = profile
        set_user_record(DATA_FILE, message.from_user.id, record)
        await message.answer("Что изменилось за 2 недели?")
    else:
        await state.set_state(NavigatorState.coach)
        await message.answer("Напиши вопрос — дам совет с учетом твоего профиля")


@dp.message(NavigatorState.reminders)
async def navigator_reminders(message: types.Message, state: FSMContext):
    mode = (message.text or "").strip().lower()
    mapper = {"ежедневно": "daily", "еженедельно": "weekly", "ежемесячно": "monthly", "off": "off"}
    if mode not in mapper:
        await message.answer("Формат: ежедневно / еженедельно / ежемесячно / off")
        return
    record = get_user_record(DATA_FILE, message.from_user.id)
    profile = record.get("user_life_profile") or default_life_profile()
    profile["reminder_settings"]["mode"] = mapper[mode]
    profile["reminder_settings"]["last_sent"] = ""
    record["user_life_profile"] = profile
    set_user_record(DATA_FILE, message.from_user.id, record)
    await state.set_state(NavigatorState.coach)
    await message.answer("✅ Настройки сохранены", reply_markup=dashboard_kb())


@dp.message(NavigatorState.edit_goals)
async def navigator_edit_goals(message: types.Message, state: FSMContext):
    raw = (message.text or "").strip()
    if not raw:
        await message.answer("⚠️ Напиши хотя бы 1 цель")
        return
    parts = [x.strip("• -\t ") for x in raw.replace("\n", ",").split(",") if x.strip()]
    goals = parts[:5]
    if not goals:
        await message.answer("⚠️ Не смог выделить цели. Попробуй ещё раз.")
        return
    record = get_user_record(DATA_FILE, message.from_user.id)
    profile = record.get("user_life_profile") or default_life_profile()
    profile["goals"] = goals
    profile["last_update"] = datetime.now().isoformat()
    record["user_life_profile"] = profile
    set_user_record(DATA_FILE, message.from_user.id, record)
    await state.set_state(NavigatorState.coach)
    await message.answer("✅ Цели обновлены и сохранены", reply_markup=dashboard_kb())


@dp.message(NavigatorState.edit_today)
async def navigator_edit_today(message: types.Message, state: FSMContext):
    daily = (message.text or "").strip()
    if len(daily) < 4:
        await message.answer("⚠️ Напиши чуть подробнее, что сделать сегодня")
        return
    record = get_user_record(DATA_FILE, message.from_user.id)
    profile = record.get("user_life_profile") or default_life_profile()
    profile["daily_plan"] = daily
    profile["last_update"] = datetime.now().isoformat()
    record["user_life_profile"] = profile
    set_user_record(DATA_FILE, message.from_user.id, record)
    await state.set_state(NavigatorState.coach)
    await message.answer("✅ План на сегодня сохранён", reply_markup=dashboard_kb())


@dp.message(NavigatorState.update)
async def navigator_update(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    record = get_user_record(DATA_FILE, message.from_user.id)
    profile = record.get("user_life_profile") or default_life_profile()
    profile["update_answers"].append(text)
    if len(profile["update_answers"]) < 3:
        followups = ["Что дало лучший результат?", "Что мешает прямо сейчас?"]
        await message.answer(followups[len(profile["update_answers"]) - 1])
        record["user_life_profile"] = profile
        set_user_record(DATA_FILE, message.from_user.id, record)
        return
    analysis = await run_llm_with_status(
        message,
        status_for("navigator"),
        lambda: ask_llm(openai_client, OPENROUTER_MODEL, OPENROUTER_API_KEY, "Обнови анализ без полного onboarding", str(profile["update_answers"]), max_tokens=800),
    )
    profile["ai_analysis"] = analysis
    profile.update(parse_analysis(analysis))
    profile["update_answers"] = []
    profile["last_update"] = datetime.now().isoformat()
    record["user_life_profile"] = profile
    set_user_record(DATA_FILE, message.from_user.id, record)
    await state.set_state(NavigatorState.coach)
    await message.answer("✅ Анализ обновлён", reply_markup=dashboard_kb())


@dp.message(NavigatorState.coach)
async def navigator_coach(message: types.Message):
    user_text = (message.text or "").strip()
    if not user_text:
        return
    record = get_user_record(DATA_FILE, message.from_user.id)
    profile = record.get("user_life_profile") or default_life_profile()
    history = profile.get("history", [])[-8:]
    prompt = f"analysis={profile.get('ai_analysis')} goals={profile.get('goals')} history={history} user={user_text}"
    answer = await run_llm_with_status(
        message,
        status_for("navigator"),
        lambda: ask_llm(openai_client, OPENROUTER_MODEL, OPENROUTER_API_KEY, "Ты AI Life Navigator. Коучинг: кратко, точно, по делу.", prompt, max_tokens=700),
    )
    profile["history"] = history + [{"q": user_text, "a": answer, "time": datetime.now().isoformat()}]
    record["user_life_profile"] = profile
    set_user_record(DATA_FILE, message.from_user.id, record)
    await message.answer(f"🧭 {answer}")


@dp.message(F.text == BTN_ESOTERIC)
async def esoteric_menu(message: types.Message, state: FSMContext):
    if not await ensure_premium(message):
        return
    await state.set_state(EsotericState.waiting_system)
    buttons = [[InlineKeyboardButton(text=name, callback_data=f"eso:{i}")] for i, name in enumerate(ESOTERIC_MENU.keys(), start=1)]
    await message.answer("🪄 Выбери направление:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@dp.callback_query(F.data.startswith("eso:"))
async def esoteric_pick(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.split(":", 1)[1]) - 1
    names = list(ESOTERIC_MENU.keys())
    if idx not in range(len(names)):
        await callback.answer("Ошибка", show_alert=True)
        return
    name = names[idx]
    await state.set_state(EsotericState.waiting_payload)
    await state.update_data(esoteric_name=name)
    cfg = ESOTERIC_MENU[name]
    await callback.message.answer(f"{name}\n\n🧭 {cfg['description']}\n\n📌 Что отправить:\n{cfg['input']}")
    await callback.answer()


@dp.message(EsotericState.waiting_payload)
async def esoteric_run(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data.get("esoteric_name")
    payload = (message.text or "").strip()
    if not payload or len(payload) < 8:
        await message.answer(f"Добавь больше данных по формату:\n{ESOTERIC_MENU.get(name, {}).get('input', 'Опиши запрос подробнее')}")
        return
    answer = await run_llm_with_status(
        message,
        status_for("assistant"),
        lambda: ask_llm(openai_client, OPENROUTER_MODEL, OPENROUTER_API_KEY, f"Ты эксперт {name}. Дай глубокий персональный разбор.", payload, max_tokens=900),
    )
    await message.answer(f"{name}\n\n{answer}")


@dp.message(F.text == BTN_CRYPTO)
async def crypto_menu(message: types.Message, state: FSMContext):
    if not await ensure_premium(message):
        return
    await state.set_state(CryptoState.waiting_coin)
    await message.answer(
        "Введи монету или пару Binance: биткоин / btc / ETH / BTC/USDT\n"
        "После анализа можно задавать вопросы: куда может пойти актив, где риск, какие сценарии.",
        reply_markup=back_menu(),
    )


@dp.message(CryptoState.waiting_coin)
async def crypto_run(message: types.Message, state: FSMContext):
    raw = (message.text or "").strip()
    resolved = resolve_binance_pair_input(raw)
    if not resolved.get("ok"):
        hints = ", ".join(resolved.get("suggestions", ["BTC/USDT", "ETH/USDT"]))
        await message.answer(f"⚠️ {resolved.get('error', 'Не понял запрос')}\nПопробуй один из вариантов: {hints}")
        return

    pair = resolved["pair"]
    report = await asyncio.to_thread(analyze_binance_pair, pair, BINANCE_API_KEY)
    if report.startswith("⚠️"):
        await message.answer(report + "\nПопробуй другой вариант: BTC/USDT, ETH/USDT, LINK/USDT")
        return
    await state.set_state(CryptoState.waiting_followup)
    await state.update_data(last_pair=pair, last_report=report)
    await message.answer(report)
    await message.answer(
        "Могу продолжить как AI-крипто ассистент. Выбери быстрый сценарий или задай вопрос текстом 👇",
        reply_markup=crypto_suggestions_kb(pair),
    )


@dp.callback_query(F.data.startswith("crypto:"))
async def crypto_quick_actions(callback: types.CallbackQuery, state: FSMContext):
    if not await ensure_premium(callback.message):
        await callback.answer()
        return

    _, action, pair = callback.data.split(":", 2)
    pair = pair.upper()
    await state.set_state(CryptoState.waiting_followup)

    if action == "pair":
        report = await asyncio.to_thread(analyze_binance_pair, pair, BINANCE_API_KEY)
        await state.update_data(last_pair=pair, last_report=report)
        await callback.message.answer(report)
        await callback.message.answer("Готово. Можно разобрать следующий сценарий 👇", reply_markup=crypto_suggestions_kb(pair))
        await callback.answer()
        return

    prompts = {
        "setup": f"Сделай 2 торговых сетапа по {pair}: консервативный и агрессивный. Укажи триггер входа, стоп, цели и риск.",
        "where": f"Дай 2-3 сценария движения цены по {pair} на ближайшие 24-72 часа и что будет подтверждением каждого сценария.",
        "buy": f"Я частный инвестор. Как аккуратно зайти в {pair}? Дай 2 варианта (DCA и по подтверждению), с рисками.",
        "positions": f"Составь чек-лист управления позицией по {pair}: что отслеживать, когда сокращать риск, когда фиксировать прибыль.",
    }
    user_prompt = prompts.get(action, prompts["where"])
    data = await state.get_data()
    context_report = data.get("last_report", "")[:2500]
    answer = await run_llm_with_status(
        callback.message,
        status_for("crypto"),
        lambda: ask_llm(
            openai_client,
            OPENROUTER_MODEL,
            OPENROUTER_API_KEY,
            "Ты AI крипто-ассистент: объясняешь сценарии движения актива простым языком, даёшь 2-3 варианта действий и риски. Без гарантий и без финансовых обещаний.",
            f"Контекст тех.анализа:\n{context_report}\n\nЗапрос: {user_prompt}",
            max_tokens=850,
        ),
    )
    await callback.message.answer(f"📌 {pair}\n\n{answer}")
    await callback.message.answer("Если нужно — продолжим разбор 👇", reply_markup=crypto_suggestions_kb(pair))
    await callback.answer()


@dp.message(CryptoState.waiting_followup)
async def crypto_followup(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        return

    resolved = resolve_binance_pair_input(text)
    if resolved.get("ok"):
        pair = resolved["pair"]
        report = await asyncio.to_thread(analyze_binance_pair, pair, BINANCE_API_KEY)
        if report.startswith("⚠️"):
            await message.answer(report)
            return
        await state.update_data(last_pair=pair, last_report=report)
        await message.answer(report)
        await message.answer("Выбери следующий сценарий или задай вопрос 👇", reply_markup=crypto_suggestions_kb(pair))
        return

    data = await state.get_data()
    pair = data.get("last_pair", "BTC/USDT")
    context_report = data.get("last_report", "")[:2500]
    answer = await run_llm_with_status(
        message,
        status_for("crypto"),
        lambda: ask_llm(
            openai_client,
            OPENROUTER_MODEL,
            OPENROUTER_API_KEY,
            "Ты AI крипто-ассистент. Отвечай по текущему активу, давай 2-3 варианта развития и практичные действия с рисками.",
            f"Актив: {pair}\nТех. контекст:\n{context_report}\n\nВопрос пользователя: {text}",
            max_tokens=850,
        ),
    )
    await message.answer(f"📌 {pair}\n\n{answer}")
    await message.answer("Могу продолжить, выбери вариант 👇", reply_markup=crypto_suggestions_kb(pair))


@dp.message(F.text == BTN_PROJECTS)
async def my_projects(message: types.Message):
    if not await ensure_premium(message):
        return
    projects = get_user_record(DATA_FILE, message.from_user.id).get("projects", [])
    if not projects:
        await message.answer("Проектов пока нет")
        return

    lines = ["📁 Твои проекты:"]
    kb_rows = []
    for p in projects:
        pid = p.get("id", "")
        channel = p.get("channel_username") or p.get("channel") or "—"
        theme = p.get("theme") or p.get("topic") or "—"
        freq = format_freq_label(p.get("posting_frequency", "1"))
        ptime = p.get("posting_time", "09:00")
        status = "ON" if p.get("is_autopost_enabled") else "OFF"
        next_run = p.get("next_run", "—")[:16].replace("T", " ") if p.get("next_run") else "—"
        lines.append(f"• {channel}\n  Тема: {theme}\n  Частота: {freq} | Время: {ptime}\n  Автопостинг: {status} | Следующий пост: {next_run}")
        if pid:
            kb_rows.append([InlineKeyboardButton(text=f"Открыть {channel}", callback_data=f"projopen:{pid}")])

    await message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows[:20]) if kb_rows else None)


async def send_project_dashboard(chat_obj: types.Message | types.CallbackQuery, project: dict):
    pid = project.get("id", "")
    channel = project.get("channel_username") or project.get("channel") or "—"
    theme = project.get("theme") or project.get("topic") or "—"
    freq = format_freq_label(project.get("posting_frequency", "1"))
    ptime = project.get("posting_time", "09:00")
    srcs = ", ".join(project.get("content_sources", ["AI генерация"]))
    status = "ON" if project.get("is_autopost_enabled") else "OFF"
    next_run = project.get("next_run", "—")[:16].replace("T", " ") if project.get("next_run") else "—"
    last_post_at = project.get("last_post_at", "—")[:16].replace("T", " ") if project.get("last_post_at") else "—"
    last_error = project.get("last_error", "")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать тему", callback_data=f"projdash:theme:{pid}")],
        [InlineKeyboardButton(text="📝 Примеры постов", callback_data=f"projdash:examples:{pid}")],
        [InlineKeyboardButton(text="⏰ Автопостинг", callback_data=f"projdash:auto:{pid}")],
        [InlineKeyboardButton(text="🎨 Оформление", callback_data=f"projdash:style:{pid}")],
        [InlineKeyboardButton(text="📅 Расписание", callback_data=f"projdash:schedule:{pid}")],
        [InlineKeyboardButton(text="📡 Источники", callback_data=f"projdash:sources:{pid}")],
        [InlineKeyboardButton(text="❌ Удалить", callback_data=f"projdash:delete:{pid}")],
    ])
    text = (
        f"📊 Проект: {channel}\n\n"
        f"Тема: {theme}\n"
        f"Частота: {freq}\n"
        f"Время: {ptime}\n"
        f"Источники: {srcs}\n"
        f"Автопостинг: {status}\n"
        f"Следующий пост: {next_run}\n"
        f"Последний пост: {last_post_at}" + (f"\nОшибка: {last_error}" if last_error else "")
    )
    if isinstance(chat_obj, types.CallbackQuery):
        await chat_obj.message.answer(text, reply_markup=kb)
    else:
        await chat_obj.answer(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("projopen:"))
async def open_project_from_list(callback: types.CallbackQuery):
    pid = callback.data.split(":", 1)[1]
    record = get_user_record(DATA_FILE, callback.from_user.id)
    project = next((p for p in record.get("projects", []) if p.get("id") == pid), None)
    if not project:
        await callback.answer("Проект не найден", show_alert=True)
        return
    await send_project_dashboard(callback, project)
    await callback.answer()


@dp.message(F.text == BTN_CREATE_PROJECT)
async def open_project_hub(message: types.Message, state: FSMContext):
    if not await ensure_premium(message):
        return
    await state.set_state(ProjectState.intro)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✨ Начать", callback_data="proj:start")]])
    await message.answer(
        "🚀 Создание проекта.\n\n"
        "Я помогу подключить канал,\n"
        "выбрать тему\n"
        "и настроить автопостинг.\n\n"
        "Это займёт пару минут 👍.",
        reply_markup=kb,
    )


@dp.message(F.text == BTN_PROJECT_WIZARD)
async def start_project_wizard(message: types.Message, state: FSMContext):
    await state.set_state(ProjectState.channel_ready)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Канал готов", callback_data="proj:channel_ready")]])
    await message.answer(
        "STEP 1 — Создание канала\n\n"
        "Создай Telegram канал:\n"
        "Telegram → Новый канал → Название → Готово.\n\n"
        "Если канал уже есть — отлично.",
        reply_markup=kb,
    )


@dp.callback_query(F.data == "proj:start")
async def project_step_1_intro(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ProjectState.channel_ready)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Канал готов", callback_data="proj:channel_ready")]])
    await callback.message.answer(
        "STEP 1 — Создание канала\n\n"
        "Создай Telegram канал:\n"
        "Telegram → Новый канал → Название → Готово.\n\n"
        "Если канал уже есть — отлично.",
        reply_markup=kb,
    )
    await callback.answer()


@dp.callback_query(F.data == "proj:channel_ready")
async def project_step_2_username_prompt(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ProjectState.username)
    await callback.message.answer(
        "STEP 2 — Username\n\n"
        "Нужен username канала. Это ссылка после @\n"
        "Примеры: @crypto_news, @my_ai_blog\n\n"
        "Где найти: канал → информация → публичная ссылка.\n"
        "Отправь username:",
    )
    await callback.answer()


@dp.message(ProjectState.username)
async def project_step_2_username(message: types.Message, state: FSMContext):
    username = (message.text or "").strip()
    if not username.startswith("@"):
        await message.answer("⚠️ Username должен начинаться с @. Пример: @my_ai_blog")
        return
    await state.update_data(channel_username=username, project_step=2)
    await state.set_state(ProjectState.access_check)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔎 Проверить доступ", callback_data="proj:check_access")]])
    await message.answer(
        "STEP 3 — Доступ бота\n\n"
        "Добавь бота в админы канала и включи:\n"
        "✅ публиковать\n✅ редактировать",
        reply_markup=kb,
    )


@dp.callback_query(F.data == "proj:check_access")
async def project_step_3_check_access(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    username = data.get("channel_username", "")
    if not username:
        await callback.message.answer("Сначала укажи username канала")
        await callback.answer()
        return
    try:
        chat = await bot.get_chat(username)
        me = await bot.get_me()
        member = await bot.get_chat_member(chat.id, me.id)
        if member.status not in {"administrator", "creator"}:
            await callback.message.answer("❌ Бот не администратор канала.")
            await callback.answer()
            return
        await state.update_data(channel_id=chat.id, project_step=3)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка проверки доступа: {e}")
        await callback.answer()
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="AI", callback_data="proj:theme:AI"), InlineKeyboardButton(text="Крипто", callback_data="proj:theme:Крипто")],
        [InlineKeyboardButton(text="Новости", callback_data="proj:theme:Новости"), InlineKeyboardButton(text="Бизнес", callback_data="proj:theme:Бизнес")],
        [InlineKeyboardButton(text="Своя тема", callback_data="proj:theme:custom")],
    ])
    await state.set_state(ProjectState.theme_pick)
    await callback.message.answer("STEP 4 — Выбери тему", reply_markup=kb)
    await callback.answer("Доступ подтверждён")


@dp.callback_query(F.data.startswith("proj:theme:"))
async def project_step_4_theme(callback: types.CallbackQuery, state: FSMContext):
    value = callback.data.split(":", 2)[2]
    if value == "custom":
        await state.set_state(ProjectState.custom_theme)
        await callback.message.answer("Опиши свою тему (1-2 предложения)")
        await callback.answer()
        return
    await state.update_data(theme=value, custom_theme="", project_step=4)
    await project_examples_prompt(callback.message, state)
    await callback.answer()


@dp.message(ProjectState.custom_theme)
async def project_step_4_custom_theme(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 4:
        await message.answer("Слишком коротко. Опиши тему подробнее.")
        return
    await state.update_data(theme="Своя тема", custom_theme=text, project_step=4)
    await project_examples_prompt(message, state)


async def project_examples_prompt(message: types.Message, state: FSMContext):
    await state.set_state(ProjectState.examples)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data="proj:examples_skip")],
        [InlineKeyboardButton(text="Готово", callback_data="proj:examples_done")],
    ])
    await message.answer(
        "STEP 5 — Свой стиль\n\n"
        "Добавь 1–10 своих примеров постов.\n"
        "Я обучусь твоему стилю.",
        reply_markup=kb,
    )


@dp.message(ProjectState.examples)
async def project_step_5_examples_collect(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        return
    data = await state.get_data()
    examples = data.get("example_posts", [])
    if len(examples) >= 10:
        await message.answer("Уже сохранено 10 примеров. Нажми «Готово».")
        return
    examples.append(text)
    await state.update_data(example_posts=examples, project_step=5)
    await message.answer(f"✅ Пример сохранён ({len(examples)}/10)")


@dp.callback_query(F.data.in_(["proj:examples_skip", "proj:examples_done"]))
async def project_step_6_frequency_prompt(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ProjectState.frequency)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 пост день", callback_data="proj:freq:1")],
        [InlineKeyboardButton(text="3 поста день", callback_data="proj:freq:3")],
        [InlineKeyboardButton(text="5 постов день", callback_data="proj:freq:5")],
        [InlineKeyboardButton(text="Random", callback_data="proj:freq:random")],
    ])
    await callback.message.answer("STEP 6 — Выбери частоту", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("proj:freq:"))
async def project_step_6_frequency(callback: types.CallbackQuery, state: FSMContext):
    raw = callback.data.split(":", 2)[2]
    await state.update_data(posting_frequency=raw, project_step=6)
    await state.set_state(ProjectState.posting_time)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Фиксированное время", callback_data="proj:time:fixed")],
        [InlineKeyboardButton(text="Рандом в диапазоне", callback_data="proj:time:random")],
    ])
    await callback.message.answer("STEP 7 — Время публикации", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("proj:time:"))
async def project_step_7_time_mode(callback: types.CallbackQuery, state: FSMContext):
    mode = callback.data.split(":", 2)[2]
    await state.update_data(posting_time_mode=mode)
    if mode == "fixed":
        await callback.message.answer("Введи время в формате HH:MM (например 09:30)")
    else:
        await callback.message.answer("Введи диапазон в формате start-end (например 09:00-21:00)")
    await callback.answer()


@dp.message(ProjectState.posting_time)
async def project_step_7_time_value(message: types.Message, state: FSMContext):
    val = (message.text or "").strip()
    data = await state.get_data()

    edit_project_id = data.get("edit_project_id")
    edit_time_mode = data.get("edit_time_mode", "fixed")

    if edit_project_id:
        try:
            if edit_time_mode == "fixed":
                datetime.strptime(val, "%H:%M")
            else:
                start, end = [x.strip() for x in val.split("-", 1)]
                datetime.strptime(start, "%H:%M")
                datetime.strptime(end, "%H:%M")
        except Exception:
            if edit_time_mode == "fixed":
                await message.answer("⚠️ Неверный формат. Введи HH:MM (пример: 20:48)")
            else:
                await message.answer("⚠️ Неверный формат. Введи диапазон HH:MM-HH:MM (пример: 09:00-21:00)")
            return

        record = get_user_record(DATA_FILE, message.from_user.id)
        projects = record.get("projects", [])
        project = next((p for p in projects if p.get("id") == edit_project_id), None)
        if not project:
            await state.clear()
            await message.answer("⚠️ Проект не найден", reply_markup=user_menu(message.from_user.id))
            return

        project["posting_time"] = val
        project["updated_at"] = datetime.now().isoformat()
        project["next_run"] = (datetime.now() + timedelta(minutes=1)).isoformat()
        project["last_error"] = ""
        project.setdefault("frequency", {})["value"] = val
        project.setdefault("scheduler_settings", {})["random_mode"] = edit_time_mode == "random"
        set_user_record(DATA_FILE, message.from_user.id, record)

        await state.clear()
        await message.answer("✅ Расписание проекта обновлено")
        await send_project_dashboard(message, project)
        return

    await state.update_data(posting_time=val, project_step=7)
    await state.set_state(ProjectState.sources)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="AI генерация", callback_data="proj:src:ai")],
        [InlineKeyboardButton(text="RSS", callback_data="proj:src:rss")],
        [InlineKeyboardButton(text="Telegram каналы", callback_data="proj:src:tg")],
    ])
    await message.answer("STEP 8 — Источники", reply_markup=kb)


@dp.callback_query(F.data.startswith("proj:src:"))
async def project_step_8_sources(callback: types.CallbackQuery, state: FSMContext):
    source = callback.data.split(":", 2)[2]
    mapping = {"ai": ["AI генерация"], "rss": ["RSS"], "tg": ["Telegram каналы"]}
    await state.update_data(content_sources=mapping.get(source, ["AI генерация"]), project_step=8)
    await state.set_state(ProjectState.format_style)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="короткие посты", callback_data="proj:style:short")],
        [InlineKeyboardButton(text="аналитика", callback_data="proj:style:analysis")],
        [InlineKeyboardButton(text="с эмодзи", callback_data="proj:style:emoji")],
        [InlineKeyboardButton(text="строго деловой", callback_data="proj:style:strict")],
    ])
    await callback.message.answer("STEP 9 — Оформление", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("proj:style:"))
async def project_step_9_style(callback: types.CallbackQuery, state: FSMContext):
    style = callback.data.split(":", 2)[2]
    readable = {
        "short": "короткие посты",
        "analysis": "аналитика",
        "emoji": "с эмодзи",
        "strict": "строго деловой",
    }.get(style, "короткие посты")
    await state.update_data(post_style=readable, project_step=9)
    data = await state.get_data()
    await state.set_state(ProjectState.summary)
    summary = (
        "STEP 10 — Summary\n\n"
        f"Канал: {data.get('channel_username', '—')}\n"
        f"Тема: {data.get('theme', '—')} {data.get('custom_theme', '')}\n"
        f"Частота: {data.get('posting_frequency', '1')}\n"
        f"Источники: {', '.join(data.get('content_sources', ['AI генерация']))}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Запустить проект", callback_data="proj:launch")],
        [InlineKeyboardButton(text="✏️ Изменить", callback_data="proj:edit")],
    ])
    await callback.message.answer(summary, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "proj:edit")
async def project_edit(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ProjectState.theme_pick)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="AI", callback_data="proj:theme:AI"), InlineKeyboardButton(text="Крипто", callback_data="proj:theme:Крипто")],
        [InlineKeyboardButton(text="Новости", callback_data="proj:theme:Новости"), InlineKeyboardButton(text="Бизнес", callback_data="proj:theme:Бизнес")],
        [InlineKeyboardButton(text="Своя тема", callback_data="proj:theme:custom")],
    ])
    await callback.message.answer("Измени тему и пройди шаги заново", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "proj:launch")
async def project_launch(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    project = default_project()
    project["id"] = uuid.uuid4().hex[:8]
    project["project_id"] = project["id"]
    project["user_id"] = callback.from_user.id
    project["channel_username"] = data.get("channel_username", "")
    project["channel"] = project["channel_username"]
    project["channel_id"] = data.get("channel_id", "")
    project["theme"] = data.get("theme", "AI")
    project["custom_theme"] = data.get("custom_theme", "")
    project["topic"] = project["custom_theme"] or project["theme"]
    project["post_style"] = data.get("post_style", "короткие посты")
    project["style"] = project["post_style"]
    project["posting_frequency"] = data.get("posting_frequency", "1")
    project["posting_time"] = data.get("posting_time", "09:00")
    project["content_sources"] = data.get("content_sources", ["AI генерация"])
    project["sources"] = [x.lower() for x in project["content_sources"]]
    project["is_autopost_enabled"] = True
    project["enabled"] = True
    project["example_posts"] = data.get("example_posts", [])
    daily_posts = 1
    freq = str(project["posting_frequency"])
    if freq.isdigit():
        daily_posts = int(freq)
    if freq == "random":
        daily_posts = 3
        project["scheduler_settings"]["random_mode"] = True
    project["scheduler_settings"]["daily_posts"] = daily_posts
    project["frequency"] = {"mode": "daily", "value": project["posting_time"]}
    project["updated_at"] = datetime.now().isoformat()
    project["next_run"] = (datetime.now() + timedelta(minutes=1)).isoformat()
    project["last_post_at"] = ""
    project["last_error"] = ""

    record = get_user_record(DATA_FILE, callback.from_user.id)
    record.setdefault("projects", []).append(project)
    set_user_record(DATA_FILE, callback.from_user.id, record)
    await state.clear()

    await send_project_dashboard(callback, project)
    await callback.answer("Проект запущен")


@dp.callback_query(F.data.startswith("projdash:"))
async def project_dashboard_actions(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    action = parts[1]
    project_id = parts[2] if len(parts) > 2 else ""
    record = get_user_record(DATA_FILE, callback.from_user.id)
    projects = record.get("projects", [])
    project = next((p for p in projects if p.get("id") == project_id), None)
    if action == "delete" and project:
        record["projects"] = [p for p in projects if p.get("id") != project_id]
        set_user_record(DATA_FILE, callback.from_user.id, record)
        await callback.message.answer("❌ Проект удалён")
        await callback.answer()
        return
    if not project:
        await callback.answer("Проект не найден", show_alert=True)
        return

    if action == "auto":
        project["is_autopost_enabled"] = not project.get("is_autopost_enabled", True)
        project["enabled"] = project["is_autopost_enabled"]
        set_user_record(DATA_FILE, callback.from_user.id, record)
        await callback.message.answer(f"⏰ Автопостинг: {'ON' if project['is_autopost_enabled'] else 'OFF'}")
        await send_project_dashboard(callback, project)
        await callback.answer()
        return

    if action == "schedule":
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="1 пост/день", callback_data=f"projdashfreq:{project_id}:1"), InlineKeyboardButton(text="3 поста/день", callback_data=f"projdashfreq:{project_id}:3")],
                [InlineKeyboardButton(text="5 постов/день", callback_data=f"projdashfreq:{project_id}:5"), InlineKeyboardButton(text="Random", callback_data=f"projdashfreq:{project_id}:random")],
                [InlineKeyboardButton(text="🕒 Фикс время", callback_data=f"projdashtime:{project_id}:fixed")],
                [InlineKeyboardButton(text="🎲 Рандом диапазон", callback_data=f"projdashtime:{project_id}:random")],
            ]
        )
        await callback.message.answer("📅 Настрой частоту и время публикаций:", reply_markup=kb)
        await callback.answer()
        return

    if action == "theme":
        await state.set_state(ProjectState.edit_theme)
        await state.update_data(edit_project_id=project_id)
        await callback.message.answer("✏️ Введи новую тему проекта")
        await callback.answer()
        return

    if action == "examples":
        await state.set_state(ProjectState.edit_examples)
        await state.update_data(edit_project_id=project_id)
        await callback.message.answer("📝 Пришли новый пример поста. Можно отправлять несколько сообщений, затем нажми ⬅️ Назад.")
        await callback.answer()
        return

    if action == "style":
        await state.set_state(ProjectState.edit_style)
        await state.update_data(edit_project_id=project_id)
        await callback.message.answer("🎨 Введи стиль: короткие посты / аналитика / с эмодзи / строго деловой")
        await callback.answer()
        return

    if action == "sources":
        await state.set_state(ProjectState.edit_sources)
        await state.update_data(edit_project_id=project_id)
        await callback.message.answer("📡 Введи источники через запятую (AI генерация, RSS, Telegram каналы)")
        await callback.answer()
        return

    await callback.message.answer("Функция в разработке")
    await callback.answer()


@dp.callback_query(F.data.startswith("projdashfreq:"))
async def project_dashboard_frequency(callback: types.CallbackQuery):
    _, project_id, freq = callback.data.split(":", 2)
    record = get_user_record(DATA_FILE, callback.from_user.id)
    projects = record.get("projects", [])
    project = next((p for p in projects if p.get("id") == project_id), None)
    if not project:
        await callback.answer("Проект не найден", show_alert=True)
        return

    project["posting_frequency"] = freq
    project["updated_at"] = datetime.now().isoformat()
    project["next_run"] = (datetime.now() + timedelta(minutes=1)).isoformat()
    project["last_error"] = ""
    scheduler = project.setdefault("scheduler_settings", {})
    if freq == "random":
        scheduler["daily_posts"] = 3
        scheduler["random_mode"] = True
    else:
        scheduler["daily_posts"] = int(freq)
        scheduler["random_mode"] = False
    set_user_record(DATA_FILE, callback.from_user.id, record)
    await callback.message.answer(f"✅ Частота обновлена: {format_freq_label(freq)}")
    await send_project_dashboard(callback, project)
    await callback.answer()


@dp.callback_query(F.data.startswith("projdashtime:"))
async def project_dashboard_time_mode(callback: types.CallbackQuery, state: FSMContext):
    _, project_id, mode = callback.data.split(":", 2)
    await state.set_state(ProjectState.posting_time)
    await state.update_data(edit_project_id=project_id, edit_time_mode=mode)
    if mode == "fixed":
        await callback.message.answer("Введи время в формате HH:MM (например 20:48)")
    else:
        await callback.message.answer("Введи диапазон в формате HH:MM-HH:MM (например 09:00-21:00)")
    await callback.answer()


@dp.message(ProjectState.edit_theme)
async def project_edit_theme_value(message: types.Message, state: FSMContext):
    theme = (message.text or "").strip()
    if len(theme) < 2:
        await message.answer("⚠️ Тема слишком короткая")
        return
    data = await state.get_data()
    pid = data.get("edit_project_id")
    record = get_user_record(DATA_FILE, message.from_user.id)
    project = next((p for p in record.get("projects", []) if p.get("id") == pid), None)
    if not project:
        await state.clear()
        await message.answer("⚠️ Проект не найден", reply_markup=user_menu(message.from_user.id))
        return
    project["theme"] = theme
    project["topic"] = theme
    project["updated_at"] = datetime.now().isoformat()
    project["next_run"] = (datetime.now() + timedelta(minutes=1)).isoformat()
    project["last_error"] = ""
    set_user_record(DATA_FILE, message.from_user.id, record)
    await state.clear()
    await message.answer("✅ Тема обновлена")
    await send_project_dashboard(message, project)


@dp.message(ProjectState.edit_examples)
async def project_edit_examples_value(message: types.Message, state: FSMContext):
    example = (message.text or "").strip()
    if not example:
        return
    data = await state.get_data()
    pid = data.get("edit_project_id")
    record = get_user_record(DATA_FILE, message.from_user.id)
    project = next((p for p in record.get("projects", []) if p.get("id") == pid), None)
    if not project:
        await state.clear()
        await message.answer("⚠️ Проект не найден", reply_markup=user_menu(message.from_user.id))
        return
    project.setdefault("example_posts", []).append(example)
    project["example_posts"] = project["example_posts"][-20:]
    project["updated_at"] = datetime.now().isoformat()
    project["next_run"] = (datetime.now() + timedelta(minutes=1)).isoformat()
    project["last_error"] = ""
    set_user_record(DATA_FILE, message.from_user.id, record)
    await message.answer(f"✅ Пример добавлен. Всего: {len(project.get('example_posts', []))}")
    await send_project_dashboard(message, project)


@dp.message(ProjectState.edit_style)
async def project_edit_style_value(message: types.Message, state: FSMContext):
    style = (message.text or "").strip()
    if len(style) < 2:
        await message.answer("⚠️ Введи стиль текстом")
        return
    data = await state.get_data()
    pid = data.get("edit_project_id")
    record = get_user_record(DATA_FILE, message.from_user.id)
    project = next((p for p in record.get("projects", []) if p.get("id") == pid), None)
    if not project:
        await state.clear()
        await message.answer("⚠️ Проект не найден", reply_markup=user_menu(message.from_user.id))
        return
    project["post_style"] = style
    project["style"] = style
    project["updated_at"] = datetime.now().isoformat()
    project["next_run"] = (datetime.now() + timedelta(minutes=1)).isoformat()
    project["last_error"] = ""
    set_user_record(DATA_FILE, message.from_user.id, record)
    await state.clear()
    await message.answer("✅ Оформление обновлено")
    await send_project_dashboard(message, project)


@dp.message(ProjectState.edit_sources)
async def project_edit_sources_value(message: types.Message, state: FSMContext):
    raw = (message.text or "").strip()
    sources = [x.strip() for x in raw.split(",") if x.strip()]
    if not sources:
        await message.answer("⚠️ Введи хотя бы один источник")
        return
    data = await state.get_data()
    pid = data.get("edit_project_id")
    record = get_user_record(DATA_FILE, message.from_user.id)
    project = next((p for p in record.get("projects", []) if p.get("id") == pid), None)
    if not project:
        await state.clear()
        await message.answer("⚠️ Проект не найден", reply_markup=user_menu(message.from_user.id))
        return
    project["content_sources"] = sources
    project["sources"] = [x.lower() for x in sources]
    project["updated_at"] = datetime.now().isoformat()
    project["next_run"] = (datetime.now() + timedelta(minutes=1)).isoformat()
    project["last_error"] = ""
    set_user_record(DATA_FILE, message.from_user.id, record)
    await state.clear()
    await message.answer("✅ Источники обновлены")
    await send_project_dashboard(message, project)


@dp.message(F.text == BTN_AUTOPOST)
async def autopost_menu(message: types.Message):
    if not await ensure_premium(message):
        return
    await message.answer("📣 Классический режим автопостинга каналов", reply_markup=autopost_menu_keyboard())


@dp.message(F.text == BTN_ADD_CHANNEL)
async def add_channel(message: types.Message, state: FSMContext):
    if not await ensure_premium(message):
        return
    await state.set_state(ChannelSetupState.waiting_name)
    await message.answer("Название канала", reply_markup=back_menu())


@dp.message(ChannelSetupState.waiting_name)
async def ch_name(message: types.Message, state: FSMContext):
    await state.update_data(name=(message.text or "").strip())
    await state.set_state(ChannelSetupState.waiting_chat_id)
    await message.answer("chat_id канала (-100...)")


@dp.message(ChannelSetupState.waiting_chat_id)
async def ch_id(message: types.Message, state: FSMContext):
    chat_id = (message.text or "").strip()
    if not chat_id.startswith("-100"):
        await message.answer("Неверный chat_id")
        return
    await state.update_data(chat_id=chat_id)
    await state.set_state(ChannelSetupState.waiting_topic)
    await message.answer("Тема")


@dp.message(ChannelSetupState.waiting_topic)
async def ch_topic(message: types.Message, state: FSMContext):
    await state.update_data(topic=(message.text or "").strip())
    await state.set_state(ChannelSetupState.waiting_sample)
    await message.answer("Пример поста или '-' ")


@dp.message(ChannelSetupState.waiting_sample)
async def ch_sample(message: types.Message, state: FSMContext):
    sample = (message.text or "").strip()
    await state.update_data(sample_post="" if sample == "-" else sample)
    await state.set_state(ChannelSetupState.waiting_mode)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏱ Интервал", callback_data="mode:interval")],
            [InlineKeyboardButton(text="🕒 Фикс", callback_data="mode:fixed")],
            [InlineKeyboardButton(text="🎲 Рандом", callback_data="mode:random")],
        ]
    )
    await message.answer("Выбери режим", reply_markup=kb)


@dp.callback_query(F.data.startswith("mode:"))
async def ch_mode(callback: types.CallbackQuery, state: FSMContext):
    mode = callback.data.split(":", 1)[1]
    await state.update_data(mode=mode)
    if mode == "interval":
        await state.set_state(ChannelSetupState.waiting_interval)
        await callback.message.answer("Введите интервал в часах")
    elif mode == "fixed":
        await state.set_state(ChannelSetupState.waiting_fixed_times)
        await callback.message.answer("Введите HH:MM,HH:MM")
    else:
        await state.set_state(ChannelSetupState.waiting_random_window)
        await callback.message.answer("Введите start,end,count")
    await callback.answer()


async def save_channel(message: types.Message, state: FSMContext, mode: str, interval_hours=6, fixed_times=None, random_window=None):
    data = await state.get_data()
    record = get_user_record(DATA_FILE, message.from_user.id)
    channel = {
        "name": data["name"],
        "chat_id": int(data["chat_id"]),
        "topic": data["topic"],
        "enabled": True,
        "mode": mode,
        "interval_hours": interval_hours,
        "fixed_times": fixed_times or ["12:00"],
        "random_window": random_window or {"start": 9, "end": 21, "posts_per_day": 2},
        "next_run": (datetime.now() + timedelta(minutes=2)).isoformat(),
        "last_plan_date": "",
        "pending_today": [],
        "history": [],
        "sample_post": data.get("sample_post", ""),
    }
    record.setdefault("channels", []).append(channel)
    set_user_record(DATA_FILE, message.from_user.id, record)
    await state.clear()
    await message.answer("✅ Канал добавлен", reply_markup=user_menu(message.from_user.id))


@dp.message(ChannelSetupState.waiting_interval)
async def ch_interval(message: types.Message, state: FSMContext):
    await save_channel(message, state, mode="interval", interval_hours=max(1, int((message.text or "6").strip())))


@dp.message(ChannelSetupState.waiting_fixed_times)
async def ch_fixed(message: types.Message, state: FSMContext):
    times = [x.strip() for x in (message.text or "").split(",") if x.strip()]
    await save_channel(message, state, mode="fixed", fixed_times=times)


@dp.message(ChannelSetupState.waiting_random_window)
async def ch_random(message: types.Message, state: FSMContext):
    start, end, count = [int(x.strip()) for x in (message.text or "9,21,2").split(",")]
    await save_channel(message, state, mode="random", random_window={"start": start, "end": end, "posts_per_day": count})


@dp.message(F.text == BTN_MY)
async def my_channels(message: types.Message):
    if not await ensure_premium(message):
        return
    channels = get_user_record(DATA_FILE, message.from_user.id).get("channels", [])
    if not channels:
        await message.answer("Каналы не добавлены")
        return
    await message.answer("\n".join([f"• {c['name']} | {c['topic']} | {c['mode']}" for c in channels]))


@dp.message(F.text == BTN_GROUP)
async def group_menu(message: types.Message):
    if not await ensure_premium(message):
        return
    record = get_user_record(DATA_FILE, message.from_user.id)
    perms = record.get("group_permissions") or default_group_permissions()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{'✅' if perms.get(k) else '❌'} {k}", callback_data=f"gp:{k}")] for k in ["write", "edit", "delete", "ban", "posts"]])
    await message.answer("Группы и права", reply_markup=kb)


@dp.callback_query(F.data.startswith("gp:"))
async def group_toggle(callback: types.CallbackQuery):
    key = callback.data.split(":", 1)[1]
    record = get_user_record(DATA_FILE, callback.from_user.id)
    perms = record.get("group_permissions") or default_group_permissions()
    perms[key] = not perms.get(key, False)
    record["group_permissions"] = perms
    set_user_record(DATA_FILE, callback.from_user.id, record)
    await callback.answer("Обновлено")


@dp.message(F.text == BTN_ACCOUNT)
async def account(message: types.Message):
    if not await ensure_premium(message):
        return
    record = get_user_record(DATA_FILE, message.from_user.id)
    await message.answer(f"Аккаунт: premium={record.get('premium')} | projects={len(record.get('projects', []))}")


async def autopost_loop():
    while True:
        try:
            users = load_users(DATA_FILE)
            now = datetime.now()
            for user_id, record in users.items():
                if not (record.get("group_permissions") or default_group_permissions()).get("posts", True):
                    continue
                for ch in record.get("channels", []):
                    ensure_channel_defaults(ch)
                    if not ch.get("enabled") or not is_due(ch, now):
                        continue
                    prompt = build_post_prompt(ch)
                    post = ""
                    for _ in range(3):
                        candidate = ask_llm(openai_client, OPENROUTER_MODEL, OPENROUTER_API_KEY, "Ты редактор Telegram-канала", prompt, max_tokens=500)
                        if candidate and not hash_exists(ch, candidate):
                            post = candidate
                            break
                    post = post or "⚠️ Не удалось сгенерировать уникальный пост"
                    if bot is not None:
                        await bot.send_message(ch["chat_id"], f"📣 {post}")
                    add_history_text(ch, post)
                    mark_sent(ch, now)

                for p in record.get("projects", []):
                    if not p.get("enabled"):
                        continue
                    p.setdefault("next_run", (now + timedelta(minutes=1)).isoformat())
                    try:
                        next_run = datetime.fromisoformat(p["next_run"])
                    except Exception:
                        next_run = now
                    if now < next_run:
                        continue

                    destination = p.get("channel_username") or p.get("channel")
                    if not destination:
                        p["last_error"] = "Не указан канал проекта"
                        p["next_run"] = (now + timedelta(minutes=10)).isoformat()
                        continue

                    prompt = (
                        f"Канал: {destination}\n"
                        f"Тема: {p.get('topic') or p.get('theme')}\n"
                        f"Стиль: {p.get('post_style')}\n"
                        f"Источники: {', '.join(p.get('content_sources', ['AI генерация']))}\n"
                        f"Примеры: {' || '.join(p.get('example_posts', [])[:5])}"
                    )
                    post = ask_llm(openai_client, OPENROUTER_MODEL, OPENROUTER_API_KEY, "Ты создаёшь пост для Telegram-канала пользователя", prompt, max_tokens=450)
                    if bot is not None:
                        try:
                            await bot.send_message(destination, post)
                            p.setdefault("history", []).append({"ts": now.isoformat(), "text": post[:400]})
                            p["history"] = p["history"][-50:]
                            p["last_post_at"] = now.isoformat()
                            p["last_error"] = ""
                        except Exception as send_err:
                            p["last_error"] = str(send_err)
                            try:
                                await bot.send_message(int(user_id), f"⚠️ Не удалось отправить пост в {destination}: {send_err}")
                            except Exception:
                                pass
                    p["updated_at"] = now.isoformat()
                    p["next_run"] = (now + timedelta(minutes=next_project_interval_minutes(p))).isoformat()
                users[user_id] = record
            save_users(DATA_FILE, users)
        except Exception as e:
            print("AUTPOST ERROR:", e)
        await asyncio.sleep(30)


async def reminder_loop():
    while True:
        try:
            users = load_users(DATA_FILE)
            now = datetime.now()
            today_key = now.strftime("%Y-%m-%d")
            for user_id, record in users.items():
                profile = record.get("user_life_profile") or {}
                rem = profile.get("reminder_settings", {})
                mode = rem.get("mode", "off")
                if mode == "off":
                    continue
                due = mode == "daily" or (mode == "weekly" and now.weekday() == 0) or (mode == "monthly" and now.day == 1)
                if due and rem.get("last_sent") != today_key and bot is not None:
                    await bot.send_message(
                        int(user_id),
                        f"Сегодня:\n{profile.get('daily_plan','-')}\n\nНеделя:\n{profile.get('weekly_plan','-')}\n\nМесяц:\n{profile.get('monthly_plan','-')}",
                    )
                    rem["last_sent"] = today_key
                    profile["reminder_settings"] = rem
                    record["user_life_profile"] = profile
                    users[user_id] = record
            save_users(DATA_FILE, users)
        except Exception as e:
            print("REMINDER ERROR:", e)
        await asyncio.sleep(60)


@dp.message()
async def fallback(message: types.Message):
    await message.answer("Используй меню 👇", reply_markup=user_menu(message.from_user.id))


async def main():
    global bot
    err = build_token_error()
    if err:
        raise RuntimeError(err)
    bot = Bot(BOT_TOKEN)
    asyncio.create_task(autopost_loop())
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
