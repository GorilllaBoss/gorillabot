from aiogram.fsm.state import State, StatesGroup


class AccessCodeState(StatesGroup):
    waiting_code = State()


class AssistantState(StatesGroup):
    waiting_question = State()


class CryptoState(StatesGroup):
    waiting_coin = State()


class PsychologyState(StatesGroup):
    waiting_mode = State()
    waiting_question = State()
    waiting_contact = State()


class EsotericState(StatesGroup):
    waiting_system = State()
    waiting_question = State()


class NavigatorState(StatesGroup):
    waiting_message = State()


class ChannelSetupState(StatesGroup):
    waiting_name = State()
    waiting_chat_id = State()
    waiting_topic = State()
    waiting_sample = State()
    waiting_mode = State()
    waiting_interval = State()
    waiting_fixed_times = State()
    waiting_random_window = State()
