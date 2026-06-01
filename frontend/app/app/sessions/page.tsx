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
  archiveSearch,
  deleteSavedSearch,
  deleteSearch,
  getSearches,
  listSavedSearches,
  restoreSearch,
  runSavedSearchNow,
  updateSavedSearch,
} from "@/lib/api";
import {
  activeMemberUserId,
  activeTeamId,
  subscribeWorkspace,
} from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";
import { showError, showSuccess } from "@/lib/toast";
import { confirmAsync } from "@/lib/confirm";

type Tab = "history" | "schedule" | "archive";

export default function SessionsListPage() {
  const { t } = useLocale();
  const [tab, setTab] = useState<Tab>("history");
  const [sessions, setSessions] = useState<SearchSummary[] | null>(null);
  const [archived, setArchived] = useState<SearchSummary[] | null>(null);
  const [saved, setSaved] = useState<SavedSearchRow[] | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => subscribeWorkspace(() => setTick((n) => n + 1)), []);

  useEffect(() => {
    let cancelled = false;
    getSearches({ teamId: activeTeamId(), memberUserId: activeMemberUserId() })
      .then((rows) => !cancelled && setSessions(rows))
      .catch((e) => !cancelled && showError(e instanceof Error ? e.message : String(e)));
    getSearches({
      teamId: activeTeamId(),
      memberUserId: activeMemberUserId(),
      archived: true,
    })
      .then((rows) => !cancelled && setArchived(rows))
      .catch(() => {
        if (!cancelled) setArchived([]);
      });
    listSavedSearches()
      .then((r) => !cancelled && setSaved(r.items))
      .catch(() => {
        if (!cancelled) setSaved([]);
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  const handleArchive = async (id: string) => {
    if (!(await confirmAsync(t("session.confirm.archive")))) return;
    try {
      await archiveSearch(id);
      setTick((n) => n + 1);
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleRestore = async (id: string) => {
    try {
      await restoreSearch(id);
      setTick((n) => n + 1);
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleDelete = async (id: string) => {
    if (!(await confirmAsync(t("session.confirm.delete")))) return;
    try {
      await deleteSearch(id);
      setTick((n) => n + 1);
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    }
  };

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
            { id: "history" as Tab, label: t("sessions.tab.history") },
            { id: "archive" as Tab, label: t("sessions.tab.archive") },
            { id: "schedule" as Tab, label: t("sessions.tab.schedule") },
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

        {tab === "history" && (
          <>
            {sessions && sessions.length === 0 && (
              <EmptyState
                icon="search"
                title={t("sessions.empty.title")}
                body={t("sessions.history.empty.body")}
                actions={[
                  {
                    label: t("common.newSearch"),
                    href: "/app",
                    variant: "primary",
                  },
                ]}
              />
            )}
            {sessions && sessions.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {sessions.map((s) => (
                  <SessionRow
                    key={s.id}
                    session={s}
                    onArchive={handleArchive}
                    onDelete={handleDelete}
                  />
                ))}
              </div>
            )}
          </>
        )}

        {tab === "archive" && (
          <>
            {archived && archived.length === 0 && (
              <div
                className="card"
                style={{
                  padding: 32,
                  textAlign: "center",
                  color: "var(--text-muted)",
                }}
              >
                <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text)" }}>
                  {t("sessions.archive.empty.title")}
                </div>
                <div style={{ fontSize: 13, marginTop: 6 }}>
                  {t("sessions.archive.empty.body")}
                </div>
              </div>
            )}
            {archived && archived.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {archived.map((s) => (
                  <SessionRow
                    key={s.id}
                    session={s}
                    onRestore={handleRestore}
                    onDelete={handleDelete}
                  />
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
  const { t } = useLocale();
  const [busyId, setBusyId] = useState<string | null>(null);

  if (rows === null) {
    return (
      <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
        {t("common.loading")}
      </div>
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
          {t("schedule.empty.title")}
        </div>
        <div style={{ fontSize: 13, marginTop: 6 }}>
          {t("schedule.empty.body")}
        </div>
      </div>
    );
  }

  const fmt = (d: string | null) =>
    d ? new Date(d).toLocaleString() : t("common.none");

  const handleScheduleChange = async (
    id: string,
    schedule: SavedSearchSchedule,
  ) => {
    setBusyId(id);
    try {
      await updateSavedSearch(id, { schedule });
      onChange();
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const handleRun = async (id: string) => {
    setBusyId(id);
    try {
      await runSavedSearchNow(id);
      showSuccess(t("schedule.runQueued"));
      onChange();
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (id: string) => {
    if (!(await confirmAsync(t("schedule.deleteConfirm")))) return;
    setBusyId(id);
    try {
      await deleteSavedSearch(id);
      onChange();
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
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
                  {" · "}
                  {t("schedule.lastRun", { time: fmt(row.last_run_at) })}
                </>
              )}
              {row.next_run_at && (
                <>
                  {" · "}
                  {t("schedule.nextRun", { time: fmt(row.next_run_at) })}
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
            <option value="off">{t("schedule.freq.off")}</option>
            <option value="daily">{t("schedule.freq.daily")}</option>
            <option value="weekly">{t("schedule.freq.weekly")}</option>
            <option value="biweekly">{t("schedule.freq.biweekly")}</option>
            <option value="monthly">{t("schedule.freq.monthly")}</option>
          </select>

          <button
            type="button"
            className="btn btn-sm"
            onClick={() => void handleRun(row.id)}
            disabled={busyId === row.id}
          >
            <Icon name="zap" size={12} />
            {t("schedule.runNow")}
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
