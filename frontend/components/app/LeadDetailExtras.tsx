"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import {
  type LeadActivity,
  type LeadCustomField,
  type LeadTask,
  createLeadTask,
  deleteLeadCustomField,
  deleteLeadTask,
  enrichDecisionMakers,
  listLeadActivity,
  listLeadCustomFields,
  listLeadTasks,
  updateLeadTask,
  upsertLeadCustomField,
} from "@/lib/api";
import { useLocale } from "@/lib/i18n";
import { showError } from "@/lib/toast";

/**
 * Three CRM-maturity blocks rendered below the existing notes section
 * inside LeadDetailModal: tasks, custom fields, activity timeline.
 *
 * Each block is independently lazy: it fetches on mount, renders an
 * empty state when there's nothing, and only re-fetches when its own
 * mutation lands. Keeps the modal snappy and the file self-contained.
 */
export function LeadDetailExtras({ leadId }: { leadId: string }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 18,
        marginTop: 18,
      }}
    >
      <TasksBlock leadId={leadId} />
      <CustomFieldsBlock leadId={leadId} />
      <ActivityBlock leadId={leadId} />
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────
// Tasks
// ────────────────────────────────────────────────────────────────────

function TasksBlock({ leadId }: { leadId: string }) {
  const { t } = useLocale();
  const [items, setItems] = useState<LeadTask[]>([]);
  const [draft, setDraft] = useState("");
  const [dueLocal, setDueLocal] = useState("");
  const [busy, setBusy] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listLeadTasks(leadId)
      .then((r) => !cancelled && setItems(r.items))
      .catch((e) =>
        !cancelled && showError(e instanceof Error ? e.message : String(e)),
      );
    return () => {
      cancelled = true;
    };
  }, [leadId, tick]);

  const add = async () => {
    if (!draft.trim() || busy) return;
    setBusy(true);
    try {
      const due = dueLocal ? new Date(dueLocal) : null;
      await createLeadTask(leadId, draft.trim(), due);
      setDraft("");
      setDueLocal("");
      setTick((n) => n + 1);
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const toggleDone = async (task: LeadTask) => {
    setBusy(true);
    try {
      await updateLeadTask(task.id, { done: !task.done_at });
      setTick((n) => n + 1);
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    setBusy(true);
    try {
      await deleteLeadTask(id);
      setTick((n) => n + 1);
    } catch {
      // silent
    } finally {
      setBusy(false);
    }
  };

  return (
    <BlockShell title={t("lead.extras.tasks")}>
      <div style={{ display: "flex", gap: 6 }}>
        <input
          className="input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          placeholder={t("lead.extras.tasks.ph")}
          disabled={busy}
          style={{ flex: 2 }}
        />
        <input
          className="input"
          type="datetime-local"
          value={dueLocal}
          onChange={(e) => setDueLocal(e.target.value)}
          disabled={busy}
          style={{ flex: 1 }}
        />
        <button
          type="button"
          className="btn btn-sm"
          onClick={add}
          disabled={busy || !draft.trim()}
        >
          <Icon name="plus" size={13} />
        </button>
      </div>
      {items.length > 0 && (
        <div
          style={{
            marginTop: 8,
            display: "flex",
            flexDirection: "column",
            gap: 6,
          }}
        >
          {items.map((task) => (
            <TaskRow
              key={task.id}
              task={task}
              onToggle={() => toggleDone(task)}
              onDelete={() => remove(task.id)}
            />
          ))}
        </div>
      )}
    </BlockShell>
  );
}

function TaskRow({
  task,
  onToggle,
  onDelete,
}: {
  task: LeadTask;
  onToggle: () => void;
  onDelete: () => void;
}) {
  const { t } = useLocale();
  const done = Boolean(task.done_at);
  const dueLabel = task.due_at ? formatDateTime(task.due_at) : null;
  const overdue =
    !done && task.due_at && new Date(task.due_at).getTime() < Date.now();
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 8px",
        background: "var(--surface-2)",
        borderRadius: 8,
        opacity: done ? 0.6 : 1,
      }}
    >
      <button
        type="button"
        onClick={onToggle}
        title={done ? "reopen" : "done"}
        style={{
          width: 18,
          height: 18,
          borderRadius: 5,
          border: done
            ? "1px solid var(--hot)"
            : "1px solid var(--border-strong)",
          background: done ? "var(--hot)" : "var(--surface)",
          cursor: "pointer",
          padding: 0,
          display: "grid",
          placeItems: "center",
          flexShrink: 0,
        }}
      >
        {done && <Icon name="check" size={11} style={{ color: "white" }} />}
      </button>
      <div
        style={{
          flex: 1,
          fontSize: 12.5,
          color: done ? "var(--text-dim)" : "var(--text)",
          textDecoration: done ? "line-through" : "none",
          minWidth: 0,
        }}
      >
        {task.content}
      </div>
      {dueLabel && (
        <span
          style={{
            fontSize: 11,
            color: overdue ? "var(--cold)" : "var(--text-muted)",
            flexShrink: 0,
          }}
        >
          {dueLabel}
        </span>
      )}
      <button
        type="button"
        onClick={onDelete}
        style={{
          background: "none",
          border: "none",
          color: "var(--text-dim)",
          cursor: "pointer",
          padding: 4,
        }}
        aria-label={t("common.delete")}
      >
        <Icon name="x" size={11} />
      </button>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────
// Custom fields
// ────────────────────────────────────────────────────────────────────

function CustomFieldsBlock({ leadId }: { leadId: string }) {
  const { t } = useLocale();
  const [items, setItems] = useState<LeadCustomField[]>([]);
  const [keyDraft, setKeyDraft] = useState("");
  const [valDraft, setValDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [tick, setTick] = useState(0);
  const [findingDM, setFindingDM] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listLeadCustomFields(leadId)
      .then((r) => !cancelled && setItems(r.items))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [leadId, tick]);

  const findDecisionMakers = async () => {
    if (findingDM) return;
    setFindingDM(true);
    try {
      await enrichDecisionMakers(leadId);
      setTick((n) => n + 1);
    } catch {
      // silent — empty result is fine; user can retry
    } finally {
      setFindingDM(false);
    }
  };

  const upsert = async () => {
    const key = keyDraft.trim();
    if (!key || busy) return;
    setBusy(true);
    try {
      await upsertLeadCustomField(leadId, key, valDraft || null);
      setKeyDraft("");
      setValDraft("");
      setTick((n) => n + 1);
    } catch {
      // silent — user resubmits
    } finally {
      setBusy(false);
    }
  };

  const remove = async (key: string) => {
    setBusy(true);
    try {
      await deleteLeadCustomField(leadId, key);
      setTick((n) => n + 1);
    } catch {
      // silent
    } finally {
      setBusy(false);
    }
  };

  const editValue = async (item: LeadCustomField, next: string) => {
    if (next === item.value) return;
    setBusy(true);
    try {
      await upsertLeadCustomField(leadId, item.key, next);
      setTick((n) => n + 1);
    } catch {
      // silent
    } finally {
      setBusy(false);
    }
  };

  return (
    <BlockShell title={t("lead.extras.customFields")}>
      <div style={{ marginBottom: 8 }}>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={findDecisionMakers}
          disabled={findingDM || busy}
        >
          <Icon name="users" size={13} />
          {findingDM ? t("common.loading") : t("lead.extras.findDecisionMakers")}
        </button>
      </div>
      <div style={{ display: "flex", gap: 6 }}>
        <input
          className="input"
          value={keyDraft}
          onChange={(e) => setKeyDraft(e.target.value)}
          placeholder={t("lead.extras.customFields.keyPh")}
          maxLength={64}
          style={{ flex: 1 }}
        />
        <input
          className="input"
          value={valDraft}
          onChange={(e) => setValDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              upsert();
            }
          }}
          placeholder={t("lead.extras.customFields.valPh")}
          style={{ flex: 2 }}
        />
        <button
          type="button"
          className="btn btn-sm"
          onClick={upsert}
          disabled={busy || !keyDraft.trim()}
        >
          <Icon name="plus" size={13} />
        </button>
      </div>
      {items.length > 0 && (
        <div
          style={{
            marginTop: 8,
            display: "flex",
            flexDirection: "column",
            gap: 4,
          }}
        >
          {items.map((it) => (
            <CustomFieldRow
              key={it.id}
              item={it}
              onChange={(v) => editValue(it, v)}
              onDelete={() => remove(it.key)}
            />
          ))}
        </div>
      )}
    </BlockShell>
  );
}

