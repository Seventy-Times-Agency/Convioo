from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    waiting_profession = State()
    waiting_home_region = State()
    waiting_niches = State()


class SearchStates(StatesGroup):
    waiting_niche = State()
    choosing_ai_niche = State()
    waiting_region = State()
    confirming = State()


class ProfileEditStates(StatesGroup):
    """Used when the user wants to update a specific profile field."""

    waiting_profession = State()
    waiting_home_region = State()
    waiting_niches = State()
