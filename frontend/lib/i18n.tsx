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

export type Locale = "ru" | "uk" | "en";

const STORAGE_KEY = "convioo.lang";
const LEGACY_STORAGE_KEY = "leadgen.lang";

const TRANSLATIONS = {
  ru: {
    // Shared / buttons
    "common.newSearch": "Новый поиск",
    "common.cancel": "Отмена",
    "common.delete": "Удалить",
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
    "nav.billing": "Подписка",
    "nav.templates": "Шаблоны",
    "nav.import": "Импорт CSV",
    "import.title": "Импорт списка компаний",
    "import.subtitle":
      "Загрузите CSV — Convioo создаст сессию с лидами, привяжет custom-поля и подключит CRM.",
    "import.dropTitle": "Перетащите CSV сюда",
    "import.dropBody":
      "Файл с заголовком в первой строке. Поддерживаются столбцы: name (обязательно), website, region, phone, category. Любые другие — попадут в custom fields.",
    "import.pick": "Выбрать файл",
    "import.expectedColumns":
      "Пример заголовков: name,website,region,phone,category — порядок и регистр не важны. Любая дополнительная колонка станет custom-полем у каждого лида.",
    "import.empty": "В файле нет строк с данными.",
    "import.previewTitle": "Превью · {n} строк",
    "import.skipped": "Пропущено {n} строк (без name).",
    "import.pickAnother": "Выбрать другой файл",
    "import.runImport": "Импортировать",
    "import.labelField": "Название сессии",
    "import.previewTrunc": "+ ещё {n} строк, которые тоже импортируются.",
    "lead.extras.findDecisionMakers": "Найти контакты ЛПР",
    "nav.signOut": "Выйти",
    "nav.themeDark": "Тёмная тема",
    "nav.themeLight": "Светлая тема",

    "kbd.title": "Горячие клавиши",
    "kbd.dashboard": "Главная",
    "kbd.search": "Новый поиск",
    "kbd.leads": "Все лиды",
    "kbd.import": "Импорт CSV",
    "kbd.templates": "Шаблоны",
    "kbd.profile": "Профиль",
    "kbd.theme": "Сменить тему",
    "kbd.toggleHelp": "Показать/скрыть это окно",

    "templates.title": "Шаблоны outreach",
    "templates.subtitle":
      "Сохранённые письма с плейсхолдерами {name}, {niche}, {region}. Henry адаптирует их под каждого лида.",
    "templates.new": "Новый шаблон",
    "templates.copy": "Копировать тело",
    "templates.empty.title": "Шаблонов пока нет",
    "templates.empty.body":
      "Сохраните Cold #1 / Follow-up / Breakup — и копируйте одной кнопкой при работе с лидом.",
    "templates.editor.titleNew": "Новый шаблон",
    "templates.editor.titleEdit": "Редактирование шаблона",
    "templates.editor.save": "Сохранить",
    "templates.field.name": "Название",
    "templates.field.namePh": "Например: Cold #1 для стоматологий",
    "templates.field.subject": "Тема",
    "templates.field.subjectPh": "Тема письма (опционально)",
    "templates.field.body": "Тело письма",
    "templates.field.bodyHint": "плейсхолдеры: {name}, {niche}, {region}",
    "templates.field.bodyPh":
      "Привет, {name}! Заметил, что вы …",
    "templates.field.tone": "Тон",

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
    "auth.field.inviteCode": "Регистрационный код",
    "auth.field.inviteCodePh": "выдаётся основателем",
    "auth.field.inviteCodeHint": "обязательно",
    "auth.login.invalid": "Неверный email или пароль.",

    // Verify-email
    "verify.idle.title": "Подтвердить email",
    "verify.idle.body":
      "Нажмите кнопку ниже чтобы подтвердить email. Это нужно потому что почтовые сервисы автоматически проверяют ссылки в письмах — если бы мы подтверждали при загрузке, токен сгорал бы до вашего клика.",
    "verify.idle.cta": "Подтвердить email",
    "verify.verifying.title": "Подтверждаем email…",
    "verify.pending.title": "Подтверждаем email…",
    "verify.pending.body": "Секунду — проверяем ссылку.",
    "verify.ok.title": "Email подтверждён",
    "verify.ok.body":
      "Готово. Теперь можно запускать поиски. Если вы ещё не вошли — войдите обычным образом.",
    "verify.ok.continue": "В рабочую зону",
    "verify.error.title": "Не получилось подтвердить email",
    "verify.error.body":
      "Ссылка истекла или уже была использована. Запросите новую ссылку из баннера в рабочей зоне.",
    "verify.error.retry": "Попробовать ещё раз",
    "verify.gotoLogin": "Перейти ко входу",
    "verifyBanner.title": "Подтвердите email ({email})",
    "verifyBanner.body":
      "Запуск поисков заблокирован пока почта не подтверждена. Проверьте входящие — мы прислали ссылку.",
    "verifyBanner.resend": "Отправить ссылку ещё раз",
    "verifyBanner.sent": "Отправлено ✓",

    // Connectors (settings)
    "settings.account": "Аккаунт",
    "settings.account.emailLabel": "Email",
    "settings.account.passwordLabel": "Пароль",
    "settings.account.passwordHelp": "Меняется в любой момент. Требуется текущий пароль.",
    "settings.account.changeEmail": "Изменить email",
    "settings.account.changePassword": "Изменить пароль",
    "settings.account.verified": "подтверждён",
    "settings.account.unverified": "не подтверждён",
    "settings.account.newEmailPh": "Новый email",
    "settings.account.passwordConfirmPh": "Текущий пароль (для подтверждения)",
    "settings.account.sendVerify": "Отправить ссылку на подтверждение",
    "settings.account.sameEmail": "Это уже ваш текущий email.",
    "settings.account.changeEmailSent":
      "Письмо со ссылкой отправлено на {email}. Подтвердите его — после этого основной email сменится. Текущий продолжает работать до подтверждения.",
    "settings.account.currentPasswordPh": "Текущий пароль",
    "settings.account.newPasswordPh": "Новый пароль (мин. 8 символов)",
    "settings.account.confirmPasswordPh": "Повторите новый пароль",
    "settings.account.passwordsDontMatch": "Пароли не совпадают.",
    "settings.account.passwordSaved": "Пароль обновлён ✓",
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
      "Минимум для старта — имя, email и пароль. Остальное настроите внутри платформы.",
    "auth.register.submit": "Создать аккаунт",
    "auth.register.haveAccount": "Уже есть аккаунт?",
    "auth.register.signInLink": "Войти",
    "auth.field.age": "Возраст",
    "auth.field.ageHint": "по желанию — помогает AI подобрать тон",
    "auth.field.ageSkip": "Не указывать",
    "auth.field.gender": "Пол",
    "auth.field.genderHint":
      "по желанию — Henry будет обращаться в правильном роде",
    "auth.field.genderSkip": "Не указывать",
    "auth.field.gender.male": "Мужской",
    "auth.field.gender.female": "Женский",
    "auth.field.gender.other": "Другой",
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
    "dashboard.quota.eyebrow": "Лимит поисков",
    "dashboard.quota.subtitle": "Использовано {used} из {limit}",
    "dashboard.checkin.eyebrow": "Henry · итог недели",
    "tasks.todayTitle": "На сегодня",
    "tasks.today": "сегодня",
    "tasks.overdue": "просрочено",
    "lead.extras.tasks": "Задачи",
    "lead.extras.tasks.ph": "Например: позвонить в среду",
    "lead.extras.customFields": "Кастомные поля",
    "lead.extras.customFields.keyPh": "ключ (decision_maker)",
    "lead.extras.customFields.valPh": "значение",
    "lead.extras.activity": "История изменений",
    "lead.extras.activity.statusKind": "Статус: {from} → {to}",
    "lead.extras.activity.notesKind": "Обновлены заметки",
    "lead.extras.activity.assignedKind": "Назначен на #{id}",
    "lead.extras.activity.unassignedKind": "Снят с назначения",
    "lead.extras.activity.markKind": "Цветная пометка",
    "lead.extras.activity.customFieldKind": "Поле «{key}»",
    "lead.extras.activity.taskKind": "Задача: {content}",
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
    "search.consult.greetingNichesRegion":
      "Привет. Вижу — у вас в фокусе {niches} в {region}. С какой ниши сегодня начнём, или хотите подобрать что-то новое?",
    "search.consult.greetingNiches":
      "Привет. У вас в нишах {niches}. С какой работаем сегодня и в каком городе?",
    "search.consult.greetingRegionOffer":
      "Привет. Знаю что вы работаете в {region}. Какой сегмент сегодня ищем?",
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
    "assistant.applied": "Записано ✓",
    "assistant.applyError":
      "Не получилось обновить профиль ({detail}).",
    "assistant.pending.title": "Henry хочет записать",
    "assistant.pending.confirm": "Записать",
    "assistant.pending.dismiss": "Не сейчас",
    "assistant.launchedSearch": "Поиск запущен",
    "assistant.openSession": "Открыть сессию",
    "lead.email.deepResearch": "Глубокий research",
    "lead.email.deepResearchHint":
      "Henry свежо просканирует сайт лида и вытащит конкретные факты для opener-а.",
    "lead.email.notableFacts": "Что Henry нашёл на сайте:",
    "lead.email.recentSignal": "Recent signal:",
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
    "search.chat.placeholder": "Опишите кого ищете…",
    "search.chat.gotIt":
      "Понял — **{niche}** в **{region}**. Жмите «Запустить» когда готовы, или поправьте форму справа.",
    "search.chat.needBoth":
      "Укажите нишу и регион, например «кровельные компании в Нью-Йорке».",
    "search.axes.eyebrow": "Подобрать с Henry",
    "search.axes.subtitle":
      "Получи 4 готовых конфигурации поиска под твой профиль — клик и форма заполнена.",
    "search.axes.cta": "Подобрать",
    "search.axes.ctaAgain": "Подобрать ещё",
    "search.axes.hide": "Скрыть",
    "search.axes.empty":
      "Henry не смог подобрать варианты — заполните «что вы продаёте» в /app/profile и попробуйте снова.",
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
    "search.form.offerSource.profile": "Из моего профиля",
    "search.form.offerSource.custom": "Другое для этого поиска",
    "search.form.offerSource.empty":
      "В профиле пока нет описания. Заполните его в /app/profile или напишите вариант ниже — он применится только к этому поиску.",
    "search.form.offerSource.profileEmpty":
      "Описания нет — добавьте его в профиле, чтобы AI учитывал его в каждом поиске.",
    "search.form.offerSource.profileLink": "Открыть профиль →",
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
    "crm.smart.all": "Все",
    "crm.smart.hotWeek": "Hot за неделю",
    "crm.smart.newToday": "Новые сегодня",
    "crm.smart.untouched14": "Без касания 14+ дней",
    "crm.kanban.empty": "Перетащите карточку сюда",
    "crm.status.all": "все",
    "crm.status.new": "новые",
    "crm.status.contacted": "в работе",
    "crm.status.replied": "ответили",
    "crm.status.won": "сделка",
    "crm.status.archived": "архив",
    "crm.search.placeholder": "Поиск по имени, адресу, категории…",
    "crm.search.clear": "Очистить",
    "crm.search.results": "{n} лидов",
    "crm.sort.score_desc": "Скор: сначала высокие",
    "crm.sort.score_asc": "Скор: сначала низкие",
    "crm.sort.created_desc": "Сначала новые",
    "crm.sort.created_asc": "Сначала старые",
    "crm.sort.touched_desc": "Последний контакт",
    "crm.sort.name_asc": "Имя А → Я",
    "crm.sort.name_desc": "Имя Я → А",
    "crm.bulk.selectAll": "Выделить всё",
    "crm.bulk.selected": "Выделено: {n}",
    "crm.bulk.setStatus": "Статус",
    "crm.bulk.setMark": "Пометка",
    "crm.bulk.cancel": "Снять выделение",
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
    "lead.email.generate": "Сгенерировать письмо",
    "lead.email.regenerate": "Переписать",
    "lead.email.draft": "Черновик письма",
    "lead.email.subject": "Тема",
    "lead.email.body": "Тело",
    "lead.email.copy": "Копировать",
    "lead.email.copyAll": "Копировать всё",
    "lead.email.copied": "Скопировано ✓",
    "lead.email.sendGmail": "Отправить через Gmail",
    "lead.email.addExtra": "Добавить контекст",
    "lead.email.hideExtra": "Скрыть контекст",
    "lead.email.extraPh":
      "Что-то конкретное про этого лида что Henry должен учесть (опционально).",
    "lead.email.tone.professional": "Деловой",
    "lead.email.tone.casual": "Тёплый",
    "lead.email.tone.bold": "Уверенный",
    "lead.mark.title": "Моя пометка",
    "lead.mark.clear": "Снять",
    "lead.mark.help":
      "Цвет видите только вы. Используйте как угодно — приоритет, follow-up, что захотите.",

    // Profile
    "profile.title": "Мой профиль",
    "profile.subtitle": "Как AI оценивает лидов для вас",
    "profile.hint":
      "Профиль персонализирует каждый AI-скор и подачу.",

    // Privacy & data block on /app/profile
    "profile.privacy.title": "Конфиденциальность и данные",
    "profile.privacy.subtitle":
      "Скачайте копию ваших данных, посмотрите журнал активности или удалите аккаунт.",
    "profile.privacy.export": "Экспорт моих данных",
    "profile.privacy.exportHint":
      "JSON-файл со всеми вашими профилем, лидами и активностью.",
    "profile.privacy.audit": "Журнал активности",
    "profile.privacy.auditEmpty": "Записей пока нет.",
    "profile.privacy.delete": "Удалить аккаунт",
    "profile.privacy.deleteHint":
      "Без возможности восстановления. Удаляются все ваши данные.",
    "profile.privacy.deleteConfirmTitle": "Удалить аккаунт навсегда",
    "profile.privacy.deleteConfirmBody":
      "Чтобы подтвердить, введите ваш email и пароль. Это действие необратимо.",
    "profile.privacy.deleteConfirmEmail": "Ваш email",
    "profile.privacy.deleteConfirmPassword": "Пароль",
    "profile.privacy.deleteConfirmCta": "Удалить навсегда",
    "profile.privacy.deleteFailed":
      "Не удалось удалить аккаунт. Проверьте email и пароль.",

    // Legal pages
    "legal.updated": "Обновлено {date}",
    "legal.nav.privacy": "Политика конфиденциальности",
    "legal.nav.terms": "Условия использования",
    "legal.nav.cookies": "Cookies",
    "legal.nav.contact": "По вопросам — {email}",

    "legal.privacy.title": "Политика конфиденциальности",
    "legal.privacy.intro":
      "Эта страница описывает, какие данные Convioo собирает, как мы их используем и какими правами вы обладаете.",
    "legal.privacy.collect.title": "Какие данные мы собираем",
    "legal.privacy.collect.body":
      "Мы храним только то, что нужно для работы сервиса:",
    "legal.privacy.collect.li1":
      "Аккаунт: имя, email, пароль (в виде хэша argon2), настройки профиля и ниш.",
    "legal.privacy.collect.li2":
      "Поиски и лиды: запросы, результаты Google Places, заметки, статусы, активность по лидам.",
    "legal.privacy.collect.li3":
      "Технические события: даты входа, IP и user-agent в журнале активности (только для безопасности).",
    "legal.privacy.use.title": "Как мы используем данные",
    "legal.privacy.use.body":
      "Данные нужны исключительно для работы сервиса: поиск компаний, AI-скоринг, CRM, поддержка. Мы не продаём ваши данные и не используем их для рекламы.",
    "legal.privacy.share.title": "С кем мы делимся данными",
    "legal.privacy.share.body":
      "Только с провайдерами инфраструктуры, без которых сервис не работает:",
    "legal.privacy.share.li1":
      "Anthropic (Claude API) — обработка AI-скоринга и генерации писем.",
    "legal.privacy.share.li2":
      "Google Places API — получение информации о компаниях.",
    "legal.privacy.share.li3":
      "Хостинг (Railway, Vercel) — выполнение приложения и хранение БД.",
    "legal.privacy.rights.title": "Ваши права",
    "legal.privacy.rights.body":
      "В разделе «Мой профиль → Конфиденциальность» вы можете в один клик скачать полный экспорт ваших данных в JSON или удалить аккаунт навсегда. По любому вопросу о данных пишите на support@convioo.com.",
    "legal.privacy.retention.title": "Сроки хранения",
    "legal.privacy.retention.body":
      "Данные хранятся пока активен ваш аккаунт. После удаления аккаунта вся пользовательская информация (профиль, лиды, заметки, активность) удаляется немедленно.",
    "legal.privacy.contact.title": "Связь с нами",
    "legal.privacy.contact.body":
      "По вопросам конфиденциальности и GDPR пишите на support@convioo.com. Мы отвечаем в течение 30 дней.",

    "legal.terms.title": "Условия использования",
    "legal.terms.intro":
      "Используя Convioo, вы соглашаетесь с этими условиями. Если что-то непонятно — напишите нам, прежде чем продолжать.",
    "legal.terms.account.title": "Ваш аккаунт",
    "legal.terms.account.body":
      "Вы отвечаете за безопасность пароля и за все действия в своём аккаунте. Сообщите нам сразу, если заметите подозрительную активность.",
    "legal.terms.allowed.title": "Что разрешено и что — нет",
    "legal.terms.allowed.body":
      "Convioo создан для честного B2B-аутрича. Запрещено:",
    "legal.terms.allowed.li1":
      "Массовый спам и любые действия, противоречащие законодательству о персональных данных (GDPR/CCPA).",
    "legal.terms.allowed.li2":
      "Попытки обходить лимиты, реверс-инжиниринг или взлом инфраструктуры.",
    "legal.terms.allowed.li3":
      "Использование сервиса для торговли запрещёнными товарами или обмана клиентов.",
    "legal.terms.payments.title": "Оплата и подписки",
    "legal.terms.payments.body":
      "Платные тарифы оплачиваются по подписке (на момент написания — пока в beta доступ бесплатный). Возврат — по разумной просьбе в течение 14 дней.",
    "legal.terms.warranty.title": "Без гарантий",
    "legal.terms.warranty.body":
      "Сервис предоставляется «как есть». Мы стремимся к стабильной работе, но не гарантируем 100% uptime или абсолютную точность AI-результатов. Решения принимаете вы — Convioo это инструмент.",
    "legal.terms.termination.title": "Прекращение использования",
    "legal.terms.termination.body":
      "Вы можете удалить аккаунт в любой момент через профиль. Мы оставляем за собой право закрыть аккаунт при нарушении этих условий, предварительно уведомив вас.",
    "legal.terms.law.title": "Применимое право",
    "legal.terms.law.body":
      "К отношениям применяется право Эстонии (страны регистрации операционной компании), за исключением императивных норм страны вашего проживания.",

    "legal.cookies.title": "Использование cookies",
    "legal.cookies.intro":
      "Convioo использует минимальный набор cookies — только то, что нужно для работы сайта. Никакого рекламного трекинга.",
    "legal.cookies.what.title": "Что такое cookies",
    "legal.cookies.what.body":
      "Cookies — небольшие файлы, которые сайт сохраняет в вашем браузере, чтобы запомнить настройки и сессию.",
    "legal.cookies.use.title": "Какие cookies мы используем",
    "legal.cookies.use.li1":
      "Сессионные: для входа и сохранения вашей авторизации.",
    "legal.cookies.use.li2":
      "Настройки: язык интерфейса, тема, активное рабочее пространство.",
    "legal.cookies.use.li3":
      "Безопасность: защита от CSRF и нежелательных действий.",
    "legal.cookies.thirdparty.title": "Сторонние cookies",
    "legal.cookies.thirdparty.body":
      "Мы не подгружаем рекламные трекеры. Vercel и инфраструктурные провайдеры могут использовать собственные технические cookies для балансировки нагрузки.",
    "legal.cookies.control.title": "Управление",
    "legal.cookies.control.body":
      "Вы всегда можете очистить cookies в настройках браузера. Если убрать сессионные cookies — придётся заново войти в аккаунт.",

    // Public marketing pages — shared chrome
    "public.nav.pricing": "Тарифы",
    "public.nav.help": "Помощь",
    "public.nav.changelog": "Что нового",
    "public.nav.signIn": "Войти",
    "public.nav.start": "Начать бесплатно",

    // Pricing
    "pricing.headline": "Простые тарифы — без сюрпризов",
    "pricing.subhead":
      "Сначала бесплатно попробуйте AI-поиск и оценку лидов. Платите только когда поймёте, что Convioo вписывается в процесс.",
    "pricing.popular": "Популярный",

    "pricing.free.name": "Free",
    "pricing.free.tagline": "Чтобы посмотреть, как это работает",
    "pricing.free.price": "$0",
    "pricing.free.per": "/мес",
    "pricing.free.cta": "Создать аккаунт",

    "pricing.pro.name": "Personal Pro",
    "pricing.pro.tagline": "Для соло-агентств и фрилансеров",
    "pricing.pro.price": "$29",
    "pricing.pro.per": "/мес",
    "pricing.pro.cta": "Попробовать Pro",

    "pricing.team.name": "Team",
    "pricing.team.tagline": "Для команды до 5 менеджеров",
    "pricing.team.price": "$79",
    "pricing.team.per": "/мес",
    "pricing.team.cta": "Завести команду",

    "pricing.feat.searches5": "5 AI-поисков в месяц",
    "pricing.feat.searches200": "200 AI-поисков в месяц",
    "pricing.feat.searchesTeam": "500 AI-поисков на команду",
    "pricing.feat.aiScore": "AI-скоринг по каждой компании",
    "pricing.feat.henryConsult": "Helper Henry для уточнения ниши",
    "pricing.feat.crmBasic": "Базовый CRM с заметками и статусами",
    "pricing.feat.exportCsv": "Экспорт CSV/JSON",
    "pricing.feat.outreachTemplates": "Библиотека шаблонов писем",
    "pricing.feat.customFields": "Пользовательские поля у лидов",
    "pricing.feat.dailyDigest": "Ежедневный дайджест по горячим лидам",
    "pricing.feat.team5": "До 5 пользователей",
    "pricing.feat.sharedCrm": "Общий CRM и дедуп лидов",
    "pricing.feat.dedupTeam": "Лид не показывается двум менеджерам",
    "pricing.feat.activityFeed": "Лента действий команды",
    "pricing.feat.henryTeam": "Henry помнит контекст команды",

    "pricing.faq.title": "Частые вопросы",
    "pricing.faq.q1": "Что считается одним поиском?",
    "pricing.faq.a1":
      "Один запрос вида «маркетинговые агентства в Берлине». Возвращается до 60 компаний, каждая прогоняется через AI-скоринг — это и есть один кредит.",
    "pricing.faq.q2": "Можно ли отменить подписку?",
    "pricing.faq.a2":
      "Да, в любой момент через личный кабинет. Деньги за неиспользованный период возвращаем по запросу.",
    "pricing.faq.q3": "А есть пробный период у Pro?",
    "pricing.faq.a3":
      "Тариф Free уже даёт 5 настоящих поисков в месяц — этого хватит, чтобы понять, насколько Convioo попадает в вашу нишу.",
    "pricing.faq.q4": "Что с GDPR и данными?",
    "pricing.faq.a4":
      "Все данные хранятся в EU-инфраструктуре. В разделе «Профиль» в один клик можно скачать полный экспорт или удалить аккаунт.",

    // Help center
    "help.title": "Помощь",
    "help.subtitle":
      "Короткие ответы на частые вопросы. Не нашли своё — напишите нам.",
    "help.q.start": "С чего начать после регистрации?",
    "help.a.start":
      "Откройте «Новый поиск» в боковой панели, опишите свою нишу одной фразой и Henry поможет уточнить регион и аудиторию. Через минуту увидите первый список лидов с AI-скором.",
    "help.q.search": "Как формулировать запрос для поиска?",
    "help.a.search":
      "Лучше всего работает «<тип бизнеса> в <город или регион>». Например, «кровельные компании в Бостоне» или «дентал-клиники в Праге».",
    "help.q.import": "Можно загрузить свой список компаний?",
    "help.a.import":
      "Да, в разделе «Импорт» — загрузите CSV с колонками name / website / region. Convioo создаст отдельную сессию и подтянет AI-скор к каждой строке.",
    "help.q.score": "Что означает AI-скор?",
    "help.a.score":
      "Это число от 0 до 100, где 70+ обычно «горячий» — компания соответствует вашему ICP, имеет признаки, что она готова к контакту, и нет красных флагов.",
    "help.q.henry": "Кто такой Henry?",
    "help.a.henry":
      "Помощник на основе Claude. Он держит в голове ваш профиль и команду, помогает уточнять ниши, делает выжимку по конкретному лиду и подсказывает, чем зацепить.",
    "help.q.team": "Как добавить коллег?",
    "help.a.team":
      "В разделе «Команда» создаёте рабочее пространство и отправляете приглашение по ссылке. Каждый член команды видит общую базу лидов с дедупликацией.",
    "help.q.export": "Как выгрузить мои данные?",
    "help.a.export":
      "В «Профиле» → «Конфиденциальность и данные» нажмите «Экспорт моих данных». Получите JSON со всем профилем, лидами и активностью.",
    "help.q.delete": "Как удалить аккаунт?",
    "help.a.delete":
      "Там же в «Профиле» — кнопка «Удалить аккаунт». Подтверждение по email и паролю; после этого все ваши данные удаляются мгновенно и без восстановления.",
    "help.contact.title": "Не нашли ответа?",
    "help.contact.body":
      "Напишите нам — отвечаем обычно в течение рабочего дня.",

    // Changelog
    "changelog.title": "Что нового",
    "changelog.subtitle":
      "Заметные изменения в Convioo. Меньшие правки и фиксы — в pull request'ах.",
    "changelog.r21.title": "GDPR-экспорт, юридические страницы и журнал активности",
    "changelog.r21.b1":
      "Скачивание полного дампа ваших данных в JSON одной кнопкой.",
    "changelog.r21.b2":
      "Удаление аккаунта с подтверждением по email и паролю.",
    "changelog.r21.b3":
      "Публичные страницы Privacy / Terms / Cookies на двух языках.",
    "changelog.r21.b4":
      "Журнал безопасности: вход, регистрация, экспорт и удаление видны в профиле.",
    "changelog.r20.title": "CSV-импорт и поиск ЛПР",
    "changelog.r20.b1":
      "Загружайте свои списки компаний — Convioo создаст из них сессию и проскорит каждую строку.",
    "changelog.r20.b2":
      "Кнопка «Найти контакты ЛПР» в карточке лида: имя, должность, email и LinkedIn.",
    "changelog.r20.b3":
      "Любые лишние колонки CSV сохраняются как пользовательские поля у лида.",
    "changelog.r19.title": "Henry стал активнее",
    "changelog.r19.b1":
      "AI-исследование конкретного лида прямо из чата с Henry.",
    "changelog.r19.b2":
      "Запуск нового поиска по диалогу — без перехода в форму.",
    "changelog.r18.title": "CRM-зрелость",
    "changelog.r18.b1": "Пользовательские поля под каждого лида.",
    "changelog.r18.b2": "Таймлайн активности с источниками изменений.",
    "changelog.r18.b3": "Задачи и напоминания, привязанные к лиду.",

    // Comparison pages
    "vs.eyebrow": "Сравнение",
    "vs.headline": "Convioo против {competitor}",
    "vs.col.feature": "Параметр",
    "vs.row.pricing": "Цена",
    "vs.row.aiScore": "AI-скоринг",
    "vs.row.crm": "Встроенный CRM",
    "vs.row.assistant": "AI-ассистент",
    "vs.row.dataSource": "Источник данных",
    "vs.row.audience": "Для кого",

    "vs.convioo.pricing": "От $0 до $79/мес",
    "vs.convioo.aiScore": "Скор и аналитика по каждой компании",
    "vs.convioo.crm": "Заметки, статусы, задачи, активность",
    "vs.convioo.assistant": "Henry помнит ваш профиль и команду",
    "vs.convioo.dataSource": "Google Places + сайт + AI",
    "vs.convioo.audience": "Маркетинговые агентства и SMB-команды",

    "vs.apollo.name": "Apollo",
    "vs.apollo.subhead":
      "Apollo — большая база контактов и outbound-инструмент. Convioo фокусируется на AI-скоринге малых и локальных компаний по конкретной нише.",
    "vs.apollo.pricing": "От $49/пользователь",
    "vs.apollo.aiScore": "Базовый скоринг по списку",
    "vs.apollo.crm": "Лёгкий CRM, sales-engagement",
    "vs.apollo.assistant": "Не входит",
    "vs.apollo.dataSource": "Своя база контактов",
    "vs.apollo.audience": "B2B SaaS sales-команды",

    "vs.clay.name": "Clay",
    "vs.clay.subhead":
      "Clay — мощный конструктор enrichment-таблиц. Convioo проще для маркетингового агентства: пара кликов и готовый отчёт по горячим лидам.",
    "vs.clay.pricing": "От $149/мес",
    "vs.clay.aiScore": "Через no-code workflow",
    "vs.clay.crm": "Через интеграции",
    "vs.clay.assistant": "AI-ассистент только для формул",
    "vs.clay.dataSource": "Десятки источников через коннекторы",
    "vs.clay.audience": "Growth/RevOps инженеры",

    "vs.lusha.name": "Lusha",
    "vs.lusha.subhead":
      "Lusha — поставщик контактов и phone-данных. Convioo берёт на себя весь цикл: от подбора компаний до AI-аналитики и outreach-шаблонов.",
    "vs.lusha.pricing": "От $39/пользователь",
    "vs.lusha.aiScore": "Не входит",
    "vs.lusha.crm": "Не входит",
    "vs.lusha.assistant": "Не входит",
    "vs.lusha.dataSource": "База контактов",
    "vs.lusha.audience": "SDR-команды enterprise",

    "vs.cta.title": "Готовы попробовать Convioo вместо {competitor}?",
    "vs.cta.body":
      "Бесплатный тариф включает 5 настоящих AI-поисков в месяц — этого достаточно, чтобы оценить разницу.",
    "vs.cta.start": "Начать бесплатно",
    "vs.cta.pricing": "Смотреть тарифы",
    "profile.field.business": "Размер бизнеса",
    "profile.field.region": "Домашний регион",
    "profile.field.offer": "Профессия / предложение",
    "profile.field.offerRaw": "Что вы продаёте (ваши слова)",
    "profile.field.niches": "Целевые ниши",
    "profile.field.age": "Возраст",
    "profile.field.gender": "Пол",
    "profile.field.displayName": "Имя",
    "profile.empty": "Не указано",
    "profile.editor.title": "Редактирование профиля",
    "profile.editor.subtitle":
      "Чем точнее данные — тем точнее AI-скор каждого лида.",
    "profile.editor.save": "Сохранить",
    "profile.editor.cancel": "Отмена",
    "profile.editor.saving": "Сохраняем…",
    "profile.editor.saved": "Сохранено ✓",
    "profile.editor.askHenry": "Заполнить с Henry",
    "profile.editor.tooLong":
      "Поле «{field}» слишком длинное — сократите до {max} символов.",
    "profile.field.displayNamePh": "Как к вам обращаться",
    "profile.field.regionPh": "Например: Берлин, Алматы, Ню Йорк",
    "profile.field.offerRawPh":
      "Опишите своими словами — какая услуга, для кого, в чём ценность.",
    "profile.field.nichesPh": "Добавьте нишу и Enter",
    "profile.niches.suggest": "Подобрать с Henry",
    "profile.niches.suggestAgain": "Подобрать ещё",
    "profile.niches.suggestEmpty":
      "Henry не нашёл подходящих ниш — уточните «что вы продаёте» и попробуйте снова.",
    "profile.nudge.title": "Заполните профиль для лучшего качества",
    "profile.nudge.body":
      "AI оценивает каждого лида под ваш профиль: чем понятнее что вы продаёте и кому, тем точнее hot/warm/cold и подача. Заполните вручную или поговорите с Henry — он умеет извлекать данные из обычного разговора.",
    "profile.nudge.manual": "Заполнить вручную",
    "profile.nudge.henry": "Поговорить с Henry",
    "profile.nudge.dismiss": "Скрыть на сегодня",
    "profile.memory.title": "Что помнит Henry",
    "profile.memory.subtitle":
      "Henry сохраняет короткие выводы из ваших диалогов, чтобы при следующей встрече помнить контекст. Можно очистить — он начнёт с чистого листа.",
    "profile.memory.empty":
      "Пока Henry ничего не запомнил. Поговорите с ним — после нескольких сообщений тут появятся факты.",
    "profile.memory.clear": "Очистить память",
    "profile.memory.confirm": "Точно очистить",
    "profile.memory.kind.summary": "сессия",
    "profile.memory.kind.fact": "факт",

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
    "settings.tint.title": "Цвет фона",
    "settings.tint.subtitle":
      "Лёгкий оттенок фона для текущей рабочей зоны — помогает визуально различать личное и команды.",
    "settings.tint.scopePersonal": "Применяется к личной зоне",
    "settings.tint.scopeTeam": "Применяется к команде «{name}»",
    "settings.tint.default": "Стандартный",
    "settings.tint.green": "Зелёный",
    "settings.tint.dark": "Тёмный",
    "settings.tint.orange": "Оранжевый",
    "billing.title": "Подписка",
    "billing.subtitle":
      "Тарифные планы Convioo. Сейчас всё бесплатно — это карта возможностей под будущий релиз.",
    "billing.devBadge": "В разработке",
    "billing.demoNotice":
      "Сейчас Convioo работает как открытая демо-версия — все фичи доступны бесплатно. Цены ниже — предварительные ориентиры на платный релиз; финальные суммы зафиксируем ближе к запуску. Купить пока нельзя.",
    "billing.cta": "Скоро",
    "billing.popular": "Популярный",
    "billing.teamGate.title": "Команды только с подпиской",
    "billing.teamGate.body":
      "Создание команды и общий CRM будут доступны от тарифа Team Standard. Личная зона остаётся бесплатной во всех планах.",
    "billing.plan.free.name": "Free",
    "billing.plan.free.tagline":
      "Демо-доступ для одного пользователя. Подходит чтобы попробовать продукт на реальной задаче.",
    "billing.plan.free.price": "$0",
    "billing.plan.free.period": "/ навсегда",
    "billing.plan.personal_pro.name": "Personal Pro",
    "billing.plan.personal_pro.tagline":
      "Для соло-продажника или фрилансера. Снимает лимиты и открывает Henry-помощников.",
    "billing.plan.personal_pro.price": "$19",
    "billing.plan.personal_pro.period": "/ мес · предварительно",
    "billing.plan.team_standard.name": "Team Standard",
    "billing.plan.team_standard.tagline":
      "Команда до 5 человек, общий CRM, дедупликация лидов, командный Henry.",
    "billing.plan.team_standard.price": "$49",
    "billing.plan.team_standard.period": "/ мес · предварительно",
    "billing.plan.team_pro.name": "Team Pro",
    "billing.plan.team_pro.tagline":
      "Для агентств. Команда до 25 человек, кастомные поля, kanban-pipeline, API и приоритет в поддержке.",
    "billing.plan.team_pro.price": "$149",
    "billing.plan.team_pro.period": "/ мес · предварительно",
    "billing.feat.searchesFree": "5 поисков в месяц",
    "billing.feat.searchesPro": "50 поисков в месяц",
    "billing.feat.searchesTeamStandard": "100 поисков в месяц на команду",
    "billing.feat.searchesTeamPro": "500 поисков в месяц на команду",
    "billing.feat.leadsPerSession": "До 50 лидов на сессию",
    "billing.feat.aiScore": "AI-скоринг и персональная подача",
    "billing.feat.henryConsult": "Henry — встроенный консультант",
    "billing.feat.crmBasic": "Личный CRM (статусы, заметки, пометки)",
    "billing.feat.exportCsv": "Excel / CSV экспорт",
    "billing.feat.dailyDigest": "Daily digest «новые горячие»",
    "billing.feat.outreachTemplates": "Библиотека шаблонов outreach",
    "billing.feat.unlimitedHistory": "Хранение лидов без срока",
    "billing.feat.teams": "Командные пространства",
    "billing.feat.team5": "Команда до 5 человек",
    "billing.feat.team25": "Команда до 25 человек",
    "billing.feat.sharedCrm": "Общий командный CRM",
    "billing.feat.dedupTeam": "Дедупликация лидов внутри команды",
    "billing.feat.henryTeam": "Командный Henry с памятью на всех",
    "billing.feat.activityFeed": "Лента активности команды",
    "billing.feat.weeklyCheckin": "Henry Weekly Check-in",
    "billing.feat.kanbanPipeline": "Kanban-pipeline по сделкам",
    "billing.feat.customFields": "Кастомные поля на лидах",
    "billing.feat.searchAlerts": "Уведомления о новых лидах под нишу",
    "billing.feat.apiAccess": "API-доступ",
    "billing.feat.prioritySupport": "Приоритетная поддержка",
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
    "common.delete": "Delete",
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
    "nav.billing": "Plans",
    "nav.templates": "Templates",
    "nav.import": "Import CSV",
    "import.title": "Import a company list",
    "import.subtitle":
      "Upload a CSV — Convioo will create a session, attach custom fields, and wire it into the CRM.",
    "import.dropTitle": "Drop a CSV here",
    "import.dropBody":
      "Header row required. Standard columns: name (required), website, region, phone, category. Anything else becomes a custom field.",
    "import.pick": "Pick a file",
    "import.expectedColumns":
      "Sample headers: name,website,region,phone,category — order and case don't matter. Extra columns land as custom fields on every lead.",
    "import.empty": "The file has no data rows.",
    "import.previewTitle": "Preview · {n} rows",
    "import.skipped": "{n} rows skipped (missing name).",
    "import.pickAnother": "Pick another file",
    "import.runImport": "Run import",
    "import.labelField": "Session name",
    "import.previewTrunc": "+ {n} more rows that will also be imported.",
    "lead.extras.findDecisionMakers": "Find decision-makers",
    "templates.title": "Outreach templates",
    "templates.subtitle":
      "Saved emails with {name}, {niche}, {region} placeholders. Henry tailors them to each lead.",
    "templates.new": "New template",
    "templates.copy": "Copy body",
    "templates.empty.title": "No templates yet",
    "templates.empty.body":
      "Save your Cold #1 / Follow-up / Breakup once and copy them in one click on every lead.",
    "templates.editor.titleNew": "New template",
    "templates.editor.titleEdit": "Edit template",
    "templates.editor.save": "Save",
    "templates.field.name": "Name",
    "templates.field.namePh": "e.g. Cold #1 for dental clinics",
    "templates.field.subject": "Subject",
    "templates.field.subjectPh": "Email subject (optional)",
    "templates.field.body": "Body",
    "templates.field.bodyHint": "placeholders: {name}, {niche}, {region}",
    "templates.field.bodyPh":
      "Hi {name}! I noticed you …",
    "templates.field.tone": "Tone",
    "nav.signOut": "Sign out",
    "nav.themeDark": "Switch to dark",
    "nav.themeLight": "Switch to light",

    "kbd.title": "Keyboard shortcuts",
    "kbd.dashboard": "Dashboard",
    "kbd.search": "New search",
    "kbd.leads": "All leads",
    "kbd.import": "Import CSV",
    "kbd.templates": "Templates",
    "kbd.profile": "Profile",
    "kbd.theme": "Toggle theme",
    "kbd.toggleHelp": "Show / hide this overlay",

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
    "auth.field.inviteCode": "Invite code",
    "auth.field.inviteCodePh": "issued by the founder",
    "auth.field.inviteCodeHint": "required",
    "auth.login.invalid": "Invalid email or password.",

    "verify.idle.title": "Confirm your email",
    "verify.idle.body":
      "Click the button below to confirm your email. We need an explicit click because email providers pre-scan links in messages — auto-verifying on page load would burn the token before you ever clicked it.",
    "verify.idle.cta": "Confirm email",
    "verify.verifying.title": "Verifying your email…",
    "verify.pending.title": "Verifying your email…",
    "verify.pending.body": "One sec — checking the link.",
    "verify.ok.title": "Email verified",
    "verify.ok.body":
      "Done. You can launch searches now. If you weren't signed in — sign in normally.",
    "verify.ok.continue": "Go to workspace",
    "verify.error.title": "Couldn't verify your email",
    "verify.error.body":
      "The link expired or was already used. Request a fresh one from the banner in your workspace.",
    "verify.error.retry": "Try again",
    "verify.gotoLogin": "Go to login",
    "verifyBanner.title": "Verify your email ({email})",
    "verifyBanner.body":
      "Search launches are blocked until your email is verified. Check your inbox — we sent the link.",
    "verifyBanner.resend": "Resend link",
    "verifyBanner.sent": "Sent ✓",

    "settings.account": "Account",
    "settings.account.emailLabel": "Email",
    "settings.account.passwordLabel": "Password",
    "settings.account.passwordHelp": "Change anytime — requires your current password.",
    "settings.account.changeEmail": "Change email",
    "settings.account.changePassword": "Change password",
    "settings.account.verified": "verified",
    "settings.account.unverified": "unverified",
    "settings.account.newEmailPh": "New email",
    "settings.account.passwordConfirmPh": "Current password (to confirm)",
    "settings.account.sendVerify": "Send verification link",
    "settings.account.sameEmail": "That's already your current email.",
    "settings.account.changeEmailSent":
      "We've sent a confirmation link to {email}. Click it to switch — your current email keeps working until you do.",
    "settings.account.currentPasswordPh": "Current password",
    "settings.account.newPasswordPh": "New password (min 8 chars)",
    "settings.account.confirmPasswordPh": "Confirm new password",
    "settings.account.passwordsDontMatch": "Passwords don't match.",
    "settings.account.passwordSaved": "Password updated ✓",
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
    "auth.field.age": "Age",
    "auth.field.ageHint": "optional — helps AI pick the right tone",
    "auth.field.ageSkip": "Skip",
    "auth.field.gender": "Gender",
    "auth.field.genderHint":
      "optional — Henry will use the right grammatical form",
    "auth.field.genderSkip": "Skip",
    "auth.field.gender.male": "Male",
    "auth.field.gender.female": "Female",
    "auth.field.gender.other": "Other",
    "auth.register.title": "Create your account.",
    "auth.register.subtitle":
      "Bare minimum to start — name, email, password. The rest gets dialled in inside the workspace.",
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
    "dashboard.quota.eyebrow": "Search quota",
    "dashboard.quota.subtitle": "{used} of {limit} used",
    "dashboard.checkin.eyebrow": "Henry · weekly check-in",
    "tasks.todayTitle": "For today",
    "tasks.today": "today",
    "tasks.overdue": "overdue",
    "lead.extras.tasks": "Tasks",
    "lead.extras.tasks.ph": "e.g. call on Wednesday",
    "lead.extras.customFields": "Custom fields",
    "lead.extras.customFields.keyPh": "key (decision_maker)",
    "lead.extras.customFields.valPh": "value",
    "lead.extras.activity": "Activity",
    "lead.extras.activity.statusKind": "Status: {from} → {to}",
    "lead.extras.activity.notesKind": "Notes updated",
    "lead.extras.activity.assignedKind": "Assigned to #{id}",
    "lead.extras.activity.unassignedKind": "Unassigned",
    "lead.extras.activity.markKind": "Colour mark",
    "lead.extras.activity.customFieldKind": "Field \"{key}\"",
    "lead.extras.activity.taskKind": "Task: {content}",
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
    "search.consult.greetingNichesRegion":
      "Hi. I see you're focused on {niches} in {region}. Which niche do we start with today, or want to try something new?",
    "search.consult.greetingNiches":
      "Hi. Your niches are {niches}. Which one are we working today and in which city?",
    "search.consult.greetingRegionOffer":
      "Hi. I know you work in {region}. What segment are we hunting today?",
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
    "assistant.applied": "Saved ✓",
    "assistant.applyError":
      "Couldn't update profile ({detail}).",
    "assistant.pending.title": "Henry wants to save",
    "assistant.pending.confirm": "Save it",
    "assistant.pending.dismiss": "Not now",
    "assistant.launchedSearch": "Search launched",
    "assistant.openSession": "Open session",
    "lead.email.deepResearch": "Deep research",
    "lead.email.deepResearchHint":
      "Henry re-scans the lead's site and pulls concrete facts for the opener.",
    "lead.email.notableFacts": "What Henry found on the site:",
    "lead.email.recentSignal": "Recent signal:",
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
    "search.chat.placeholder": "Describe who you're looking for…",
    "search.chat.gotIt":
      "Got it — **{niche}** in **{region}**. Click Launch when ready, or tweak the form on the right.",
    "search.chat.needBoth":
      'Tell me the niche and the region, e.g. "roofing companies in New York".',
    "search.axes.eyebrow": "Pick with Henry",
    "search.axes.subtitle":
      "Get 4 ready-to-launch search configs based on your profile — click to autofill the form.",
    "search.axes.cta": "Pick options",
    "search.axes.ctaAgain": "Pick more",
    "search.axes.hide": "Hide",
    "search.axes.empty":
      "Henry couldn't suggest configs — fill 'what you sell' in /app/profile and try again.",
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
    "search.form.offerSource.profile": "From my profile",
    "search.form.offerSource.custom": "Custom for this search",
    "search.form.offerSource.empty":
      "Your profile has no offer yet. Fill it in /app/profile, or write a one-off below — it only applies to this search.",
    "search.form.offerSource.profileEmpty":
      "No offer yet — set it in your profile so AI uses it on every search.",
    "search.form.offerSource.profileLink": "Open profile →",
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
    "crm.smart.all": "All",
    "crm.smart.hotWeek": "Hot this week",
    "crm.smart.newToday": "New today",
    "crm.smart.untouched14": "Untouched 14+ days",
    "crm.kanban.empty": "Drop a card here",
    "crm.status.all": "all",
    "crm.status.new": "new",
    "crm.status.contacted": "contacted",
    "crm.status.replied": "replied",
    "crm.status.won": "won",
    "crm.status.archived": "archived",
    "crm.search.placeholder": "Search by name, address, category…",
    "crm.search.clear": "Clear",
    "crm.search.results": "{n} leads",
    "crm.sort.score_desc": "Score: high to low",
    "crm.sort.score_asc": "Score: low to high",
    "crm.sort.created_desc": "Newest first",
    "crm.sort.created_asc": "Oldest first",
    "crm.sort.touched_desc": "Recently touched",
    "crm.sort.name_asc": "Name A → Z",
    "crm.sort.name_desc": "Name Z → A",
    "crm.bulk.selectAll": "Select all",
    "crm.bulk.selected": "{n} selected",
    "crm.bulk.setStatus": "Status",
    "crm.bulk.setMark": "Mark",
    "crm.bulk.cancel": "Clear selection",
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
    "lead.email.generate": "Generate email",
    "lead.email.regenerate": "Rewrite",
    "lead.email.draft": "Email draft",
    "lead.email.subject": "Subject",
    "lead.email.body": "Body",
    "lead.email.copy": "Copy",
    "lead.email.copyAll": "Copy all",
    "lead.email.copied": "Copied ✓",
    "lead.email.sendGmail": "Send via Gmail",
    "lead.email.addExtra": "Add context",
    "lead.email.hideExtra": "Hide context",
    "lead.email.extraPh":
      "Anything specific about this lead Henry should weave in (optional).",
    "lead.email.tone.professional": "Professional",
    "lead.email.tone.casual": "Warm",
    "lead.email.tone.bold": "Bold",
    "lead.mark.title": "My mark",
    "lead.mark.clear": "Clear",
    "lead.mark.help":
      "Only you see this colour. Use it however you like — priority, follow-up, anything.",

    "profile.title": "My profile",
    "profile.subtitle": "How AI scores leads for you",
    "profile.hint":
      "Your profile personalises every AI score and pitch.",

    // Privacy & data block on /app/profile
    "profile.privacy.title": "Privacy & data",
    "profile.privacy.subtitle":
      "Download a copy of your data, review your audit log, or delete your account.",
    "profile.privacy.export": "Export my data",
    "profile.privacy.exportHint":
      "A JSON file with your full profile, leads and activity.",
    "profile.privacy.audit": "Audit log",
    "profile.privacy.auditEmpty": "No entries yet.",
    "profile.privacy.delete": "Delete account",
    "profile.privacy.deleteHint":
      "This is permanent. All of your data will be removed.",
    "profile.privacy.deleteConfirmTitle": "Delete your account permanently",
    "profile.privacy.deleteConfirmBody":
      "To confirm, retype your email and password. This action cannot be undone.",
    "profile.privacy.deleteConfirmEmail": "Your email",
    "profile.privacy.deleteConfirmPassword": "Password",
    "profile.privacy.deleteConfirmCta": "Delete forever",
    "profile.privacy.deleteFailed":
      "Could not delete the account. Check your email and password.",

    // Legal pages
    "legal.updated": "Updated {date}",
    "legal.nav.privacy": "Privacy policy",
    "legal.nav.terms": "Terms of service",
    "legal.nav.cookies": "Cookies",
    "legal.nav.contact": "Questions — {email}",

    "legal.privacy.title": "Privacy policy",
    "legal.privacy.intro":
      "This page explains what data Convioo collects, how we use it, and the rights you have.",
    "legal.privacy.collect.title": "What data we collect",
    "legal.privacy.collect.body":
      "We only store what's needed to run the service:",
    "legal.privacy.collect.li1":
      "Account: name, email, password (stored as an argon2 hash), profile and niche settings.",
    "legal.privacy.collect.li2":
      "Searches and leads: your queries, Google Places results, notes, statuses, lead activity.",
    "legal.privacy.collect.li3":
      "Technical events: sign-in dates, IP and user-agent in the audit log (security only).",
    "legal.privacy.use.title": "How we use the data",
    "legal.privacy.use.body":
      "Data is used solely to operate the service: company search, AI scoring, CRM, support. We do not sell your data and do not use it for advertising.",
    "legal.privacy.share.title": "Who we share data with",
    "legal.privacy.share.body":
      "Only infrastructure providers we cannot operate without:",
    "legal.privacy.share.li1":
      "Anthropic (Claude API) — runs the AI scoring and email drafts.",
    "legal.privacy.share.li2":
      "Google Places API — sources company information.",
    "legal.privacy.share.li3":
      "Hosting (Railway, Vercel) — runs the application and database.",
    "legal.privacy.rights.title": "Your rights",
    "legal.privacy.rights.body":
      "Under \"My profile → Privacy & data\" you can download a full export of your data as JSON or delete your account permanently in one click. For any data question email support@convioo.com.",
    "legal.privacy.retention.title": "Data retention",
    "legal.privacy.retention.body":
      "Data is kept while your account is active. When you delete your account, all of your information (profile, leads, notes, activity) is removed immediately.",
    "legal.privacy.contact.title": "Contact",
    "legal.privacy.contact.body":
      "For privacy and GDPR requests email support@convioo.com. We respond within 30 days.",

    "legal.terms.title": "Terms of service",
    "legal.terms.intro":
      "By using Convioo you agree to these terms. If anything is unclear, contact us before continuing.",
    "legal.terms.account.title": "Your account",
    "legal.terms.account.body":
      "You are responsible for the security of your password and for all activity in your account. Tell us right away if you notice anything suspicious.",
    "legal.terms.allowed.title": "Allowed and forbidden uses",
    "legal.terms.allowed.body":
      "Convioo is built for honest B2B outreach. The following are not allowed:",
    "legal.terms.allowed.li1":
      "Mass spam or any action that breaks data-protection law (GDPR/CCPA).",
    "legal.terms.allowed.li2":
      "Trying to bypass limits, reverse-engineer or attack the infrastructure.",
    "legal.terms.allowed.li3":
      "Using the service to sell unlawful goods or to deceive clients.",
    "legal.terms.payments.title": "Payments and subscriptions",
    "legal.terms.payments.body":
      "Paid plans are charged on subscription (today access is free during beta). Refunds available on reasonable request within 14 days.",
    "legal.terms.warranty.title": "No warranties",
    "legal.terms.warranty.body":
      "The service is provided as-is. We aim for high uptime but do not guarantee 100% availability or absolute AI accuracy. You make the final decisions — Convioo is a tool.",
    "legal.terms.termination.title": "Termination",
    "legal.terms.termination.body":
      "You can delete your account anytime from the profile page. We may close accounts that violate these terms after notifying you.",
    "legal.terms.law.title": "Governing law",
    "legal.terms.law.body":
      "These terms are governed by Estonian law (where the operating entity is registered), without prejudice to mandatory consumer protections of your country of residence.",

    "legal.cookies.title": "Cookies",
    "legal.cookies.intro":
      "Convioo uses a minimal set of cookies — only what's needed to run the site. No advertising trackers.",
    "legal.cookies.what.title": "What are cookies",
    "legal.cookies.what.body":
      "Cookies are small files a site stores in your browser to remember settings and sessions.",
    "legal.cookies.use.title": "Cookies we use",
    "legal.cookies.use.li1":
      "Session: for authentication and keeping you signed in.",
    "legal.cookies.use.li2":
      "Preferences: interface language, theme, active workspace.",
    "legal.cookies.use.li3":
      "Security: protection against CSRF and unwanted actions.",
    "legal.cookies.thirdparty.title": "Third-party cookies",
    "legal.cookies.thirdparty.body":
      "We do not load advertising trackers. Vercel and our infrastructure providers may set their own technical cookies for load balancing.",
    "legal.cookies.control.title": "Controlling cookies",
    "legal.cookies.control.body":
      "You can clear cookies anytime in your browser settings. Removing session cookies will sign you out.",

    // Public marketing pages — shared chrome
    "public.nav.pricing": "Pricing",
    "public.nav.help": "Help",
    "public.nav.changelog": "Changelog",
    "public.nav.signIn": "Sign in",
    "public.nav.start": "Start free",

    // Pricing
    "pricing.headline": "Simple pricing — no surprises",
    "pricing.subhead":
      "Try the AI search and lead scoring for free first. Pay only when you've decided Convioo fits the way you work.",
    "pricing.popular": "Popular",

    "pricing.free.name": "Free",
    "pricing.free.tagline": "To see how it works",
    "pricing.free.price": "$0",
    "pricing.free.per": "/mo",
    "pricing.free.cta": "Create account",

    "pricing.pro.name": "Personal Pro",
    "pricing.pro.tagline": "For solo agencies and freelancers",
    "pricing.pro.price": "$29",
    "pricing.pro.per": "/mo",
    "pricing.pro.cta": "Try Pro",

    "pricing.team.name": "Team",
    "pricing.team.tagline": "For teams up to 5 people",
    "pricing.team.price": "$79",
    "pricing.team.per": "/mo",
    "pricing.team.cta": "Set up team",

    "pricing.feat.searches5": "5 AI searches per month",
    "pricing.feat.searches200": "200 AI searches per month",
    "pricing.feat.searchesTeam": "500 AI searches per team",
    "pricing.feat.aiScore": "AI scoring on every company",
    "pricing.feat.henryConsult": "Helper Henry to refine the niche",
    "pricing.feat.crmBasic": "Basic CRM with notes and statuses",
    "pricing.feat.exportCsv": "CSV / JSON export",
    "pricing.feat.outreachTemplates": "Outreach template library",
    "pricing.feat.customFields": "Custom fields on leads",
    "pricing.feat.dailyDigest": "Daily digest of hot leads",
    "pricing.feat.team5": "Up to 5 users",
    "pricing.feat.sharedCrm": "Shared CRM and lead deduplication",
    "pricing.feat.dedupTeam": "A lead never shows up for two reps",
    "pricing.feat.activityFeed": "Team activity feed",
    "pricing.feat.henryTeam": "Henry remembers team context",

    "pricing.faq.title": "Frequently asked",
    "pricing.faq.q1": "What counts as one search?",
    "pricing.faq.a1":
      "One query like \"marketing agencies in Berlin\". Returns up to 60 companies, each scored by the AI — that's one credit.",
    "pricing.faq.q2": "Can I cancel anytime?",
    "pricing.faq.a2":
      "Yes, from your account in one click. We refund the unused period on request.",
    "pricing.faq.q3": "Is there a Pro trial?",
    "pricing.faq.a3":
      "Free already gives you 5 real searches a month — enough to see whether Convioo lands in your niche.",
    "pricing.faq.q4": "What about GDPR and data?",
    "pricing.faq.a4":
      "Everything is hosted on EU infrastructure. From the profile page you can export all your data or delete the account in one click.",

    // Help center
    "help.title": "Help",
    "help.subtitle":
      "Short answers to common questions. Didn't find yours — send us a note.",
    "help.q.start": "Where do I start after signing up?",
    "help.a.start":
      "Open \"New search\" in the sidebar, describe your niche in one phrase and Henry will help refine the region and audience. In a minute you'll see the first list of leads with AI scores.",
    "help.q.search": "How should I phrase a search?",
    "help.a.search":
      "What works best is \"<business type> in <city or region>\". For example, \"roofing companies in Boston\" or \"dental clinics in Prague\".",
    "help.q.import": "Can I upload my own list?",
    "help.a.import":
      "Yes — go to Import and upload a CSV with columns name / website / region. Convioo creates a new session and scores each row.",
    "help.q.score": "What does the AI score mean?",
    "help.a.score":
      "A 0–100 number where 70+ usually means \"hot\" — the company matches your ICP, shows signs of being ready to be contacted, and has no red flags.",
    "help.q.henry": "Who is Henry?",
    "help.a.henry":
      "An assistant powered by Claude. Henry remembers your profile and team, helps refine niches, summarises specific leads and suggests how to open the conversation.",
    "help.q.team": "How do I add teammates?",
    "help.a.team":
      "Open Team, create a workspace and send an invite link. Each member sees the shared lead base with deduplication.",
    "help.q.export": "How do I download my data?",
    "help.a.export":
      "From Profile → Privacy & data click Export my data. You'll get a JSON with your full profile, leads and activity.",
    "help.q.delete": "How do I delete my account?",
    "help.a.delete":
      "Same place in Profile — Delete account. Confirms via email + password and removes everything immediately, with no recovery.",
    "help.contact.title": "Didn't find an answer?",
    "help.contact.body":
      "Send us a note — we usually reply within a business day.",

    // Changelog
    "changelog.title": "Changelog",
    "changelog.subtitle":
      "Notable Convioo changes. Smaller fixes live in the pull requests.",
    "changelog.r21.title": "GDPR export, legal pages and audit log",
    "changelog.r21.b1":
      "One-click JSON dump of all your data.",
    "changelog.r21.b2":
      "Account deletion with email and password confirmation.",
    "changelog.r21.b3":
      "Public Privacy / Terms / Cookies pages in two languages.",
    "changelog.r21.b4":
      "Security log: sign-ins, sign-ups, exports and deletions visible from the profile.",
    "changelog.r20.title": "CSV import and decision-maker lookup",
    "changelog.r20.b1":
      "Upload your own list of companies — Convioo turns it into a session and scores each row.",
    "changelog.r20.b2":
      "Find decision-makers button on every lead: name, role, email and LinkedIn.",
    "changelog.r20.b3":
      "Any extra CSV columns are kept as custom fields on the lead.",
    "changelog.r19.title": "Henry got more active",
    "changelog.r19.b1":
      "Per-lead AI research right from the chat with Henry.",
    "changelog.r19.b2":
      "Launch a new search from the conversation — no need to leave the chat.",
    "changelog.r18.title": "CRM maturity",
    "changelog.r18.b1": "Custom fields on every lead.",
    "changelog.r18.b2": "Activity timeline with sourced changes.",
    "changelog.r18.b3": "Tasks and reminders attached to a lead.",

    // Comparison pages
    "vs.eyebrow": "Comparison",
    "vs.headline": "Convioo vs {competitor}",
    "vs.col.feature": "Feature",
    "vs.row.pricing": "Pricing",
    "vs.row.aiScore": "AI scoring",
    "vs.row.crm": "Built-in CRM",
    "vs.row.assistant": "AI assistant",
    "vs.row.dataSource": "Data source",
    "vs.row.audience": "Built for",

    "vs.convioo.pricing": "From $0 to $79/mo",
    "vs.convioo.aiScore": "Score and analysis on every company",
    "vs.convioo.crm": "Notes, statuses, tasks, activity",
    "vs.convioo.assistant": "Henry remembers your profile and team",
    "vs.convioo.dataSource": "Google Places + website + AI",
    "vs.convioo.audience": "Marketing agencies and SMB teams",

    "vs.apollo.name": "Apollo",
    "vs.apollo.subhead":
      "Apollo is a large contact database and outbound tool. Convioo focuses on AI-scoring small / local companies in your specific niche.",
    "vs.apollo.pricing": "From $49 / user",
    "vs.apollo.aiScore": "Basic scoring across the list",
    "vs.apollo.crm": "Light CRM, sales engagement",
    "vs.apollo.assistant": "Not included",
    "vs.apollo.dataSource": "Own contact database",
    "vs.apollo.audience": "B2B SaaS sales teams",

    "vs.clay.name": "Clay",
    "vs.clay.subhead":
      "Clay is a powerful enrichment-table builder. Convioo is simpler for a marketing agency: a few clicks and a ready report on hot leads.",
    "vs.clay.pricing": "From $149 / mo",
    "vs.clay.aiScore": "Via no-code workflows",
    "vs.clay.crm": "Through integrations",
    "vs.clay.assistant": "AI assistant only for formulas",
    "vs.clay.dataSource": "Dozens of sources via connectors",
    "vs.clay.audience": "Growth / RevOps engineers",

    "vs.lusha.name": "Lusha",
    "vs.lusha.subhead":
      "Lusha is a contact and phone-data provider. Convioo handles the whole flow: from picking companies to AI analysis and outreach templates.",
    "vs.lusha.pricing": "From $39 / user",
    "vs.lusha.aiScore": "Not included",
    "vs.lusha.crm": "Not included",
    "vs.lusha.assistant": "Not included",
    "vs.lusha.dataSource": "Contact database",
    "vs.lusha.audience": "Enterprise SDR teams",

    "vs.cta.title": "Ready to try Convioo instead of {competitor}?",
    "vs.cta.body":
      "The free tier includes 5 real AI searches a month — enough to feel the difference.",
    "vs.cta.start": "Start free",
    "vs.cta.pricing": "See pricing",
    "profile.field.business": "Business size",
    "profile.field.region": "Home region",
    "profile.field.offer": "Profession / offer",
    "profile.field.offerRaw": "What you sell (your words)",
    "profile.field.niches": "Target niches",
    "profile.field.age": "Age",
    "profile.field.gender": "Gender",
    "profile.field.displayName": "Display name",
    "profile.empty": "Not set",
    "profile.editor.title": "Edit profile",
    "profile.editor.subtitle":
      "The sharper the data, the sharper the AI score on every lead.",
    "profile.editor.save": "Save",
    "profile.editor.cancel": "Cancel",
    "profile.editor.saving": "Saving…",
    "profile.editor.saved": "Saved ✓",
    "profile.editor.askHenry": "Fill with Henry",
    "profile.editor.tooLong":
      'The "{field}" field is too long — trim it to {max} characters.',
    "profile.field.displayNamePh": "How should we address you",
    "profile.field.regionPh": "e.g. Berlin, Almaty, New York",
    "profile.field.offerRawPh":
      "Describe in your own words — the service, who it's for, the value.",
    "profile.field.nichesPh": "Add a niche, hit Enter",
    "profile.niches.suggest": "Pick with Henry",
    "profile.niches.suggestAgain": "Pick more",
    "profile.niches.suggestEmpty":
      "Henry couldn't find matching niches — sharpen 'what you sell' and try again.",
    "profile.nudge.title": "Fill your profile for better results",
    "profile.nudge.body":
      "AI scores every lead against your profile — the clearer your offer and target, the sharper hot/warm/cold and pitch get. Fill it manually or chat with Henry — he extracts the data from a normal conversation.",
    "profile.nudge.manual": "Fill manually",
    "profile.nudge.henry": "Chat with Henry",
    "profile.nudge.dismiss": "Hide for today",
    "profile.memory.title": "What Henry remembers",
    "profile.memory.subtitle":
      "Henry keeps short notes from your dialogues so the next time he's caught up. Clear it whenever — he'll start fresh.",
    "profile.memory.empty":
      "Henry hasn't recorded anything yet. Chat with him for a bit and notes will appear here.",
    "profile.memory.clear": "Clear memory",
    "profile.memory.confirm": "Yes, clear it",
    "profile.memory.kind.summary": "session",
    "profile.memory.kind.fact": "fact",

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
    "settings.tint.title": "Background tint",
    "settings.tint.subtitle":
      "A subtle tint for the active workspace — helps tell personal apart from team at a glance.",
    "settings.tint.scopePersonal": "Applies to your personal workspace",
    "settings.tint.scopeTeam": "Applies to team \"{name}\"",
    "settings.tint.default": "Default",
    "settings.tint.green": "Green",
    "settings.tint.dark": "Dark",
    "settings.tint.orange": "Orange",
    "billing.title": "Plans",
    "billing.subtitle":
      "Convioo subscription tiers. Everything is free right now — this is a roadmap of what ships at launch.",
    "billing.devBadge": "In development",
    "billing.demoNotice":
      "Convioo runs as an open demo for now — every feature is free. Prices below are preliminary anchors for the paid release; final numbers land closer to launch. Checkout isn't live yet.",
    "billing.cta": "Soon",
    "billing.popular": "Popular",
    "billing.teamGate.title": "Teams require a paid plan",
    "billing.teamGate.body":
      "Creating a team and the shared CRM unlock at Team Standard and up. Personal workspaces stay free across all plans.",
    "billing.plan.free.name": "Free",
    "billing.plan.free.tagline":
      "Demo access for one user. Enough to try the product on a real task.",
    "billing.plan.free.price": "$0",
    "billing.plan.free.period": "/ forever",
    "billing.plan.personal_pro.name": "Personal Pro",
    "billing.plan.personal_pro.tagline":
      "For solo salespeople and freelancers. Lifts limits and opens Henry helpers.",
    "billing.plan.personal_pro.price": "$19",
    "billing.plan.personal_pro.period": "/ mo · preliminary",
    "billing.plan.team_standard.name": "Team Standard",
    "billing.plan.team_standard.tagline":
      "Up to 5 teammates, shared CRM, lead dedup, team-mode Henry.",
    "billing.plan.team_standard.price": "$49",
    "billing.plan.team_standard.period": "/ mo · preliminary",
    "billing.plan.team_pro.name": "Team Pro",
    "billing.plan.team_pro.tagline":
      "For agencies. Up to 25 teammates, custom fields, kanban pipeline, API and priority support.",
    "billing.plan.team_pro.price": "$149",
    "billing.plan.team_pro.period": "/ mo · preliminary",
    "billing.feat.searchesFree": "5 searches a month",
    "billing.feat.searchesPro": "50 searches a month",
    "billing.feat.searchesTeamStandard": "100 team searches a month",
    "billing.feat.searchesTeamPro": "500 team searches a month",
    "billing.feat.leadsPerSession": "Up to 50 leads per session",
    "billing.feat.aiScore": "AI scoring and personal pitch",
    "billing.feat.henryConsult": "Henry, the in-product consultant",
    "billing.feat.crmBasic": "Personal CRM (status, notes, marks)",
    "billing.feat.exportCsv": "Excel / CSV export",
    "billing.feat.dailyDigest": "Daily 'fresh hot' digest",
    "billing.feat.outreachTemplates": "Outreach templates library",
    "billing.feat.unlimitedHistory": "Unlimited lead history",
    "billing.feat.teams": "Team workspaces",
    "billing.feat.team5": "Team up to 5 people",
    "billing.feat.team25": "Team up to 25 people",
    "billing.feat.sharedCrm": "Shared team CRM",
    "billing.feat.dedupTeam": "Lead dedup inside the team",
    "billing.feat.henryTeam": "Team-aware Henry with shared memory",
    "billing.feat.activityFeed": "Team activity feed",
    "billing.feat.weeklyCheckin": "Henry Weekly Check-in",
    "billing.feat.kanbanPipeline": "Kanban deal pipeline",
    "billing.feat.customFields": "Custom fields on leads",
    "billing.feat.searchAlerts": "Alerts for fresh in-niche leads",
    "billing.feat.apiAccess": "API access",
    "billing.feat.prioritySupport": "Priority support",
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
  // Ukrainian — first AI pass over the high-traffic strings (nav,
  // dashboard, search, CRM, lead modal, profile, onboarding, billing,
  // auth, legal). Anything we don't translate here falls through to
  // the Russian dictionary at lookup time, which Ukrainian readers
  // parse without effort. Pending manual proofread before locking.
  uk: {
    // Shared / buttons
    "common.newSearch": "Новий пошук",
    "common.cancel": "Скасувати",
    "common.delete": "Видалити",
    "common.save": "Зберегти",
    "common.saving": "Зберігаю…",
    "common.viewAll": "Усі →",
    "common.openCrm": "Відкрити CRM →",
    "common.back": "Назад",
    "common.signIn": "Увійти",
    "common.loading": "Завантаження…",
    "common.retry": "Повторити",
    "common.none": "—",
    "common.export": "Експорт",
    "common.excel": "Excel",
    "common.edit": "Змінити",
    "common.invite": "Запросити",

    "lang.switch": "Мова",

    // Sidebar / nav
    "nav.workspace": "Робочий простір",
    "nav.team": "Команда",
    "nav.dashboard": "Дашборд",
    "nav.newSearch": "Новий пошук",
    "nav.sessions": "Сесії",
    "nav.leads": "Усі ліди",
    "nav.teamPage": "Команда",
    "nav.profile": "Мій профіль",
    "nav.settings": "Налаштування",
    "nav.billing": "Підписка",
    "nav.templates": "Шаблони",
    "nav.import": "Імпорт CSV",
    "nav.signOut": "Вийти",
    "nav.themeDark": "Темна тема",
    "nav.themeLight": "Світла тема",

    // Import
    "import.title": "Імпорт списку компаній",
    "import.subtitle":
      "Завантажте CSV — Convioo створить сесію з лідами, прив’яже custom-поля та підключить CRM.",
    "import.dropTitle": "Перетягніть CSV сюди",
    "import.dropBody":
      "Файл із заголовком у першому рядку. Підтримуються стовпці: name (обов’язково), website, region, phone, category. Будь-які інші — потраплять у custom fields.",
    "import.pick": "Обрати файл",
    "import.expectedColumns":
      "Приклад заголовків: name,website,region,phone,category — порядок і регістр не важливі. Будь-який додатковий стовпець стане custom-полем у кожного ліда.",
    "import.empty": "У файлі немає рядків з даними.",
    "import.previewTitle": "Прев’ю · {n} рядків",
    "import.skipped": "Пропущено {n} рядків (без name).",
    "import.pickAnother": "Обрати інший файл",
    "import.runImport": "Імпортувати",
    "import.labelField": "Назва сесії",
    "import.previewTrunc": "+ ще {n} рядків, які теж імпортуються.",

    "lead.extras.findDecisionMakers": "Знайти контакти ОПР",

    // Hotkeys
    "kbd.title": "Гарячі клавіші",
    "kbd.dashboard": "Головна",
    "kbd.search": "Новий пошук",
    "kbd.leads": "Усі ліди",
    "kbd.import": "Імпорт CSV",
    "kbd.templates": "Шаблони",
    "kbd.profile": "Профіль",
    "kbd.theme": "Змінити тему",
    "kbd.toggleHelp": "Показати/приховати це вікно",

    // Templates
    "templates.title": "Шаблони outreach",
    "templates.subtitle":
      "Збережені листи з плейсхолдерами {name}, {niche}, {region}. Henry адаптує їх під кожного ліда.",
    "templates.new": "Новий шаблон",
    "templates.copy": "Копіювати тіло",
    "templates.empty.title": "Шаблонів поки немає",
    "templates.empty.body":
      "Збережіть Cold #1 / Follow-up / Breakup — і копіюйте однією кнопкою під час роботи з лідом.",
    "templates.editor.titleNew": "Новий шаблон",
    "templates.editor.titleEdit": "Редагування шаблону",
    "templates.editor.save": "Зберегти",
    "templates.field.name": "Назва",
    "templates.field.namePh": "Наприклад: Cold #1 для стоматологій",
    "templates.field.subject": "Тема",
    "templates.field.subjectPh": "Тема листа (опційно)",
    "templates.field.body": "Тіло листа",
    "templates.field.bodyHint": "плейсхолдери: {name}, {niche}, {region}",
    "templates.field.bodyPh": "Привіт, {name}! Помітив, що ви …",
    "templates.field.tone": "Тон",

    // Workspace switcher
    "workspace.label": "Робочий простір",
    "workspace.personal": "Особистий",
    "workspace.manage": "Керувати командами",
    "workspace.viewingAs": "Дивитесь як {name}",
    "workspace.stopViewAs": "Повернутися до свого вигляду",

    // Landing
    "landing.nav.signIn": "Увійти",
    "landing.nav.register": "Реєстрація",
    "landing.hero.eyebrow": "B2B-інтелект по лідах — готово за 90 секунд",
    "landing.hero.titlePre": "Перші",
    "landing.hero.titleAccent": "50 компаній,",
    "landing.hero.titlePost1": "які справді",
    "landing.hero.titlePost2": "вам підходять.",
    "landing.hero.subtitle":
      "Опишіть кому ви продаєте. Ми знаходимо кожен збіг у Google Places, проходимося їхніми сайтами та відгуками й повертаємо список, розмічений AI, з персональною подачею для кожного.",
    "landing.stats.time": "Середній час",
    "landing.stats.perQuery": "Лідів за запит",
    "landing.stats.accuracy": "Точність контактів",
    "landing.stats.speed": "Швидше за ручний пошук",
    "landing.how.eyebrow": "Як це працює",
    "landing.how.title1": "Від ніші до",
    "landing.how.titleItalic": "готового до холодного дотику",
    "landing.how.title2": "списку — без рутини.",
    "landing.how.01.title": "Опишіть ціль",
    "landing.how.01.body":
      "Введіть нішу та регіон. І все — жодного матричного фільтра, жодних форм. Асистент допоможе звузити охоплення, якщо потрібно.",
    "landing.how.02.title": "Шукаємо, збагачуємо, оцінюємо",
    "landing.how.02.body":
      "Беремо збіги з Google Places, заходимо на кожен сайт, збираємо соцмережі та відгуки, проганяємо лідів через Claude для персональної оцінки.",
    "landing.how.03.title": "Ведемо в CRM",
    "landing.how.03.body":
      "Кожен лід отримує AI-підказку під вашу пропозицію. Ставте статуси, нотатки, передавайте команді, вивантажуйте в Excel.",
    "landing.cta.title1": "Досить шукати лідів вручну.",
    "landing.cta.title2": "Починайте закривати угоди.",
    "landing.cta.primary": "Створити акаунт",
    "landing.cta.secondary": "Увійти",
    "landing.footer.built": "© 2026 Convioo. Для агенцій.",
    "landing.footer.privacy": "Приватність",
    "landing.footer.terms": "Умови",
    "landing.footer.contact": "Контакти",

    "preview.session": "Сесія",
    "preview.analyzed": "{n} лідів проаналізовано",
    "preview.hot": "Гарячі",
    "preview.warm": "Теплі",
    "preview.cold": "Холодні",

    // Auth
    "auth.field.firstName": "Ім’я",
    "auth.field.firstNamePh": "",
    "auth.field.lastName": "Прізвище",
    "auth.field.lastNamePh": "",
    "auth.field.email": "Email",
    "auth.field.emailPh": "[email protected]",
    "auth.field.password": "Пароль",
    "auth.field.passwordPh": "",
    "auth.field.passwordHint": "мінімум 8 символів",
    "auth.field.inviteCode": "Реєстраційний код",
    "auth.field.inviteCodePh": "видається засновником",
    "auth.field.inviteCodeHint": "обов’язково",
    "auth.login.invalid": "Невірний email або пароль.",

    // Verify-email
    "verify.idle.title": "Підтвердити email",
    "verify.idle.body":
      "Натисніть кнопку нижче, щоб підтвердити email. Це потрібно тому що поштові сервіси автоматично перевіряють посилання в листах — якщо б ми підтверджували при завантаженні, токен згоряв би до вашого кліку.",
    "verify.idle.cta": "Підтвердити email",
    "verify.verifying.title": "Підтверджуємо email…",
    "verify.pending.title": "Підтверджуємо email…",
    "verify.pending.body": "Секунду — перевіряємо посилання.",
    "verify.ok.title": "Email підтверджено",
    "verify.ok.body":
      "Готово. Тепер можна запускати пошуки. Якщо ви ще не увійшли — увійдіть звичним чином.",
    "verify.ok.continue": "До робочої зони",
    "verify.error.title": "Не вдалося підтвердити email",
    "verify.error.body":
      "Посилання застаріло або вже використано. Запросіть нове посилання з банера в робочій зоні.",
    "verify.error.retry": "Спробувати ще раз",
    "verify.gotoLogin": "Перейти до входу",
    "verifyBanner.title": "Підтвердіть email ({email})",
    "verifyBanner.body":
      "Запуск пошуків заблоковано, поки пошта не підтверджена. Перевірте вхідні — ми надіслали посилання.",
    "verifyBanner.resend": "Надіслати посилання ще раз",
    "verifyBanner.sent": "Надіслано ✓",

    // Settings — account & connectors
    "settings.account": "Акаунт",
    "settings.account.emailLabel": "Email",
    "settings.account.passwordLabel": "Пароль",
    "settings.account.passwordHelp": "Можна змінити будь-коли. Потрібен поточний пароль.",
    "settings.account.changeEmail": "Змінити email",
    "settings.account.changePassword": "Змінити пароль",
    "settings.account.verified": "підтверджено",
    "settings.account.unverified": "не підтверджено",
    "settings.account.newEmailPh": "Новий email",
    "settings.account.passwordConfirmPh": "Поточний пароль (для підтвердження)",
    "settings.account.sendVerify": "Надіслати посилання на підтвердження",
    "settings.account.sameEmail": "Це вже ваш поточний email.",
    "settings.account.changeEmailSent":
      "Лист із посиланням надіслано на {email}. Підтвердіть його — після цього основний email зміниться. Поточний продовжує працювати до підтвердження.",
    "settings.account.currentPasswordPh": "Поточний пароль",
    "settings.account.newPasswordPh": "Новий пароль (мін. 8 символів)",
    "settings.account.confirmPasswordPh": "Повторіть новий пароль",
    "settings.account.passwordsDontMatch": "Паролі не збігаються.",
    "settings.account.passwordSaved": "Пароль оновлено ✓",
    "settings.connectors": "Конектори",
    "settings.connector.gmail": "Google Workspace (Gmail)",
    "settings.connector.gmail.desc":
      "Надсилати листи від імені вашої робочої скриньки, прямо з картки ліда. Скоро.",
    "settings.connector.outlook": "Microsoft 365 (Outlook)",
    "settings.connector.outlook.desc":
      "Те саме для Microsoft-акаунтів. Скоро.",
    "settings.connector.smtp": "Custom SMTP",
    "settings.connector.smtp.desc":
      "Власний поштовий сервер для тих, у кого корпоративні обмеження. Скоро.",
    "settings.connector.connect": "Підключити",
    "settings.connector.soon": "скоро",

    "auth.login.title": "З поверненням.",
    "auth.login.subtitle": "Введіть ім’я та прізвище, під якими ви реєструвалися.",
    "auth.login.submit": "Увійти",
    "auth.login.notFound": "Користувача з таким ім’ям не знайдено. Зареєструйтеся.",
    "auth.login.noAccount": "Немає акаунта?",
    "auth.login.registerLink": "Зареєструватися",
    "auth.login.back": "На головну",
    "auth.register.title": "Створіть акаунт.",
    "auth.register.subtitle":
      "Мінімум для старту — ім’я, email і пароль. Решту налаштуєте всередині платформи.",
    "auth.register.submit": "Створити акаунт",
    "auth.register.haveAccount": "Вже є акаунт?",
    "auth.register.signInLink": "Увійти",
    "auth.field.age": "Вік",
    "auth.field.ageHint": "за бажанням — допомагає AI підібрати тон",
    "auth.field.ageSkip": "Не вказувати",
    "auth.field.gender": "Стать",
    "auth.field.genderHint": "за бажанням — Henry звертатиметься у правильному роді",
    "auth.field.genderSkip": "Не вказувати",
    "auth.field.gender.male": "Чоловіча",
    "auth.field.gender.female": "Жіноча",
    "auth.field.gender.other": "Інша",
    "auth.inside.eyebrow": "Усередині",
    "auth.inside.body":
      "50 лідів з AI-оцінкою у кожному пошуку. Персоналізовано під те, що продаєте саме ви.",
    "auth.inside.tags": "Google Places · Claude Haiku · Живе збагачення",

    // Onboarding
    "onboarding.eyebrow": "Крок {step} з {total}",
    "onboarding.next": "Далі",
    "onboarding.finish": "Готово",
    "onboarding.skip": "Пропустити",
    "onboarding.step.0.title": "Як до вас звертатися?",
    "onboarding.step.0.help":
      "Це ім’я AI використовуватиме у подачі для кожного ліда.",
    "onboarding.step.0.ph": "Як до вас звертатися",
    "onboarding.step.1.title": "Скільки вам років?",
    "onboarding.step.1.help":
      "Допомагає Claude підібрати тон висновків. Можна пропустити.",
    "onboarding.step.2.title": "Який у вас бізнес?",
    "onboarding.step.2.help":
      "Соло, мала команда, агенція — це змінює рекомендації. Можна пропустити.",
    "onboarding.step.3.title": "Що ви продаєте?",
    "onboarding.step.3.help":
      "Опишіть своїми словами — це найважливіший крок. AI оцінюватиме кожного ліда саме під цю послугу.",
    "onboarding.step.3.ph": "",
    "onboarding.step.4.title": "Звідки ви працюєте?",
    "onboarding.step.4.help":
      "Базовий регіон. Допомагає з подачею, особливо якщо шукаєте лідів поруч.",
    "onboarding.step.4.ph": "",
    "onboarding.step.5.title": "На які ніші ви полюєте?",
    "onboarding.step.5.help":
      "Введіть 3–7 ніш через Enter. Це допомагає AI розуміти ваш кругозір.",
    "onboarding.step.5.ph": "",
    "onboarding.step.5.counter": "{n} з 7",
    "onboarding.age.lt18": "до 18",
    "onboarding.age.18_24": "18–24",
    "onboarding.age.25_34": "25–34",
    "onboarding.age.35_44": "35–44",
    "onboarding.age.45_54": "45–54",
    "onboarding.age.55plus": "55+",
    "onboarding.size.solo": "Соло / фрілансер",
    "onboarding.size.small": "Мала команда (2–10)",
    "onboarding.size.medium": "Компанія (10–50)",
    "onboarding.size.large": "Великий бізнес (50+)",

    // Dashboard
    "dashboard.topbar.greetingMorning": "Доброго ранку",
    "dashboard.topbar.greetingAfternoon": "Доброго дня",
    "dashboard.topbar.subtitle": "Що відбувається у вашій робочій зоні.",
    "dashboard.stats.sessions": "Сесій запущено",
    "dashboard.stats.sessionsSub": "{n} зараз активні",
    "dashboard.stats.leads": "Лідів проаналізовано",
    "dashboard.stats.leadsSub": "у всіх сесіях",
    "dashboard.stats.hot": "Гарячих лідів",
    "dashboard.stats.hotSub": "готові до контакту",
    "dashboard.stats.rest": "Теплі + холодні",
    "dashboard.stats.restSub": "варті другого проходу",
    "dashboard.quota.eyebrow": "Ліміт пошуків",
    "dashboard.quota.subtitle": "Використано {used} з {limit}",
    "dashboard.checkin.eyebrow": "Henry · підсумок тижня",
    "tasks.todayTitle": "На сьогодні",
    "tasks.today": "сьогодні",
    "tasks.overdue": "прострочено",
    "lead.extras.tasks": "Завдання",
    "lead.extras.tasks.ph": "Наприклад: подзвонити в середу",
    "lead.extras.customFields": "Кастомні поля",
    "lead.extras.customFields.keyPh": "ключ (decision_maker)",
    "lead.extras.customFields.valPh": "значення",
    "lead.extras.activity": "Історія змін",
    "lead.extras.activity.statusKind": "Статус: {from} → {to}",
    "lead.extras.activity.notesKind": "Оновлено нотатки",
    "lead.extras.activity.assignedKind": "Призначено на #{id}",
    "lead.extras.activity.unassignedKind": "Знято з призначення",
    "lead.extras.activity.markKind": "Кольорова позначка",
    "lead.extras.activity.customFieldKind": "Поле «{key}»",
    "lead.extras.activity.taskKind": "Завдання: {content}",
    "dashboard.recent.eyebrow": "Останні сесії",
    "dashboard.recent.title": "Ваші пошуки",
    "dashboard.empty.title": "Пошуків поки немає",
    "dashboard.empty.body": "Запустіть перший пошук із бічної панелі — займає близько 90 секунд.",
    "dashboard.quick.eyebrow": "Почати зараз",
    "dashboard.quick.title": "Швидкі дії",
    "dashboard.quick.launch.title": "Запустити новий пошук",
    "dashboard.quick.launch.body":
      "Опишіть цільову нішу й регіон. Henry візьме решту на себе.",
    "dashboard.quick.leads.title": "Відкрити базу лідів",
    "dashboard.quick.leads.body": "Шукайте, фільтруйте та ведіть кожного зібраного ліда.",
    "dashboard.hot.eyebrow": "Гарячі за тиждень",
    "dashboard.hot.title": "Ліди з найкращим скором",

    "session.row.running": "Виконується — {status}",
    "session.row.failed": "Помилка — {err}",
    "session.row.summary": "{n} лідів · {hot} гарячих",
    "session.row.hot": "гарячих",
    "session.row.rest": "інших",

    // Search
    "search.crumb.workspace": "Робоча зона",
    "search.crumb.new": "Новий пошук",
    "search.crumb.running": "Пошук виконується",
    "search.crumb.done": "Пошук завершено",
    "search.chat.greeting":
      "Привіт — я Henry, ваш AI-асистент по лідах. Опишіть кого шукаєте, і я зберу список за ~90 секунд.",
    "search.consult.greeting":
      "Привіт, я Henry. Розкажіть кого шукаєте: яка ніша, в якому місті та що для вас ідеальний лід. Я уточнюватиму по ходу й одразу заповню форму праворуч.",
    "search.consult.greetingNichesRegion":
      "Привіт. Бачу — у вас у фокусі {niches} в {region}. З якої ніші сьогодні почнемо чи хочете підібрати щось нове?",
    "search.consult.greetingNiches":
      "Привіт. У вас в нішах {niches}. З якою працюємо сьогодні і в якому місті?",
    "search.consult.greetingRegionOffer":
      "Привіт. Знаю, що ви працюєте в {region}. Який сегмент сьогодні шукаємо?",
    "search.consult.placeholder": "Напишіть Henry...",
    "search.consult.role": "AI-консультант з підбору лідів",
    "search.consult.thinking": "Думаю над відповіддю...",
    "search.consult.error":
      "Не вдалося отримати відповідь ({detail}). Спробуйте ще раз або заповніть форму праворуч вручну.",
    "search.form.nicheHint": "обов’язково",
    "search.form.regionHint": "обов’язково",
    "search.form.ideal": "Ідеальний клієнт",
    "search.form.idealHint": "за бажанням",
    "search.form.idealPh": "",
    "search.form.exclude": "Кого не потрібно",
    "search.form.excludeHint": "за бажанням",
    "search.form.excludePh": "",
    "search.form.lang": "Мови лідів",
    "search.form.langHint": "за бажанням",
    "search.form.langHelp":
      "Якщо обрано мови — залишимо лише лідів, у яких є ознаки володіння хоча б однією з них (мова назви, відгуків, сайту). Корисно коли ви працюєте на іноземний ринок але лише з російсько- чи україномовними.",
    "search.lang.ru": "Російська",
    "search.lang.uk": "Українська",
    "search.lang.en": "English",
    "search.lang.de": "Deutsch",
    "search.lang.es": "Español",
    "search.lang.fr": "Français",
    "search.lang.pl": "Polski",

    // Henry assistant
    "assistant.open": "Відкрити Henry",
    "assistant.close": "Згорнути",
    "assistant.reset": "Очистити чат",
    "assistant.role": "Консультант Convioo",
    "assistant.thinking": "Думаю...",
    "assistant.placeholder": "Запитайте Henry...",
    "assistant.greeting":
      "Привіт, я Henry — ваш консультант Convioo. Допоможу налаштувати профіль, поясню як працює оцінка лідів або підкажу як точніше описати цільовий сегмент. З чим допомогти?",
    "assistant.error": "Не вдалося отримати відповідь ({detail}). Спробуйте ще раз.",
    "assistant.suggestion": "Запропоновані зміни профілю",
    "assistant.apply": "Застосувати",
    "assistant.applied": "Записано ✓",
    "assistant.applyError": "Не вдалося оновити профіль ({detail}).",
    "assistant.pending.title": "Henry хоче записати",
    "assistant.pending.confirm": "Записати",
    "assistant.pending.dismiss": "Не зараз",
    "assistant.launchedSearch": "Пошук запущено",
    "assistant.openSession": "Відкрити сесію",
    "lead.email.deepResearch": "Глибокий research",
    "lead.email.deepResearchHint":
      "Henry заново просканує сайт ліда та витягне конкретні факти для opener-а.",
    "lead.email.notableFacts": "Що Henry знайшов на сайті:",
    "lead.email.recentSignal": "Recent signal:",
    "assistant.greeting.team":
      "Привіт. Зараз ви працюєте в команді «{team}» — допоможу з підбором лідів під її специфіку, розкажу про колег і їхні зони відповідальності. З чим працюємо?",
    "assistant.team.suggestion": "Запропоновані правки команди",
    "assistant.team.descriptionLabel": "Опис команди",
    "assistant.team.memberLabel": "Опис для учасника #{id}",

    "search.preflight.title": "Цей зв’язок уже використовувався у команді",
    "search.preflight.body":
      "Один і той самий набір «ніша + регіон» не можна запускати двічі — ліди б перетнулися із вже зібраними у колег. Відкрийте існуючу сесію або спробуйте інше формулювання.",
    "search.preflight.leadsCount": "{n} лідів",
    "search.preflight.openSession": "Відкрити сесію →",

    "team.descriptionLabel": "Опис команди",
    "team.descriptionEmpty": "Опис ще не заданий — розкажіть команді, навіщо вона існує.",
    "team.descriptionPh": "",
    "team.member.descriptionEmpty":
      "Немає опису учасника. Клікніть олівець, щоб додати.",
    "team.member.descriptionPh": "Чим займається людина, що закриває.",

    "search.chat.placeholder": "Опишіть кого шукаєте…",
    "search.chat.gotIt":
      "Зрозумів — **{niche}** в **{region}**. Тисніть «Запустити», коли готові, або поправте форму праворуч.",
    "search.chat.needBoth":
      "Вкажіть нішу та регіон, наприклад «покрівельні компанії в Нью-Йорку».",
    "search.axes.eyebrow": "Підібрати з Henry",
    "search.axes.subtitle":
      "Отримай 4 готові конфігурації пошуку під твій профіль — клік і форма заповнена.",
    "search.axes.cta": "Підібрати",
    "search.axes.ctaAgain": "Підібрати ще",
    "search.axes.hide": "Приховати",
    "search.axes.empty":
      "Henry не зміг підібрати варіанти — заповніть «що ви продаєте» в /app/profile і спробуйте знову.",
    "search.form.eyebrow": "Параметри пошуку",
    "search.form.title": "Або заповніть вручну",
    "search.form.subtitle": "Henry дозаповнить поля по ходу діалогу.",
    "search.form.niche": "Ніша",
    "search.form.nichePh": "",
    "search.form.region": "Регіон",
    "search.form.regionPh": "",
    "search.form.offer": "Що ви продаєте (для AI-оцінки)",
    "search.form.offerPh": "",
    "search.form.offerSource.profile": "З мого профілю",
    "search.form.offerSource.custom": "Інше для цього пошуку",
    "search.form.offerSource.empty":
      "У профілі поки немає опису. Заповніть його в /app/profile або напишіть варіант нижче — він застосується лише до цього пошуку.",
    "search.form.offerSource.profileEmpty":
      "Опису немає — додайте його в профілі, щоб AI враховував його у кожному пошуку.",
    "search.form.offerSource.profileLink": "Відкрити профіль →",
    "search.form.offerHint":
      "Claude використовує це, щоб персоналізувати кожен скор і подачу.",
    "search.form.meta": "До 50 лідів · 60–120 секунд · живий прогрес нижче.",
    "search.form.launch": "Запустити пошук",
    "search.running.eyebrowSearching": "Шукаємо",
    "search.running.eyebrowDone": "Готово",
    "search.running.inGlue": "в",
    "search.running.defaultSubtitle":
      "Зазвичай це займає 60–120 секунд. Залишайтеся на сторінці — побачите живий прогрес по фазах.",
    "search.running.phaseEyebrow": "Поточна фаза",
    "search.running.bootingPipeline": "Запускаю пайплайн…",
    "search.running.openAnyway": "Відкрити сесію все одно",
    "search.done.title": "{niche} · {region} — готово.",
    "search.done.subtitle": "Кожен лід оцінено під ваш профіль із персональною подачею.",
    "search.done.open": "Відкрити результати",

    // Sessions
    "sessions.title": "Сесії",
    "sessions.subtitle": "Усі ваші запущені пошуки",
    "sessions.empty.title": "Сесій поки немає",
    "sessions.empty.body": "Запустіть перший пошук із бічної панелі — займає ~90 секунд.",

    // Session detail
    "detail.crumb.sessions": "Сесії",
    "detail.status.pending": "очікує",
    "detail.status.running": "виконується",
    "detail.status.done": "готово",
    "detail.status.failed": "помилка",
    "detail.source.web": "веб",
    "detail.source.telegram": "телеграм",
    "detail.stat.total": "усього",
    "detail.stat.hot": "гарячих",
    "detail.stat.warm": "теплих",
    "detail.stat.cold": "холодних",
    "detail.insights.eyebrow": "AI-інсайт ринку",
    "detail.loader.title": "Готуємо вашу добірку",
    "detail.loader.subtitle":
      "Збираємо компанії, проходимося сайтами та відгуками й оцінюємо кожного ліда під ваш профіль. Зазвичай це 60–120 секунд — сторінка відкриється сама.",
    "detail.loader.phase.pending": "Запускаємо пайплайн",
    "detail.loader.phase.discovering": "Шукаємо компанії в Google Places",
    "detail.loader.phase.enriching": "Збагачуємо сайтами та відгуками",
    "detail.loader.phase.scoring": "Claude оцінює кожного ліда",
    "detail.filter.all": "Усі · {n}",
    "detail.filter.hot": "Гарячі · {n}",
    "detail.filter.warm": "Теплі · {n}",
    "detail.filter.cold": "Холодні · {n}",
    "detail.empty":
      "За цією сесією поки немає лідів. Якщо щойно завершилася — оновіть через пару секунд.",

    // Leads CRM
    "crm.title": "Усі ліди",
    "crm.subtitle": "{leads} лідів з {sessions} сесій",
    "crm.empty": "Лідів поки немає. Запустіть перший пошук із бічної панелі.",
    "crm.smart.all": "Усі",
    "crm.smart.hotWeek": "Hot за тиждень",
    "crm.smart.newToday": "Нові сьогодні",
    "crm.smart.untouched14": "Без дотику 14+ днів",
    "crm.kanban.empty": "Перетягніть картку сюди",
    "crm.status.all": "усі",
    "crm.status.new": "нові",
    "crm.status.contacted": "у роботі",
    "crm.status.replied": "відповіли",
    "crm.status.won": "угода",
    "crm.status.archived": "архів",
    "crm.search.placeholder": "Пошук за ім’ям, адресою, категорією…",
    "crm.search.clear": "Очистити",
    "crm.search.results": "{n} лідів",
    "crm.sort.score_desc": "Скор: спершу високі",
    "crm.sort.score_asc": "Скор: спершу низькі",
    "crm.sort.created_desc": "Спершу нові",
    "crm.sort.created_asc": "Спершу старі",
    "crm.sort.touched_desc": "Останній контакт",
    "crm.sort.name_asc": "Ім’я А → Я",
    "crm.sort.name_desc": "Ім’я Я → А",
    "crm.bulk.selectAll": "Виділити все",
    "crm.bulk.selected": "Виділено: {n}",
    "crm.bulk.setStatus": "Статус",
    "crm.bulk.setMark": "Позначка",
    "crm.bulk.cancel": "Зняти виділення",
    "crm.table.lead": "Лід",
    "crm.table.session": "Сесія",
    "crm.table.score": "Скор",
    "crm.table.status": "Статус",
    "crm.table.touched": "Останній контакт",
    "crm.relative.now": "щойно",
    "crm.relative.m": "{n}хв тому",
    "crm.relative.h": "{n}год тому",
    "crm.relative.d": "{n}д тому",

    // Lead detail modal
    "lead.howToPitch": "Як презентувати цьому ліду",
    "lead.strengths": "Сильні сторони",
    "lead.weaknesses": "Слабкі сторони",
    "lead.redFlags": "Червоні прапори",
    "lead.notes": "Нотатки",
    "lead.notesPh": "Запишіть свої спостереження по цьому ліду…",
    "lead.status": "Статус",
    "lead.contact": "Контакт",
    "lead.rating": "відгуків",
    "lead.statusLabel.new": "новий",
    "lead.statusLabel.contacted": "у роботі",
    "lead.statusLabel.replied": "відповів",
    "lead.statusLabel.won": "угода",
    "lead.statusLabel.archived": "архів",
    "lead.sendEmail.gmail": "Написати через Gmail",
    "lead.sendEmail.soon":
      "Скоро: підключіть Google Workspace у налаштуваннях, і зможете писати листа ліду прямо звідси.",
    "lead.email.generate": "Згенерувати лист",
    "lead.email.regenerate": "Переписати",
    "lead.email.draft": "Чернетка листа",
    "lead.email.subject": "Тема",
    "lead.email.body": "Тіло",
    "lead.email.copy": "Копіювати",
    "lead.email.copyAll": "Копіювати все",
    "lead.email.copied": "Скопійовано ✓",
    "lead.email.sendGmail": "Надіслати через Gmail",
    "lead.email.addExtra": "Додати контекст",
    "lead.email.hideExtra": "Приховати контекст",
    "lead.email.extraPh":
      "Щось конкретне про цього ліда, що Henry повинен врахувати (опційно).",
    "lead.email.tone.professional": "Діловий",
    "lead.email.tone.casual": "Теплий",
    "lead.email.tone.bold": "Впевнений",
    "lead.mark.title": "Моя позначка",
    "lead.mark.clear": "Зняти",
    "lead.mark.help":
      "Колір бачите тільки ви. Використовуйте як завгодно — пріоритет, follow-up, що захочете.",

    // Profile
    "profile.title": "Мій профіль",
    "profile.subtitle": "Як AI оцінює лідів для вас",
    "profile.hint": "Профіль персоналізує кожен AI-скор і подачу.",
    "profile.privacy.title": "Конфіденційність і дані",
    "profile.privacy.subtitle":
      "Завантажте копію ваших даних, перегляньте журнал активності або видаліть акаунт.",
    "profile.privacy.export": "Експорт моїх даних",
    "profile.privacy.exportHint":
      "JSON-файл з усіма вашими профілем, лідами та активністю.",
    "profile.privacy.audit": "Журнал активності",
    "profile.privacy.auditEmpty": "Записів поки немає.",
    "profile.privacy.delete": "Видалити акаунт",
    "profile.privacy.deleteHint":
      "Без можливості відновлення. Видаляються всі ваші дані.",
    "profile.privacy.deleteConfirmTitle": "Видалити акаунт назавжди",
    "profile.privacy.deleteConfirmBody":
      "Щоб підтвердити, введіть свій email і пароль. Ця дія незворотна.",
    "profile.privacy.deleteConfirmEmail": "Ваш email",
    "profile.privacy.deleteConfirmPassword": "Пароль",
    "profile.privacy.deleteConfirmCta": "Видалити назавжди",
    "profile.privacy.deleteFailed":
      "Не вдалося видалити акаунт. Перевірте email і пароль.",

    "profile.field.business": "Розмір бізнесу",
    "profile.field.region": "Домашній регіон",
    "profile.field.offer": "Професія / пропозиція",
    "profile.field.offerRaw": "Що ви продаєте (вашими словами)",
    "profile.field.niches": "Цільові ніші",
    "profile.field.age": "Вік",
    "profile.field.gender": "Стать",
    "profile.field.displayName": "Ім’я",
    "profile.empty": "Не вказано",
    "profile.editor.title": "Редагування профілю",
    "profile.editor.subtitle": "Чим точніші дані — тим точніший AI-скор кожного ліда.",
    "profile.editor.save": "Зберегти",
    "profile.editor.cancel": "Скасувати",
    "profile.editor.saving": "Зберігаємо…",
    "profile.editor.saved": "Збережено ✓",
    "profile.editor.askHenry": "Заповнити з Henry",
    "profile.editor.tooLong":
      "Поле «{field}» задовге — скоротіть до {max} символів.",
    "profile.field.displayNamePh": "Як до вас звертатися",
    "profile.field.regionPh": "Наприклад: Київ, Львів, Берлін",
    "profile.field.offerRawPh":
      "Опишіть своїми словами — яка послуга, для кого, в чому цінність.",
    "profile.field.nichesPh": "Додайте нішу та Enter",
    "profile.niches.suggest": "Підібрати з Henry",
    "profile.niches.suggestAgain": "Підібрати ще",
    "profile.niches.suggestEmpty":
      "Henry не знайшов відповідних ніш — уточніть «що ви продаєте» і спробуйте знову.",
    "profile.nudge.title": "Заповніть профіль для кращої якості",
    "profile.nudge.body":
      "AI оцінює кожного ліда під ваш профіль: чим зрозуміліше, що ви продаєте і кому, тим точніший hot/warm/cold і подача. Заповніть вручну або поговоріть з Henry — він уміє витягувати дані зі звичайної розмови.",
    "profile.nudge.manual": "Заповнити вручну",
    "profile.nudge.henry": "Поговорити з Henry",
    "profile.nudge.dismiss": "Приховати на сьогодні",
    "profile.memory.title": "Що пам’ятає Henry",
    "profile.memory.subtitle":
      "Henry зберігає короткі висновки з ваших діалогів, щоб при наступній зустрічі пам’ятати контекст. Можна очистити — він почне з чистого аркуша.",
    "profile.memory.empty":
      "Поки Henry нічого не запам’ятав. Поговоріть з ним — після кількох повідомлень тут з’являться факти.",
    "profile.memory.clear": "Очистити пам’ять",
    "profile.memory.confirm": "Точно очистити",
    "profile.memory.kind.summary": "сесія",
    "profile.memory.kind.fact": "факт",

    // Team
    "team.title": "Команда",
    "team.subtitle": "Створюйте спільні простори та запрошуйте до них людей",
    "team.create.eyebrow": "Команду ще не створено",
    "team.create.title": "Створіть свою першу команду",
    "team.create.subtitle":
      "Команда — це спільний CRM. Усі її учасники бачать ті самі сесії та лідів; власник розсилає інвайти й керує ролями.",
    "team.create.placeholder": "Наприклад: Acme Agency",
    "team.create.submit": "Створити команду",
    "team.create.another": "Створити ще одну команду",
    "team.detail.eyebrow": "Команда",
    "team.detail.members": "Учасники · {n}",
    "team.owner.eyebrow": "Лише власнику",
    "team.owner.title": "CRM кожного учасника",
    "team.owner.subtitle":
      "У команді кожен бачить лише своїх лідів. Тут ви як власник можете зайти в CRM будь-якого учасника й подивитися, з чим він працює.",
    "team.owner.empty": "Поки в команді тільки ви.",
    "team.owner.col.member": "Учасник",
    "team.owner.col.role": "Роль",
    "team.owner.col.sessions": "Сесій",
    "team.owner.col.leads": "Лідів",
    "team.owner.col.hot": "Гарячих",
    "team.owner.viewAs": "Дивитися як",
    "team.owner.viewMine": "Мій CRM",
    "team.invite.eyebrow": "Інвайт",
    "team.invite.title": "Запросити в команду",
    "team.invite.subtitle":
      "Згенеруйте посилання, діє 10 хвилин. Користувач має пройти реєстрацію або увійти, після цього стане членом команди.",
    "team.invite.generate": "Згенерувати посилання",
    "team.invite.regenerate": "Згенерувати знову",
    "team.invite.copy": "Скопіювати",
    "team.invite.expiresIn": "Діє ще {mm}",
    "team.invite.expired": "Термін інвайта закінчився",
    "team.empty.title": "Команд поки немає",
    "team.empty.body":
      "Створіть команду, щоб ділитися лідами та простором з колегами.",
    "team.table.member": "Учасник",
    "team.table.role": "Роль",
    "team.table.active": "Остання активність",

    "invite.title": "Вас запросили до команди",
    "invite.subtitle":
      "Роль: {role}. Прийнявши інвайт ви потрапите у спільний CRM команди.",
    "invite.expiresIn": "Закінчиться через {mm}",
    "invite.expired":
      "Цей інвайт уже закінчився. Попросіть власника команди згенерувати новий.",
    "invite.alreadyUsed": "Це посилання вже використано.",
    "invite.signInToAccept": "Увійти й прийняти",
    "invite.registerToAccept": "Створити акаунт і прийняти",
    "invite.accept": "Прийняти і перейти до команди",

    // Settings — workspace + tint + billing
    "settings.title": "Налаштування",
    "settings.subtitle": "Конфігурація робочої зони",
    "settings.workspace": "Робоча зона",
    "settings.workspaceName": "Назва",
    "settings.auth": "Авторизація",
    "settings.authValue":
      "Відкрита демо-версія — логін додамо на наступному етапі",
    "settings.tint.title": "Колір фону",
    "settings.tint.subtitle":
      "Легкий відтінок фону для поточної робочої зони — допомагає візуально розрізняти особисте та команди.",
    "settings.tint.scopePersonal": "Застосовується до особистої зони",
    "settings.tint.scopeTeam": "Застосовується до команди «{name}»",
    "settings.tint.default": "Стандартний",
    "settings.tint.green": "Зелений",
    "settings.tint.dark": "Темний",
    "settings.tint.orange": "Помаранчевий",
    "billing.title": "Підписка",
    "billing.subtitle":
      "Тарифні плани Convioo. Зараз усе безкоштовно — це карта можливостей під майбутній реліз.",
    "billing.devBadge": "У розробці",
    "billing.demoNotice":
      "Зараз Convioo працює як відкрита демо-версія — усі фічі доступні безкоштовно. Ціни нижче — попередні орієнтири на платний реліз; фінальні суми зафіксуємо ближче до запуску. Купити поки не можна.",
    "billing.cta": "Скоро",
    "billing.popular": "Популярний",
    "billing.teamGate.title": "Команди тільки з підпискою",
    "billing.teamGate.body":
      "Створення команди та спільний CRM будуть доступні від тарифу Team Standard. Особиста зона залишається безкоштовною в усіх планах.",
    "billing.plan.free.name": "Free",
    "billing.plan.free.tagline":
      "Демо-доступ для одного користувача. Підходить, щоб спробувати продукт на реальному завданні.",
    "billing.plan.free.price": "$0",
    "billing.plan.free.period": "/ назавжди",
    "billing.plan.personal_pro.name": "Personal Pro",
    "billing.plan.personal_pro.tagline":
      "Для соло-продажника або фрілансера. Знімає ліміти і відкриває Henry-помічників.",
    "billing.plan.personal_pro.price": "$19",
    "billing.plan.personal_pro.period": "/ міс · попередньо",
    "billing.plan.team_standard.name": "Team Standard",
    "billing.plan.team_standard.tagline":
      "Команда до 5 осіб, спільний CRM, дедуплікація лідів, командний Henry.",
    "billing.plan.team_standard.price": "$49",
    "billing.plan.team_standard.period": "/ міс · попередньо",
    "billing.plan.team_pro.name": "Team Pro",
    "billing.plan.team_pro.tagline":
      "Для агенцій. Команда до 25 осіб, кастомні поля, kanban-pipeline, API і пріоритет у підтримці.",
    "billing.plan.team_pro.price": "$149",
    "billing.plan.team_pro.period": "/ міс · попередньо",
    "billing.feat.searchesFree": "5 пошуків на місяць",
    "billing.feat.searchesPro": "50 пошуків на місяць",
    "billing.feat.searchesTeamStandard": "100 пошуків на місяць на команду",
    "billing.feat.searchesTeamPro": "500 пошуків на місяць на команду",
    "billing.feat.leadsPerSession": "До 50 лідів на сесію",
    "billing.feat.aiScore": "AI-скоринг і персональна подача",
    "billing.feat.henryConsult": "Henry — вбудований консультант",
    "billing.feat.crmBasic": "Особистий CRM (статуси, нотатки, позначки)",
    "billing.feat.exportCsv": "Excel / CSV експорт",
    "billing.feat.dailyDigest": "Daily digest «нові гарячі»",
    "billing.feat.outreachTemplates": "Бібліотека шаблонів outreach",
    "billing.feat.unlimitedHistory": "Зберігання лідів без терміну",
    "billing.feat.teams": "Командні простори",
    "billing.feat.team5": "Команда до 5 осіб",
    "billing.feat.team25": "Команда до 25 осіб",
    "billing.feat.sharedCrm": "Спільний командний CRM",
    "billing.feat.dedupTeam": "Дедуплікація лідів усередині команди",
    "billing.feat.henryTeam": "Командний Henry з пам’яттю на всіх",
    "billing.feat.activityFeed": "Стрічка активності команди",
    "billing.feat.weeklyCheckin": "Henry Weekly Check-in",
    "billing.feat.kanbanPipeline": "Kanban-pipeline по угодах",
    "billing.feat.customFields": "Кастомні поля на лідах",
    "billing.feat.searchAlerts": "Сповіщення про нові ліди під нішу",
    "billing.feat.apiAccess": "API-доступ",
    "billing.feat.prioritySupport": "Пріоритетна підтримка",
    "settings.backend": "Бекенд",
    "settings.health": "Стан API",
    "settings.commit": "Задеплоєний коміт",
    "settings.unknown": "невідомо",
    "settings.integrations": "Інтеграції",
    "settings.int.googlePlaces": "Google Places",
    "settings.int.anthropic": "Anthropic (Claude)",
    "settings.int.telegram": "Telegram-бот",
    "settings.int.redis": "Черга Redis",
    "settings.int.email": "Email-доставка",
    "settings.int.connected": "підключено",
    "settings.int.notConfigured": "не налаштовано",
    "settings.int.redis.connected": "worker arq обробляє пошуки",
    "settings.int.redis.fallback":
      "inline-fallback через asyncio — увімкніть REDIS_URL для масштабу",
    "settings.int.email.planned": "планується з логіном",

    // Public marketing nav (covers /pricing, /help, /changelog)
    "public.nav.pricing": "Тарифи",
    "public.nav.help": "Допомога",
    "public.nav.changelog": "Що нового",
    "public.nav.signIn": "Увійти",
    "public.nav.start": "Почати безкоштовно",

    // Pricing page (most visible)
    "pricing.headline": "Прості тарифи — без сюрпризів",
    "pricing.subhead":
      "Спочатку безкоштовно спробуйте AI-пошук та оцінку лідів. Платіть лише коли зрозумієте, що Convioo вписується в процес.",
    "pricing.popular": "Популярний",
    "pricing.free.name": "Free",
    "pricing.free.tagline": "Щоб подивитися, як це працює",
    "pricing.free.price": "$0",
    "pricing.free.per": "/міс",
    "pricing.free.cta": "Створити акаунт",
    "pricing.pro.name": "Personal Pro",
    "pricing.pro.tagline": "Для соло-агенцій та фрілансерів",
    "pricing.pro.price": "$29",
    "pricing.pro.per": "/міс",
    "pricing.pro.cta": "Спробувати Pro",
    "pricing.team.name": "Team",
    "pricing.team.tagline": "Для команди до 5 менеджерів",
    "pricing.team.price": "$79",
    "pricing.team.per": "/міс",
    "pricing.team.cta": "Завести команду",

    // Help / changelog (just titles — body falls to ru)
    "help.title": "Допомога",
    "help.subtitle":
      "Короткі відповіді на часті запитання. Не знайшли своє — напишіть нам.",
    "changelog.title": "Що нового",
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
    if (stored === "en" || stored === "ru" || stored === "uk") {
      setLangState(stored);
      return;
    }
    // First visit: auto-detect from navigator.language. Default stays
    // ru for users on locales we don't ship (so the QA team keeps
    // seeing Russian without re-clicking).
    try {
      const nav = (navigator.language || "").toLowerCase();
      if (nav.startsWith("uk")) setLangState("uk");
      else if (nav.startsWith("en")) setLangState("en");
    } catch {
      // SSR or restricted env — leave default
    }
  }, []);

  const setLang = useCallback((l: Locale) => {
    setLangState(l);
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      // ignore quota / disabled storage
    }
    // Best-effort sync to the server so Henry's prompts pick the
    // matching language directive on the next turn. Failures are
    // intentional no-ops — UI is the source of truth, the column is
    // a convenience hint only.
    try {
      void fetch("/api/v1/users/me", {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ language_code: l }),
      });
    } catch {
      // ignore — user may be logged-out on a public page
    }
  }, []);

  const t = useCallback(
    (key: TranslationKey, vars?: Record<string, string | number>) => {
      const dict = TRANSLATIONS[lang] as Record<string, string>;
      // Fallback chain: uk falls through to ru (closer cognate) before en;
      // en/ru fall through to en. Mirrors the existing legacy behaviour
      // for the original two locales.
      const ruDict = TRANSLATIONS.ru as Record<string, string>;
      const raw =
        dict[key] ??
        (lang === "uk" ? ruDict[key] : undefined) ??
        TRANSLATIONS.en[key] ??
        key;
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
