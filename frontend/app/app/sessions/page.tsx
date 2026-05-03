"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import { SessionRow } from "@/components/app/SessionRow";
import { EmptyState } from "@/components/app/EmptyState";
import {
  type SavedSearchRow,
  type SavedSearchSchedule,
  type SearchSummary,
  deleteSavedSearch,
  getSearches,
  listSavedSearches,
  runSavedSearchNow,
  updateSavedSearch,
} from "@/lib/api";
import {
  activeMemberUserId,
  activeTeamId,
  subscribeWorkspace,
} from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";

type Tab = "history" | "schedule";

export default function SessionsListPage() {
  const { t } = useLocale();
  const [tab, setTab] = useState<Tab>("history");
  const [sessions, setSessions] = useState<SearchSummary[] | null>(null);
  const [saved, setSaved] = useState<SavedSearchRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => subscribeWorkspace(() => setTick((n) => n + 1)), []);

  useEffect(() => {
    let cancelled = false;
    getSearches({ teamId: activeTeamId(), memberUserId: activeMemberUserId() })
      .then((rows) => !cancelled && setSessions(rows))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    listSavedSearches()
      .then((r) => !cancelled && setSaved(r.items))
      .catch(() => {
        if (!cancelled) setSaved([]);
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  const refreshSaved = () => {
    listSavedSearches().then((r) => setSaved(r.items)).catch(() => {});
  };

  return (
    <>
      <Topbar
        title={t("sessions.title")}
        subtitle={t("sessions.subtitle")}
        right={
          <Link href="/app/search" className="btn">
            <Icon name="plus" size={14} />
            {t("common.newSearch")}
          </Link>
        }
      />
      <div className="page">
        <div
          style={{
            display: "flex",
            gap: 6,
            marginBottom: 16,
            borderBottom: "1px solid var(--border)",
          }}
        >
          {[
            { id: "history" as Tab, label: "История" },
            { id: "schedule" as Tab, label: "Расписание" },
          ].map((opt) => {
            const active = tab === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => setTab(opt.id)}
                style={{
                  padding: "8px 14px",
                  fontSize: 13,
                  fontWeight: active ? 700 : 500,
                  color: active ? "var(--accent)" : "var(--text-muted)",
                  background: "none",
                  border: "none",
                  borderBottom: active
                    ? "2px solid var(--accent)"
                    : "2px solid transparent",
                  cursor: "pointer",
                  marginBottom: -1,
                }}
              >
                {opt.label}
                {opt.id === "schedule" && saved && saved.length > 0 && (
                  <span
                    style={{
                      marginLeft: 6,
                      fontSize: 11,
                      color: "var(--text-dim)",
                    }}
                  >
                    {saved.length}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {error && (
          <div
            className="card"
            style={{
              padding: 14,
              color: "var(--cold)",
              borderColor: "var(--cold)",
              marginBottom: 16,
            }}
          >
            {error}
          </div>
        )}

        {tab === "history" && (
          <>
            {sessions && sessions.length === 0 && !error && (
              <EmptyState
                icon="folder"
                title={t("sessions.empty.title")}
                body={t("sessions.empty.body")}
                actions={[
                  {
                    label: "Запустить первый поиск",
                    href: "/app/search",
                    variant: "primary",
                  },
                ]}
              />
            )}
            {sessions && sessions.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {sessions.map((s) => (
                  <SessionRow key={s.id} session={s} />
                ))}
              </div>
            )}
          </>
        )}

        {tab === "schedule" && (
          <ScheduleTab
            rows={saved}
            onChange={refreshSaved}
          />
        )}
      </div>
    </>
  );
}

function ScheduleTab({
  rows,
  onChange,
}: {
  rows: SavedSearchRow[] | null;
  onChange: () => void;
}) {
  const [busyId, setBusyId] = useState<string | null>(null);

  if (rows === null) {
    return (
      <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Загрузка…</div>
    );
  }
  if (rows.length === 0) {
    return (
      <div
        className="card"
        style={{
          padding: 32,
          textAlign: "center",
          color: "var(--text-muted)",
        }}
      >
        <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text)" }}>
          Нет сохранённых поисков
        </div>
        <div style={{ fontSize: 13, marginTop: 6 }}>
          Запустите поиск и нажмите «Сохранить» рядом с результатами,
          чтобы добавить его сюда.
        </div>
      </div>
    );
  }

  const fmt = (d: string | null) =>
    d ? new Date(d).toLocaleString() : "—";

  const handleScheduleChange = async (
    id: string,
    schedule: SavedSearchSchedule,
  ) => {
    setBusyId(id);
    try {
      await updateSavedSearch(id, { schedule });
      onChange();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const handleRun = async (id: string) => {
    setBusyId(id);
    try {
      await runSavedSearchNow(id);
      alert("Запуск отправлен. Прогресс смотрите во вкладке «История».");
      onChange();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Удалить сохранённый поиск?")) return;
    setBusyId(id);
    try {
      await deleteSavedSearch(id);
      onChange();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {rows.map((row) => (
        <div
          key={row.id}
          className="card"
          style={{
            padding: "16px 18px",
            display: "flex",
            alignItems: "center",
            gap: 16,
            flexWrap: "wrap",
          }}
        >
          <div style={{ flex: 1, minWidth: 220 }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
              {row.name}
            </div>
            <div
              style={{
                fontSize: 12.5,
                color: "var(--text-muted)",
                lineHeight: 1.5,
              }}
            >
              {row.niche} · {row.region} · {row.scope}
              {row.last_run_at && (
                <>
                  {" · "}последний запуск {fmt(row.last_run_at)}
                </>
              )}
              {row.next_run_at && (
                <>
                  {" · "}следующий {fmt(row.next_run_at)}
                </>
              )}
            </div>
          </div>

          <select
            className="input"
            value={row.schedule ?? "off"}
            onChange={(e) =>
              handleScheduleChange(
                row.id,
                e.target.value as SavedSearchSchedule,
              )
            }
            disabled={busyId === row.id}
            style={{ width: 140, fontSize: 13 }}
          >
            <option value="off">Вручную</option>
            <option value="daily">Ежедневно</option>
            <option value="weekly">Еженедельно</option>
            <option value="biweekly">Раз в 2 недели</option>
            <option value="monthly">Ежемесячно</option>
          </select>

          <button
            type="button"
            className="btn btn-sm"
            onClick={() => void handleRun(row.id)}
            disabled={busyId === row.id}
          >
            <Icon name="zap" size={12} />
            Запустить
          </button>

          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => void handleDelete(row.id)}
            disabled={busyId === row.id}
            style={{ color: "var(--cold)" }}
          >
            <Icon name="x" size={12} />
          </button>
        </div>
      ))}
    </div>
  );
}