function CustomFieldRow({
  item,
  onChange,
  onDelete,
}: {
  item: LeadCustomField;
  onChange: (v: string) => void;
  onDelete: () => void;
}) {
  const { t } = useLocale();
  const [val, setVal] = useState(item.value ?? "");
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        fontSize: 12.5,
      }}
    >
      <span
        style={{
          minWidth: 110,
          color: "var(--text-dim)",
          fontWeight: 600,
          flexShrink: 0,
        }}
      >
        {item.key}
      </span>
      <input
        className="input"
        value={val}
        onChange={(e) => setVal(e.target.value)}
        onBlur={() => onChange(val)}
        style={{ flex: 1, padding: "6px 10px" }}
      />
      <button
        type="button"
        onClick={onDelete}
        style={{
          background: "none",
          border: "none",
          color: "var(--text-dim)",
          cursor: "pointer",
          padding: 4,
        }}
        aria-label={t("common.delete")}
      >
        <Icon name="x" size={11} />
      </button>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────
// Activity timeline
// ────────────────────────────────────────────────────────────────────

function ActivityBlock({ leadId }: { leadId: string }) {
  const { t } = useLocale();
  const [items, setItems] = useState<LeadActivity[]>([]);

  useEffect(() => {
    let cancelled = false;
    listLeadActivity(leadId)
      .then((r) => !cancelled && setItems(r.items))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [leadId]);

  if (items.length === 0) return null;

  return (
    <BlockShell title={t("lead.extras.activity")}>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 4,
          maxHeight: 220,
          overflowY: "auto",
          paddingRight: 4,
        }}
      >
        {items.map((a) => (
          <ActivityRow key={a.id} activity={a} />
        ))}
      </div>
    </BlockShell>
  );
}

