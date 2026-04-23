from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    waiting_name = State()
    waiting_age = State()
    waiting_business_size = State()
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

    waiting_name = State()
    waiting_profession = State()
    waiting_home_region = State()
    waiting_niches = State()
