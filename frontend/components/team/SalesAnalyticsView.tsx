"use client";

import { useRouter } from "next/navigation";
import type { CSSProperties, ReactNode } from "react";
import { Icon, type IconName } from "@/components/brand/Icon";
import { Avatar, CountUp } from "@/components/ui";
import type {
  SalesAnalytics,
  SalesBucket,
  SalesFunnelStep,
  SalesMemberRow,
} from "@/lib/api";
import { useLocale, type TranslationKey } from "@/lib/i18n";
import { roleLabel } from "@/lib/roles";

/**
 * Вкладка «Продажи» на странице аналитики. Строгая сетка: полоса
 * чисел → строка выводов → график + воронка → три карточки → люди.
 * Все вычисления сделал сервер; здесь только раскладка и подписи
 * «что это значит».
 */
export function SalesAnalyticsView({ data }: { data: SalesAnalytics }) {
  const { t } = useLocale();
  const k = data.kpi;
  const pct = (r: number | null) => (r === null ? "—" : `${Math.round(r * 100)}%`);
  const mmss = (s: number | null) =>
    s === null ? "—" : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  const money = (n: number) =>
    n >= 1000 ? `$${(n / 1000).toFixed(1).replace(/\.0$/, "")}k` : `$${Math.round(n)}`;
  const delta = (cur: number, prev: number) => {
    const d = cur - prev;
    if (!d) return null;
    return (
      <span style={{ fontSize: 12, color: d > 0 ? "var(--accent)" : "var(--cold)", fontWeight: 600 }}>
        {d > 0 ? "▲" : "▼"}
        {Math.abs(d)}
      </span>
    );
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* ── полоса чисел ── */}
      <div className="card an-kpi">
        <Kpi
          label={t("an.kpi.goals")}
          value={<><CountUp value={k.goals} /> {delta(k.goals, k.goals_prev)}</>}
          hint={k.goals_plan ? t("an.kpi.goalsHint", { plan: k.goals_plan }) : t("an.kpi.goalsHintNoPlan")}
          tone={k.goals_plan ? tone(k.goals, k.goals_plan) : undefined}
        />
        <Kpi
          label={t("an.kpi.reach")}
          value={k.reach_rate === null ? "—" : <CountUp value={Math.round(k.reach_rate * 100)} format={(n) => `${Math.round(n)}%`} />}
          hint={t("an.kpi.reachHint", { talks: k.talks, dials: k.dials })}
          tone={k.reach_rate !== null && k.dials >= 20 ? (k.reach_rate < 0.4 ? "bad" : "ok") : undefined}
        />
        <Kpi
          label={t("an.kpi.quality")}
          value={k.quality_avg === null ? "—" : <><CountUp value={k.quality_avg} format={(n) => (Number.isInteger(k.quality_avg) ? String(Math.round(n)) : n.toFixed(1))} /><span style={{ fontSize: 12, color: "var(--text-dim)" }}>/10</span></>}
          hint={t("an.kpi.qualityHint", { n: k.quality_n, t: mmss(k.talk_avg_sec) })}
        />
        <Kpi
          label={t("an.kpi.money")}
          value={<CountUp value={k.money_in_work} format={money} />}
          hint={t("an.kpi.moneyHint", { n: k.closed_count, sum: money(k.money_closed) })}
        />
        <Kpi
          label={t("an.kpi.speed")}
          value={k.days_to_first_call === null ? "—" : <><CountUp value={k.days_to_first_call} format={(n) => (Number.isInteger(k.days_to_first_call) ? String(Math.round(n)) : n.toFixed(1))} /> <span style={{ fontSize: 12, color: "var(--text-dim)" }}>{t("an.kpi.days")}</span></>}
          hint={t("an.kpi.speedHint")}
          tone={k.days_to_first_call !== null ? (k.days_to_first_call <= 1 ? "ok" : k.days_to_first_call <= 3 ? "warn" : "bad") : undefined}
        />
        <Kpi
          label={t("an.kpi.overdue")}
          value={<CountUp value={k.overdue_callbacks} />}
          hint={t("an.kpi.overdueHint", { n: k.cooling_leads })}
          tone={k.overdue_callbacks > 0 ? "bad" : "ok"}
          last
        />
      </div>

      {/* ── выводы ── */}
      <div className="card an-ins">
        {data.insights.map((i, idx) => (
          <div key={idx}>
            <Icon name={INSIGHT_ICON[i.kind]} size={14} style={{ color: INSIGHT_COLOR[i.kind], flexShrink: 0, marginTop: 2 }} />
            <span>{i.text}</span>
          </div>
        ))}
      </div>

      {/* ── график + воронка ── */}
      <div className="an-2">
        <Card title={t("an.byDay")} aside={
          <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
            <Sw c="color-mix(in srgb, var(--accent) 30%, transparent)" /> {t("an.dials")}{" "}
            <Sw c="var(--accent)" /> {t("an.talks")}{" "}
            <Sw c="var(--hot)" line /> {t("an.goals")}
          </span>
        }>
          <DayChart data={data} />
        </Card>
        <Card title={t("an.funnel")}>
          <Funnel steps={data.funnel} />
          <Note>{t("an.funnelNote")}</Note>
        </Card>
      </div>

      {/* ── три карточки ── */}
      <div className="an-3">
        <Card title={t("an.outcomes", { n: k.dials })}>
          <Bars
            items={data.outcomes.map((b) => ({
              label: t(OUTCOME_KEY[b.key] ?? "calls.outcome.refused"),
              value: b.share,
              text: `${Math.round(b.share * 100)}%`,
              color: OUTCOME_COLOR[b.key] ?? "var(--text-dim)",
            }))}
          />
          <Sub>{t("an.objections")}</Sub>
          {data.objections.length === 0 ? (
            <Note>{t("an.objectionsEmpty")}</Note>
          ) : (
            <Bars
              items={data.objections.map((b: SalesBucket) => ({
                label: b.key,
                value: b.share,
                text: `${Math.round(b.share * 100)}%`,
                color: "#7F77DD",
              }))}
            />
          )}
        </Card>

        <Card title={t("an.heat")}>
          <Heatmap data={data} />
          <Note>{bestWindowText(t, data.best_window)}</Note>
          <Sub>{t("an.emails")}</Sub>
          <Bars
            items={[
              { label: t("an.emails.sent"), value: data.emails.sent ? 1 : 0, text: String(data.emails.sent), color: "color-mix(in srgb, var(--accent) 35%, transparent)" },
              { label: t("an.emails.replied"), value: data.emails.sent ? data.emails.replied / data.emails.sent : 0, text: data.emails.sent ? `${Math.round((data.emails.replied / data.emails.sent) * 100)}%` : "—", color: "var(--accent)" },
              { label: t("an.emails.hot"), value: data.emails.sent ? data.emails.hot / data.emails.sent : 0, text: String(data.emails.hot), color: "var(--hot)" },
            ]}
          />
        </Card>

        <Card title={t("an.whatWorks")}>
          <Sub first>{t("an.byTemp")}</Sub>
          <Bars
            items={data.by_temp.map((r) => ({
              label: r.temp,
              value: r.rate ?? 0,
              text: r.rate === null ? "—" : `${Math.round(r.rate * 100)}%`,
              color: r.temp === "hot" ? "var(--hot)" : r.temp === "warm" ? "var(--warm)" : "var(--cold)",
              muted: r.talks === 0,
            }))}
          />
          <Note>{tempNote(t, data)}</Note>
          <Sub>{t("an.byNiche")}</Sub>
          {data.by_niche.length === 0 ? (
            <Note>{t("an.nicheEmpty")}</Note>
          ) : (
            <Bars
              items={data.by_niche.map((r) => ({
                label: r.niche,
                value: r.rate ?? 0,
                text: r.rate === null ? "—" : `${Math.round(r.rate * 100)}%`,
                color: "var(--accent)",
              }))}
            />
          )}
        </Card>
      </div>

      {/* ── люди ── */}
      <Card title={t("an.people")}>
        <People rows={data.members} />
        <Note>{t("an.peopleNote")}</Note>
      </Card>
    </div>
  );
}

