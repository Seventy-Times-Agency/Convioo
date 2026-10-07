"use client";

import { useMemo, useState, type ReactNode } from "react";
import { Card } from "@/components/ui";
import type { TechInfo } from "@/lib/api";
import { useLocale } from "@/lib/i18n";
import { roleLabel } from "@/lib/roles";

/** Блоки технической сводки для вкладки «Техническое». Всё, что нужно
 * техотделу, чтобы связать Convioo со своим ядром: адреса и IP,
 * доступ к API, идентификаторы, вебхуки, сервисы, задачи, лимиты. */

function Copy({ value }: { value: string | null | undefined }) {
  const { t } = useLocale();
  const [done, setDone] = useState(false);
  if (!value) return null;
  return (
    <button
      type="button"
      className="btn btn-ghost btn-sm"
      style={{ padding: "2px 8px", fontSize: 11 }}
      onClick={() => {
        void navigator.clipboard?.writeText(value);
        setDone(true);
        setTimeout(() => setDone(false), 1200);
      }}
    >
      {done ? t("tel.copied") : t("tel.copy")}
    </button>
  );
}

function Row({ k, v, copy, mono }: { k: string; v: ReactNode; copy?: string | null; mono?: boolean }) {
  return (
    <div className="st-row tk-row">
      <span>{k}</span>
      <span className={mono ? "tk-mono" : undefined} style={{ display: "flex", gap: 6, alignItems: "center", minWidth: 0 }}>
        <span className="tk-val">{v ?? "—"}</span>
        {copy !== undefined && <Copy value={copy} />}
      </span>
    </div>
  );
}

function Head({ children, hint }: { children: ReactNode; hint?: ReactNode }) {
  return (
    <>
      <div className="eyebrow" style={{ marginBottom: hint ? 4 : 8 }}>{children}</div>
      {hint && <div style={{ fontSize: 12.5, color: "var(--text-dim)", marginBottom: 8, lineHeight: 1.5 }}>{hint}</div>}
    </>
  );
}

const Dot = ({ ok }: { ok: boolean | null | undefined }) => (
  <span className={"st-dot " + (ok ? "ok" : ok === false ? "bad" : "off")} />
);

export function TechPlatform({ d }: { d: TechInfo }) {
  const { t } = useLocale();
  const r = d.runtime;
  return (
    <Card>
      <Head>{t("tk.platform")}</Head>
      <Row k={t("tk.version")} v={`${r.commit}${r.branch ? ` · ${r.branch}` : ""}`} mono copy={r.commit} />
      <Row k={t("tk.hosting")} v={r.hosting} />
      <Row k={t("tk.env")} v={[r.environment, r.service, r.region].filter(Boolean).join(" · ") || "—"} />
      <Row k={t("tc.db")} v={<><Dot ok={r.db_ok} /> {r.db_dialect}{r.db_revision ? ` · миграция ${r.db_revision}` : ""}</>} />
      <Row
        k={t("tc.queue")}
        v={<><Dot ok={r.redis} /> {r.redis == null ? t("tk.noRedis") : r.redis ? t("tc.queueOk", { n: r.queue_depth ?? 0 }) : t("tc.down")}</>}
      />
      <Row k="Python" v={`${r.python} · ${r.platform}`} />
      <Row k={t("tk.started")} v={new Date(r.started_at).toLocaleString()} />
      {r.private_domain && <Row k={t("tk.privateDomain")} v={r.private_domain} mono copy={r.private_domain} />}
    </Card>
  );
}

