"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import {
  Button,
  Card,
  Chip,
  EmptyState,
  Input,
  Select,
  SkeletonLines,
  Textarea,
} from "@/components/ui";
import {
  createFunnel,
  deleteFunnel,
  duplicateFunnel,
  listFunnels,
  updateFunnel,
  type Funnel,
  type FunnelStep,
} from "@/lib/api";
import { getActiveWorkspace, subscribeWorkspace } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";
import { showError } from "@/lib/toast";
import { confirmAsync } from "@/lib/confirm";

function toMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

const EMPTY_DRAFT = {
  name: "",
  goal_name: "",
  goal_price: "" as string,
  goal_action: "none",
  script: "",
  status: "draft",
  no_answer_attempts: 3,
  no_answer_pause_days: 14,
  steps: [{ kind: "call", day_offset: 0, auto: false }] as FunnelStep[],
};

type Draft = typeof EMPTY_DRAFT;

function draftFrom(f: Funnel): Draft {
  return {
    name: f.name,
    goal_name: f.goal_name,
    goal_price: f.goal_price != null ? String(f.goal_price) : "",
    goal_action: f.goal_action,
    script: f.script ?? "",
    status: f.status,
    no_answer_attempts: f.no_answer_attempts,
    no_answer_pause_days: f.no_answer_pause_days,
    steps: f.steps.map((s) => ({
      kind: s.kind,
      day_offset: s.day_offset,
      auto: s.auto,
      note: s.note ?? undefined,
    })),
  };
}