/* ── примитивы ────────────────────────────────────────────────────── */

type Tone = "ok" | "warn" | "bad";
const TONE: Record<Tone, string> = { ok: "var(--accent)", warn: "var(--warm)", bad: "var(--cold)" };
function tone(done: number, plan: number): Tone {
  const r = done / plan;
  return r >= 1 ? "ok" : r >= 0.5 ? "warn" : "bad";
}

const INSIGHT_ICON: Record<string, IconName> = { up: "sortDesc", warn: "flame", bad: "clock", info: "chat" };
const INSIGHT_COLOR: Record<string, string> = {
  up: "var(--accent)",
  warn: "var(--warm)",
  bad: "var(--cold)",
  info: "var(--text-muted)",
};
const OUTCOME_KEY: Record<string, TranslationKey> = {
  goal: "calls.outcome.goal",
  callback: "calls.outcome.callback",
  thinking: "calls.outcome.thinking",
  refused: "calls.outcome.refused",
  no_answer: "calls.outcome.no_answer",
  wrong_number: "calls.outcome.wrong_number",
};
const OUTCOME_COLOR: Record<string, string> = {
  goal: "var(--accent)",
  callback: "#378ADD",
  thinking: "#7F77DD",
  refused: "var(--hot)",
  no_answer: "var(--text-dim)",
  wrong_number: "#888780",
};
const FUNNEL_KEY: Record<SalesFunnelStep["key"], TranslationKey> = {
  found: "an.f.found",
  in_work: "an.f.inWork",
  dials: "an.f.dials",
  talks: "an.f.talks",
  goals: "an.f.goals",
  deals: "an.f.deals",
};

