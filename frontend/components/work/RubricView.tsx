"use client";

import type { RubricItem } from "@/lib/api";
import { useLocale, type TranslationKey } from "@/lib/i18n";

const ORDER = ["opening", "relevance", "discovery", "listening", "value", "objections", "next_step", "clarity"];

/** Строгая шкала звонка: по каждому критерию уровень, цитата и что
 * не так. Балл — из шкалы, не «на глаз». */
export function RubricView({ items }: { items: RubricItem[] }) {
  const { t } = useLocale();
  const sorted = [...items].sort((a, b) => ORDER.indexOf(a.key) - ORDER.indexOf(b.key));
  return (
    <div className="rb-list">
      {sorted.map((r) => (
        <div key={r.key} className="rb-row">
          <span className={"rb-level " + r.level}>{t(`rb.level.${r.level}` as TranslationKey)}</span>
          <div style={{ minWidth: 0 }}>
            <div className="rb-name">{t(`rb.c.${r.key}` as TranslationKey)}</div>
            {r.comment && r.level !== "met" && <div className="rb-comment">{r.comment}</div>}
            {r.evidence && <div className="rb-evidence">«{r.evidence}»</div>}
          </div>
        </div>
      ))}
    </div>
  );
}
