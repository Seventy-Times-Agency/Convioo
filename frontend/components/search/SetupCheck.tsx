"use client";

import { useEffect, useRef, useState } from "react";
import { Modal } from "@/components/ui";
import {
  checkSearchSetup,
  type SetupCheckBody,
  type SetupCheckItem,
  type SetupCheckResult,
  type SetupCityResult,
  type SetupFix,
  type SetupLevel,
} from "@/lib/api";
import { useLocale, type TranslationKey } from "@/lib/i18n";

/** Светофор хотя бы столько крутится, даже если ответ пришёл мгновенно. */
const MIN_SPIN_MS = 1600;

type Params = Record<string, number | string | boolean | null | undefined>;

/** «Проверить» в строке запуска: светофор → вердикт → «Подробнее». */
export function SetupCheck({ body, disabled }: { body: SetupCheckBody; disabled?: boolean }) {
  const { t } = useLocale();
  const [state, setState] = useState<"idle" | "checking" | "done" | "error">("idle");
  const [result, setResult] = useState<SetupCheckResult | null>(null);
  const [checkedKey, setCheckedKey] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const runId = useRef(0);
  const key = JSON.stringify(body);
  const stale = state === "done" && checkedKey !== key;

  // Новая ниша — старый вердикт ни к чему.
  useEffect(() => {
    setState("idle");
    setResult(null);
  }, [body.niche]);

  const run = async () => {
    const id = ++runId.current;
    setState("checking");
    setOpen(false);
    const started = Date.now();
    try {
      const res = await checkSearchSetup(body);
      await new Promise((r) => setTimeout(r, Math.max(0, MIN_SPIN_MS - (Date.now() - started))));
      if (id !== runId.current) return;
      setResult(res);
      setCheckedKey(key);
      setState("done");
    } catch {
      if (id === runId.current) setState("error");
    }
  };

  const level = state === "done" && result ? result.level : null;
  const tt = (k: string, params?: Params) => t(k as TranslationKey, params as Record<string, string | number>);

  return (
    <>
      <button
        type="button"
        className="btn btn-ghost"
        onClick={() => void run()}
        disabled={disabled || state === "checking"}
        style={{ padding: "9px 14px", fontSize: 13.5, gap: 8 }}
      >
        <TrafficLight state={state === "checking" ? "spin" : level ?? "off"} dim={stale} />
        {state === "checking" ? t("sc.checking") : state === "done" ? t("sc.again") : t("sc.check")}
      </button>
      {state === "done" && result && (
        <div className={"sc-verdict anim-pop" + (stale ? " stale" : "")} aria-live="polite">
          <div className={"sc-verdict-title " + result.level}>
            {t(`sc.level.${result.level}` as TranslationKey)}
            <span className="sc-score">{result.score}/100</span>
          </div>
          <div className="sc-verdict-line">
            {stale ? t("sc.stale") : tt(`sc.h.${result.headline.key}`, result.headline.params)}
          </div>
        </div>
      )}
      {state === "done" && result && (
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOpen(true)}>
          {t("sc.more")}
        </button>
      )}
      {state === "error" && <span style={{ fontSize: 12.5, color: "var(--cold)" }}>{t("sc.failed")}</span>}
      {result && (
        <Modal open={open} onClose={() => setOpen(false)} title={t("sc.why")} width={560}>
          <SetupReport result={result} />
        </Modal>
      )}
    </>
  );
}

/** Три лампы: крутятся, пока идёт проверка, потом горит одна. */
function TrafficLight({ state, dim }: { state: "off" | "spin" | Exclude<SetupLevel, "unknown">; dim?: boolean }) {
  const lit = (lamp: "bad" | "fair" | "good") => (state === lamp ? " on" : "");
  return (
    <span className={"sc-tl" + (state === "spin" ? " spin" : "") + (dim ? " dim" : "")} aria-hidden="true">
      <i className={"r" + lit("bad")} />
      <i className={"y" + lit("fair")} />
      <i className={"g" + lit("good")} />
    </span>
  );
}