function ActivityRow({ activity }: { activity: LeadActivity }) {
  const { t } = useLocale();
  const label = describeActivity(activity, t);
  const reply =
    activity.kind === "email_replied"
      ? (activity.payload as ReplyPayload | null)
      : null;
  const category = reply?.category;
  const suggested = (reply?.suggested_reply ?? "").trim();
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 4,
        padding: "4px 0",
        fontSize: 12,
        color: "var(--text-muted)",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span style={{ flex: 1, lineHeight: 1.45 }}>
          {label}
          {category ? <CategoryBadge category={category} /> : null}
        </span>
        <span
          style={{
            flexShrink: 0,
            fontSize: 10.5,
            color: "var(--text-dim)",
            fontFamily: "var(--font-mono)",
          }}
        >
          {formatDateTime(activity.created_at)}
        </span>
      </div>
      {suggested ? (
        <div
          style={{
            marginTop: 2,
            padding: "6px 8px",
            borderRadius: 6,
            background: "var(--surface-2, rgba(127,127,127,0.08))",
            border: "1px solid var(--border)",
            fontSize: 11.5,
            lineHeight: 1.45,
            color: "var(--text-muted)",
          }}
        >
          <span style={{ color: "var(--text-dim)", fontWeight: 600 }}>
            {t("lead.extras.activity.suggestedReply")}
          </span>{" "}
          {suggested}
        </div>
      ) : null}
    </div>
  );
}

