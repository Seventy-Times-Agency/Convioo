"use client";

import { Icon } from "@/components/Icon";
import { Card, EmptyState } from "@/components/ui";
import { useLocale } from "@/lib/i18n";

/** Телефония — вкладка зарезервирована под OpenPhone-подключение. */
export default function SettingsTelephonyPage() {
  const { t } = useLocale();
  return (
    <Card>
      <EmptyState
        icon={<Icon name="phone" size={20} />}
        title={t("tel.soonTitle")}
        hint={t("tel.soonBody")}
      />
    </Card>
  );
}
