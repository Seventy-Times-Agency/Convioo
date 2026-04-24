"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

/**
 * Minimal i18n for the open-demo web app.
 *
 * One flat dictionary per locale, looked up by dotted keys. No
 * interpolation, no pluralization — when a string needs a runtime
 * value the caller should pass the translated template to a helper
 * that does the substitution.
 *
 * Persists the selection in localStorage under "leadgen.lang"; defaults
 * to Russian because the team that QAs the site is Russian-speaking.
 */

export type Locale = "ru" | "en";

const STORAGE_KEY = "leadgen.lang";

const TRANSLATIONS = {
  ru: {
    // Shared / buttons
    "common.newSearch": "Новый поиск",
    "common.cancel": "Отмена",
    "common.save": "Сохранить",
    "common.saving": "Сохраняю…",
    "common.viewAll": "Все →",
    "common.openCrm": "Открыть CRM →",
    "common.back": "Назад",
    "common.signIn": "Войти",
    "common.loading": "Загрузка…",
    "common.retry": "Повторить",
    "common.none": "—",
    "common.export": "Экспорт",
    "common.excel": "Excel",
    "common.edit": "Изменить",
    "common.invite": "Пригласить",

    // Language switcher
    "lang.switch": "Язык",

    // Sidebar
    "nav.workspace": "Рабочее пространство",
    "nav.team": "Команда",
    "nav.dashboard": "Дашборд",
    "nav.newSearch": "Новый поиск",
    "nav.sessions": "Сессии",
    "nav.leads": "Все лиды",
    "nav.teamPage": "Команда",
    "nav.profile": "Мой профиль",
    "nav.settings": "Настройки",

    // Landing
    "landing.nav.signIn": "Войти",
    "landing.nav.register": "Регистрация",
    "landing.hero.eyebrow": "B2B-интеллект по лидам — готово за 90 секунд",
    "landing.hero.titlePre": "Первые",
    "landing.hero.titleAccent": "50 компаний,",
    "landing.hero.titlePost1": "которые действительно",
    "landing.hero.titlePost2": "подходят вам.",
    "landing.hero.subtitle":
      "Опишите кого вы продаёте. Мы достаём каждое совпадение из Google Places, проходимся по их сайтам и отзывам, и возвращаем список, размеченный AI, с персональной подачей для каждого.",
    "landing.stats.time": "Среднее время",
    "landing.stats.perQuery": "Лидов за запрос",
    "landing.stats.accuracy": "Точность контактов",
    "landing.stats.speed": "Быстрее ручного поиска",
    "landing.how.eyebrow": "Как это работает",
    "landing.how.title1": "От ниши до",
    "landing.how.titleItalic": "готового к холодному касанию",
    "landing.how.title2": "списка — без рутины.",
    "landing.how.01.title": "Опишите цель",
    "landing.how.01.body":
      "Введите нишу и регион. Всё — никакого матричного фильтра, никаких форм. Ассистент поможет сузить охват если нужно.",
    "landing.how.02.title": "Ищем, обогащаем, оцениваем",
    "landing.how.02.body":
      "Забираем совпадения из Google Places, заходим на каждый сайт, собираем соцсети и отзывы, прогоняем лидов через Claude для персональной оценки.",
    "landing.how.03.title": "Ведём в CRM",
    "landing.how.03.body":
      "Каждый лид получает AI-пчикап под ваше предложение. Ставьте статусы, заметки, передавайте команде, выгружайте в Excel.",
    "landing.cta.title1": "Хватит искать лидов вручную.",
    "landing.cta.title2": "Начните закрывать сделки.",
    "landing.cta.primary": "Создать аккаунт",
    "landing.cta.secondary": "Посмотреть прототип",
    "landing.footer.built": "© 2026 Leadgen. Для агентств.",
    "landing.footer.privacy": "Приватность",
    "landing.footer.terms": "Условия",
    "landing.footer.contact": "Контакты",

    // Preview (fake browser chrome on landing)
    "preview.session": "Сессия",
    "preview.analyzed": "{n} лидов проанализировано",
    "preview.hot": "Горячие",
    "preview.warm": "Тёплые",
    "preview.cold": "Холодные",

    // Auth (stubs)
    "auth.login.title": "С возвращением.",
    "auth.login.subtitle":
      "Регистрация и вход добавятся вместе с обычным логином. Пока демо — заходите сразу.",
    "auth.login.enter": "Войти в рабочее пространство",
    "auth.login.back": "На главную",
    "auth.login.demoNote":
      "Заметка: публичная демо-версия работает без аккаунтов. Telegram-вход и email-ссылки добавим ближе к релизу.",
    "auth.register.title": "Присоединяйтесь к команде.",
    "auth.register.subtitle":
      "Регистрация откроется когда будет готов логин. Демо-воркспейс открыт по ссылке.",
    "auth.register.enter": "Открыть демо",
    "auth.inside.eyebrow": "Внутри",
    "auth.inside.body":
      "50 лидов с AI-оценкой в каждом поиске. Персонализировано под то, что продаёте именно вы.",
    "auth.inside.tags": "Google Places · Claude Haiku · Живое обогащение",

    // Dashboard
    "dashboard.topbar.greetingMorning": "Доброе утро",
    "dashboard.topbar.greetingAfternoon": "Добрый день",
    "dashboard.topbar.subtitle": "Что происходит в вашей рабочей зоне.",
    "dashboard.stats.sessions": "Сессий запущено",
    "dashboard.stats.sessionsSub": "{n} сейчас активно",
    "dashboard.stats.leads": "Лидов проанализировано",
    "dashboard.stats.leadsSub": "во всех сессиях",
    "dashboard.stats.hot": "Горячих лидов",
    "dashboard.stats.hotSub": "готовы к контакту",
    "dashboard.stats.rest": "Тёплые + холодные",
    "dashboard.stats.restSub": "стоят второго прохода",
    "dashboard.recent.eyebrow": "Недавние сессии",
    "dashboard.recent.title": "Ваши поиски",
    "dashboard.empty.title": "Поисков пока нет",
    "dashboard.empty.body": "Запустите первый поиск из сайдбара — занимает около 90 секунд.",
    "dashboard.quick.eyebrow": "Начать сейчас",
    "dashboard.quick.title": "Быстрые действия",
    "dashboard.quick.launch.title": "Запустить новый поиск",
    "dashboard.quick.launch.body":
      "Опишите целевую нишу и регион. Lumen возьмёт остальное на себя.",
    "dashboard.quick.leads.title": "Открыть базу лидов",
    "dashboard.quick.leads.body":
      "Ищите, фильтруйте и ведите каждого собранного лида.",
    "dashboard.hot.eyebrow": "Горячие за неделю",
    "dashboard.hot.title": "Лиды с лучшим скором",

    // Session row
    "session.row.running": "Выполняется — {status}",
    "session.row.failed": "Ошибка — {err}",
    "session.row.summary": "{n} лидов · {hot} горячих",
    "session.row.hot": "горячих",
    "session.row.rest": "остальных",

    // New Search
    "search.crumb.workspace": "Рабочая зона",
    "search.crumb.new": "Новый поиск",
    "search.crumb.running": "Поиск выполняется",
    "search.crumb.done": "Поиск завершён",
    "search.chat.greeting":
      "Привет — я Lumen, ваш AI-ассистент по лидам. Опишите кого ищете, и я соберу список за ~90 секунд.",
    "search.chat.tryThese": "Попробуйте один из вариантов",
    "search.chat.placeholder": "Опишите кого ищете…",
    "search.chat.gotIt":
      "Понял — **{niche}** в **{region}**. Жмите «Запустить» когда готовы, или поправьте форму справа.",
    "search.chat.needBoth":
      "Укажите нишу и регион, например «кровельные компании в Нью-Йорке».",
    "search.prompts.0": "Кровельные компании в Нью-Йорке",
    "search.prompts.1": "Кофейни в Астане",
    "search.prompts.2": "Дизайнеры интерьеров в Берлине",
    "search.prompts.3": "Стоматологические клиники в Лондоне",
    "search.form.eyebrow": "Параметры поиска",
    "search.form.title": "Или заполните вручную",
    "search.form.subtitle": "Lumen дозаполнит поля по ходу диалога.",
    "search.form.niche": "Ниша",
    "search.form.nichePh": "кровельные компании",
    "search.form.region": "Регион",
    "search.form.regionPh": "Нью-Йорк, NY",
    "search.form.offer": "Что вы продаёте (для AI-оценки)",
    "search.form.offerPh":
      "например: делаю SEO-сайты для локальных подрядчиков",
    "search.form.offerHint":
      "Claude использует это чтобы персонализировать каждый скор и подачу.",
    "search.form.meta": "До 50 лидов · 60–120 секунд · живой прогресс ниже.",
    "search.form.launch": "Запустить поиск",
    "search.running.eyebrowSearching": "Ищем",
    "search.running.eyebrowDone": "Готово",
    "search.running.inGlue": "в",
    "search.running.defaultSubtitle":
      "Обычно это занимает 60–120 секунд. Оставайтесь на странице — увидите живой прогресс по фазам.",
    "search.running.phaseEyebrow": "Текущая фаза",
    "search.running.bootingPipeline": "Запускаю пайплайн…",
    "search.running.openAnyway": "Открыть сессию всё равно",
    "search.done.title": "{niche} · {region} — готово.",
    "search.done.subtitle":
      "Каждый лид оценён под ваш профиль с персональной подачей.",
    "search.done.open": "Открыть результаты",

    // Sessions list
    "sessions.title": "Сессии",
    "sessions.subtitle": "Все ваши запущенные поиски",
    "sessions.empty.title": "Сессий пока нет",
    "sessions.empty.body":
      "Запустите первый поиск из сайдбара — занимает ~90 секунд.",

    // Session detail
    "detail.crumb.sessions": "Сессии",
    "detail.status.pending": "ожидает",
    "detail.status.running": "выполняется",
    "detail.status.done": "готово",
    "detail.status.failed": "ошибка",
    "detail.source.web": "веб",
    "detail.source.telegram": "телеграм",
    "detail.stat.total": "всего",
    "detail.stat.hot": "горячих",
    "detail.stat.warm": "тёплых",
    "detail.stat.cold": "холодных",
    "detail.insights.eyebrow": "AI-инсайт рынка",
    "detail.filter.all": "Все · {n}",
    "detail.filter.hot": "Горячие · {n}",
    "detail.filter.warm": "Тёплые · {n}",
    "detail.filter.cold": "Холодные · {n}",
    "detail.empty":
      "По этой сессии пока нет лидов. Если только что завершилась — обновите через пару секунд.",

    // Leads CRM
    "crm.title": "Все лиды",
    "crm.subtitle": "{leads} лидов из {sessions} сессий",
    "crm.empty": "Лидов пока нет. Запустите первый поиск из сайдбара.",
    "crm.status.all": "все",
    "crm.status.new": "новые",
    "crm.status.contacted": "в работе",
    "crm.status.replied": "ответили",
    "crm.status.won": "сделка",
    "crm.status.archived": "архив",
    "crm.table.lead": "Лид",
    "crm.table.session": "Сессия",
    "crm.table.score": "Скор",
    "crm.table.status": "Статус",
    "crm.table.touched": "Последний контакт",
    "crm.relative.now": "только что",
    "crm.relative.m": "{n}м назад",
    "crm.relative.h": "{n}ч назад",
    "crm.relative.d": "{n}д назад",

    // Lead detail modal
    "lead.howToPitch": "Как презентовать этому лиду",
    "lead.strengths": "Сильные стороны",
    "lead.weaknesses": "Слабые стороны",
    "lead.redFlags": "Красные флаги",
    "lead.notes": "Заметки",
    "lead.notesPh": "Запишите ваши наблюдения по этому лиду…",
    "lead.status": "Статус",
    "lead.contact": "Контакт",
    "lead.rating": "отзывов",
    "lead.statusLabel.new": "новый",
    "lead.statusLabel.contacted": "в работе",
    "lead.statusLabel.replied": "ответил",
    "lead.statusLabel.won": "сделка",
    "lead.statusLabel.archived": "архив",

    // Profile
    "profile.title": "Мой профиль",
    "profile.subtitle": "Как AI оценивает лидов для вас",
    "profile.hint":
      "Профиль персонализирует каждый AI-скор и подачу. Редактирование откроется вместе с обычным логином.",
    "profile.field.business": "Размер бизнеса",
    "profile.field.region": "Домашний регион",
    "profile.field.offer": "Профессия / предложение",
    "profile.field.niches": "Целевые ниши",
    "profile.empty": "Не указано",

    // Team
    "team.title": "Команда",
    "team.subtitle": "Доступ и роли",
    "team.empty.title": "Команды пока нет",
    "team.empty.body":
      "Приглашения откроются вместе с обычным логином.",
    "team.table.member": "Участник",
    "team.table.role": "Роль",
    "team.table.active": "Последняя активность",

    // Settings
    "settings.title": "Настройки",
    "settings.subtitle": "Конфигурация рабочей зоны",
    "settings.workspace": "Рабочая зона",
    "settings.workspaceName": "Название",
    "settings.auth": "Авторизация",
    "settings.authValue": "Открытая демо-версия — логин добавим на следующем этапе",
    "settings.backend": "Бэкенд",
    "settings.health": "Состояние API",
    "settings.commit": "Задеплоенный коммит",
    "settings.unknown": "неизвестно",
    "settings.integrations": "Интеграции",
    "settings.int.googlePlaces": "Google Places",
    "settings.int.anthropic": "Anthropic (Claude)",
    "settings.int.telegram": "Telegram-бот",
    "settings.int.redis": "Очередь Redis",
    "settings.int.email": "Email-доставка",
    "settings.int.connected": "подключено",
    "settings.int.notConfigured": "не настроено",
    "settings.int.redis.connected": "worker arq обрабатывает поиски",
    "settings.int.redis.fallback":
      "inline-fallback через asyncio — включите REDIS_URL для масштаба",
    "settings.int.email.planned": "планируется с логином",
    "settings.viewPrototype": "Открыть прототип (Figma-style)",
  },
  en: {
    "common.newSearch": "New search",
    "common.cancel": "Cancel",
    "common.save": "Save",
    "common.saving": "Saving…",
    "common.viewAll": "View all →",
    "common.openCrm": "Open CRM →",
    "common.back": "Back",
    "common.signIn": "Sign in",
    "common.loading": "Loading…",
    "common.retry": "Retry",
    "common.none": "—",
    "common.export": "Export",
    "common.excel": "Excel",
    "common.edit": "Edit",
    "common.invite": "Invite",

    "lang.switch": "Language",

    "nav.workspace": "Workspace",
    "nav.team": "Team",
    "nav.dashboard": "Dashboard",
    "nav.newSearch": "New search",
    "nav.sessions": "Sessions",
    "nav.leads": "All leads",
    "nav.teamPage": "Team",
    "nav.profile": "My profile",
    "nav.settings": "Settings",

    "landing.nav.signIn": "Sign in",
    "landing.nav.register": "Sign up",
    "landing.hero.eyebrow": "B2B lead intelligence — live in 90 seconds",
    "landing.hero.titlePre": "The first",
    "landing.hero.titleAccent": "50 prospects",
    "landing.hero.titlePost1": "that actually",
    "landing.hero.titlePost2": "fit your service.",
    "landing.hero.subtitle":
      "Describe who you're selling to. We pull every match from Google Places, scan their sites and reviews, and hand you an AI-scored list with a custom pitch for each one.",
    "landing.stats.time": "Avg. search time",
    "landing.stats.perQuery": "Leads per query",
    "landing.stats.accuracy": "Contact-info accuracy",
    "landing.stats.speed": "Faster than manual",
    "landing.how.eyebrow": "How it works",
    "landing.how.title1": "From niche to",
    "landing.how.titleItalic": "outreach-ready",
    "landing.how.title2": "list, without the grunt work.",
    "landing.how.01.title": "Describe your target",
    "landing.how.01.body":
      "Type a niche and a region. That's it — no filter matrix, no form fatigue. Our assistant can help you narrow it too.",
    "landing.how.02.title": "We search, enrich, score",
    "landing.how.02.body":
      "We pull matches from Google Places, visit every site, grab socials and reviews, and pass each lead through Claude for a personalized score.",
    "landing.how.03.title": "Work them in your CRM",
    "landing.how.03.body":
      "Every lead gets an AI-written pitch tailored to your offer. Mark status, add notes, hand off to your team, export to Excel.",
    "landing.cta.title1": "Stop prospecting.",
    "landing.cta.title2": "Start closing.",
    "landing.cta.primary": "Create an account",
    "landing.cta.secondary": "Explore the prototype",
    "landing.footer.built": "© 2026 Leadgen. Built for agencies.",
    "landing.footer.privacy": "Privacy",
    "landing.footer.terms": "Terms",
    "landing.footer.contact": "Contact",

    "preview.session": "Session",
    "preview.analyzed": "{n} leads analyzed",
    "preview.hot": "Hot",
    "preview.warm": "Warm",
    "preview.cold": "Cold",

    "auth.login.title": "Welcome back.",
    "auth.login.subtitle":
      "Sign-in is coming with the next milestone. For the demo, jump straight in.",
    "auth.login.enter": "Enter the workspace",
    "auth.login.back": "Back to home",
    "auth.login.demoNote":
      "Note: the public demo runs without accounts. Telegram login + email magic-link ship before launch.",
    "auth.register.title": "Join your team.",
    "auth.register.subtitle":
      "Account signup unlocks when auth ships. The demo workspace is open to anyone with the link.",
    "auth.register.enter": "Open the demo workspace",
    "auth.inside.eyebrow": "Inside",
    "auth.inside.body":
      "50 AI-scored prospects. Every search. Personalized to what you sell.",
    "auth.inside.tags": "Google Places · Claude Haiku · Live enrichment",

    "dashboard.topbar.greetingMorning": "Good morning",
    "dashboard.topbar.greetingAfternoon": "Good afternoon",
    "dashboard.topbar.subtitle": "Here's what's happening in your workspace.",
    "dashboard.stats.sessions": "Sessions run",
    "dashboard.stats.sessionsSub": "{n} active now",
    "dashboard.stats.leads": "Leads analyzed",
    "dashboard.stats.leadsSub": "across all sessions",
    "dashboard.stats.hot": "Hot leads",
    "dashboard.stats.hotSub": "ready for outreach",
    "dashboard.stats.rest": "Warm + cold",
    "dashboard.stats.restSub": "worth a second pass",
    "dashboard.recent.eyebrow": "Recent sessions",
    "dashboard.recent.title": "Your searches",
    "dashboard.empty.title": "No searches yet",
    "dashboard.empty.body":
      "Launch your first search from the sidebar — it takes about 90 seconds.",
    "dashboard.quick.eyebrow": "Start now",
    "dashboard.quick.title": "Quick actions",
    "dashboard.quick.launch.title": "Launch a new search",
    "dashboard.quick.launch.body":
      "Describe your target niche and region. Lumen will handle the rest.",
    "dashboard.quick.leads.title": "Open the lead base",
    "dashboard.quick.leads.body":
      "Search, filter and organize every lead you've collected.",
    "dashboard.hot.eyebrow": "Hot this week",
    "dashboard.hot.title": "Top-scoring leads",

    "session.row.running": "Running — {status}",
    "session.row.failed": "Failed — {err}",
    "session.row.summary": "{n} leads · {hot} hot",
    "session.row.hot": "hot",
    "session.row.rest": "rest",

    "search.crumb.workspace": "Workspace",
    "search.crumb.new": "New search",
    "search.crumb.running": "Search in progress",
    "search.crumb.done": "Search complete",
    "search.chat.greeting":
      "Hi — I'm Lumen, your Leadgen copilot. Tell me who you're looking for and I'll build you a list in ~90 seconds.",
    "search.chat.tryThese": "Try one of these",
    "search.chat.placeholder": "Describe who you're looking for…",
    "search.chat.gotIt":
      "Got it — **{niche}** in **{region}**. Click Launch when ready, or tweak the form on the right.",
    "search.chat.needBoth":
      'Tell me the niche and the region, e.g. "roofing companies in New York".',
    "search.prompts.0": "Roofing contractors in New York",
    "search.prompts.1": "Coffee shops in Astana",
    "search.prompts.2": "Interior designers in Berlin",
    "search.prompts.3": "Orthodontic clinics in London",
    "search.form.eyebrow": "Search parameters",
    "search.form.title": "Or set it manually",
    "search.form.subtitle": "Lumen auto-fills these as you chat.",
    "search.form.niche": "Niche",
    "search.form.nichePh": "roofing companies",
    "search.form.region": "Region",
    "search.form.regionPh": "New York, NY",
    "search.form.offer": "Your offer (for AI scoring)",
    "search.form.offerPh":
      "e.g. I build SEO-optimized websites for local contractors",
    "search.form.offerHint":
      "Claude uses this to personalize every score and pitch.",
    "search.form.meta": "Up to 50 leads · 60–120 seconds · live progress below.",
    "search.form.launch": "Launch search",
    "search.running.eyebrowSearching": "Searching",
    "search.running.eyebrowDone": "Complete",
    "search.running.inGlue": "in",
    "search.running.defaultSubtitle":
      "This usually takes 60–120 seconds. Stay on the page — you'll see live phase progress below.",
    "search.running.phaseEyebrow": "Current phase",
    "search.running.bootingPipeline": "Booting the pipeline…",
    "search.running.openAnyway": "Open session anyway",
    "search.done.title": "{niche} · {region} — ready.",
    "search.done.subtitle":
      "Each lead was scored against your profile with a custom pitch.",
    "search.done.open": "Open results",

    "sessions.title": "Sessions",
    "sessions.subtitle": "Every search you have launched",
    "sessions.empty.title": "No sessions yet",
    "sessions.empty.body":
      "Launch your first search from the sidebar — it takes about 90 seconds.",

    "detail.crumb.sessions": "Sessions",
    "detail.status.pending": "pending",
    "detail.status.running": "running",
    "detail.status.done": "done",
    "detail.status.failed": "failed",
    "detail.source.web": "web",
    "detail.source.telegram": "telegram",
    "detail.stat.total": "total",
    "detail.stat.hot": "hot",
    "detail.stat.warm": "warm",
    "detail.stat.cold": "cold",
    "detail.insights.eyebrow": "AI market insight",
    "detail.filter.all": "All · {n}",
    "detail.filter.hot": "Hot · {n}",
    "detail.filter.warm": "Warm · {n}",
    "detail.filter.cold": "Cold · {n}",
    "detail.empty":
      "No leads stored for this session yet. If it just completed, refresh in a couple seconds.",

    "crm.title": "All leads",
    "crm.subtitle": "{leads} leads across {sessions} sessions",
    "crm.empty": "No leads yet. Run your first search from the sidebar.",
    "crm.status.all": "all",
    "crm.status.new": "new",
    "crm.status.contacted": "contacted",
    "crm.status.replied": "replied",
    "crm.status.won": "won",
    "crm.status.archived": "archived",
    "crm.table.lead": "Lead",
    "crm.table.session": "Session",
    "crm.table.score": "Score",
    "crm.table.status": "Status",
    "crm.table.touched": "Last touched",
    "crm.relative.now": "just now",
    "crm.relative.m": "{n}m ago",
    "crm.relative.h": "{n}h ago",
    "crm.relative.d": "{n}d ago",

    "lead.howToPitch": "How to pitch this lead",
    "lead.strengths": "Strengths",
    "lead.weaknesses": "Weaknesses",
    "lead.redFlags": "Red flags",
    "lead.notes": "Notes",
    "lead.notesPh": "Add your notes about this lead…",
    "lead.status": "Status",
    "lead.contact": "Contact",
    "lead.rating": "reviews",
    "lead.statusLabel.new": "new",
    "lead.statusLabel.contacted": "contacted",
    "lead.statusLabel.replied": "replied",
    "lead.statusLabel.won": "won",
    "lead.statusLabel.archived": "archived",

    "profile.title": "My profile",
    "profile.subtitle": "How AI scores leads for you",
    "profile.hint":
      "Your profile personalizes every AI score and pitch. Editing unlocks when auth lands.",
    "profile.field.business": "Business size",
    "profile.field.region": "Home region",
    "profile.field.offer": "Profession / offer",
    "profile.field.niches": "Target niches",
    "profile.empty": "Not set",

    "team.title": "Team",
    "team.subtitle": "Access and roles",
    "team.empty.title": "No team yet",
    "team.empty.body": "Inviting opens when auth ships.",
    "team.table.member": "Member",
    "team.table.role": "Role",
    "team.table.active": "Last active",

    "settings.title": "Settings",
    "settings.subtitle": "Workspace configuration",
    "settings.workspace": "Workspace",
    "settings.workspaceName": "Name",
    "settings.auth": "Auth",
    "settings.authValue": "Open demo — login ships with the next milestone",
    "settings.backend": "Backend",
    "settings.health": "API health",
    "settings.commit": "Deployed commit",
    "settings.unknown": "unknown",
    "settings.integrations": "Integrations",
    "settings.int.googlePlaces": "Google Places",
    "settings.int.anthropic": "Anthropic (Claude)",
    "settings.int.telegram": "Telegram bot",
    "settings.int.redis": "Redis job queue",
    "settings.int.email": "Email delivery",
    "settings.int.connected": "connected",
    "settings.int.notConfigured": "not configured",
    "settings.int.redis.connected": "arq worker processes searches",
    "settings.int.redis.fallback":
      "inline asyncio fallback — enable REDIS_URL to scale",
    "settings.int.email.planned": "planned with login",
    "settings.viewPrototype": "View the Figma-style prototype",
  },
} as const;

export type TranslationKey = keyof (typeof TRANSLATIONS)["ru"];

type Ctx = {
  lang: Locale;
  setLang: (l: Locale) => void;
  t: (key: TranslationKey, vars?: Record<string, string | number>) => string;
};

const LocaleContext = createContext<Ctx | null>(null);

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Locale>("ru");

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "ru") setLangState(stored);
  }, []);

  const setLang = useCallback((l: Locale) => {
    setLangState(l);
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      // ignore quota / disabled storage
    }
  }, []);

  const t = useCallback(
    (key: TranslationKey, vars?: Record<string, string | number>) => {
      const dict = TRANSLATIONS[lang] as Record<string, string>;
      const raw = dict[key] ?? TRANSLATIONS.en[key] ?? key;
      if (!vars) return raw;
      return raw.replace(/\{(\w+)\}/g, (_, k) =>
        k in vars ? String(vars[k]) : `{${k}}`,
      );
    },
    [lang],
  );

  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): Ctx {
  const ctx = useContext(LocaleContext);
  if (!ctx) {
    throw new Error("useLocale must be used inside <LocaleProvider>");
  }
  return ctx;
}