interface ReplyPayload {
  category?: string;
  sentiment?: string;
  summary?: string;
  suggested_reply?: string;
}

// Color-code the reply category so a triaged inbox reads at a glance.
const CATEGORY_TONE: Record<string, { bg: string; fg: string }> = {
  interested: { bg: "rgba(34,197,94,0.15)", fg: "#16a34a" },
  meeting_request: { bg: "rgba(34,197,94,0.15)", fg: "#16a34a" },
  question: { bg: "rgba(59,130,246,0.15)", fg: "#2563eb" },
  objection: { bg: "rgba(245,158,11,0.15)", fg: "#d97706" },
  not_interested: { bg: "rgba(239,68,68,0.15)", fg: "#dc2626" },
  unsubscribe: { bg: "rgba(239,68,68,0.15)", fg: "#dc2626" },
  auto_reply: { bg: "rgba(127,127,127,0.15)", fg: "var(--text-dim)" },
  referral: { bg: "rgba(139,92,246,0.15)", fg: "#7c3aed" },
  other: { bg: "rgba(127,127,127,0.15)", fg: "var(--text-dim)" },
};

function CategoryBadge({ category }: { category: string }) {
  const { t } = useLocale();
  const tone = CATEGORY_TONE[category] ?? CATEGORY_TONE.other;
  return (
    <span
      style={{
        marginLeft: 6,
        padding: "1px 6px",
        borderRadius: 999,
        fontSize: 10,
        fontWeight: 600,
        background: tone.bg,
        color: tone.fg,
        whiteSpace: "nowrap",
      }}
    >
      {t(
        `lead.extras.activity.replyCategory.${category}` as Parameters<
          typeof t
        >[0],
      )}
    </span>
  );
}

function describeActivity(
  a: LeadActivity,
  t: ReturnType<typeof useLocale>["t"],
): string {
  const p = a.payload || {};
  switch (a.kind) {
    case "status": {
      const from = (p as { from?: string }).from ?? "—";
      const to = (p as { to?: string }).to ?? "—";
      return t("lead.extras.activity.statusKind", { from, to });
    }
    case "notes":
      return t("lead.extras.activity.notesKind");
    case "assigned": {
      const to = (p as { to?: number | null }).to;
      return to
        ? t("lead.extras.activity.assignedKind", { id: String(to) })
        : t("lead.extras.activity.unassignedKind");
    }
    case "mark":
      return t("lead.extras.activity.markKind");
    case "custom_field": {
      const key = (p as { key?: string }).key ?? "—";
      return t("lead.extras.activity.customFieldKind", { key });
    }
    case "task": {
      const content = ((p as { content?: string }).content ?? "").slice(0, 60);
      return t("lead.extras.activity.taskKind", { content });
    }
    case "email_sent": {
      const to = (p as { to?: string }).to ?? "";
      return to ? `Email sent to ${to}` : "Email sent";
    }
    case "email_opened":
      return "Opened email";
    case "email_replied": {
      const summary = ((p as ReplyPayload).summary ?? "").slice(0, 120);
      return summary
        ? t("lead.extras.activity.repliedKind", { summary })
        : t("lead.extras.activity.repliedKindBare");
    }
    default:
      return a.kind;
  }
}

// ────────────────────────────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────────────────────────────

function BlockShell({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="eyebrow" style={{ marginBottom: 8 }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const now = Date.now();
  const diff = now - d.getTime();
  const hr = Math.abs(diff) / 3_600_000;
  if (hr < 24 && diff >= 0) {
    const mins = Math.max(1, Math.floor(diff / 60_000));
    if (mins < 60) return `${mins}m`;
    return `${Math.floor(mins / 60)}h`;
  }
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

