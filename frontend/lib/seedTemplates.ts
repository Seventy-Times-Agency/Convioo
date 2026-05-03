/**
 * Starter outreach templates offered to brand-new users on the empty
 * /app/templates page. They are not seeded server-side — the user
 * imports them on demand via POST /api/v1/templates so they end up
 * owned by the user's account and freely editable afterwards.
 */

export interface SeedTemplate {
  name: string;
  subject: string;
  body: string;
  tone: string;
}

export const SEED_TEMPLATES: SeedTemplate[] = [
  {
    name: "Холодное интро",
    subject: "Идея для {name} — короткое сообщение",
    tone: "professional",
    body: [
      "Здравствуйте, {name}!",
      "",
      "Я заметил, что вы работаете в нише «{niche}» в регионе «{region}»,",
      "и подумал, что мы могли бы быть друг другу полезны.",
      "",
      "Можем созвониться на 15 минут на этой неделе?",
      "",
      "Спасибо,",
    ].join("\n"),
  },
  {
    name: "Follow-up через 3 дня",
    subject: "Повторно: {name}",
    tone: "professional",
    body: [
      "Здравствуйте, {name}!",
      "",
      "Возвращаюсь к моему прошлому письму — понимаю, что у вас",
      "много задач. Если интересно обсудить, выберите удобное время",
      "или напишите, что не подходит сейчас.",
      "",
      "С уважением,",
    ].join("\n"),
  },
  {
    name: "Спасибо за встречу",
    subject: "Спасибо за разговор, {name}",
    tone: "warm",
    body: [
      "Здравствуйте, {name}!",
      "",
      "Спасибо за время сегодня. Краткое резюме того, о чём договорились:",
      "— ...",
      "— ...",
      "",
      "Жду следующего шага. Если что-то нужно уточнить — пишите.",
      "",
    ].join("\n"),
  },
];
