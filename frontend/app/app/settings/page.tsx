"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui";
import { BrandingSection } from "@/components/settings/BrandingSection";
import { ICPSection } from "@/components/settings/ICPSection";
import { getTeamDetail, updateTeam } from "@/lib/api";
import { useActiveTeam } from "@/lib/hooks/useActiveTeam";
import { useLocale } from "@/lib/i18n";
import { showError, showSuccess } from "@/lib/toast";

/** Компания: кто мы (это читает ИИ при оценке и в письмах), портрет
 * клиента и брендинг отчётов. Личное — в профиле. */
export default function SettingsCompanyPage() {
  return (
    <div className="st-grid-2" style={{ gridTemplateColumns: "1.6fr 1fr" }}>
      <AboutCompany />
      <div className="st-col">
        <ICPSection />
        <BrandingSection />
      </div>
    </div>
  );
}

function AboutCompany() {
  const { t } = useLocale();
  const { teamId, role } = useActiveTeam();
  const [text, setText] = useState("");
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(false);
  const canEdit = role === "owner" || role === "admin";

  useEffect(() => {
    if (!teamId) return;
    getTeamDetail(teamId)
      .then((d) => {
        setText(d.description ?? "");
        setSaved(d.description ?? "");
      })
      .catch(() => undefined);
  }, [teamId]);

  if (!teamId) return null;

  const save = async () => {
    setBusy(true);
    try {
      await updateTeam(teamId, { description: text.trim() || null });
      setSaved(text);
      showSuccess(t("common.saved"));
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div className="eyebrow">{t("cp.aboutTitle")}</div>
      <div style={{ fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.5 }}>{t("cp.aboutHint")}</div>
      <textarea
        className="textarea"
        rows={12}
        maxLength={4000}
        value={text}
        disabled={!canEdit}
        onChange={(e) => setText(e.target.value)}
        placeholder={t("team.descriptionPh")}
        style={{ fontSize: 13, lineHeight: 1.6, flex: 1, minHeight: 280, resize: "none" }}
      />
      {canEdit && (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button type="button" className="btn btn-sm" disabled={busy || text === saved} onClick={() => void save()}>
            {busy ? t("common.saving") : t("common.save")}
          </button>
          <span style={{ fontSize: 12, color: "var(--text-dim)" }}>{t("cp.chars", { n: text.length })}</span>
        </div>
      )}
    </Card>
  );
}
