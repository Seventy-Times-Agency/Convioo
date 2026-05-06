"use client";

import { useEffect, useState } from "react";

interface SequenceStep {
  day: number;
  subject: string;
  body: string;
}

interface Sequence {
  id: string;
  name: string;
  steps: SequenceStep[];
  created_at: string;
}

const API = process.env.NEXT_PUBLIC_API_URL;

export default function SequencesPage() {
  const [sequences, setSequences] = useState<Sequence[]>([]);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [steps, setSteps] = useState<SequenceStep[]>([
    { day: 0, subject: "", body: "" },
    { day: 3, subject: "", body: "" },
    { day: 7, subject: "", body: "" },
  ]);

  useEffect(() => {
    fetch(`${API}/api/v1/sequences`, { credentials: "include" })
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) setSequences(data);
      })
      .catch(() => {});
  }, []);

  async function createSequence() {
    setCreating(true);
    try {
      const res = await fetch(`${API}/api/v1/sequences`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, steps }),
      });
      if (res.ok) {
        const created = await res.json();
        setSequences((prev) => [
          ...prev,
          {
            id: created.id,
            name: created.name,
            steps,
            created_at: new Date().toISOString(),
          },
        ]);
        setName("");
      }
    } finally {
      setCreating(false);
    }
  }

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "32px 24px" }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 24 }}>
        Follow-up последовательности
      </h1>

      <div className="card" style={{ padding: 24, marginBottom: 24 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>
          Новая последовательность
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
          placeholder="Название (напр. Кровельные компании UK)"
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
              День {step.day} {i === 0 ? "(сразу)" : ""}
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
              placeholder="Тема письма"
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
              placeholder={"Текст письма. Используй {{name}} и {{website}}"}
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
        <button
          onClick={createSequence}
          disabled={creating || !name}
          style={{
            padding: "7px 18px",
            borderRadius: 6,
            fontSize: 13,
            background: "var(--accent)",
            color: "#fff",
            border: "none",
            cursor: "pointer",
          }}
        >
          {creating ? "Создаю..." : "Создать"}
        </button>
      </div>

      {sequences.map((seq) => (
        <div
          key={seq.id}
          className="card"
          style={{ padding: 20, marginBottom: 12 }}
        >
          <div style={{ fontWeight: 600, marginBottom: 4 }}>{seq.name}</div>
          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
            {seq.steps.length} шагов · создано{" "}
            {new Date(seq.created_at).toLocaleDateString("ru")}
          </div>
        </div>
      ))}
      {sequences.length === 0 && (
        <div
          style={{
            textAlign: "center",
            color: "var(--text-muted)",
            fontSize: 13,
            padding: 40,
          }}
        >
          Нет последовательностей. Создайте первую выше.
        </div>
      )}
    </div>
  );
}
