"use client";

import { useEffect, useState } from "react";
import { getCostPrices, setCostPrice, type CostPriceRow } from "@/lib/api";
import { useLocale, type TranslationKey } from "@/lib/i18n";
import { showError, showSuccess } from "@/lib/toast";
import { useServiceLabel } from "./CostsPanel";

const SERVICE_RE = /^[a-z0-9_]{2,48}$/;

/** Мелкие цены (токены, секунды, письма) показываем и вводим в
 * привычных единицах — за 1M токенов, за час, за 1000 писем. */
function unitOf(service: string): { scale: number; key: TranslationKey } {
  if (service.startsWith("claude_")) return { scale: 1_000_000, key: "cp.u.mtok" };
  if (service.endsWith("_seconds")) return { scale: 3600, key: "cp.u.hour" };
  if (service === "resend_email") return { scale: 1000, key: "cp.u.k" };
  return { scale: 1, key: "cp.u.one" };
}

const clean = (n: number) => String(Number(n.toPrecision(6)));
const price = (n: number | null | undefined, scale: number) => (n == null ? "—" : `$${clean(n * scale)}`);

/** Админка платформы: цены сервисов, по которым журнал трат считает
 * деньги. Правка перекрывает цену из кода и из переменной окружения. */
export function CostPricesCard() {
  const { t } = useLocale();
  const svc = useServiceLabel();
  const [rows, setRows] = useState<CostPriceRow[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [newName, setNewName] = useState("");
  const [newPrice, setNewPrice] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getCostPrices().then(setRows).catch(() => setRows([]));
  }, []);

  const save = async (service: string, value: number | null) => {
    setBusy(true);
    try {
      setRows(await setCostPrice(service, value));
      setDrafts((d) => {
        const next = { ...d };
        delete next[service];
        return next;
      });
      showSuccess(t("common.saved"));
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const parse = (raw: string) => {
    const n = Number(raw.replace(",", "."));
    return raw.trim() !== "" && Number.isFinite(n) && n >= 0 ? n : null;
  };

  const addNew = async () => {
    const name = newName.trim();
    if (!SERVICE_RE.test(name)) {
      showError(t("cp.badName"));
      return;
    }
    const n = parse(newPrice);
    if (n == null) return;
    await save(name, n / unitOf(name).scale);
    setNewName("");
    setNewPrice("");
  };

  return (
    <div className="card" style={{ padding: 18, marginTop: 12 }}>
      <div className="eyebrow" style={{ marginBottom: 4 }}>{t("cp.title")}</div>
      <div style={{ fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.5, marginBottom: 12 }}>{t("cp.hint")}</div>
      {!rows ? (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>{t("common.loading")}</div>
      ) : (
        <div className="ec-table-wrap">
          <table className="ec-table" style={{ minWidth: 640 }}>
            <thead>
              <tr>
                <th>{t("cp.service")}</th>
                <th className="r">{t("cp.default")}</th>
                <th className="r">{t("cp.current")}</th>
                <th>{t("cp.price")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const { scale, key } = unitOf(r.service);
                const draft = drafts[r.service];
                const draftUsd = draft !== undefined && parse(draft) !== null ? parse(draft)! / scale : null;
                const changed = draftUsd !== null && Math.abs(draftUsd - r.effective_usd) > 1e-12;
                return (
                  <tr key={r.service}>
                    <td>
                      <div style={{ fontWeight: 700 }}>{svc(r.service)}</div>
                      <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-dim)" }}>
                        {r.service}
                        {r.env_usd != null && r.override_usd == null ? ` · ${t("cp.fromEnv")}` : ""}
                      </div>
                    </td>
                    <td className="n r" style={{ color: "var(--text-dim)" }}>{price(r.default_usd, scale)}</td>
                    <td className="n r" style={{ color: r.override_usd != null ? "var(--accent)" : undefined, fontWeight: 700 }}>{price(r.effective_usd, scale)}</td>
                    <td>
                      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                        <input
                          className="input"
                          inputMode="decimal"
                          aria-label={`${svc(r.service)} — ${t(key)}`}
                          value={draft ?? clean((r.override_usd ?? r.effective_usd) * scale)}
                          onChange={(e) => setDrafts((d) => ({ ...d, [r.service]: e.target.value }))}
                          style={{ width: 110, height: 30, fontFamily: "var(--font-mono)", fontSize: 12 }}
                        />
                        <span style={{ fontSize: 11.5, color: "var(--text-dim)", whiteSpace: "nowrap" }}>{t(key)}</span>
                        {changed && (
                          <button type="button" className="btn btn-sm" disabled={busy} onClick={() => void save(r.service, draftUsd)}>
                            {t("common.save")}
                          </button>
                        )}
                        {r.override_usd != null && !changed && (
                          <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={() => void save(r.service, null)}>
                            {t("cp.reset")}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap", alignItems: "center" }}>
        <input className="input" value={newName} onChange={(e) => setNewName(e.target.value.toLowerCase())} placeholder={t("cp.newService")} aria-label={t("cp.service")} style={{ width: 200, height: 32, fontFamily: "var(--font-mono)", fontSize: 12 }} />
        <input className="input" value={newPrice} onChange={(e) => setNewPrice(e.target.value)} placeholder="0.01" inputMode="decimal" aria-label={t("cp.perUnit")} style={{ width: 110, height: 32, fontFamily: "var(--font-mono)", fontSize: 12 }} />
        <button type="button" className="btn btn-ghost btn-sm" disabled={busy || !newName || parse(newPrice) == null} onClick={() => void addNew()}>
          {t("cp.add")}
        </button>
      </div>
    </div>
  );
}
