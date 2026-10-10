"use client";

import { useState, type ReactNode } from "react";
import type { BaseFacets as Facets, LeadTemp } from "@/lib/api";
import { useLocale } from "@/lib/i18n";

/** Состояние панели фильтров «Базы» (то, что запоминается). */
export interface BasePanelState {
  owners: (number | "free")[];
  niches: string[];
  regions: string[];
  temps: LeadTemp[];
  hasPhone: boolean;
  hasEmail: boolean;
  noWebsite: boolean;
  added: "" | "day" | "week" | "month";
  /** Сессии поиска (id). */
  sessions: string[];
}

export const EMPTY_PANEL: BasePanelState = {
  owners: [],
  niches: [],
  regions: [],
  temps: [],
  hasPhone: false,
  hasEmail: false,
  noWebsite: false,
  added: "",
  sessions: [],
};

export function panelIsEmpty(p: BasePanelState): boolean {
  return (
    !p.owners.length &&
    !p.niches.length &&
    !p.regions.length &&
    !p.temps.length &&
    !p.hasPhone &&
    !p.hasEmail &&
    !p.noWebsite &&
    !p.added &&
    !(p.sessions ?? []).length
  );
}

function toggle<T>(list: T[], v: T): T[] {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}

const LIMIT = 6;

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="bf-group">
      <div className="bf-title">{title}</div>
      {children}
    </div>
  );
}

function Opt({
  on,
  label,
  count,
  onClick,
  radio,
}: {
  on: boolean;
  label: ReactNode;
  count?: number;
  onClick: () => void;
  radio?: boolean;
}) {
  return (
    <button type="button" className={"bf-opt" + (on ? " on" : "")} onClick={onClick} aria-pressed={on}>
      <span className={radio ? "bf-radio" : "bf-box"} />
      <span className="bf-label">{label}</span>
      {count !== undefined && <span className="bf-count">{count}</span>}
    </button>
  );
}

function Many({
  items,
  selected,
  onToggle,
}: {
  items: { value: string; count: number }[];
  selected: string[];
  onToggle: (v: string) => void;
}) {
  const { t } = useLocale();
  const [all, setAll] = useState(false);
  // Выбранные показываем всегда, даже если не попали в первые строки.
  const top = all ? items : items.slice(0, LIMIT);
  const hiddenSelected = all ? [] : items.slice(LIMIT).filter((i) => selected.includes(i.value));
  const rows = [...top, ...hiddenSelected];
  return (
    <>
      {items.length === 0 && <div className="bf-empty">—</div>}
      {rows.map((i) => (
        <Opt key={i.value} on={selected.includes(i.value)} label={i.value} count={i.count} onClick={() => onToggle(i.value)} />
      ))}
      {items.length > LIMIT && (
        <button type="button" className="bf-more" onClick={() => setAll((v) => !v)}>
          {all ? t("bf.less") : t("bf.more", { n: items.length - LIMIT })}
        </button>
      )}
    </>
  );
}

function SessionList({
  items,
  selected,
  label,
  onToggle,
}: {
  items: { id: string; niche: string; region: string; created_at: string | null; count: number }[];
  selected: string[];
  label: (x: { niche: string; region: string; created_at: string | null }) => string;
  onToggle: (id: string) => void;
}) {
  const { t } = useLocale();
  const [all, setAll] = useState(false);
  const top = all ? items : items.slice(0, LIMIT);
  const hiddenSelected = all ? [] : items.slice(LIMIT).filter((i) => selected.includes(i.id));
  return (
    <>
      {[...top, ...hiddenSelected].map((i) => (
        <Opt key={i.id} on={selected.includes(i.id)} label={label(i)} count={i.count} onClick={() => onToggle(i.id)} />
      ))}
      {items.length > LIMIT && (
        <button type="button" className="bf-more" onClick={() => setAll((v) => !v)}>
          {all ? t("bf.less") : t("bf.more", { n: items.length - LIMIT })}
        </button>
      )}
    </>
  );
}

