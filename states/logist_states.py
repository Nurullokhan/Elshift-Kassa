from aiogram.fsm.state import State, StatesGroup

class LogistStates(StatesGroup):
    waiting_for_contact = State()
    waiting_for_object = State()
    waiting_for_report = State()
