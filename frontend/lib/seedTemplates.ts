import type { TranslationKey } from "@/lib/i18n";

/**
 * Starter outreach templates offered to brand-new users on the empty
 * /app/templates page. They are not seeded server-side — the user
 * imports them on demand via POST /api/v1/templates so they end up
 * owned by the user's account and freely editable afterwards.
 *
 * Text is localized through the i18n dictionary (templates.seed.*). The
 * {name}/{niche}/{region} merge tags inside subject/body are intentionally
 * left intact — they are filled later by the outreach engine, not by t().
 */

export interface SeedTemplate {
  name: string;
  subject: string;
  body: string;
  tone: string;
}

type TFn = (key: TranslationKey) => string;

export function getSeedTemplates(t: TFn): SeedTemplate[] {
  return [
    {
      name: t("templates.seed.coldIntro.name"),
      subject: t("templates.seed.coldIntro.subject"),
      body: t("templates.seed.coldIntro.body"),
      tone: "professional",
    },
    {
      name: t("templates.seed.followUp.name"),
      subject: t("templates.seed.followUp.subject"),
      body: t("templates.seed.followUp.body"),
      tone: "professional",
    },
    {
      name: t("templates.seed.thanks.name"),
      subject: t("templates.seed.thanks.subject"),
      body: t("templates.seed.thanks.body"),
      tone: "warm",
    },
  ];
}
