"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  disconnectPipedrive,
  getPipedriveStatus,
  listPipedrivePipelines,
  setPipedriveConfig,
  startPipedriveAuthorize,
  type PipedriveIntegrationStatus,
  type PipedrivePipeline,
} from "@/lib/api";

export function PipedriveSection() {
  const [status, setStatus] = useState<PipedriveIntegrationStatus | null>(
    null,
  );
  const [pipelines, setPipelines] = useState<PipedrivePipeline[] | null>(
    null,
  );
  const [pipelineId, setPipelineId] = useState<number | null>(null);
  const [stageId, setStageId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPipedriveStatus()
      .then((s) => {
        if (cancelled) return;
        setStatus(s);
        setPipelineId(s.default_pipeline_id);
        setStageId(s.default_stage_id);
      })
      .catch(() => {
        if (cancelled) return;
        setStatus({
          connected: false,
          api_domain: null,
          account_email: null,
          scope: null,
          expires_at: null,
          default_pipeline_id: null,
          default_stage_id: null,
        });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!status?.connected || pipelines !== null) return;
    let cancelled = false;
    listPipedrivePipelines()
      .then((r) => {
        if (cancelled) return;
        setPipelines(r.items);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : String(e));
        setPipelines([]);
      });
    return () => {
      cancelled = true;
    };
  }, [status?.connected, pipelines]);

  const connect = async () => {
    setBusy(true);
    setError(null);
    try {
      const { url } = await startPipedriveAuthorize();
      window.location.href = url;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!confirm("Отключить Pipedrive? Сохранённые токены будут удалены."))
      return;
    setBusy(true);
    setError(null);
    try {
      await disconnectPipedrive();
      setStatus({
        connected: false,
        api_domain: null,
        account_email: null,
        scope: null,
        expires_at: null,
        default_pipeline_id: null,
        default_stage_id: null,
      });
      setPipelines(null);
      setPipelineId(null);
      setStageId(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const saveConfig = async () => {
    if (!pipelineId || !stageId) return;
    setBusy(true);
    setError(null);
    try {
      const next = await setPipedriveConfig({
        defaultPipelineId: pipelineId,
        defaultStageId: stageId,
      });
      setStatus(next);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const stagesForPipeline =
    pipelines?.find((p) => p.id === pipelineId)?.stages ?? [];

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        Интеграция: Pipedrive
      </div>

      {status === null ? (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
          Загрузка…
        </div>
      ) : status.connected ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 16,
              justifyContent: "space-between",
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}
              >
                Подключено
                {status.account_email ? ` (${status.account_email})` : ""}
              </div>
              <div
                style={{
                  fontSize: 12.5,
                  color: "var(--text-muted)",
                  lineHeight: 1.5,
                }}
              >
                API:{" "}
                <span style={{ fontFamily: "var(--font-mono)" }}>
                  {status.api_domain ?? "—"}
                </span>
              </div>
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => void disconnect()}
              disabled={busy}
              style={{ color: "var(--cold)" }}
            >
              Отключить
            </button>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div className="eyebrow" style={{ fontSize: 11 }}>
              Куда складывать новые сделки
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <select
                className="input"
                style={{ flex: 1, minWidth: 180 }}
                value={pipelineId ?? ""}
                onChange={(e) => {
                  const v = e.target.value
                    ? Number(e.target.value)
                    : null;
                  setPipelineId(v);
                  setStageId(null);
                }}
                disabled={busy || pipelines === null}
              >
                <option value="">Pipeline…</option>
                {(pipelines ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <select
                className="input"
                style={{ flex: 1, minWidth: 180 }}
                value={stageId ?? ""}
                onChange={(e) =>
                  setStageId(e.target.value ? Number(e.target.value) : null)
                }
                disabled={busy || !pipelineId}
              >
                <option value="">Stage…</option>
                {stagesForPipeline.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => void saveConfig()}
                disabled={busy || !pipelineId || !stageId}
              >
                Сохранить
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <p
            style={{
              fontSize: 13,
              color: "var(--text-muted)",
              lineHeight: 1.5,
              margin: 0,
            }}
          >
            Подключите Pipedrive чтобы экспортировать выбранных лидов
            как Person + Deal в выбранный pipeline. Конвиу пишет только
            в Persons и Deals — никаких изменений в существующих
            организациях или активностях.
          </p>
          <div>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => void connect()}
              disabled={busy}
            >
              {busy ? "..." : "Подключить Pipedrive"}
            </button>
          </div>
        </div>
      )}

      {error && (
        <div
          style={{
            marginTop: 12,
            fontSize: 12.5,
            color: "var(--cold)",
            lineHeight: 1.5,
          }}
        >
          {error}
        </div>
      )}
    </div>
  );
}
