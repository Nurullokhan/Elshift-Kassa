from aiogram.fsm.state import State, StatesGroup

class LogistStates(StatesGroup):
    waiting_for_contact = State()
    waiting_for_object = State()
    waiting_for_action = State()
    waiting_for_items_text = State()
    waiting_for_items_photo = State()
    waiting_for_items_video = State()
