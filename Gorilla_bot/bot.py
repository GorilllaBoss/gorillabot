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

from personal_bot.config import ACCESS_CODE, BOT_TOKEN, DATA_FILE, OPENROUTER_API_KEY, OPENROUTER_MODEL, build_token_error
from personal_bot.scheduler import add_history_text, build_post_prompt, ensure_channel_defaults, hash_exists, is_due, mark_sent
from personal_bot.services import ask_llm, fetch_crypto_snapshot
from personal_bot.states import AccessCodeState, AiHelpState, AssistantState, ChannelSetupState, CryptoState, EsotericState, NavigatorState, ProjectState
from personal_bot.storage import default_group_permissions, default_life_profile, default_project, get_user_record, load_users, save_users, set_user_record, user_has_premium
from personal_bot.ui import (
    BTN_ACCESS,
    BTN_ACCOUNT,
    BTN_ADD_CHANNEL,
    BTN_AI,
    BTN_AI_HELP,
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

ESOTERIC_MENU = {
    "🃏 Таро": "Введи: ситуация + вопрос + горизонт (дни/недели)",
    "🔮 Оракулы": "Введи: запрос + что хочешь получить на выходе",
    "ᚱ Руны": "Введи: контекст + цель на 30 дней",
    "☯️ И-цзин": "Введи: ситуация / выбор А / выбор Б",
    "☕ Интуитивные методы": "Введи: эмоция дня + главный вопрос",
    "⭐ Западная астрология": "Введи: ДД.ММ.ГГГГ ЧЧ:ММ Город",
    "🪐 Джйотиш": "Введи: ДД.ММ.ГГГГ ЧЧ:ММ Город",
    "🐉 Китайская астрология": "Введи: ДД.ММ.ГГГГ Пол + вопрос",
    "🌙 Лунная астрология": "Введи: дата + цель месяца + вопрос",
    "🔢 Пифагор": "Введи: ДД.ММ.ГГГГ",
    "🧾 Каббалистическая": "Введи: ФИО + ДД.ММ.ГГГГ",
    "🧩 Матрица судьбы": "Введи: ДД.ММ.ГГГГ + ключевой вопрос",
    "🧠 Human Design": "Введи: ДД.ММ.ГГГГ ЧЧ:ММ Город",
    "🧠 Соционика": "Введи: 3 типичных сценария общения",
    "🧠 MBTI": "Введи: как принимаешь решения + что заряжает",
    "🧠 Эннеаграмма": "Введи: мотивация + главный страх",
    "🌀 Чакры": "Введи: самочувствие + эмоции + запрос",
    "✨ Рейки": "Введи: энергия (1-10) + стресс + цель",
    "🧿 Карма": "Введи: повторяющийся сценарий + желаемый сдвиг",
    "✋ Хиромантия": "Введи: описание ладони + вопрос",
    "🙂 Физиогномика": "Введи: черты лица + вопрос",
    "🏡 Фэншуй": "Введи: тип пространства + проблема + цель",
    "📆 Ба-цзы": "Введи: ДД.ММ.ГГГГ ЧЧ:ММ Пол",
    "🥋 Цигун": "Введи: уровень подготовки + цель + ограничения",
}


def user_menu(user_id: int):
    return main_menu(user_has_premium(DATA_FILE, user_id))


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
    if random.random() < 0.2:
        return "Можно странный вопрос? Если деньги не проблема — чем займёшься в ближайший год?"
    seen = profile.get("onboarding_topics", [])
    available = [x for x in TOPIC_QUESTIONS if x not in seen] or list(TOPIC_QUESTIONS)
    topic = random.choice(available)
    seen.append(topic)
    profile["onboarding_topics"] = seen
    return TOPIC_QUESTIONS[topic]


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


async def ensure_premium(message: types.Message) -> bool:
    if user_has_premium(DATA_FILE, message.from_user.id):
        return True
    await message.answer("🔐 Функция доступна после кода. Нажми «🔐 Премиум услуги».", reply_markup=user_menu(message.from_user.id))
    return False


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer("🚀 GorillaAI. Выбери раздел.", reply_markup=user_menu(message.from_user.id))


@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    await message.answer("🏠 Главное меню", reply_markup=user_menu(message.from_user.id))


@dp.message(F.text == BTN_BACK)
async def back_to_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("⬅️ Возврат в меню", reply_markup=user_menu(message.from_user.id))


@dp.message(F.text == BTN_ACCESS)
@dp.message(Command("access"))
async def cmd_access(message: types.Message, state: FSMContext):
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


@dp.message(F.text == BTN_AI_HELP)
async def ai_help_menu(message: types.Message, state: FSMContext):
    if not await ensure_premium(message):
        return
    await state.set_state(AiHelpState.waiting_mode)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧠 Помощь ИИ агент", callback_data="help:ai")],
            [InlineKeyboardButton(text="📞 Психолог онлайн", callback_data="help:online")],
        ]
    )
    await message.answer("Выбери формат помощи", reply_markup=kb)


