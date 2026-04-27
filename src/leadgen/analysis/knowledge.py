"""Static product / sales knowledge Henry leans on.

These blocks are folded into Henry's system prompt (both the personal
floating widget and the search-composer chat) so he can answer
product questions and give competent B2B-sales advice without
hallucinating about Convioo features that don't exist.

Keep these strings short, concrete and editable in one place: when we
ship a new feature, add a line here and Henry knows about it on the
next request without redeploying anything else.
"""

from __future__ import annotations

PRODUCT_FEATURES = """\
Что умеет Convioo:
- Поиск B2B-лидов из Google Maps / Google Places. Юзер задаёт нишу
  и регион — мы находим до 50 компаний и обогащаем каждую (сайт,
  отзывы, соцсети, рейтинг).
- AI-скоринг каждого лида под профиль продавца. Score 0-100; по нему
  лиды делятся на hot (>=75), warm (50-74), cold (<50).
- Персональная подача (advice) и черновик cold-email под каждого
  лида — пишутся Claude Haiku под конкретный лид и под то что
  продаёт юзер.
- Сессии («поиски») сохраняются: каждая сессия — это niche+region+50
  лидов. По сессиям доступна статистика (avg_score, hot/warm/cold).
- CRM-вкладка /app/leads: статусы (new/contacted/replied/won/archived),
  заметки на лид, цветные пометки (только для себя), bulk-обновления.
- Команды: общий CRM на нескольких юзеров, дедупликация лидов внутри
  команды (одна niche+region не запускается дважды).
- Henry — встроенный AI-консультант, помогает заполнять профиль и
  собирать поисковый запрос."""


SCORING_EXPLAINED = """\
Как работает AI-скор:
- Каждый лид анализируется Claude Haiku по: сайту, отзывам Google,
  рейтингу, соцсетям, описанию категории, плюс под профиль юзера
  (что он продаёт, его ниши, регион).
- Hot (>=75) — высокая совместимость + признаки что лид готов
  к разговору: рабочий сайт, активные соцсети, рейтинг 4+, 30+ отзывов.
- Warm (50-74) — релевантен, но что-то слабое: устаревший сайт,
  мало отзывов, или сегмент чуть шире целевого.
- Cold (<50) — низкая совместимость или явные red flags (нет сайта,
  нет контактов, плохой рейтинг)."""


SALES_PRINCIPLES = """\
B2B-sales принципы которыми ты опираешься как консультант:
- ICP (Ideal Customer Profile) — это не «B2B вообще», это конкретный
  тип бизнеса + размер + цифровая зрелость + триггер покупки.
- Сегментация: лучше 50 точно подходящих лидов, чем 500 «всех подряд».
- Personalisation: первое касание должно ссылаться на что-то
  конкретное у лида (последний пост, новая локация, особенность сайта).
- Outbound-метрики: hot-rate <15% обычно значит размытый ICP;
  reply-rate <5% — слабая подача; conversion <10% — не та оферта.
- Не давишь со скидкой и созвонами в первом письме. Один soft CTA.
- Ниша определяется по тому что бизнес делает, не по индустрии:
  «барбершоп», «стоматологическая клиника», «юр.фирма по корп.праву».
- Регион — конкретный город, не страна и не «вся Европа»."""


WORKFLOW_TIPS = """\
Как юзер обычно работает с Convioo:
1. Заполняет профиль (что продаёт + ниши + регион + размер бизнеса).
   Чем точнее профиль — тем точнее скор лидов.
2. Запускает поиск: niche + region + (опционально) идеальный клиент,
   exclusions, языки. Henry помогает уточнить параметры в чате.
3. Получает 50 лидов через 60-120 секунд. Сортирует по hot/warm/cold.
4. Открывает hot-лиды, изучает summary/strengths/weaknesses, читает
   AI-совет «как презентовать», копирует cold-email черновик.
5. В CRM ведёт статусы и заметки. Когда сделка идёт — меняет lead_status."""


def all_blocks() -> str:
    """Concatenate all knowledge blocks for inlining into a system prompt."""
    return "\n\n".join(
        [
            PRODUCT_FEATURES,
            SCORING_EXPLAINED,
            SALES_PRINCIPLES,
            WORKFLOW_TIPS,
        ]
    )
