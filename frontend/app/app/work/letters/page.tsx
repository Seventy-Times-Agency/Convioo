"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import { Card, EmptyState, SkeletonLines } from "@/components/ui";
import { getWorkLetters, type WorkLetters, type LetterRow } from "@/lib/api";
import { activeTeamId, subscribeWorkspace } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";

/**
 * Письма — Letters.dc.html, вкладка рядом с прозвоном.
 *
 * Две очереди разделяет флаг `auto` у шага воронки — то же поле, по
 * которому решает воркер. Экран поэтому показывает не свою версию
 * происходящего, а ровно то, что произойдёт.
 *
 * Редактора черновика из макета здесь нет: черновик пишется под
 * конкретный исход звонка и живёт в карточке лида. Дублировать его
 * тут значило бы завести второе место, где одно и то же письмо можно
 * править по-разному.
 */
export default function LettersPage() {
  const { t } = useLocale();
  const [data, setData] = useState<WorkLetters | null>(null);
  const [teamId, setTeamId] = useState<string | null>(() => activeTeamId() ?? null);

  useEffect(
    () => subscribeWorkspace(() => setTeamId(activeTeamId() ?? null)),
    [],
  );

  useEffect(() => {
    if (!teamId) return;
    setData(null);
    getWorkLetters(teamId)
      .then(setData)
      .catch(() => setData(null));
  }, [teamId]);

  const row = (r: LetterRow) => (
    <div
      key={r.lead_id}
      style={{
        display: "flex",
        justifyContent: "space-between",
        gap: 10,
        padding: "10px 0",
        borderBottom: "1px solid var(--border)",
        alignItems: "baseline",
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13.5, fontWeight: 600 }}>{r.lead_name}</div>
        <div style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
          {t("letters.touch", { i: r.step_index, n: r.steps_total })}
          {r.note ? ` · ${r.note}` : ""}
        </div>
      </div>
      <div
        style={{
          fontSize: 11.5,
          color: "var(--text-dim)",
          whiteSpace: "nowrap",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {r.due_at
          ? new Date(r.due_at).toLocaleTimeString("ru-RU", {
              hour: "2-digit",
              minute: "2-digit",
            })
          : "—"}
      </div>
    </div>
  );

  return (
    <>
      <Topbar crumbs={[{ label: t("nav.work") }]} />
      <div className="page" style={{ maxWidth: 1100 }}>
        <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
          <Link href="/app/work" className="btn btn-ghost btn-sm">
            {t("letters.tabCalls")}
          </Link>
          <span className="btn btn-primary btn-sm">
            {t("letters.tabLetters")}
          </span>
        </div>

        {!teamId && (
          <Card>
            <EmptyState
              icon={<Icon name="mail" size={20} />}
              title={t("funnels.noTeamTitle")}
              hint={t("work.noTeamHint")}
            />
          </Card>
        )}

        {teamId && !data && (
          <Card>
            <SkeletonLines lines={5} />
          </Card>
        )}

        {data && (
          <>
            <div
              style={{
                fontSize: 12.5,
                color: "var(--text-dim)",
                marginBottom: 14,
                paddingBottom: 12,
                borderBottom: "1px solid var(--border)",
              }}
            >
              {t("letters.quota", {
                sent: data.sent_today,
                cap: data.cap,
                day: data.warmup_day,
              })}
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
                gap: 12,
              }}
            >
              <Card>
                <div className="eyebrow" style={{ marginBottom: 10 }}>
                  {t("letters.pending", { n: data.pending_approval.length })}
                </div>
                {data.pending_approval.length === 0 ? (
                  <div style={{ fontSize: 12.5, color: "var(--text-dim)" }}>
                    {t("letters.pendingEmpty")}
                  </div>
                ) : (
                  data.pending_approval.map(row)
                )}
              </Card>

              <Card>
                <div className="eyebrow" style={{ marginBottom: 10 }}>
                  {t("letters.scheduled", { n: data.scheduled.length })}
                </div>
                {data.scheduled.length === 0 ? (
                  <div style={{ fontSize: 12.5, color: "var(--text-dim)" }}>
                    {t("letters.scheduledEmpty")}
                  </div>
                ) : (
                  data.scheduled.map(row)
                )}
              </Card>
            </div>

            <div
              style={{
                fontSize: 11.5,
                color: "var(--text-dim)",
                marginTop: 12,
                lineHeight: 1.5,
              }}
            >
              {t("letters.suppressionNote")}
              <br />
              {t("letters.workerNote")}
            </div>
          </>
        )}
      </div>
    </>
  );
}