export function TechNetwork({ d }: { d: TechInfo }) {
  const { t } = useLocale();
  const n = d.network;
  return (
    <Card>
      <Head hint={t("tk.networkHint")}>{t("tk.network")}</Head>
      <Row k={t("tk.appUrl")} v={n.app_url} mono copy={n.app_url} />
      <Row k={t("tk.apiViaApp")} v={n.api_via_app} mono copy={n.api_via_app} />
      <Row k={t("tk.apiDirect")} v={n.api_direct} mono copy={n.api_direct} />
      <Row k={t("tk.apiIps")} v={n.api_host_ips.join(", ") || "—"} mono copy={n.api_host_ips.join(", ")} />
      <Row k={t("tk.appIps")} v={n.app_host_ips.join(", ") || "—"} mono copy={n.app_host_ips.join(", ")} />
      <Row k={t("tk.egressIp")} v={n.egress_ip ?? "—"} mono copy={n.egress_ip} />
      <Row k={t("tk.yourIp")} v={n.your_ip ?? "—"} mono />
      <Row k="CORS" v={n.cors_origins.join(", ") || "—"} mono />
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 10 }}>
        {[
          ["Swagger", n.docs.swagger],
          ["OpenAPI", n.docs.openapi],
          ["Health", n.docs.health],
          ["Metrics", n.docs.metrics],
        ].map(([label, href]) => (
          <a key={label} href={href} target="_blank" rel="noreferrer" className="btn btn-ghost btn-sm">
            {label} ↗
          </a>
        ))}
      </div>
    </Card>
  );
}

export function TechAccess({ d }: { d: TechInfo }) {
  const { t } = useLocale();
  const a = d.auth;
  return (
    <Card>
      <Head hint={a.api_key_where}>{t("tk.access")}</Head>
      <Row k={t("tk.apiKeyHeader")} v={a.api_key_header} mono />
      <Row k={t("tk.cookie")} v={a.session_cookie} mono />
      <Row k="CSRF" v={a.csrf} />
      <Row k={t("tk.roles")} v={a.roles.join(" → ")} mono />
      <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 10, lineHeight: 1.5 }}>{t("tk.accessHint")}</div>
    </Card>
  );
}

