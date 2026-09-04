"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, EmptyState, SkeletonLines } from "@/components/ui";
import { Icon } from "@/components/Icon";
import {
  ApiError,
  getTeamDetail,
  getTeamJournal,
  type JournalEntry,
  type TeamMember,
} from "@/lib/api";
import { activeTeamId, subscribeWorkspace } from "@/lib/workspace";
import { roleLabel } from "@/lib/roles";
import { useLocale, type TranslationKey } from "@/lib/i18n";

/**
 * Журнал действий — AuditLog.dc.html. Записи неизменяемы; текст
 * события собирается здесь из машинного kind + payload, поэтому
 * лента переживает смену формулировок и читается на языке
 * пользователя.
 */

const PERIODS: { days: number; label: TranslationKey }[] = [
  { days: 7, label: "jr.days7" },
  { days: 30, label: "jr.days30" },
  { days: 90, label: "jr.days90" },
];

export default function SettingsJournalPage() {
  const { t, lang } = useLocale();
  const [teamId, setTeamId] = useState<string | null>(
    () => activeTeamId() ?? null,
  );
  const [entries, setEntries] = useState<JournalEntry[] | null>(null);
  const [kinds, setKinds] = useState<string[]>([]);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [kind, setKind] = useState("");
  const [actorId, setActorId] = useState("");
  const [days, setDays] = useState(7);
  const [denied, setDenied] = useState(false);

  useEffect(
    () => subscribeWorkspace(() => setTeamId(activeTeamId() ?? null)),
    [],
  );

  useEffect(() => {
    if (!teamId) return;
    getTeamDetail(teamId)
      .then((d) => setMembers(d.members))
      .catch(() => undefined);
  }, [teamId]);

  useEffect(() => {
    if (!teamId) return;
    setEntries(null);
    setDenied(false);
    getTeamJournal(teamId, {
      kind: kind || undefined,
      actorId: actorId ? Number(actorId) : undefined,
      days,
    })
      .then((d) => {
        setEntries(d.entries);
        setKinds(d.kinds);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 403) setDenied(true);
        setEntries([]);
      });
  }, [teamId, kind, actorId, days]);

  const fmtCap = (v: unknown) =>
    v == null ? t("jr.noCap") : `$${Number(v)}`;

  const phrase = (e: JournalEntry): { action: string; object: string } => {
    const p = (e.payload ?? {}) as Record<string, unknown>;
    const str = (k: string) => (p[k] != null ? String(p[k]) : "");
    switch (e.kind) {
      case "batch_assigned":
        return {
          action: p.assignee
            ? t("jr.k.batch_assigned", {
                count: str("count"),
                assignee: str("assignee"),
              })
            : t("jr.k.batch_assigned_pool", { count: str("count") }),
          object: p.funnel
            ? t("jr.o.batch", { funnel: str("funnel") })
            : t("jr.o.base"),
        };
      case "funnel_created":
        return {
          action: t("jr.k.funnel_created", { name: str("name") }),
          object: t("jr.o.funnels"),
        };
      case "funnel_updated":
        return {
          action: t("jr.k.funnel_updated", { name: str("name") }),
          object: t("jr.o.funnels"),
        };
      case "funnel_deleted":
        return {
          action: t("jr.k.funnel_deleted", { name: str("name") }),
          object: t("jr.o.funnels"),
        };
      case "member_invited":
        return {
          action: t("jr.k.member_invited", {
            role: roleLabel(t, str("role")).toLowerCase(),
          }),
          object: t("jr.o.team"),
        };
      case "role_changed":
        return {
          action: t("jr.k.role_changed", {
            member: str("member"),
            from: roleLabel(t, str("from")).toLowerCase(),
            to: roleLabel(t, str("to")).toLowerCase(),
          }),
          object: t("jr.o.team"),
        };
      case "member_removed": {
        const base = p.left
          ? t("jr.k.member_left", { member: str("member") })
          : t("jr.k.member_removed", { member: str("member") });
        const extra =
          Number(p.transferred_leads ?? 0) > 0
            ? ` · ${t("jr.k.transferredLeads", {
                count: str("transferred_leads"),
              })}`
            : "";
        return { action: base + extra, object: t("jr.o.team") };
      }
      case "ownership_transferred":
        return {
          action: t("jr.k.ownership_transferred", { to: str("to") }),
          object: t("jr.o.team"),
        };
      case "cost_cap_changed":
        return {
          action: t("jr.k.cost_cap_changed", {
            from: fmtCap(p.from),
            to: fmtCap(p.to),
          }),
          object: t("jr.o.settings"),
        };
      case "search_finished":
        return {
          action: t("jr.k.search_finished", {
            leads: str("leads"),
            tokens: str("tokens"),
          }),
          object: p.region
            ? t("jr.o.search", { region: str("region") })
            : t("jr.o.base"),
        };
      case "leads_exported":
        return { action: t("jr.k.leads_exported"), object: t("jr.o.base") };
      case "squad_created":
        return {
          action: t("jr.k.squad_created", { name: str("name") }),
          object: t("jr.o.team"),
        };
      case "squad_updated":
        return {
          action: t("jr.k.squad_updated", { name: str("name") }),
          object: t("jr.o.team"),
        };
      case "squad_deleted":
        return {
          action: t("jr.k.squad_deleted", { name: str("name") }),
          object: t("jr.o.team"),
        };
      case "squad_member_moved":
        return {
          action: p.squad
            ? t("jr.k.squad_member_moved", {
                member: str("member"),
                squad: str("squad"),
              })
            : t("jr.k.squad_member_pooled", { member: str("member") }),
          object: t("jr.o.team"),
        };
      default:
        return { action: e.kind, object: e.object_label ?? "" };
    }
  };

  const dtLocale =
    lang === "uk" ? "uk-UA" : lang === "en" ? "en-GB" : "ru-RU";

  const when = (iso: string) => {
    const d = new Date(iso);
    const now = new Date();
    const time = d.toLocaleTimeString(dtLocale, {
      hour: "2-digit",
      minute: "2-digit",
    });
    const sameDay = d.toDateString() === now.toDateString();
    if (sameDay) return `${t("jr.today")} ${time}`;
    const yest = new Date(now);
    yest.setDate(now.getDate() - 1);
    if (d.toDateString() === yest.toDateString())
      return `${t("jr.yesterday")} ${time}`;
    return `${d.toLocaleDateString(dtLocale, {
      day: "numeric",
      month: "short",
    })} ${time}`;
  };

  const kindLabel = (k: string): string => {
    const key = `jr.k.${k}` as TranslationKey;
    // Для фильтра берём фразу без параметров — обрезаем по «:».
    try {
      return t(key, {
        count: "…",
        assignee: "…",
        name: "…",
        role: "…",
        member: "…",
        from: "…",
        to: "…",
        leads: "…",
        tokens: "…",
      }).split(":")[0];
    } catch {
      return k;
    }
  };

  const actorCell = (e: JournalEntry) => {
    if (e.actor_id == null) {
      return (
        <span style={{ fontWeight: 700, color: "var(--text-dim)" }}>
          {t("jr.system")}
        </span>
      );
    }
    return (
      <span style={{ fontWeight: 700, color: "var(--accent)" }}>
        {e.actor_name ?? `#${e.actor_id}`}
      </span>
    );
  };

  const rows = useMemo(() => entries ?? [], [entries]);

  if (!teamId) {
    return (
      <Card>
        <EmptyState
          icon={<Icon name="clock" size={20} />}
          title={t("st.tab.journal")}
          hint={t("jr.noTeam")}
        />
      </Card>
    );
  }
  if (denied) {
    return (
      <Card>
        <EmptyState
          icon={<Icon name="clock" size={20} />}
          title={t("st.tab.journal")}
          hint={t("jr.denied")}
        />
      </Card>
    );
  }

  const select = (
    value: string,
    onChange: (v: string) => void,
    options: { value: string; label: string }[],
  ) => (
    <select
      className="input"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      style={{ width: "auto", fontSize: 12.5, fontWeight: 700 }}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );

  return (
    <>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          flexWrap: "wrap",
          marginBottom: 14,
        }}
      >
        {select(actorId, setActorId, [
          { value: "", label: `${t("jr.who")}: ${t("jr.all")}` },
          ...members.map((m) => ({
            value: String(m.id),
            label: m.name,
          })),
        ])}
        {select(kind, setKind, [
          { value: "", label: `${t("jr.kindF")}: ${t("jr.allKinds")}` },
          ...kinds.map((k) => ({ value: k, label: kindLabel(k) })),
        ])}
        {select(String(days), (v) => setDays(Number(v)), [
          ...PERIODS.map((pd) => ({
            value: String(pd.days),
            label: `${t("jr.period")}: ${t(pd.label)}`,
          })),
        ])}
        <span
          style={{
            marginLeft: "auto",
            fontSize: 12.5,
            color: "var(--text-dim)",
          }}
        >
          {t("jr.immutable")}
        </span>
      </div>

      <Card style={{ padding: 0, overflow: "hidden" }}>
        {entries === null ? (
          <div style={{ padding: 18 }}>
            <SkeletonLines lines={6} />
          </div>
        ) : rows.length === 0 ? (
          <div
            style={{
              padding: 24,
              fontSize: 13,
              color: "var(--text-dim)",
            }}
          >
            {t("jr.empty")}
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <div style={{ minWidth: 720 }}>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "120px 150px 1.6fr 1fr",
                  gap: 10,
                  padding: "11px 18px",
                }}
                className="eyebrow"
              >
                <span>{t("jr.col.when")}</span>
                <span>{t("jr.col.who")}</span>
                <span>{t("jr.col.action")}</span>
                <span>{t("jr.col.object")}</span>
              </div>
              {rows.map((e) => {
                const ph = phrase(e);
                return (
                  <div
                    key={e.id}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "120px 150px 1.6fr 1fr",
                      gap: 10,
                      alignItems: "center",
                      padding: "10px 18px",
                      borderTop: "1px solid var(--border)",
                      fontSize: 13,
                      whiteSpace: "nowrap",
                    }}
                  >
                    <span
                      style={{
                        color: "var(--text-dim)",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {when(e.at)}
                    </span>
                    {actorCell(e)}
                    <span
                      style={{
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {ph.action}
                    </span>
                    <span
                      style={{
                        color: "var(--text-dim)",
                        fontSize: 12.5,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {ph.object}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </Card>
    </>
  );
}
