from aiogram.fsm.state import State, StatesGroup


class AccessCodeState(StatesGroup):
    waiting_code = State()


class AssistantState(StatesGroup):
    waiting_question = State()


class CryptoState(StatesGroup):
    waiting_coin = State()
    waiting_followup = State()


class PsychologyState(StatesGroup):
    waiting_mode = State()
    waiting_question = State()


class EsotericState(StatesGroup):
    waiting_system = State()
    waiting_payload = State()


class NavigatorState(StatesGroup):
    onboarding = State()
    coach = State()
    update = State()
    reminders = State()
    edit_goals = State()
    edit_today = State()


class ProjectState(StatesGroup):
    intro = State()
    channel_ready = State()
    username = State()
    access_check = State()
    theme_pick = State()
    custom_theme = State()
    examples = State()
    frequency = State()
    posting_time = State()
    sources = State()
    format_style = State()
    summary = State()
    edit_theme = State()
    edit_examples = State()
    edit_sources = State()
    edit_style = State()


class ChannelSetupState(StatesGroup):
    waiting_name = State()
    waiting_chat_id = State()
    waiting_topic = State()
    waiting_sample = State()
    waiting_mode = State()
    waiting_interval = State()
    waiting_fixed_times = State()
    waiting_random_window = State()