export function TechIds({ d }: { d: TechInfo }) {
  const { t } = useLocale();
  const tm = d.team;
  return (
    <Card>
      <Head hint={t("tk.idsHint")}>{t("tk.ids")}</Head>
      <div className="tk-split">
        <div style={{ minWidth: 0 }}>
          <Row k={t("tk.teamId")} v={tm.id} mono copy={tm.id} />
          <Row k={t("tk.yourId")} v={String(tm.your_user_id)} mono copy={String(tm.your_user_id)} />
          <div className="eyebrow" style={{ fontSize: 10, margin: "14px 0 6px" }}>{t("tk.funnels")}</div>
          {tm.funnels.length === 0 && <div className="tk-empty">—</div>}
          {tm.funnels.map((f) => (
            <Row key={f.id} k={`${f.name} · ${f.status}`} v={f.id} mono copy={f.id} />
          ))}
          <div className="eyebrow" style={{ fontSize: 10, margin: "14px 0 6px" }}>{t("tk.statuses")}</div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {tm.lead_statuses.map((s) => (
              <span key={s.key} className="chip" style={{ fontSize: 11.5 }} title={s.label}>
                <span className="tk-mono">{s.key}</span>
                {s.terminal ? " · ⏹" : ""}
              </span>
            ))}
          </div>
        </div>
        <div className="tk-table-wrap">
          <table className="tk-table">
            <thead>
              <tr>
                <th>user_id</th>
                <th>{t("tk.member")}</th>
                <th>email</th>
                <th>{t("tk.role")}</th>
              </tr>
            </thead>
            <tbody>
              {tm.members.map((m) => (
                <tr key={m.user_id}>
                  <td className="tk-mono">{m.user_id}</td>
                  <td>{m.name ?? "—"}</td>
                  <td className="tk-mono">{m.email ?? "—"}</td>
                  <td>{roleLabel(t, m.role)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Card>
  );
}

export function TechInbound({ d }: { d: TechInfo }) {
  const { t } = useLocale();
  return (
    <Card>
      <Head hint={t("tk.inboundHint")}>{t("tk.inbound")}</Head>
      <div className="tk-table-wrap">
        <table className="tk-table">
          <thead>
            <tr>
              <th>{t("tk.what")}</th>
              <th>{t("tk.method")}</th>
              <th>URL</th>
              <th>{t("tk.authCol")}</th>
            </tr>
          </thead>
          <tbody>
            {d.inbound.map((e) => (
              <tr key={e.name}>
                <td>{e.name}</td>
                <td className="tk-mono">{e.method}</td>
                <td className="tk-mono tk-url">
                  {e.url ?? <span style={{ color: "var(--text-dim)" }}>{t("tk.notSet")}</span>} <Copy value={e.url} />
                </td>
                <td>{e.auth}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function TechOutbound({ d }: { d: TechInfo }) {
  const { t } = useLocale();
  const w = d.outbound_webhooks;
  return (
    <Card>
      <Head hint={t("tk.outboundHint")}>{t("tk.outbound")}</Head>
      <Row k={t("tk.events")} v={w.events.join(", ")} mono />
      <Row k={t("tk.signature")} v={w.signature} mono />
      <Row k={t("tk.signatureTs")} v={w.signature_timestamped} mono />
      <Row k={t("tk.timeout")} v={`${w.timeout_s} с · ${t("tk.disableAfter", { n: w.disable_after_failures })}`} />
      <Row k={t("tk.manage")} v={w.manage} mono copy={w.manage} />
      <Row k={t("tk.yourHooks")} v={w.yours.length ? w.yours.map((h) => `${h.active ? "●" : "○"} ${h.url}`).join("; ") : "—"} mono />
    </Card>
  );
}

export function TechIntegrations({ d }: { d: TechInfo }) {
  const { t } = useLocale();
  const on = d.integrations.filter((i) => i.configured).length;
  return (
    <Card>
      <Head hint={t("tk.integrationsHint", { on, all: d.integrations.length })}>{t("tk.integrations")}</Head>
      <div className="tk-table-wrap">
        <table className="tk-table">
          <thead>
            <tr>
              <th>{t("tk.service")}</th>
              <th>{t("tk.state")}</th>
              <th>{t("tk.purpose")}</th>
              <th>{t("tk.envVars")}</th>
            </tr>
          </thead>
          <tbody>
            {d.integrations.map((i) => (
              <tr key={i.key}>
                <td style={{ fontWeight: 700 }}>{i.name}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <Dot ok={i.configured ? true : null} /> {i.configured ? t("tk.on") : t("tk.off")}
                </td>
                <td>{i.purpose}</td>
                <td className="tk-mono" style={{ fontSize: 11 }}>{i.env.join(" ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function TechJobs({ d }: { d: TechInfo }) {
  const { t } = useLocale();
  return (
    <Card>
      <Head hint={t("tk.jobsHint")}>{t("tk.jobs")}</Head>
      {d.jobs.map((j, i) => (
        <div key={j.name} className={"st-row" + (i === 0 ? " first" : "")} style={{ alignItems: "flex-start" }}>
          <span style={{ minWidth: 0 }}>
            <span className="tk-mono" style={{ color: "var(--text)" }}>{j.name}</span>
            <span style={{ display: "block", fontSize: 11.5, color: "var(--text-dim)" }}>{j.purpose}</span>
          </span>
          <span style={{ fontSize: 12, whiteSpace: "nowrap" }}>{j.schedule}</span>
        </div>
      ))}
    </Card>
  );
}

export function TechLimits({ d }: { d: TechInfo }) {
  const { t } = useLocale();
  const { rate_limits, ...rest } = d.limits;
  return (
    <Card>
      <Head>{t("tk.limits")}</Head>
      {Object.entries(rest).map(([k, v]) => (
        <Row key={k} k={k} v={String(v)} mono />
      ))}
      <div className="eyebrow" style={{ fontSize: 10, margin: "14px 0 6px" }}>{t("tk.rateLimits")}</div>
      {Object.entries(rate_limits).map(([k, v]) => (
        <Row key={k} k={k} v={v} mono />
      ))}
      <div className="eyebrow" style={{ fontSize: 10, margin: "14px 0 6px" }}>{t("tk.flags")}</div>
      {Object.entries(d.flags).map(([k, v]) => (
        <Row key={k} k={k} v={v === null ? "—" : String(v)} mono />
      ))}
    </Card>
  );
}

export function TechApiCatalog({ d }: { d: TechInfo }) {
  const { t } = useLocale();
  const [q, setQ] = useState("");
  const groups = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const rows = needle
      ? d.api.filter((r) => `${r.method} ${r.path} ${r.summary} ${r.group}`.toLowerCase().includes(needle))
      : d.api;
    const map = new Map<string, typeof rows>();
    for (const r of rows) map.set(r.group, [...(map.get(r.group) ?? []), r]);
    return [...map.entries()];
  }, [d.api, q]);
  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <Head hint={t("tk.apiHint", { n: d.api.length })}>{t("tk.api")}</Head>
        <input
          className="input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("tk.apiSearch")}
          style={{ width: 260 }}
        />
      </div>
      <div className="tk-api">
        {groups.map(([group, rows]) => (
          <details key={group} open={!!q}>
            <summary>
              <b>{group}</b> <span style={{ color: "var(--text-dim)" }}>· {rows.length}</span>
            </summary>
            <div className="tk-table-wrap">
              <table className="tk-table">
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.method + r.path}>
                      <td className={"tk-mono tk-method m-" + r.method.toLowerCase()}>{r.method}</td>
                      <td className="tk-mono">{r.path}</td>
                      <td style={{ color: "var(--text-muted)" }}>{r.summary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        ))}
      </div>
    </Card>
  );
}

/** Сводка текстом — для вставки в документацию или тикет. */
export function techInfoAsText(d: TechInfo): string {
  const lines: string[] = [];
  const h = (s: string) => lines.push("", `## ${s}`);
  lines.push(`# Convioo — техническая сводка (${d.generated_at})`);
  h("Платформа");
  Object.entries(d.runtime).forEach(([k, v]) => lines.push(`- ${k}: ${v ?? "—"}`));
  h("Сеть и адреса");
  Object.entries(d.network).forEach(([k, v]) =>
    lines.push(`- ${k}: ${typeof v === "object" && v !== null ? JSON.stringify(v) : v ?? "—"}`),
  );
  h("Доступ к API");
  Object.entries(d.auth).forEach(([k, v]) => lines.push(`- ${k}: ${Array.isArray(v) ? v.join(", ") : v}`));
  h("Идентификаторы команды");
  lines.push(`- team_id: ${d.team.id}`, `- your_user_id: ${d.team.your_user_id}`);
  d.team.members.forEach((m) => lines.push(`- user ${m.user_id}: ${m.name ?? ""} <${m.email ?? ""}> — ${m.role}`));
  d.team.funnels.forEach((f) => lines.push(`- funnel ${f.id}: ${f.name} (${f.status})`));
  lines.push(`- статусы лида: ${d.team.lead_statuses.map((s) => s.key).join(", ")}`);
  h("Входящие адреса");
  d.inbound.forEach((e) => lines.push(`- ${e.name}: ${e.method} ${e.url ?? "не настроено"} (${e.auth})`));
  h("Исходящие вебхуки");
  lines.push(
    `- события: ${d.outbound_webhooks.events.join(", ")}`,
    `- подпись: ${d.outbound_webhooks.signature}`,
    `- подпись с меткой времени: ${d.outbound_webhooks.signature_timestamped}`,
  );
  h("Внешние сервисы");
  d.integrations.forEach((i) =>
    lines.push(`- ${i.name}: ${i.configured ? "настроено" : "не настроено"} — ${i.purpose} [${i.env.join(", ")}]`),
  );
  h("Фоновые задачи (UTC)");
  d.jobs.forEach((j) => lines.push(`- ${j.name}: ${j.schedule} — ${j.purpose}`));
  h("Лимиты и флаги");
  Object.entries(d.limits).forEach(([k, v]) => lines.push(`- ${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`));
  Object.entries(d.flags).forEach(([k, v]) => lines.push(`- ${k}: ${v}`));
  h("Каталог API");
  d.api.forEach((r) => lines.push(`- ${r.method} ${r.path} — ${r.summary}`));
  return lines.join("\n");
}
