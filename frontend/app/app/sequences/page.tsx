"use client";

import { useEffect, useState } from "react";

import {
  createSequence,
  listSequences,
  type Sequence,
  type SequenceStep,
} from "@/lib/api/sequences";
import { ApiError } from "@/lib/api/_core";
import { useLocale } from "@/lib/i18n";

const INITIAL_STEPS: SequenceStep[] = [
  { day: 0, subject: "", body: "" },
  { day: 3, subject: "", body: "" },
  { day: 7, subject: "", body: "" },
];

export default function SequencesPage() {
  const { t } = useLocale();
  const [sequences, setSequences] = useState<Sequence[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [steps, setSteps] = useState<SequenceStep[]>(INITIAL_STEPS);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listSequences()
      .then((data) => {
        if (!cancelled) setSequences(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail =
          err instanceof ApiError ? err.message : t("sequences.error.load");
        setError(detail);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleCreate() {
    if (creating || !name.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const created = await createSequence(name.trim(), steps);
      setSequences((prev) => [
        ...prev,
        {
          id: created.id,
          name: created.name,
          steps: created.steps ?? steps,
          created_at: created.created_at ?? new Date().toISOString(),
        },
      ]);
      setName("");
      setSteps(INITIAL_STEPS);
    } catch (err: unknown) {
      const detail =
        err instanceof ApiError ? err.message : t("sequences.error.create");
      setError(detail);
    } finally {
      setCreating(false);
    }
  }

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "32px 24px" }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 24 }}>
        {t("sequences.title")}
      </h1>

      <div className="card" style={{ padding: 24, marginBottom: 24 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>
          {t("sequences.new")}
        </div>
        <input
          style={{
            width: "100%",
            padding: "6px 10px",
            borderRadius: 6,
            border: "1px solid var(--border)",
            fontSize: 13,
            background: "var(--surface)",
            color: "var(--text)",
            marginBottom: 16,
          }}
          placeholder={t("sequences.namePh")}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        {steps.map((step, i) => (
          <div
            key={i}
            style={{
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: 16,
              marginBottom: 12,
            }}
          >
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>
              {t("sequences.day", { day: step.day })}
              {i === 0 ? " " + t("sequences.immediately") : ""}
            </div>
            <input
              style={{
                width: "100%",
                padding: "5px 10px",
                borderRadius: 6,
                border: "1px solid var(--border)",
                fontSize: 12,
                background: "var(--surface)",
                color: "var(--text)",
                marginBottom: 8,
              }}
              placeholder={t("sequences.subjectPh")}
              value={step.subject}
              onChange={(e) =>
                setSteps((prev) =>
                  prev.map((s, j) =>
                    j === i ? { ...s, subject: e.target.value } : s,
                  ),
                )
              }
            />
            <textarea
              rows={4}
              style={{
                width: "100%",
                padding: "5px 10px",
                borderRadius: 6,
                border: "1px solid var(--border)",
                fontSize: 12,
                background: "var(--surface)",
                color: "var(--text)",
                resize: "vertical",
              }}
              placeholder={t("sequences.bodyPh")}
              value={step.body}
              onChange={(e) =>
                setSteps((prev) =>
                  prev.map((s, j) =>
                    j === i ? { ...s, body: e.target.value } : s,
                  ),
                )
              }
            />
          </div>
        ))}
        {error && (
          <div
            role="alert"
            style={{
              fontSize: 12,
              color: "var(--danger, #dc2626)",
              marginBottom: 12,
            }}
          >
            {error}
          </div>
        )}
        <button
          onClick={handleCreate}
          disabled={creating || !name.trim()}
          style={{
            padding: "7px 18px",
            borderRadius: 6,
            fontSize: 13,
            background: "var(--accent)",
            color: "#fff",
            border: "none",
            cursor: creating || !name.trim() ? "not-allowed" : "pointer",
            opacity: creating || !name.trim() ? 0.6 : 1,
          }}
        >
          {creating ? t("common.creating") : t("sequences.create")}
        </button>
      </div>

      {loading ? (
        <div
          style={{
            textAlign: "center",
            color: "var(--text-muted)",
            fontSize: 13,
            padding: 40,
          }}
        >
          {t("common.loading")}
        </div>
      ) : (
        <>
          {sequences.map((seq) => (
            <div
              key={seq.id}
              className="card"
              style={{ padding: 20, marginBottom: 12 }}
            >
              <div style={{ fontWeight: 600, marginBottom: 4 }}>{seq.name}</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                {t("sequences.meta", {
                  count: seq.steps.length,
                  date: new Date(seq.created_at).toLocaleDateString(),
                })}
              </div>
            </div>
          ))}
          {sequences.length === 0 && !error && (
            <div
              style={{
                textAlign: "center",
                color: "var(--text-muted)",
                fontSize: 13,
                padding: 40,
              }}
            >
              {t("sequences.empty")}
            </div>
          )}
        </>
      )}
    </div>
  );
}
