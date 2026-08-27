"use client";

import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import { Card, EmptyState } from "@/components/ui";
import { useLocale } from "@/lib/i18n";

/** Работа — рабочее место селза (режим прозвона). Полный конвейер
 * очередь → карточка → исход строится задачей волны 1.5; этот экран
 * держит маршрут и учит, что здесь появится. */
export default function WorkPage() {
  const { t } = useLocale();
  return (
    <>
      <Topbar crumbs={[{ label: t("nav.work") }]} />
      <div className="page">
        <Card>
          <EmptyState
            icon={<Icon name="zap" size={20} />}
            title={t("work.emptyTitle")}
            hint={t("work.emptyHint")}
          />
        </Card>
      </div>
    </>
  );
}
