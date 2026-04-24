"use client";

import Link from "next/link";
import { AuthShell } from "@/components/AuthShell";
import { Icon } from "@/components/Icon";
import { useLocale } from "@/lib/i18n";

export default function RegisterPage() {
  const { t } = useLocale();
  return (
    <AuthShell title={t("auth.register.title")}>
      <div style={{ color: "var(--text-muted)", marginBottom: 28, fontSize: 15 }}>
        {t("auth.register.subtitle")}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <Link
          href="/app"
          className="btn btn-lg"
          style={{ justifyContent: "center" }}
        >
          {t("auth.register.enter")} <Icon name="arrow" size={15} />
        </Link>
        <Link
          href="/"
          className="btn btn-ghost btn-lg"
          style={{ justifyContent: "center" }}
        >
          {t("auth.login.back")}
        </Link>
      </div>
    </AuthShell>
  );
}
