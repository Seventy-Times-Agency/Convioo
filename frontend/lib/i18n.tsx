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
 * Persists the selection in localStorage under "convioo.lang"; defaults
 * to Russian because the team that QAs the site is Russian-speaking.
 */

export type Locale = "ru" | "en";

const STORAGE_KEY = "convioo.lang";
const LEGACY_STORAGE_KEY = "leadgen.lang";

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
    "nav.signOut": "Выйти",

    // Workspace switcher
    "workspace.label": "Рабочее пространство",
    "workspace.personal": "Личное",
    "workspace.manage": "Управлять командами",
    "workspace.viewingAs": "Смотрите как {name}",
    "workspace.stopViewAs": "Вернуться к своему виду",

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
    "landing.cta.secondary": "Войти",
    "landing.footer.built": "© 2026 Convioo. Для агентств.",
    "landing.footer.privacy": "Приватность",
    "landing.footer.terms": "Условия",
    "landing.footer.contact": "Контакты",

    // Preview (fake browser chrome on landing)
    "preview.session": "Сессия",
    "preview.analyzed": "{n} лидов проанализировано",
    "preview.hot": "Горячие",
    "preview.warm": "Тёплые",
    "preview.cold": "Холодные",

    // Auth
    "auth.field.firstName": "Имя",
    "auth.field.firstNamePh": "",
    "auth.field.lastName": "Фамилия",
    "auth.field.lastNamePh": "",
    "auth.field.email": "Email",
    "auth.field.emailPh": "[email protected]",
    "auth.field.password": "Пароль",
    "auth.field.passwordPh": "",
    "auth.field.passwordHint": "минимум 8 символов",
    "auth.login.invalid": "Неверный email или пароль.",

    // Verify-email
    "verify.pending.title": "Подтверждаем email…",
    "verify.pending.body": "Секунду — проверяем ссылку.",
    "verify.ok.title": "Email подтверждён",
    "verify.ok.body":
      "Готово. Теперь можно запускать поиски. Если вы ещё не вошли — войдите обычным образом.",
    "verify.ok.continue": "В рабочую зону",
    "verify.error.title": "Не получилось подтвердить email",
    "verify.error.body":
      "Ссылка истекла или уже была использована. Запросите новую ссылку из баннера в рабочей зоне.",
    "verify.gotoLogin": "Перейти ко входу",
    "verifyBanner.title": "Подтвердите email ({email})",
    "verifyBanner.body":
      "Запуск поисков заблокирован пока почта не подтверждена. Проверьте входящие — мы прислали ссылку.",
    "verifyBanner.resend": "Отправить ссылку ещё раз",
    "verifyBanner.sent": "Отправлено ✓",

    // Connectors (settings)
    "settings.connectors": "Коннекторы",
    "settings.connector.gmail": "Google Workspace (Gmail)",
    "settings.connector.gmail.desc":
      "Отправлять письма от лица вашего рабочего ящика, прямо из карточки лида. Скоро.",
    "settings.connector.outlook": "Microsoft 365 (Outlook)",
    "settings.connector.outlook.desc":
      "То же самое для Microsoft-аккаунтов. Скоро.",
    "settings.connector.smtp": "Custom SMTP",
    "settings.connector.smtp.desc":
      "Свой почтовый сервер для тех у кого корпоративные ограничения. Скоро.",
    "settings.connector.connect": "Подключить",
    "settings.connector.soon": "скоро",
    "auth.login.title": "С возвращением.",
    "auth.login.subtitle":
      "Введите имя и фамилию, под которыми вы регистрировались.",
    "auth.login.submit": "Войти",
    "auth.login.notFound": "Пользователь с таким именем не найден. Зарегистрируйтесь.",
    "auth.login.noAccount": "Нет аккаунта?",
    "auth.login.registerLink": "Зарегистрироваться",
    "auth.login.back": "На главную",
    "auth.register.title": "Создайте аккаунт.",
    "auth.register.subtitle":
      "Пока нужны только имя и фамилия. Остальное добавим позже.",
    "auth.register.submit": "Создать аккаунт",
    "auth.register.haveAccount": "Уже есть аккаунт?",
    "auth.register.signInLink": "Войти",
    "auth.inside.eyebrow": "Внутри",
    "auth.inside.body":
      "50 лидов с AI-оценкой в каждом поиске. Персонализировано под то, что продаёте именно вы.",
    "auth.inside.tags": "Google Places · Claude Haiku · Живое обогащение",

    // Onboarding (web mirror of the Telegram bot's 6-step flow)
    "onboarding.eyebrow": "Шаг {step} из {total}",
    "onboarding.next": "Дальше",
    "onboarding.finish": "Готово",
    "onboarding.skip": "Пропустить",
    "onboarding.step.0.title": "Как к вам обращаться?",
    "onboarding.step.0.help":
      "Это имя AI будет использовать в подаче для каждого лида.",
    "onboarding.step.0.ph": "Как к вам обращаться",
    "onboarding.step.1.title": "Сколько вам лет?",
    "onboarding.step.1.help":
      "Помогает Claude подобрать тон выводов. Можно пропустить.",
    "onboarding.step.2.title": "Какой у вас бизнес?",
    "onboarding.step.2.help":
      "Соло, малая команда, агентство — это меняет рекомендации. Можно пропустить.",
    "onboarding.step.3.title": "Что вы продаёте?",
    "onboarding.step.3.help":
      "Опишите своими словами — это самый важный шаг. AI будет оценивать каждого лида под именно эту услугу.",
    "onboarding.step.3.ph": "",
    "onboarding.step.4.title": "Откуда вы работаете?",
    "onboarding.step.4.help":
      "Базовый регион. Помогает с подачей, особенно если ищете лидов рядом.",
    "onboarding.step.4.ph": "",
    "onboarding.step.5.title": "На какие ниши вы охотитесь?",
    "onboarding.step.5.help":
      "Введите 3–7 ниш через Enter. Это помогает AI понимать ваш кругозор.",
    "onboarding.step.5.ph": "",
    "onboarding.step.5.counter": "{n} из 7",
    "onboarding.age.lt18": "до 18",
    "onboarding.age.18_24": "18–24",
    "onboarding.age.25_34": "25–34",
    "onboarding.age.35_44": "35–44",
    "onboarding.age.45_54": "45–54",
    "onboarding.age.55plus": "55+",
    "onboarding.size.solo": "Соло / фрилансер",
    "onboarding.size.small": "Малая команда (2–10)",
    "onboarding.size.medium": "Компания (10–50)",
    "onboarding.size.large": "Крупный бизнес (50+)",

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
      "Опишите целевую нишу и регион. Henry возьмёт остальное на себя.",
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
      "Привет — я Henry, ваш AI-ассистент по лидам. Опишите кого ищете, и я соберу список за ~90 секунд.",
    "search.consult.greeting":
      "Привет, я Henry. Расскажите кого ищете: какая ниша, в каком городе, и что для вас идеальный лид. Я буду уточнять по ходу и сразу заполню форму справа.",
    "search.consult.placeholder": "Напишите Henry...",
    "search.consult.role": "AI-консультант по подбору лидов",
    "search.consult.thinking": "Думаю над ответом...",
    "search.consult.error":
      "Не получилось получить ответ ({detail}). Попробуйте ещё раз или заполните форму справа вручную.",
    "search.form.nicheHint": "обязательно",
    "search.form.regionHint": "обязательно",
    "search.form.ideal": "Идеальный клиент",
    "search.form.idealHint": "по желанию",
    "search.form.idealPh":
      "",
    "search.form.exclude": "Кого не нужно",
    "search.form.excludeHint": "по желанию",
    "search.form.excludePh": "",
    "search.form.lang": "Языки лидов",
    "search.form.langHint": "по желанию",
    "search.form.langHelp":
      "Если выбраны языки — оставим только лидов, у которых есть признаки владения хотя бы одним из них (язык названия, отзывов, сайта). Полезно когда вы работаете на иностранный рынок но только с русско- или украиноязычными.",
    "search.lang.ru": "Русский",
    "search.lang.uk": "Украинский",
    "search.lang.en": "English",
    "search.lang.de": "Deutsch",
    "search.lang.es": "Español",
    "search.lang.fr": "Français",
    "search.lang.pl": "Polski",

    // Floating assistant (Henry)
    "assistant.open": "Открыть Henry",
    "assistant.close": "Свернуть",
    "assistant.reset": "Очистить чат",
    "assistant.role": "Консультант Convioo",
    "assistant.thinking": "Думаю...",
    "assistant.placeholder": "Спросите Henry...",
    "assistant.greeting":
      "Привет, я Henry — ваш консультант Convioo. Помогу настроить профиль, объясню как работает оценка лидов или подскажу как точнее описать целевой сегмент. С чем поможем?",
    "assistant.error":
      "Не получилось получить ответ ({detail}). Попробуйте ещё раз.",
    "assistant.suggestion": "Предложенные изменения профиля",
    "assistant.apply": "Применить",
    "assistant.applied": "Профиль обновлён.",
    "assistant.applyError":
      "Не получилось обновить профиль ({detail}).",
    "assistant.greeting.team":
      "Привет. Сейчас вы работаете в команде «{team}» — помогу с подбором лидов под её специфику, расскажу про коллег и их зоны ответственности. С чем работаем?",
    "assistant.team.suggestion": "Предложенные правки команды",
    "assistant.team.descriptionLabel": "Описание команды",
    "assistant.team.memberLabel": "Описание для участника #{id}",

    // Search preflight (team duplicate combo)
    "search.preflight.title": "Эта связка уже использовалась в команде",
    "search.preflight.body":
      "Один и тот же набор «ниша + регион» нельзя запускать дважды — лиды бы пересеклись с уже собранными у коллег. Откройте существующую сессию или попробуйте другую формулировку.",
    "search.preflight.leadsCount": "{n} лидов",
    "search.preflight.openSession": "Открыть сессию →",

    // Team description / member descriptions
    "team.descriptionLabel": "Описание команды",
    "team.descriptionEmpty": "Описание ещё не задано — расскажите команде зачем она существует.",
    "team.descriptionPh": "",
    "team.member.descriptionEmpty":
      "Нет описания участника. Кликните карандаш чтобы добавить.",
    "team.member.descriptionPh":
      "Чем занимается человек, что закрывает.",
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
    "search.form.subtitle": "Henry дозаполнит поля по ходу диалога.",
    "search.form.niche": "Ниша",
    "search.form.nichePh": "",
    "search.form.region": "Регион",
    "search.form.regionPh": "",
    "search.form.offer": "Что вы продаёте (для AI-оценки)",
    "search.form.offerPh":
      "",
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
    "detail.loader.title": "Готовим вашу подборку",
    "detail.loader.subtitle":
      "Собираем компании, проходим по сайтам и отзывам, и оцениваем каждого лида под ваш профиль. Обычно это 60–120 секунд — страница откроется сама.",
    "detail.loader.phase.pending": "Запускаем пайплайн",
    "detail.loader.phase.discovering": "Ищем компании в Google Places",
    "detail.loader.phase.enriching": "Обогащаем сайтами и отзывами",
    "detail.loader.phase.scoring": "Claude оценивает каждого лида",
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
    "lead.sendEmail.gmail": "Написать через Gmail",
    "lead.sendEmail.soon":
      "Скоро: подключите Google Workspace в настройках, и сможете писать письмо лиду прямо отсюда.",
    "lead.mark.title": "Моя пометка",
    "lead.mark.clear": "Снять",
    "lead.mark.help":
      "Цвет видите только вы. Используйте как угодно — приоритет, follow-up, что захотите.",

    // Profile
    "profile.title": "Мой профиль",
    "profile.subtitle": "Как AI оценивает лидов для вас",
    "profile.hint":
      "Профиль персонализирует каждый AI-скор и подачу. Редактирование откроется вместе с обычным логином.",
    "profile.field.business": "Размер бизнеса",
    "profile.field.region": "Домашний регион",
    "profile.field.offer": "Профессия / предложение",
    "profile.field.offerRaw": "Что вы продаёте (ваши слова)",
    "profile.field.niches": "Целевые ниши",
    "profile.field.age": "Возраст",
    "profile.field.displayName": "Имя",
    "profile.empty": "Не указано",

    // Team
    "team.title": "Команда",
    "team.subtitle": "Создавайте общие пространства и приглашайте в них людей",
    "team.create.eyebrow": "Команда ещё не создана",
    "team.create.title": "Создайте свою первую команду",
    "team.create.subtitle":
      "Команда — это общий CRM. Все её участники видят одни и те же сессии и лидов; владелец рассылает инвайты и управляет ролями.",
    "team.create.placeholder": "Например: Acme Agency",
    "team.create.submit": "Создать команду",
    "team.create.another": "Создать ещё одну команду",
    "team.detail.eyebrow": "Команда",
    "team.detail.members": "Участники · {n}",
    "team.owner.eyebrow": "Только владельцу",
    "team.owner.title": "CRM каждого участника",
    "team.owner.subtitle":
      "В команде каждый видит только своих лидов. Здесь вы как владелец можете зайти в CRM любого участника и посмотреть с чем он работает.",
    "team.owner.empty": "Пока в команде только вы.",
    "team.owner.col.member": "Участник",
    "team.owner.col.role": "Роль",
    "team.owner.col.sessions": "Сессий",
    "team.owner.col.leads": "Лидов",
    "team.owner.col.hot": "Горячих",
    "team.owner.viewAs": "Смотреть как",
    "team.owner.viewMine": "Мой CRM",
    "team.invite.eyebrow": "Инвайт",
    "team.invite.title": "Пригласить в команду",
    "team.invite.subtitle":
      "Сгенерируйте ссылку, действует 10 минут. Пользователь должен пройти регистрацию или войти, после этого станет членом команды.",
    "team.invite.generate": "Сгенерировать ссылку",
    "team.invite.regenerate": "Сгенерировать заново",
    "team.invite.copy": "Скопировать",
    "team.invite.expiresIn": "Действует ещё {mm}",
    "team.invite.expired": "Срок инвайта истёк",
    "team.empty.title": "Команды пока нет",
    "team.empty.body":
      "Создайте команду чтобы делиться лидами и пространством с коллегами.",
    "team.table.member": "Участник",
    "team.table.role": "Роль",
    "team.table.active": "Последняя активность",

    // Invite landing
    "invite.title": "Вас пригласили в команду",
    "invite.subtitle": "Роль: {role}. Принимая инвайт вы попадёте в общий CRM команды.",
    "invite.expiresIn": "Истечёт через {mm}",
    "invite.expired": "Этот инвайт уже истёк. Попросите владельца команды сгенерировать новый.",
    "invite.alreadyUsed": "Эта ссылка уже использована.",
    "invite.signInToAccept": "Войти и принять",
    "invite.registerToAccept": "Создать аккаунт и принять",
    "invite.accept": "Принять и перейти в команду",

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
    "nav.signOut": "Sign out",

    "workspace.label": "Workspace",
    "workspace.personal": "Personal",
    "workspace.manage": "Manage teams",
    "workspace.viewingAs": "Viewing as {name}",
    "workspace.stopViewAs": "Back to your own view",

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
    "landing.cta.secondary": "Sign in",
    "landing.footer.built": "© 2026 Convioo. Built for agencies.",
    "landing.footer.privacy": "Privacy",
    "landing.footer.terms": "Terms",
    "landing.footer.contact": "Contact",

    "preview.session": "Session",
    "preview.analyzed": "{n} leads analyzed",
    "preview.hot": "Hot",
    "preview.warm": "Warm",
    "preview.cold": "Cold",

    "auth.field.firstName": "First name",
    "auth.field.firstNamePh": "",
    "auth.field.lastName": "Last name",
    "auth.field.lastNamePh": "",
    "auth.field.email": "Email",
    "auth.field.emailPh": "[email protected]",
    "auth.field.password": "Password",
    "auth.field.passwordPh": "",
    "auth.field.passwordHint": "min 8 characters",
    "auth.login.invalid": "Invalid email or password.",

    "verify.pending.title": "Verifying your email…",
    "verify.pending.body": "One sec — checking the link.",
    "verify.ok.title": "Email verified",
    "verify.ok.body":
      "Done. You can launch searches now. If you weren't signed in — sign in normally.",
    "verify.ok.continue": "Go to workspace",
    "verify.error.title": "Couldn't verify your email",
    "verify.error.body":
      "The link expired or was already used. Request a fresh one from the banner in your workspace.",
    "verify.gotoLogin": "Go to login",
    "verifyBanner.title": "Verify your email ({email})",
    "verifyBanner.body":
      "Search launches are blocked until your email is verified. Check your inbox — we sent the link.",
    "verifyBanner.resend": "Resend link",
    "verifyBanner.sent": "Sent ✓",

    "settings.connectors": "Connectors",
    "settings.connector.gmail": "Google Workspace (Gmail)",
    "settings.connector.gmail.desc":
      "Send emails from your work inbox, straight from the lead card. Coming soon.",
    "settings.connector.outlook": "Microsoft 365 (Outlook)",
    "settings.connector.outlook.desc":
      "Same flow for Microsoft accounts. Coming soon.",
    "settings.connector.smtp": "Custom SMTP",
    "settings.connector.smtp.desc":
      "Your own SMTP server for stricter corporate setups. Coming soon.",
    "settings.connector.connect": "Connect",
    "settings.connector.soon": "soon",
    "auth.login.title": "Welcome back.",
    "auth.login.subtitle":
      "Enter the first and last name you signed up with.",
    "auth.login.submit": "Sign in",
    "auth.login.notFound": "No account with that name. Try signing up instead.",
    "auth.login.noAccount": "No account yet?",
    "auth.login.registerLink": "Create one",
    "auth.login.back": "Back to home",
    "auth.register.title": "Create your account.",
    "auth.register.subtitle":
      "Just first and last name for now. The rest comes later.",
    "auth.register.submit": "Create account",
    "auth.register.haveAccount": "Already have an account?",
    "auth.register.signInLink": "Sign in",
    "onboarding.eyebrow": "Step {step} of {total}",
    "onboarding.next": "Continue",
    "onboarding.finish": "Finish",
    "onboarding.skip": "Skip",
    "onboarding.step.0.title": "What should we call you?",
    "onboarding.step.0.help":
      "The AI uses this name when it writes the pitch for each lead.",
    "onboarding.step.0.ph": "Display name",
    "onboarding.step.1.title": "How old are you?",
    "onboarding.step.1.help":
      "Helps Claude pick the right tone. You can skip this.",
    "onboarding.step.2.title": "How big is your business?",
    "onboarding.step.2.help":
      "Solo, small team, agency — it changes the recommendations. Optional.",
    "onboarding.step.3.title": "What do you sell?",
    "onboarding.step.3.help":
      "Describe it in your own words — this is the most important step. AI scores every lead against this service.",
    "onboarding.step.3.ph": "",
    "onboarding.step.4.title": "Where are you based?",
    "onboarding.step.4.help":
      "Your home region. Sharpens the pitch when you're prospecting nearby.",
    "onboarding.step.4.ph": "",
    "onboarding.step.5.title": "Which niches do you target?",
    "onboarding.step.5.help":
      "Add 3–7 niches with Enter. Helps the AI understand your scope.",
    "onboarding.step.5.ph": "",
    "onboarding.step.5.counter": "{n} of 7",
    "onboarding.age.lt18": "under 18",
    "onboarding.age.18_24": "18–24",
    "onboarding.age.25_34": "25–34",
    "onboarding.age.35_44": "35–44",
    "onboarding.age.45_54": "45–54",
    "onboarding.age.55plus": "55+",
    "onboarding.size.solo": "Solo / freelance",
    "onboarding.size.small": "Small team (2–10)",
    "onboarding.size.medium": "Company (10–50)",
    "onboarding.size.large": "Large (50+)",

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
      "Describe your target niche and region. Henry will handle the rest.",
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
      "Hi — I'm Henry, your Convioo copilot. Tell me who you're looking for and I'll build you a list in ~90 seconds.",
    "search.consult.greeting":
      "Hi, I'm Henry. Tell me who you're after — niche, city, and what makes an ideal lead. I'll ask follow-ups and fill in the form on the right as we go.",
    "search.consult.placeholder": "Message Henry...",
    "search.consult.role": "AI lead-gen consultant",
    "search.consult.thinking": "Thinking...",
    "search.consult.error":
      "Couldn't get a reply ({detail}). Try again or fill the form on the right.",
    "search.form.nicheHint": "required",
    "search.form.regionHint": "required",
    "search.form.ideal": "Ideal customer",
    "search.form.idealHint": "optional",
    "search.form.idealPh":
      "",
    "search.form.exclude": "Skip these",
    "search.form.excludeHint": "optional",
    "search.form.excludePh": "",
    "search.form.lang": "Lead languages",
    "search.form.langHint": "optional",
    "search.form.langHelp":
      "When set, we only keep leads showing signals of operating in at least one of the picked languages (name, reviews, site). Useful when working a foreign market but only with Russian/Ukrainian-speaking businesses.",
    "search.lang.ru": "Russian",
    "search.lang.uk": "Ukrainian",
    "search.lang.en": "English",
    "search.lang.de": "German",
    "search.lang.es": "Spanish",
    "search.lang.fr": "French",
    "search.lang.pl": "Polish",

    "assistant.open": "Open Henry",
    "assistant.close": "Minimise",
    "assistant.reset": "Clear chat",
    "assistant.role": "Convioo consultant",
    "assistant.thinking": "Thinking...",
    "assistant.placeholder": "Ask Henry...",
    "assistant.greeting":
      "Hi, I'm Henry — your Convioo consultant. I can help tune your profile, explain how lead scoring works, or sharpen how you describe your target segment. What can I help with?",
    "assistant.error":
      "Couldn't get a reply ({detail}). Try again.",
    "assistant.suggestion": "Profile changes Henry suggests",
    "assistant.apply": "Apply",
    "assistant.applied": "Profile updated.",
    "assistant.applyError":
      "Couldn't update profile ({detail}).",
    "assistant.greeting.team":
      "Hi. You're working in team \"{team}\" right now — I'll help with leads scoped to its focus and share what your teammates are doing. What's up?",
    "assistant.team.suggestion": "Suggested team edits",
    "assistant.team.descriptionLabel": "Team description",
    "assistant.team.memberLabel": "Note for member #{id}",

    "search.preflight.title": "This combo was already used in the team",
    "search.preflight.body":
      "Same niche + region can't run twice — leads would overlap with what teammates already have. Open the existing session or pick a different angle.",
    "search.preflight.leadsCount": "{n} leads",
    "search.preflight.openSession": "Open session →",

    "team.descriptionLabel": "Team description",
    "team.descriptionEmpty": "Description hasn't been set yet — tell the team why it exists.",
    "team.descriptionPh":
      "",
    "team.member.descriptionEmpty":
      "No description for this member. Click the pencil to add one.",
    "team.member.descriptionPh":
      "What this person works on, what they close.",
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
    "search.form.subtitle": "Henry auto-fills these as you chat.",
    "search.form.niche": "Niche",
    "search.form.nichePh": "",
    "search.form.region": "Region",
    "search.form.regionPh": "",
    "search.form.offer": "Your offer (for AI scoring)",
    "search.form.offerPh":
      "",
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
    "detail.loader.title": "Preparing your list",
    "detail.loader.subtitle":
      "We pull the companies, visit each site and review feed, then score every lead against your profile. Usually 60–120 seconds — this page opens on its own.",
    "detail.loader.phase.pending": "Booting the pipeline",
    "detail.loader.phase.discovering": "Finding companies on Google Places",
    "detail.loader.phase.enriching": "Enriching with sites and reviews",
    "detail.loader.phase.scoring": "Claude is scoring each lead",
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
    "lead.sendEmail.gmail": "Email via Gmail",
    "lead.sendEmail.soon":
      "Coming soon — connect Google Workspace in Settings and you'll be able to email leads from here.",
    "lead.mark.title": "My mark",
    "lead.mark.clear": "Clear",
    "lead.mark.help":
      "Only you see this colour. Use it however you like — priority, follow-up, anything.",

    "profile.title": "My profile",
    "profile.subtitle": "How AI scores leads for you",
    "profile.hint":
      "Your profile personalises every AI score and pitch. Edit it any time.",
    "profile.field.business": "Business size",
    "profile.field.region": "Home region",
    "profile.field.offer": "Profession / offer",
    "profile.field.offerRaw": "What you sell (your words)",
    "profile.field.niches": "Target niches",
    "profile.field.age": "Age",
    "profile.field.displayName": "Display name",
    "profile.empty": "Not set",

    "team.title": "Team",
    "team.subtitle": "Create shared workspaces and bring people in",
    "team.create.eyebrow": "No team yet",
    "team.create.title": "Spin up your first team",
    "team.create.subtitle":
      "A team is a shared CRM. Every member sees the same sessions and leads; the owner sends invites and manages roles.",
    "team.create.placeholder": "Acme Agency",
    "team.create.submit": "Create team",
    "team.create.another": "Create another team",
    "team.detail.eyebrow": "Team",
    "team.detail.members": "Members · {n}",
    "team.owner.eyebrow": "Owner-only",
    "team.owner.title": "Each member's CRM",
    "team.owner.subtitle":
      "In a team everyone sees only their own leads. As the owner you can drop into any member's CRM and see what they're working on.",
    "team.owner.empty": "You're the only one in the team so far.",
    "team.owner.col.member": "Member",
    "team.owner.col.role": "Role",
    "team.owner.col.sessions": "Sessions",
    "team.owner.col.leads": "Leads",
    "team.owner.col.hot": "Hot",
    "team.owner.viewAs": "View as",
    "team.owner.viewMine": "My CRM",
    "team.invite.eyebrow": "Invite",
    "team.invite.title": "Invite a teammate",
    "team.invite.subtitle":
      "Generate a 10-minute link. The recipient signs up or signs in; once accepted they're a team member.",
    "team.invite.generate": "Generate link",
    "team.invite.regenerate": "Regenerate",
    "team.invite.copy": "Copy",
    "team.invite.expiresIn": "Valid for {mm}",
    "team.invite.expired": "Invite has expired",
    "team.empty.title": "No team yet",
    "team.empty.body":
      "Create a team to share leads and the workspace with teammates.",
    "team.table.member": "Member",
    "team.table.role": "Role",
    "team.table.active": "Last active",

    "invite.title": "You've been invited to a team",
    "invite.subtitle": "Role: {role}. Accepting drops you into the team's shared CRM.",
    "invite.expiresIn": "Expires in {mm}",
    "invite.expired": "This invite has expired. Ask the owner to regenerate it.",
    "invite.alreadyUsed": "This link has already been used.",
    "invite.signInToAccept": "Sign in to accept",
    "invite.registerToAccept": "Create account and accept",
    "invite.accept": "Accept and switch to team",

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
    let stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      stored = localStorage.getItem(LEGACY_STORAGE_KEY);
      if (stored) {
        localStorage.setItem(STORAGE_KEY, stored);
        localStorage.removeItem(LEGACY_STORAGE_KEY);
      }
    }
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