export default function FunnelsPage() {
  const { t } = useLocale();
  const [teamId, setTeamId] = useState<string | null>(() => {
    const w = getActiveWorkspace();
    return w.kind === "team" ? w.team_id : null;
  });
  const [funnels, setFunnels] = useState<Funnel[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(
    () =>
      subscribeWorkspace(() => {
        const w = getActiveWorkspace();
        setTeamId(w.kind === "team" ? w.team_id : null);
      }),
    [],
  );

  // Мастер онбординга команды: /app/funnels?new=1 открывает
  // конструктор первой воронки сразу после создания команды.
  useEffect(() => {
    if (
      typeof window !== "undefined" &&
      new URLSearchParams(window.location.search).get("new") === "1"
    ) {
      setSelectedId(null);
      setDraft(EMPTY_DRAFT);
      setCreating(true);
    }
  }, []);

  const reload = useCallback(() => {
    if (!teamId) {
      setFunnels([]);
      return;
    }
    listFunnels(teamId)
      .then(setFunnels)
      .catch((e) => showError(toMessage(e)));
  }, [teamId]);

  useEffect(() => {
    setFunnels(null);
    reload();
  }, [reload]);

  const selected = useMemo(
    () => funnels?.find((f) => f.id === selectedId) ?? null,
    [funnels, selectedId],
  );

  useEffect(() => {
    if (selected) {
      setDraft(draftFrom(selected));
      setCreating(false);
    }
  }, [selected]);

  const startNew = () => {
    setSelectedId(null);
    setDraft(EMPTY_DRAFT);
    setCreating(true);
  };

  const save = async () => {
    if (!teamId) return;
    const payload = {
      name: draft.name.trim(),
      goal_name: draft.goal_name.trim(),
      goal_price:
        draft.goal_price.trim() === ""
          ? null
          : Number(draft.goal_price),
      goal_action: draft.goal_action,
      script: draft.script.trim() || null,
      status: draft.status,
      no_answer_attempts: draft.no_answer_attempts,
      no_answer_pause_days: draft.no_answer_pause_days,
      steps: draft.steps,
    };
    if (!payload.name || !payload.goal_name) {
      showError(t("funnels.validation"));
      return;
    }
    setSaving(true);
    try {
      if (creating) {
        const created = await createFunnel(teamId, payload);
        setSelectedId(created.id);
        setCreating(false);
      } else if (selectedId) {
        await updateFunnel(selectedId, payload);
      }
      reload();
    } catch (e) {
      showError(toMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!selectedId) return;
    const ok = await confirmAsync(t("funnels.confirmDelete"));
    if (!ok) return;
    try {
      await deleteFunnel(selectedId);
      setSelectedId(null);
      setDraft(EMPTY_DRAFT);
      reload();
    } catch (e) {
      showError(toMessage(e));
    }
  };

  const duplicate = async () => {
    if (!selectedId) return;
    try {
      const copy = await duplicateFunnel(selectedId);
      reload();
      setSelectedId(copy.id);
    } catch (e) {
      showError(toMessage(e));
    }
  };

  const setStep = (i: number, patch: Partial<FunnelStep>) => {
    setDraft((d) => ({
      ...d,
      steps: d.steps.map((s, j) => (j === i ? { ...s, ...patch } : s)),
    }));
  };

  const editorOpen = creating || selected !== null;

  return (
    <>
      <Topbar crumbs={[{ label: t("nav.funnels") }]} />
      <div className="page">
        {!teamId && (
          <Card>
            <EmptyState
              icon={<Icon name="zap" size={20} />}
              title={t("funnels.noTeamTitle")}
              hint={t("funnels.noTeamHint")}
            />
          </Card>
        )}

        {teamId && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "300px 1fr",
              gap: 20,
              alignItems: "start",
            }}
          >
            {/* Список воронок */}
            <Card padding={16}>
              <div
                className="eyebrow"
                style={{ marginBottom: 10 }}
              >
                {t("funnels.listTitle")}
              </div>
              {funnels === null && <SkeletonLines lines={4} />}
              {funnels !== null && funnels.length === 0 && (
                <div
                  style={{
                    fontSize: 13,
                    color: "var(--text-muted)",
                    lineHeight: 1.5,
                    marginBottom: 10,
                  }}
                >
                  {t("funnels.emptyTeaches")}
                </div>
              )}
              <div
                style={{ display: "flex", flexDirection: "column", gap: 6 }}
              >
                {(funnels ?? []).map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => setSelectedId(f.id)}
                    style={{
                      textAlign: "left",
                      padding: "10px 12px",
                      borderRadius: 10,
                      border: "1px solid",
                      borderColor:
                        f.id === selectedId
                          ? "var(--accent)"
                          : "var(--border)",
                      background:
                        f.id === selectedId
                          ? "var(--accent-soft)"
                          : "var(--surface)",
                      cursor: "pointer",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        gap: 8,
                        alignItems: "center",
                      }}
                    >
                      <span style={{ fontWeight: 700, fontSize: 13.5 }}>
                        {f.name}
                      </span>
                      <Chip
                        tone={f.status === "active" ? "positive" : "default"}
                      >
                        {f.status === "active"
                          ? t("funnels.statusActive")
                          : f.status === "draft"
                            ? t("funnels.statusDraft")
                            : t("funnels.statusArchived")}
                      </Chip>
                    </div>
                    <div
                      style={{
                        fontSize: 12,
                        color: "var(--text-muted)",
                        marginTop: 3,
                      }}
                    >
                      {t("funnels.cardMeta", {
                        n: f.leads_count,
                        goal: f.goal_name,
                      })}
                    </div>
                  </button>
                ))}
              </div>
              <Button
                variant="soft"
                size="sm"
                onClick={startNew}
                style={{ marginTop: 12 }}
              >
                <Icon name="plus" size={13} /> {t("funnels.new")}
              </Button>
              <div
                style={{
                  fontSize: 11.5,
                  color: "var(--text-dim)",
                  marginTop: 12,
                  lineHeight: 1.5,
                }}
              >
                {t("funnels.footnote")}
              </div>
            </Card>

            {/* Конструктор */}
            {!editorOpen ? (
              <Card>
                <EmptyState
                  icon={<Icon name="zap" size={20} />}
                  title={t("funnels.pickTitle")}
                  hint={t("funnels.pickHint")}
                  action={
                    <Button onClick={startNew}>{t("funnels.new")}</Button>
                  }
                />
              </Card>
            ) : (
              <Card>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: 12,
                    marginBottom: 18,
                    flexWrap: "wrap",
                  }}
                >
                  <div style={{ fontSize: 18, fontWeight: 800 }}>
                    {creating
                      ? t("funnels.newTitle")
                      : selected?.name}
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    {!creating && (
                      <>
                        <Button variant="ghost" size="sm" onClick={duplicate}>
                          {t("funnels.duplicate")}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={remove}
                          style={{ color: "var(--cold)" }}
                        >
                          {t("common.delete")}
                        </Button>
                      </>
                    )}
                    <Button size="sm" loading={saving} onClick={save}>
                      {t("common.save")}
                    </Button>
                  </div>
                </div>

                <div
                  className="eyebrow"
                  style={{ marginBottom: 10 }}
                >
                  {t("funnels.goalSection")}
                </div>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: 12,
                    marginBottom: 20,
                  }}
                >
                  <Input
                    label={t("funnels.name")}
                    value={draft.name}
                    onChange={(e) =>
                      setDraft((d) => ({ ...d, name: e.target.value }))
                    }
                    placeholder="Аудит-первый"
                  />
                  <Select
                    label={t("funnels.status")}
                    value={draft.status}
                    onChange={(e) =>
                      setDraft((d) => ({ ...d, status: e.target.value }))
                    }
                  >
                    <option value="draft">{t("funnels.statusDraft")}</option>
                    <option value="active">
                      {t("funnels.statusActive")}
                    </option>
                    <option value="archived">
                      {t("funnels.statusArchived")}
                    </option>
                  </Select>
                  <Input
                    label={t("funnels.goalName")}
                    hint={t("funnels.goalNameHint")}
                    value={draft.goal_name}
                    onChange={(e) =>
                      setDraft((d) => ({ ...d, goal_name: e.target.value }))
                    }
                    placeholder={t("funnels.goalPh")}
                  />
                  <Input
                    label={t("funnels.goalPrice")}
                    type="number"
                    min={0}
                    value={draft.goal_price}
                    onChange={(e) =>
                      setDraft((d) => ({
                        ...d,
                        goal_price: e.target.value,
                      }))
                    }
                    placeholder="100"
                  />
                  <Select
                    label={t("funnels.goalAction")}
                    value={draft.goal_action}
                    onChange={(e) =>
                      setDraft((d) => ({
                        ...d,
                        goal_action: e.target.value,
                      }))
                    }
                  >
                    <option value="payment_calendar">
                      {t("funnels.actionPaymentCalendar")}
                    </option>
                    <option value="invoice">
                      {t("funnels.actionInvoice")}
                    </option>
                    <option value="booking">
                      {t("funnels.actionBooking")}
                    </option>
                    <option value="none">{t("funnels.actionNone")}</option>
                  </Select>
                </div>

                <div className="eyebrow" style={{ marginBottom: 10 }}>
                  {t("funnels.pathSection")}{" "}
                  <span style={{ textTransform: "none", letterSpacing: 0 }}>
                    ·{" "}
                    {t("funnels.noAnswerRule", {
                      n: draft.no_answer_attempts,
                      d: draft.no_answer_pause_days,
                    })}
                  </span>
                </div>
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                    marginBottom: 12,
                  }}
                >
                  {draft.steps.map((s, i) => (
                    <div
                      key={i}
                      style={{
                        display: "flex",
                        gap: 8,
                        alignItems: "center",
                        flexWrap: "wrap",
                        padding: "8px 10px",
                        border: "1px solid var(--border)",
                        borderRadius: 10,
                        background: "var(--surface)",
                      }}
                    >
                      <span
                        style={{
                          width: 22,
                          height: 22,
                          borderRadius: 7,
                          background: "var(--accent-soft)",
                          color: "var(--accent)",
                          display: "grid",
                          placeItems: "center",
                          fontSize: 12,
                          fontWeight: 800,
                          flexShrink: 0,
                        }}
                      >
                        {i + 1}
                      </span>
                      <select
                        className="select"
                        style={{ width: 120, padding: "6px 8px", fontSize: 13 }}
                        value={s.kind}
                        onChange={(e) =>
                          setStep(i, {
                            kind: e.target.value as "call" | "email",
                          })
                        }
                      >
                        <option value="call">{t("funnels.stepCall")}</option>
                        <option value="email">{t("funnels.stepEmail")}</option>
                      </select>
                      <label
                        style={{
                          fontSize: 12.5,
                          color: "var(--text-muted)",
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                        }}
                      >
                        +
                        <input
                          className="input"
                          type="number"
                          min={0}
                          max={365}
                          style={{ width: 64, padding: "6px 8px" }}
                          value={s.day_offset}
                          onChange={(e) =>
                            setStep(i, {
                              day_offset: Math.max(
                                0,
                                Number(e.target.value) || 0,
                              ),
                            })
                          }
                        />
                        {t("funnels.days")}
                      </label>
                      {s.kind === "email" && (
                        <label
                          style={{
                            fontSize: 12.5,
                            color: "var(--text-muted)",
                            display: "flex",
                            alignItems: "center",
                            gap: 6,
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={s.auto}
                            onChange={(e) =>
                              setStep(i, { auto: e.target.checked })
                            }
                          />
                          {t("funnels.stepAuto")}
                        </label>
                      )}
                      <input
                        className="input"
                        style={{
                          flex: 1,
                          minWidth: 140,
                          padding: "6px 10px",
                          fontSize: 13,
                        }}
                        placeholder={t("funnels.stepNotePh")}
                        value={s.note ?? ""}
                        onChange={(e) =>
                          setStep(i, { note: e.target.value })
                        }
                      />
                      <Button
                        variant="icon"
                        title={t("common.delete")}
                        onClick={() =>
                          setDraft((d) => ({
                            ...d,
                            steps: d.steps.filter((_, j) => j !== i),
                          }))
                        }
                      >
                        <Icon name="trash" size={13} />
                      </Button>
                    </div>
                  ))}
                </div>
                <Button
                  variant="soft"
                  size="sm"
                  onClick={() =>
                    setDraft((d) => ({
                      ...d,
                      steps: [
                        ...d.steps,
                        { kind: "call", day_offset: 1, auto: false },
                      ],
                    }))
                  }
                >
                  <Icon name="plus" size={13} /> {t("funnels.addStep")}
                </Button>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: 12,
                    margin: "20px 0",
                  }}
                >
                  <Input
                    label={t("funnels.attempts")}
                    type="number"
                    min={1}
                    max={10}
                    value={String(draft.no_answer_attempts)}
                    onChange={(e) =>
                      setDraft((d) => ({
                        ...d,
                        no_answer_attempts: Math.max(
                          1,
                          Number(e.target.value) || 1,
                        ),
                      }))
                    }
                  />
                  <Input
                    label={t("funnels.pauseDays")}
                    type="number"
                    min={1}
                    max={365}
                    value={String(draft.no_answer_pause_days)}
                    onChange={(e) =>
                      setDraft((d) => ({
                        ...d,
                        no_answer_pause_days: Math.max(
                          1,
                          Number(e.target.value) || 1,
                        ),
                      }))
                    }
                  />
                </div>

                <Textarea
                  label={t("funnels.script")}
                  hint={t("funnels.scriptHint")}
                  rows={6}
                  value={draft.script}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, script: e.target.value }))
                  }
                />
              </Card>
            )}
          </div>
        )}
      </div>
    </>
  );
}
