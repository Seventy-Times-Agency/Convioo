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
import { useLocale } from "@/lib/i18n";
import { showError } from "@/lib/toast";
import { confirmAsync } from "@/lib/confirm";

/**
 * Per-user affiliate dashboard. Lists owned codes, lets the user
 * create / rename / deactivate them, and shows attribution counts.
 * Revenue-share automation lights up when Stripe is wired (Phase 7).
 */
export default function AffiliatePage() {
  const { t } = useLocale();
  const [overview, setOverview] = useState<AffiliateOverview | null>(null);
  const [busy, setBusy] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [draftSlug, setDraftSlug] = useState("");

  const refresh = async () => {
    try {
      const o = await getAffiliateOverview();
      setOverview(o);
    } catch (e) {
      showError(e instanceof ApiError ? e.message : String(e));
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      await createAffiliateCode({
        code: draftSlug.trim() || null,
        name: draftName.trim() || null,
      });
      setDraftSlug("");
      setDraftName("");
      await refresh();
    } catch (e) {
      showError(e instanceof ApiError ? e.message : String(e));
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
    if (!(await confirmAsync(t("affiliate.confirmDelete", { code: code.code })))) return;
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
        title={t("affiliate.title")}
        subtitle={t("affiliate.subtitle")}
      />
      <div className="page" style={{ maxWidth: 820 }}>
        <div className="card" style={{ padding: 24, marginBottom: 14 }}>
          <div className="eyebrow" style={{ marginBottom: 14 }}>
            {t("affiliate.summary")}
          </div>
          <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
            <Stat label={t("affiliate.stat.totalReferrals")} value={overview?.total_referrals ?? 0} />
            <Stat label={t("affiliate.stat.paid")} value={overview?.total_paid_referrals ?? 0} />
            <Stat label={t("affiliate.stat.activeCodes")} value={overview?.codes.filter((c) => c.active).length ?? 0} />
          </div>
        </div>

        <div className="card" style={{ padding: 24, marginBottom: 14 }}>
          <div className="eyebrow" style={{ marginBottom: 14 }}>
            {t("affiliate.createNew")}
          </div>
          <form onSubmit={create} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <input
              className="input"
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
              placeholder={t("affiliate.namePh")}
            />
            <input
              className="input"
              value={draftSlug}
              onChange={(e) => setDraftSlug(e.target.value)}
              placeholder={t("affiliate.slugPh")}
              style={{ fontFamily: "var(--font-mono)" }}
            />
            <button type="submit" className="btn btn-sm" disabled={busy}>
              {busy ? t("common.creating") : t("affiliate.createCode")}
            </button>
          </form>
        </div>

        <div className="card" style={{ padding: 24 }}>
          <div className="eyebrow" style={{ marginBottom: 14 }}>
            {t("affiliate.myCodes")}
          </div>
          {overview === null ? (
            <div style={{ fontSize: 13, color: "var(--text-muted)" }}>{t("common.loading")}</div>
          ) : overview.codes.length === 0 ? (
            <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
              {t("affiliate.empty")}
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
                          {t("common.copy")}
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          disabled={busy}
                          onClick={() => void toggleActive(code)}
                        >
                          {code.active ? t("common.disable") : t("common.enable")}
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          disabled={busy}
                          onClick={() => void remove(code)}
                          style={{ color: "var(--cold)" }}
                        >
                          {t("common.delete")}
                        </button>
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 16, fontSize: 12, color: "var(--text-muted)" }}>
                      <span>{t("affiliate.code.referrals")}: <b>{code.referrals_count}</b></span>
                      <span>{t("affiliate.code.paid")}: <b>{code.paid_referrals_count}</b></span>
                      <span>{t("affiliate.code.share")}: <b>{code.percent_share}%</b></span>
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
