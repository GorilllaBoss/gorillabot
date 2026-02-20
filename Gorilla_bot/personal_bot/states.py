from aiogram.fsm.state import State, StatesGroup


class AccessCodeState(StatesGroup):
    waiting_code = State()


class AssistantState(StatesGroup):
    waiting_question = State()


class CryptoState(StatesGroup):
    waiting_coin = State()


class AiHelpState(StatesGroup):
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


class ProjectState(StatesGroup):
    waiting_channel = State()
    waiting_topic = State()
    waiting_style = State()
    waiting_formatting = State()
    waiting_frequency = State()
    waiting_sources = State()


class ChannelSetupState(StatesGroup):
    waiting_name = State()
    waiting_chat_id = State()
    waiting_topic = State()
    waiting_sample = State()
    waiting_mode = State()
    waiting_interval = State()
    waiting_fixed_times = State()
    waiting_random_window = State()