export function BaseFacetsPanel({
  facets,
  state,
  onChange,
  showOwners,
  open = false,
  onCollapse,
  onPin,
  sessionActions,
  onSessionAction,
}: {
  facets: Facets | null;
  state: BasePanelState;
  onChange: (next: BasePanelState) => void;
  showOwners: boolean;
  /** Узкий экран: панель видна, только если её раскрыли кнопкой. */
  open?: boolean;
  /** Свернуть панель (кнопка «Фильтры» вернёт её). */
  onCollapse?: () => void;
  /** Узкий экран: закрепить панель слева, как на большом. */
  onPin?: () => void;
  /** Что можно сделать с выбранной сессией. */
  sessionActions?: { archive: boolean; restore: boolean; delete: boolean };
  onSessionAction?: (id: string, action: "archive" | "restore" | "delete") => void;
}) {
  const { t, lang } = useLocale();
  const set = (patch: Partial<BasePanelState>) => onChange({ ...state, ...patch });
  const picked = state.sessions ?? [];
  const sessionLabel = (x: { niche: string; region: string; created_at: string | null }) =>
    [
      x.niche,
      x.region,
      x.created_at
        ? new Date(x.created_at).toLocaleDateString(lang === "en" ? "en-US" : lang === "uk" ? "uk-UA" : "ru-RU", {
            day: "numeric",
            month: "short",
          })
        : null,
    ]
      .filter(Boolean)
      .join(" · ");

  return (
    <aside className={"bf-panel card" + (open ? " open" : "")}>
      <div className="bf-head">
        <b>{t("bf.title")}</b>
        <span style={{ display: "inline-flex", gap: 10 }}>
          {!panelIsEmpty(state) && (
            <button type="button" className="bf-reset" onClick={() => onChange(EMPTY_PANEL)}>
              {t("bf.reset")}
            </button>
          )}
          {onPin && (
            <button type="button" className="bf-reset bf-pin" onClick={onPin}>
              {t("bf.pin")}
            </button>
          )}
          {onCollapse && (
            <button type="button" className="bf-reset bf-collapse" onClick={onCollapse} title={t("bf.collapse")}>
              {t("bf.collapse")}
            </button>
          )}
        </span>
      </div>

      {showOwners && (
        <Group title={t("bf.owner")}>
          <Opt
            on={state.owners.includes("free")}
            label={t("bf.free")}
            count={facets?.free}
            onClick={() => set({ owners: toggle(state.owners, "free" as const) })}
          />
          {facets?.owners.map((o) => (
            <Opt
              key={o.id}
              on={state.owners.includes(o.id)}
              label={o.name}
              count={o.count}
              onClick={() => set({ owners: toggle(state.owners, o.id) })}
            />
          ))}
        </Group>
      )}

      {(facets?.sessions?.length ?? 0) > 0 && (
        <Group title={t("bf.session")}>
          <SessionList
            items={facets?.sessions ?? []}
            selected={picked}
            label={sessionLabel}
            onToggle={(id) => set({ sessions: toggle(picked, id) })}
          />
          {picked.length === 1 && sessionActions && onSessionAction && (
            <div className="bf-session-actions">
              {sessionActions.archive && (
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => onSessionAction(picked[0], "archive")}>
                  {t("bf.sessionArchive")}
                </button>
              )}
              {sessionActions.restore && (
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => onSessionAction(picked[0], "restore")}>
                  {t("bf.sessionRestore")}
                </button>
              )}
              {sessionActions.delete && (
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ color: "var(--cold)" }}
                  onClick={() => onSessionAction(picked[0], "delete")}
                >
                  {t("bf.sessionDelete")}
                </button>
              )}
            </div>
          )}
        </Group>
      )}

      <Group title={t("bf.niche")}>
        <Many items={facets?.niches ?? []} selected={state.niches} onToggle={(v) => set({ niches: toggle(state.niches, v) })} />
      </Group>

      <Group title={t("bf.city")}>
        <Many items={facets?.regions ?? []} selected={state.regions} onToggle={(v) => set({ regions: toggle(state.regions, v) })} />
      </Group>

      <Group title={t("bf.score")}>
        {(["hot", "warm", "cold"] as LeadTemp[]).map((k) => (
          <Opt
            key={k}
            on={state.temps.includes(k)}
            label={t(k === "hot" ? "bf.hot" : k === "warm" ? "bf.warm" : "bf.cold")}
            count={facets?.temps[k]}
            onClick={() => set({ temps: toggle(state.temps, k) })}
          />
        ))}
      </Group>

      <Group title={t("bf.contacts")}>
        <Opt on={state.hasPhone} label={t("bf.hasPhone")} count={facets?.contacts.phone} onClick={() => set({ hasPhone: !state.hasPhone })} />
        <Opt on={state.hasEmail} label={t("bf.hasEmail")} count={facets?.contacts.email} onClick={() => set({ hasEmail: !state.hasEmail })} />
        <Opt
          on={state.noWebsite}
          label={t("bf.noWebsite")}
          count={facets?.contacts.no_website}
          onClick={() => set({ noWebsite: !state.noWebsite })}
        />
      </Group>

      <Group title={t("bf.added")}>
        {(["", "day", "week", "month"] as const).map((k) => (
          <Opt
            key={k || "all"}
            radio
            on={state.added === k}
            label={t(k === "" ? "bf.anytime" : k === "day" ? "bf.today" : k === "week" ? "bf.week" : "bf.month")}
            onClick={() => set({ added: k })}
          />
        ))}
      </Group>
    </aside>
  );
}
