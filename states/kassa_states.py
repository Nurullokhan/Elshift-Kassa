from aiogram.fsm.state import State, StatesGroup


class KassaState(StatesGroup):
    """Yagona holat — foydalanuvchi '100000 - Izoh' formatida yozadi."""
    input = State()