@dp.callback_query(F.data.startswith("help:"))
async def ai_help_mode(callback: types.CallbackQuery, state: FSMContext):
    mode = callback.data.split(":", 1)[1]
    if mode == "online":
        await state.clear()
        await callback.message.answer("Психолог онлайн: @aggressive_chik")
    else:
        await state.set_state(AiHelpState.waiting_question)
        await callback.message.answer("Опиши ситуацию")
    await callback.answer()


@dp.message(AiHelpState.waiting_question)
async def ai_help_run(message: types.Message):
    answer = await run_llm_with_status(
        message,
        status_for("assistant"),
        lambda: ask_llm(openai_client, OPENROUTER_MODEL, OPENROUTER_API_KEY, "Ты ИИ-агент помощи: умный, живой, поддерживающий, немного дерзкий.", (message.text or ""), max_tokens=700),
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
        return

    if user_count % 3 == 0:
        await message.answer("⚡ Похоже, ты практик: быстро переводишь мысли в действия.")
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
        await message.answer("🎯 Мои цели:\n" + "\n".join(f"• {x}" for x in profile.get("goals", [])))
    elif message.text == NAV_BTN_PROFILE:
        await message.answer(f"📊 Архетип: {profile.get('archetype')}\n\n{profile.get('ai_analysis','')[:3500]}")
    elif message.text == NAV_BTN_TODAY:
        await message.answer(f"📅 План сегодня:\n{profile.get('daily_plan')}")
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
    await callback.message.answer(f"{name}\n{ESOTERIC_MENU[name]}")
    await callback.answer()


@dp.message(EsotericState.waiting_payload)
async def esoteric_run(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data.get("esoteric_name")
    payload = (message.text or "").strip()
    if not payload or len(payload) < 8:
        await message.answer("Добавь больше данных по формату")
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
    await message.answer("Введи coin id (bitcoin, ethereum, solana)", reply_markup=back_menu())


@dp.message(CryptoState.waiting_coin)
async def crypto_run(message: types.Message, state: FSMContext):
    coin = (message.text or "").strip().lower()
    if not coin:
        await message.answer("Нужен coin id")
        return
    snapshot = fetch_crypto_snapshot(coin)
    if not snapshot:
        await message.answer("Монета не найдена")
        return
    prompt = f"Монета {coin}, usd={snapshot.get('usd')}, change24={snapshot.get('usd_24h_change')}, cap={snapshot.get('usd_market_cap')}"
    answer = await run_llm_with_status(message, status_for("crypto"), lambda: ask_llm(openai_client, OPENROUTER_MODEL, OPENROUTER_API_KEY, "Ты крипто-аналитик", prompt, max_tokens=450))
    await state.clear()
    await message.answer(answer, reply_markup=user_menu(message.from_user.id))


@dp.message(F.text == BTN_PROJECTS)
async def my_projects(message: types.Message):
    if not await ensure_premium(message):
        return
    projects = get_user_record(DATA_FILE, message.from_user.id).get("projects", [])
    if not projects:
        await message.answer("Проектов пока нет")
        return
    await message.answer("\n".join([f"• {p.get('topic')} | {p.get('channel')} | {'ON' if p.get('enabled') else 'OFF'}" for p in projects]))


@dp.message(F.text == BTN_CREATE_PROJECT)
async def open_project_hub(message: types.Message):
    if not await ensure_premium(message):
        return
    await message.answer(
        "🚀 Создать проект\n\n"
        "Что это даёт:\n"
        "• подключаешь СВОЙ канал и настраиваешь его под себя\n"
        "• выбираешь тему, стиль, формат, частоту и источники\n"
        "• включаешь индивидуальный автопостинг (вплоть до рандома)\n"
        "• ИИ ведёт твой канал: генерирует и публикует контент по правилам проекта\n\n"
        "Нажми «✨ Запустить мастер проекта» и пройди пошаговую настройку.",
        reply_markup=project_hub_keyboard(),
    )


@dp.message(F.text == BTN_PROJECT_WIZARD)
async def create_project(message: types.Message, state: FSMContext):
    if not await ensure_premium(message):
        return
    await state.set_state(ProjectState.waiting_channel)
    await message.answer("STEP 1/8: подключи свой канал — отправь @channel_username\n\nПример: @my_channel")


@dp.message(ProjectState.waiting_channel)
async def p_channel(message: types.Message, state: FSMContext):
    channel = (message.text or "").strip()
    if not channel.startswith("@"):
        await message.answer("Нужен @channel")
        return
    await state.update_data(channel=channel)
    await state.set_state(ProjectState.waiting_topic)
    await message.answer("STEP 2: тема проекта")


@dp.message(ProjectState.waiting_topic)
async def p_topic(message: types.Message, state: FSMContext):
    await state.update_data(topic=(message.text or "").strip())
    await state.set_state(ProjectState.waiting_style)
    await message.answer("STEP 3: стиль (expert/analytical/hype/funny/news)")


@dp.message(ProjectState.waiting_style)
async def p_style(message: types.Message, state: FSMContext):
    await state.update_data(style=(message.text or "").strip())
    await state.set_state(ProjectState.waiting_formatting)
    await message.answer("STEP 4: формат yes/no,yes/no,yes/no,signature")


@dp.message(ProjectState.waiting_formatting)
async def p_format(message: types.Message, state: FSMContext):
    parts = [x.strip() for x in (message.text or "").split(",")]
    if len(parts) < 4:
        await message.answer("Формат: yes/no,yes/no,yes/no,signature")
        return
    await state.update_data(formatting={"emojis": parts[0] == "yes", "cta": parts[1] == "yes", "hashtags": parts[2] == "yes", "signature": parts[3]})
    await state.set_state(ProjectState.waiting_frequency)
    await message.answer("STEP 5: частота interval:6 / daily / times:09:00|18:00")


@dp.message(ProjectState.waiting_frequency)
async def p_frequency(message: types.Message, state: FSMContext):
    raw = (message.text or "").strip().lower()
    frequency = {"mode": "interval", "value": 6}
    if raw.startswith("interval:"):
        frequency = {"mode": "interval", "value": max(1, int(raw.split(":", 1)[1]))}
    elif raw == "daily":
        frequency = {"mode": "daily", "value": "09:00"}
    elif raw.startswith("times:"):
        frequency = {"mode": "times", "value": raw.split(":", 1)[1].split("|")}
    await state.update_data(frequency=frequency)
    await state.set_state(ProjectState.waiting_sources)
    await message.answer("STEP 6: источники через запятую (gpt,rss,api,scrape)")


@dp.message(ProjectState.waiting_sources)
async def p_sources_and_confirm(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if "project_previewed" not in data:
        sources = [x.strip() for x in (message.text or "gpt").split(",") if x.strip()]
        project = default_project()
        project.update(data)
        project["id"] = uuid.uuid4().hex[:8]
        project["sources"] = sources
        preview = await run_llm_with_status(
            message,
            status_for("assistant"),
            lambda: ask_llm(openai_client, OPENROUTER_MODEL, OPENROUTER_API_KEY, "Сгенерируй preview поста", str(project), max_tokens=350),
        )
        await state.update_data(project=project, project_previewed=True)
        await message.answer(f"STEP 7 Preview:\n{preview}\n\nSTEP 8: отправь start для запуска")
        return

    if (message.text or "").strip().lower() != "start":
        await message.answer("Отправь start для запуска проекта")
        return
    project = data.get("project")
    project["enabled"] = True
    record = get_user_record(DATA_FILE, message.from_user.id)
    record.setdefault("projects", []).append(project)
    set_user_record(DATA_FILE, message.from_user.id, record)
    await state.clear()
    await message.answer("✅ Проект автопостинга запущен", reply_markup=user_menu(message.from_user.id))


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
                    p.setdefault("next_run", (now + timedelta(hours=1)).isoformat())
                    if now < datetime.fromisoformat(p["next_run"]):
                        continue
                    post = ask_llm(openai_client, OPENROUTER_MODEL, OPENROUTER_API_KEY, "SaaS autopost generator", str(p), max_tokens=450)
                    if bot is not None:
                        await bot.send_message(p.get("channel"), post)
                    hours = int(p.get("frequency", {}).get("value", 6)) if p.get("frequency", {}).get("mode") == "interval" else 24
                    p["next_run"] = (now + timedelta(hours=hours)).isoformat()
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