function SetupReport({ result }: { result: SetupCheckResult }) {
  const { t } = useLocale();
  const tt = (k: string, params?: Params) => t(k as TranslationKey, params as Record<string, string | number>);
  const tot = result.totals;
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div className={"sc-ring " + result.level} style={{ ["--p" as string]: `${result.score}%` }}>
          <span>{result.score}</span>
        </div>
        <div style={{ minWidth: 0 }}>
          <div className={"sc-verdict-title " + result.level} style={{ fontSize: 16 }}>
            {t(`sc.level.${result.level}` as TranslationKey)}
          </div>
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            {tt(`sc.h.${result.headline.key}`, result.headline.params)}
          </div>
        </div>
      </div>

      <section>
        <div className="eyebrow" style={{ marginBottom: 6 }}>{t("sc.cities")}</div>
        <div style={{ display: "grid", gap: 8 }}>
          {result.cities.map((c) => <CityRow key={c.region} c={c} />)}
        </div>
        {!result.scouted && <div className="sc-note">{t("sc.noScout")}</div>}
      </section>

      <section>
        <div className="eyebrow" style={{ marginBottom: 6 }}>{t("sc.checks")}</div>
        {result.checks.filter((c) => c.key !== "cost").map((c, i) => <CheckRow key={c.key} c={c} first={i === 0} />)}
      </section>

      <section className="sc-totals">
        <div>
          <div className="eyebrow">{t("sc.get")}</div>
          <div className="v">~{tot.expected} <span>/ {tot.requested}</span></div>
          <div className="h">
            {[
              tot.hot != null ? t("sc.hot", { n: tot.hot }) : null,
              tot.dm ? t("sc.dm", { n: tot.dm }) : null,
            ].filter(Boolean).join(" · ") || " "}
          </div>
        </div>
        <div>
          <div className="eyebrow">{t("sc.pay")}</div>
          <div className="v">{t("sc.tokens", { n: tot.tokens_max })}</div>
          <div className="h">{t("sc.usd", { usd: tot.cost_usd.toFixed(2), burned: tot.burned_usd.toFixed(2) })}</div>
        </div>
      </section>
    </div>
  );
}

function Lamp({ level }: { level: SetupLevel }) {
  return <i className={"sc-lamp " + level} aria-hidden="true" />;
}

function FixLine({ fixes }: { fixes?: SetupFix[] }) {
  const { t } = useLocale();
  if (!fixes?.length) return null;
  return (
    <div className="sc-fix">
      {fixes.map((f) => t(`sc.fix.${f.kind}` as TranslationKey, { value: f.value })).join(" · ")}
    </div>
  );
}

function CityRow({ c }: { c: SetupCityResult }) {
  const { t } = useLocale();
  const known = (c.fresh ?? 0) + (c.already ?? 0);
  return (
    <div className="sc-city">
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Lamp level={c.level} />
        <b>{c.region}</b>
        {c.expected != null && (
          <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)" }}>
            {t("sc.expected", { n: c.expected })}
          </span>
        )}
      </div>
      {c.scouted && known > 0 && (
        <div className="sc-supply" role="img" aria-label={t("sc.supply", { fresh: c.fresh ?? 0, already: c.already ?? 0 })}>
          <i style={{ width: `${((c.fresh ?? 0) / known) * 100}%`, background: "var(--accent)" }} />
          <i style={{ width: `${((c.already ?? 0) / known) * 100}%`, background: "var(--border-strong)" }} />
        </div>
      )}
      <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
        {c.scouted
          ? t("sc.supply", { fresh: c.fresh ?? 0, already: c.already ?? 0 })
          : c.exhausted
            ? t("sc.cityExhausted")
            : c.expected != null
              ? t("sc.fromMemory", { n: c.expected })
              : t("sc.supplyUnknown")}
        {" · "}
        {t("sc.covered", { covered: c.covered, total: c.total })}
      </div>
      <FixLine fixes={c.fixes} />
    </div>
  );
}

function CheckRow({ c, first }: { c: SetupCheckItem; first: boolean }) {
  const { t } = useLocale();
  return (
    <div className={"st-row" + (first ? " first" : "")} style={{ alignItems: "flex-start", justifyContent: "flex-start", gap: 10 }}>
      <span style={{ paddingTop: 4 }}><Lamp level={c.level} /></span>
      <span style={{ color: "var(--text)", flex: 1 }}>
        {t(`sc.c.${c.key}` as TranslationKey, c.params as Record<string, string | number>)}
        <FixLine fixes={c.fixes} />
      </span>
    </div>
  );
}
