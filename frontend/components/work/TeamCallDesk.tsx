"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, EmptyState, SkeletonLines } from "@/components/ui";
import { Icon } from "@/components/Icon";
import { getWorkOverview, type WorkOverview } from "@/lib/api";
import { roleLabel } from "@/lib/roles";
import { useLocale } from "@/lib/i18n";

/**
 * Пульт прозвона отдела — то, что видит на «Работе» владелец, РОП и
 * тимлид вместо звонилки: кто сколько набрал, поговорил и закрыл,
 * у кого висят просроченные перезвоны и кто давно молчит. Тимлиду
 * сервер отдаёт только его команду.
 */
export function TeamCallDesk({ teamId }: { teamId: string }) {
  const { t } = useLocale();
  const [data, setData] = useState<WorkOverview | null>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    getWorkOverview(teamId)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setData({ rows: [], dials: 0, talks: 0, goals: 0 });
      });
    const timer = window.setInterval(() => {
      getWorkOverview(teamId)
        .then((d) => {
          if (!cancelled) setData(d);
        })
        .catch(() => undefined);
    }, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [teamId]);

  if (data === null) {
    return (
      <Card>
        <SkeletonLines lines={6} />
      </Card>
    );
  }

  const time = (iso: string | null) =>
    iso
      ? new Date(iso).toLocaleTimeString("ru-RU", {
          hour: "2-digit",
          minute: "2-digit",
        })
      : "—";

  const activityBadge = (iso: string | null) => {
    if (!iso)
      return (
        <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
          {t("desk.idle")}
        </span>
      );
    const mins = (Date.now() - new Date(iso).getTime()) / 60_000;
    const live = mins <= 30;
    return (
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 5,
          fontSize: 11,
          fontWeight: 700,
          color: live ? "var(--accent)" : "var(--text-dim)",
        }}
      >
        <span
          style={{
            width: 7,
            height: 7,
            borderRadius: "50%",
            background: live ? "var(--accent)" : "var(--border)",
          }}
        />
        {live ? t("desk.live") : t("desk.quietSince", { time: time(iso) })}
      </span>
    );
  };

  return (
    <>
      <div
        style={{
          display: "flex",
          gap: 22,
          fontSize: 13,
          color: "var(--text-muted)",
          marginBottom: 14,
          flexWrap: "wrap",
        }}
      >
        {(
          [
            [t("desk.dials"), data.dials],
            [t("desk.talks"), data.talks],
            [t("desk.goals"), data.goals],
          ] as const
        ).map(([label, value]) => (
          <div key={label} style={{ display: "flex", gap: 7, alignItems: "baseline" }}>
            <span className="eyebrow" style={{ fontSize: 10 }}>
              {label}
            </span>
            <span
              style={{
                fontSize: 20,
                fontWeight: 800,
                color: "var(--text)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {value}
            </span>
          </div>
        ))}
      </div>

      {data.rows.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Icon name="users" size={20} />}
            title={t("desk.emptyTitle")}
            hint={t("desk.emptyHint")}
          />
          <div style={{ textAlign: "center", marginTop: 4 }}>
            <Link href="/app/leads" className="btn btn-primary btn-sm">
              {t("work.emptyOpenCrm")}
            </Link>
          </div>
        </Card>
      ) : (
        <Card padding={0} style={{ overflow: "hidden" }}>
          <div style={{ overflowX: "auto" }}>
            <div style={{ minWidth: 760 }}>
              <div
                className="eyebrow"
                style={{
                  display: "grid",
                  gridTemplateColumns:
                    "1.4fr 0.9fr 0.55fr 0.7fr 0.55fr 0.9fr 1fr",
                  gap: 10,
                  padding: "12px 18px",
                }}
              >
                <span>{t("desk.col.rep")}</span>
                <span>{t("desk.col.squad")}</span>
                <span>{t("desk.col.dials")}</span>
                <span>{t("desk.col.talks")}</span>
                <span>{t("desk.col.goals")}</span>
                <span>{t("desk.col.overdue")}</span>
                <span>{t("desk.col.state")}</span>
              </div>
              {data.rows.map((r) => (
                <div
                  key={r.user_id}
                  style={{
                    display: "grid",
                    gridTemplateColumns:
                      "1.4fr 0.9fr 0.55fr 0.7fr 0.55fr 0.9fr 1fr",
                    gap: 10,
                    alignItems: "center",
                    padding: "11px 18px",
                    borderTop: "1px solid var(--border)",
                    fontSize: 13,
                  }}
                >
                  <span style={{ minWidth: 0 }}>
                    <span style={{ fontWeight: 700 }}>{r.name}</span>
                    <span
                      style={{
                        fontSize: 11,
                        color: "var(--text-dim)",
                        marginLeft: 7,
                      }}
                    >
                      {roleLabel(t, r.role)}
                    </span>
                  </span>
                  <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    {r.squad_name ?? "—"}
                  </span>
                  <span style={{ fontVariantNumeric: "tabular-nums" }}>
                    {r.dials}
                  </span>
                  <span style={{ fontVariantNumeric: "tabular-nums" }}>
                    {r.talks}
                  </span>
                  <span
                    style={{
                      fontVariantNumeric: "tabular-nums",
                      fontWeight: r.goals > 0 ? 800 : 500,
                      color: r.goals > 0 ? "var(--accent)" : undefined,
                    }}
                  >
                    {r.goals}
                  </span>
                  <span
                    style={{
                      fontVariantNumeric: "tabular-nums",
                      color:
                        r.overdue_callbacks > 0
                          ? "var(--warm)"
                          : "var(--text-dim)",
                      fontWeight: r.overdue_callbacks > 0 ? 700 : 500,
                    }}
                  >
                    {r.overdue_callbacks > 0
                      ? t("desk.overdueN", { n: r.overdue_callbacks })
                      : "—"}
                  </span>
                  {activityBadge(r.last_call_at)}
                </div>
              ))}
            </div>
          </div>
          <div
            style={{
              padding: "10px 18px",
              background: "var(--surface-2)",
              fontSize: 11.5,
              color: "var(--text-dim)",
            }}
          >
            {t("desk.footnote")}
          </div>
        </Card>
      )}
    </>
  );
}
