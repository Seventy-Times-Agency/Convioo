"use client";

import { useEffect, useState } from "react";

import { Topbar } from "@/components/layout/Topbar";
import {
  ApiError,
  type AffiliateCode,
  type AffiliateOverview,
  createAffiliateCode,
  deleteAffiliateCode,
  getAffiliateOverview,
  updateAffiliateCode,
} from "@/lib/api";

/**
 * Per-user affiliate dashboard. Lists owned codes, lets the user
 * create / rename / deactivate them, and shows attribution counts.
 * Revenue-share automation lights up when Stripe is wired (Phase 7).
 */
export default function AffiliatePage() {
  const [overview, setOverview] = useState<AffiliateOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [draftSlug, setDraftSlug] = useState("");

  const refresh = async () => {
    try {
      const o = await getAffiliateOverview();
      setOverview(o);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createAffiliateCode({
        code: draftSlug.trim() || null,
        name: draftName.trim() || null,
      });
      setDraftSlug("");
      setDraftName("");
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const toggleActive = async (code: AffiliateCode) => {
    setBusy(true);
    try {
      await updateAffiliateCode(code.code, { active: !code.active });
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const remove = async (code: AffiliateCode) => {
    if (!confirm(`Удалить код "${code.code}"? Атрибуция уже привязанных рефералов сохранится.`)) return;
    setBusy(true);
    try {
      await deleteAffiliateCode(code.code);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const origin =
    typeof window !== "undefined" ? window.location.origin : "https://convioo.com";

  return (
    <>
      <Topbar
        title="Affiliate"
        subtitle="Делись ссылкой → получай долю с каждой подписки приглашённого"
      />
      <div className="page" style={{ maxWidth: 820 }}>
        <div className="card" style={{ padding: 24, marginBottom: 14 }}>
          <div className="eyebrow" style={{ marginBottom: 14 }}>
            Сводка
          </div>
          <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
            <Stat label="Всего рефералов" value={overview?.total_referrals ?? 0} />
            <Stat label="Платящих" value={overview?.total_paid_referrals ?? 0} />
            <Stat label="Активных кодов" value={overview?.codes.filter((c) => c.active).length ?? 0} />
          </div>
        </div>

        <div className="card" style={{ padding: 24, marginBottom: 14 }}>
          <div className="eyebrow" style={{ marginBottom: 14 }}>
            Создать новый код
          </div>
          <form onSubmit={create} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <input
              className="input"
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
              placeholder="Название (для тебя — например Twitter Q1)"
            />
            <input
              className="input"
              value={draftSlug}
              onChange={(e) => setDraftSlug(e.target.value)}
              placeholder="Слаг (опционально, иначе сгенерируем)"
              style={{ fontFamily: "var(--font-mono)" }}
            />
            {error && <div style={{ fontSize: 13, color: "var(--cold)" }}>{error}</div>}
            <button type="submit" className="btn btn-sm" disabled={busy}>
              {busy ? "Создаём…" : "Создать код"}
            </button>
          </form>
        </div>

        <div className="card" style={{ padding: 24 }}>
          <div className="eyebrow" style={{ marginBottom: 14 }}>
            Мои коды
          </div>
          {overview === null ? (
            <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Загрузка…</div>
          ) : overview.codes.length === 0 ? (
            <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
              Пока ни одного кода. Создай первый выше.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {overview.codes.map((code) => {
                const url = `${origin}/r/${code.code}`;
                return (
                  <div
                    key={code.code}
                    style={{
                      border: "1px solid var(--border)",
                      borderRadius: 10,
                      padding: 14,
                      display: "flex",
                      flexDirection: "column",
                      gap: 8,
                      opacity: code.active ? 1 : 0.55,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                      <div>
                        <div style={{ fontSize: 14, fontWeight: 600 }}>
                          {code.name ?? code.code}
                        </div>
                        <div
                          style={{
                            fontSize: 11.5,
                            color: "var(--text-muted)",
                            fontFamily: "var(--font-mono)",
                            marginTop: 2,
                          }}
                        >
                          {url}
                        </div>
                      </div>
                      <div style={{ display: "flex", gap: 6, alignItems: "flex-start" }}>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          disabled={busy}
                          onClick={() => {
                            void navigator.clipboard?.writeText(url);
                          }}
                        >
                          Копировать
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          disabled={busy}
                          onClick={() => void toggleActive(code)}
                        >
                          {code.active ? "Отключить" : "Включить"}
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          disabled={busy}
                          onClick={() => void remove(code)}
                          style={{ color: "var(--cold)" }}
                        >
                          Удалить
                        </button>
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 16, fontSize: 12, color: "var(--text-muted)" }}>
                      <span>Рефералов: <b>{code.referrals_count}</b></span>
                      <span>Платящих: <b>{code.paid_referrals_count}</b></span>
                      <span>Доля: <b>{code.percent_share}%</b></span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="eyebrow" style={{ fontSize: 10 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, lineHeight: 1.1 }}>{value}</div>
    </div>
  );
}