function Kpi({
  label,
  value,
  hint,
  tone: tn,
  last,
}: {
  label: string;
  value: ReactNode;
  hint: string;
  tone?: Tone;
  last?: boolean;
}) {
  return (
    <div style={{ padding: "12px 14px", borderRight: last ? "none" : "1px solid var(--border)", minWidth: 0 }}>
      <div className="eyebrow" style={{ fontSize: 9.5, marginBottom: 4 }}>{label}</div>
      <div
        style={{
          fontSize: 24,
          fontWeight: 800,
          lineHeight: 1.1,
          fontVariantNumeric: "tabular-nums",
          color: tn ? TONE[tn] : "var(--text)",
          display: "flex",
          alignItems: "baseline",
          gap: 6,
        }}
      >
        {value}
      </div>
      <div style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 3, lineHeight: 1.4 }}>{hint}</div>
    </div>
  );
}

function Card({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <div className="card" style={{ padding: "14px 16px", minWidth: 0, display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 10 }}>
        <span className="eyebrow" style={{ fontSize: 10 }}>{title}</span>
        {aside && <span style={{ marginLeft: "auto" }}>{aside}</span>}
      </div>
      {children}
    </div>
  );
}

function Sub({ children, first }: { children: ReactNode; first?: boolean }) {
  return (
    <div className="eyebrow" style={{ fontSize: 9.5, margin: first ? "0 0 6px" : "12px 0 6px", color: "var(--text-dim)" }}>
      {children}
    </div>
  );
}

function Note({ children }: { children: ReactNode }) {
  return <div style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 8, lineHeight: 1.45 }}>{children}</div>;
}

function Sw({ c, line }: { c: string; line?: boolean }) {
  return (
    <span
      style={{
        display: "inline-block",
        width: 10,
        height: line ? 2 : 10,
        background: c,
        verticalAlign: "middle",
        borderRadius: 2,
      }}
    />
  );
}

