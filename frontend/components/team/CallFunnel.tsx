"use client";

import { useEffect, useState } from "react";
import {
  getTeamCallFunnel,
  type CallFunnel as CallFunnelData,
} from "@/lib/api";
import { useLocale } from "@/lib/i18n";

/**
 * Воронка отдела по звонкам — Analytics.dc.html.
 *
 * Из макета сознательно отсутствуют три показателя: «разговоры 2+ мин»
 * и «средний разговор» требуют длительности звонка, а телефония ещё не
 * подключена; «оплаты» требуют записи о платеже, а система фиксирует
 * только достижение цели. Ставить туда выдуманные числа хуже, чем не
 * ставить ничего.
 */
export function CallFunnel({
  teamId,
  days,
}: {
  teamId: string;
  days: number;
}) {
  const { t } = useLocale();
  const [data, setData] = useState<CallFunnelData | null>(null);

  useEffect(() => {
    let cancelled = false;
    getTeamCallFunnel(teamId, days)
      .then((d) => !cancelled && setData(d))
      .catch(() => !cancelled && setData(null));
    return () => {
      cancelled = true;
    };
  }, [teamId, days]);

  if (!data) return null;
  const maxDay = Math.max(1, ...data.by_day.map((d) => d.dials));

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 12,
        marginBottom: 12,
      }}
    >
      <div className="card" style={{ padding: 16 }}>
        <div className="eyebrow" style={{ marginBottom: 12 }}>
          {t("team.calls.funnel", { days: data.days })}
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
            gap: 10,
          }}
        >
          {(
            [
              [t("team.calls.dials"), String(data.dials), ""],
              [
                t("team.calls.connects"),
                String(data.connects),
                `${data.connect_rate}%`,
              ],
              [
                t("team.calls.goals"),
                String(data.goals),
                t("team.calls.goalRate", { p: data.goal_rate }),
              ],
            ] as const
          ).map(([label, value, hint]) => (
            <div key={label}>
              <div
                style={{
                  fontSize: 9.5,
                  fontWeight: 800,
                  letterSpacing: "0.09em",
                  textTransform: "uppercase",
                  color: "var(--text-dim)",
                }}
              >
                {label}
              </div>
              <div
                style={{
                  fontSize: 26,
                  fontWeight: 800,
                  lineHeight: 1.15,
                  marginTop: 4,
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {value}
              </div>
              {hint && (
                <div style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
                  {hint}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="card" style={{ padding: 16 }}>
        <div className="eyebrow" style={{ marginBottom: 12 }}>
          {t("team.calls.byDay")}
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            gap: 5,
            height: 110,
          }}
        >
          {data.by_day.map((d) => (
            <div
              key={d.date}
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 4,
                minWidth: 0,
              }}
              title={`${d.date}: ${d.dials}`}
            >
              <span
                style={{
                  fontSize: 10,
                  color: "var(--text-muted)",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {d.dials}
              </span>
              <span
                style={{
                  width: "100%",
                  background: "var(--accent)",
                  borderRadius: "4px 4px 0 0",
                  minHeight: 3,
                  height: `${(d.dials / maxDay) * 70}px`,
                }}
              />
              <span style={{ fontSize: 9, color: "var(--text-dim)" }}>
                {d.date.slice(8)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {data.by_rep.length > 0 && (
        <div className="card" style={{ padding: 16 }}>
          <div className="eyebrow" style={{ marginBottom: 10 }}>
            {t("team.calls.byRep", { days: data.days })}
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>{t("team.calls.rep")}</th>
                  <th>{t("team.calls.dials")}</th>
                  <th>{t("team.calls.connects")}</th>
                  <th>{t("team.calls.goals")}</th>
                  <th>{t("team.calls.conversion")}</th>
                </tr>
              </thead>
              <tbody>
                {data.by_rep.map((r) => (
                  <tr key={r.user_id}>
                    <td style={{ fontWeight: 600 }}>{r.name}</td>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>
                      {r.dials}
                    </td>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>
                      {r.connects} · {r.connect_rate}%
                    </td>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>
                      {r.goals}
                    </td>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>
                      {r.goal_rate}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