function Bars({
  items,
}: {
  items: { label: string; value: number; text: string; color: string; muted?: boolean }[];
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      {items.map((it, i) => (
        <div
          key={it.label}
          style={{
            display: "grid",
            gridTemplateColumns: "96px 1fr 40px",
            gap: 8,
            alignItems: "center",
            fontSize: 12,
            opacity: it.muted ? 0.5 : 1,
          }}
        >
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={it.label}>
            {it.label}
          </span>
          <div style={{ height: 8, borderRadius: 4, background: "var(--surface-2)", overflow: "hidden" }}>
            <div className="m-bar" style={{ width: `${Math.min(100, Math.round(it.value * 100))}%`, height: "100%", background: it.color, borderRadius: 4, ["--i" as string]: i }} />
          </div>
          <span style={{ textAlign: "right", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>{it.text}</span>
        </div>
      ))}
    </div>
  );
}

function Funnel({ steps }: { steps: SalesFunnelStep[] }) {
  const { t } = useLocale();
  const max = Math.max(1, ...steps.map((s) => s.count));
  // Самый слабый переход (кроме первого) подсвечиваем.
  // Переход с долей > 1 (наборов больше, чем лидов) — не слабое место.
  const rated = steps.filter((s) => s.rate !== null && s.rate <= 1);
  const weakest = rated.length
    ? rated.reduce((a, b) => ((b.rate ?? 1) < (a.rate ?? 1) ? b : a))
    : null;
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {steps.map((s, i) => {
        const weak = weakest?.key === s.key && (s.rate ?? 1) < 0.5;
        return (
          <div
            key={s.key}
            style={{
              display: "grid",
              gridTemplateColumns: "88px 1fr 84px",
              gap: 8,
              alignItems: "center",
              padding: "5px 0",
              borderTop: i === 0 ? "none" : "1px solid var(--border)",
              fontSize: 12,
            }}
          >
            <span>{t(FUNNEL_KEY[s.key])}</span>
            <div style={{ height: 14, borderRadius: 4, background: "var(--accent-soft)", overflow: "hidden" }}>
              <div
                className="m-bar"
                style={{
                  ["--i" as string]: i,
                  width: `${Math.max(1, Math.round((s.count / max) * 100))}%`,
                  height: "100%",
                  background: weak ? "var(--warm)" : "var(--accent)",
                  borderRadius: 4,
                }}
              />
            </div>
            <span style={{ textAlign: "right", color: weak ? "var(--warm)" : "var(--text-muted)", fontVariantNumeric: "tabular-nums", fontWeight: weak ? 600 : 400 }}>
              {s.count}
              {s.rate !== null && s.rate <= 1 && ` · ${Math.round(s.rate * 100)}%`}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function DayChart({ data }: { data: SalesAnalytics }) {
  const pts = data.by_day;
  const W = 600;
  const H = 150;
  const max = Math.max(1, ...pts.map((p) => p.dials));
  const n = pts.length;
  const bw = W / n;
  const y = (v: number) => H - 20 - (v / max) * (H - 30);
  const goalsMax = Math.max(1, ...pts.map((p) => p.goals));
  const gy = (v: number) => H - 20 - (v / goalsMax) * (H - 30) * 0.9;
  const step = n > 45 ? 7 : n > 14 ? 3 : 1;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: 150, display: "block" }} aria-hidden="true">
      {[0.25, 0.5, 0.75, 1].map((f) => (
        <line key={f} x1={0} x2={W} y1={y(max * f)} y2={y(max * f)} stroke="var(--border)" strokeWidth={0.6} />
      ))}
      {pts.map((p, i) => (
        <g key={p.date}>
          <rect className="m-col" style={{ ["--i" as string]: i }} x={i * bw + bw * 0.15} y={y(p.dials)} width={bw * 0.7} height={H - 20 - y(p.dials)} fill="color-mix(in srgb, var(--accent) 30%, transparent)" rx={1.5} />
          <rect className="m-col" style={{ ["--i" as string]: i }} x={i * bw + bw * 0.15} y={y(p.talks)} width={bw * 0.7} height={H - 20 - y(p.talks)} fill="var(--accent)" rx={1.5} />
          {i % step === 0 && (
            <text x={i * bw + bw / 2} y={H - 6} fontSize={9} textAnchor="middle" fill="var(--text-dim)">
              {p.date.slice(8)}
            </text>
          )}
        </g>
      ))}
      <polyline
        className="m-line"
        pathLength={1}
        fill="none"
        stroke="var(--hot)"
        strokeWidth={2}
        points={pts.map((p, i) => `${i * bw + bw / 2},${gy(p.goals)}`).join(" ")}
      />
    </svg>
  );
}

function Heatmap({ data }: { data: SalesAnalytics }) {
  const { t } = useLocale();
  const hours = Array.from({ length: 11 }, (_, i) => 8 + i);
  const days = [0, 1, 2, 3, 4];
  const cell = new Map<string, { d: number; t: number }>();
  for (const c of data.heatmap) cell.set(`${c.weekday}:${c.hour}`, { d: c.dials, t: c.talks });
  const dayNames = [t("an.wd.mon"), t("an.wd.tue"), t("an.wd.wed"), t("an.wd.thu"), t("an.wd.fri")];
  return (
    <div style={{ display: "grid", gridTemplateColumns: `24px repeat(${hours.length}, 1fr)`, gap: 2, fontSize: 10, color: "var(--text-dim)" }}>
      <span />
      {hours.map((h) => (
        <span key={h} style={{ textAlign: "center" }}>{h}</span>
      ))}
      {days.map((d) => (
        <DayRow key={d} label={dayNames[d]} cells={hours.map((h) => cell.get(`${d}:${h}`) ?? null)} />
      ))}
    </div>
  );
}

function DayRow({ label, cells }: { label: string; cells: ({ d: number; t: number } | null)[] }) {
  return (
    <>
      <span style={{ lineHeight: "14px" }}>{label}</span>
      {cells.map((c, i) => {
        const r = c && c.d > 0 ? c.t / c.d : null;
        const alpha = r === null ? 0 : 0.15 + r * 0.85;
        return (
          <span
            key={i}
            title={c ? `${c.t}/${c.d}` : ""}
            className="m-fade"
            style={{
              ["--i" as string]: i,
              height: 14,
              borderRadius: 2,
              background: r === null ? "var(--surface-2)" : `color-mix(in srgb, var(--accent) ${Math.round(alpha * 100)}%, var(--surface-2))`,
            }}
          />
        );
      })}
    </>
  );
}

function bestWindowText(t: ReturnType<typeof useLocale>["t"], w: string | null): string {
  if (!w) return t("an.heatEmpty");
  const [wd, h, p] = w.split(":").map(Number);
  const names = [t("an.wd.mon"), t("an.wd.tue"), t("an.wd.wed"), t("an.wd.thu"), t("an.wd.fri"), t("an.wd.sat"), t("an.wd.sun")];
  return t("an.heatBest", { day: names[wd] ?? "", h: `${h}:00`, p });
}

function tempNote(t: ReturnType<typeof useLocale>["t"], data: SalesAnalytics): string {
  const hot = data.by_temp.find((r) => r.temp === "hot");
  const cold = data.by_temp.find((r) => r.temp === "cold");
  if (!hot?.rate || !cold?.rate) return t("an.tempNoteEmpty");
  const x = hot.rate / cold.rate;
  return x >= 1.5 ? t("an.tempNoteGood", { x: x.toFixed(1) }) : t("an.tempNoteFlat");
}

function People({ rows }: { rows: SalesMemberRow[] }) {
  const { t } = useLocale();
  const router = useRouter();
  const mmss = (s: number | null) =>
    s === null ? "—" : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  const cellPlan = (done: number, plan: number | null) => (
    <div style={{ minWidth: 86 }}>
      <span style={{ fontVariantNumeric: "tabular-nums" }}>
        {done}
        {plan ? <span style={{ color: "var(--text-dim)" }}> / {plan}</span> : null}
      </span>
      {plan ? (
        <div style={{ height: 4, borderRadius: 2, background: "var(--surface-2)", marginTop: 3, overflow: "hidden" }}>
          <div className="m-bar" style={{ width: `${Math.min(100, Math.round((done / plan) * 100))}%`, height: "100%", background: TONE[tone(done, plan)] }} />
        </div>
      ) : null}
    </div>
  );
  const th: CSSProperties = { padding: "6px 8px" };
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="tbl team-ov-tbl" style={{ fontSize: 12.5 }}>
        <thead>
          <tr>
            <th style={th}>{t("team.owner.col.member")}</th>
            <th style={th}>{t("an.col.dials")}</th>
            <th style={th}>{t("an.col.reach")}</th>
            <th style={th}>{t("an.col.goals")}</th>
            <th style={th}>{t("an.col.quality")}</th>
            <th style={th}>{t("an.col.talk")}</th>
            <th style={th}>{t("an.col.overdue")}</th>
            <th style={th}>{t("an.col.hot")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => (
            <tr key={m.user_id} style={{ cursor: "pointer" }} onClick={() => router.push("/app/team")}>
              <td style={th}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Avatar src={m.avatar_url} initials={m.name.slice(0, 1).toUpperCase()} size={24} />
                  <span style={{ fontWeight: 600 }}>{m.name}</span>
                  <span style={{ color: "var(--text-dim)" }}>· {roleLabel(t, m.role).toLowerCase()}</span>
                </div>
              </td>
              <td style={th}>{cellPlan(m.dials, m.dials_plan)}</td>
              <td style={th}>{m.reach_rate === null ? "—" : `${Math.round(m.reach_rate * 100)}%`}</td>
              <td style={th}>{cellPlan(m.goals, m.goals_plan)}</td>
              <td style={th}>{m.quality_avg ?? "—"}</td>
              <td style={th}>{mmss(m.talk_avg_sec)}</td>
              <td style={{ ...th, color: m.overdue ? "var(--cold)" : undefined, fontWeight: m.overdue ? 600 : 400 }}>{m.overdue}</td>
              <td style={th}>{m.hot_leads}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
