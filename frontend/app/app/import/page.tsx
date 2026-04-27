"use client";

import { useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import { ApiError, importLeadsCsv, type CsvImportRow } from "@/lib/api";
import { activeTeamId } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";

const MAX_ROWS = 500;

const STANDARD_KEYS: Record<string, keyof CsvImportRow> = {
  name: "name",
  company: "name",
  business: "name",
  title: "name",

  website: "website",
  url: "website",
  site: "website",
  domain: "website",

  region: "region",
  city: "region",
  location: "region",
  address: "region",

  phone: "phone",
  tel: "phone",
  telephone: "phone",

  category: "category",
  industry: "category",
  niche: "category",
};

interface ParsedCsv {
  headers: string[];
  rows: CsvImportRow[];
  raw_count: number;
  skipped: number;
}

/**
 * CSV bulk import page.
 *
 * Browser-side parse → preview → server upload. The CSV parser is
 * deliberately small (split on "\n" / "," with quote support) — we
 * only support flat sheets with a header row, which covers 99% of
 * "give me a list of companies and a column for region/website".
 */
export default function ImportPage() {
  const { t } = useLocale();
  const router = useRouter();
  const fileInput = useRef<HTMLInputElement>(null);
  const [parsed, setParsed] = useState<ParsedCsv | null>(null);
  const [label, setLabel] = useState("CSV import");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onFile = async (file: File) => {
    setError(null);
    try {
      const text = await file.text();
      const out = parseCsv(text);
      if (out.rows.length === 0) {
        setError(t("import.empty"));
        return;
      }
      if (out.rows.length > MAX_ROWS) {
        out.rows = out.rows.slice(0, MAX_ROWS);
        out.skipped += out.raw_count - MAX_ROWS;
      }
      setParsed(out);
      setLabel(file.name.replace(/\.csv$/i, "").slice(0, 80) || "CSV import");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const submit = async () => {
    if (!parsed) return;
    setBusy(true);
    setError(null);
    try {
      const res = await importLeadsCsv({
        rows: parsed.rows,
        label,
        teamId: activeTeamId(),
      });
      router.push(`/app/sessions/${res.search_id}`);
    } catch (e) {
      const detail =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : String(e);
      setError(detail);
      setBusy(false);
    }
  };

  return (
    <>
      <Topbar
        title={t("import.title")}
        subtitle={t("import.subtitle")}
      />
      <div className="page" style={{ maxWidth: 880 }}>
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

        <div
          className="card"
          style={{
            padding: 28,
            display: "flex",
            flexDirection: "column",
            gap: 16,
          }}
        >
          {!parsed ? (
            <>
              <div
                style={{
                  textAlign: "center",
                  padding: "20px 16px",
                  border: "2px dashed var(--border-strong)",
                  borderRadius: 12,
                  background: "var(--surface-2)",
                  cursor: "pointer",
                }}
                onClick={() => fileInput.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const f = e.dataTransfer.files?.[0];
                  if (f) onFile(f);
                }}
              >
                <div
                  style={{
                    fontSize: 24,
                    fontWeight: 700,
                    marginBottom: 6,
                    letterSpacing: "-0.01em",
                  }}
                >
                  {t("import.dropTitle")}
                </div>
                <div
                  style={{
                    fontSize: 13,
                    color: "var(--text-muted)",
                    lineHeight: 1.5,
                    marginBottom: 16,
                  }}
                >
                  {t("import.dropBody")}
                </div>
                <button type="button" className="btn">
                  <Icon name="folder" size={14} /> {t("import.pick")}
                </button>
              </div>
              <input
                ref={fileInput}
                type="file"
                accept=".csv,text/csv"
                style={{ display: "none" }}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) onFile(f);
                  if (fileInput.current) fileInput.current.value = "";
                }}
              />
              <div
                style={{
                  fontSize: 12,
                  color: "var(--text-dim)",
                  lineHeight: 1.5,
                }}
              >
                {t("import.expectedColumns")}
              </div>
            </>
          ) : (
            <>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 12,
                  flexWrap: "wrap",
                }}
              >
                <div>
                  <div
                    style={{
                      fontSize: 16,
                      fontWeight: 700,
                      marginBottom: 2,
                    }}
                  >
                    {t("import.previewTitle", {
                      n: parsed.rows.length.toString(),
                    })}
                  </div>
                  {parsed.skipped > 0 && (
                    <div
                      style={{
                        fontSize: 12,
                        color: "var(--warm)",
                      }}
                    >
                      {t("import.skipped", {
                        n: parsed.skipped.toString(),
                      })}
                    </div>
                  )}
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => setParsed(null)}
                    disabled={busy}
                  >
                    {t("import.pickAnother")}
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={submit}
                    disabled={busy}
                  >
                    {busy ? t("common.loading") : t("import.runImport")}
                  </button>
                </div>
              </div>

              <div>
                <label
                  className="eyebrow"
                  style={{ display: "block", marginBottom: 6 }}
                >
                  {t("import.labelField")}
                </label>
                <input
                  className="input"
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  maxLength={120}
                />
              </div>

              <div
                style={{
                  border: "1px solid var(--border)",
                  borderRadius: 10,
                  overflow: "auto",
                  maxHeight: 380,
                }}
              >
                <table
                  style={{
                    width: "100%",
                    borderCollapse: "collapse",
                    fontSize: 12.5,
                  }}
                >
                  <thead
                    style={{
                      background: "var(--surface-2)",
                      position: "sticky",
                      top: 0,
                    }}
                  >
                    <tr>
                      <Th>name</Th>
                      <Th>website</Th>
                      <Th>region</Th>
                      <Th>phone</Th>
                      <Th>category</Th>
                      <Th>extras</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {parsed.rows.slice(0, 30).map((row, i) => (
                      <tr
                        key={i}
                        style={{ borderTop: "1px solid var(--border)" }}
                      >
                        <Td>{row.name}</Td>
                        <Td>{row.website ?? "—"}</Td>
                        <Td>{row.region ?? "—"}</Td>
                        <Td>{row.phone ?? "—"}</Td>
                        <Td>{row.category ?? "—"}</Td>
                        <Td>
                          {row.extras
                            ? Object.entries(row.extras)
                                .map(([k, v]) => `${k}=${v}`)
                                .slice(0, 3)
                                .join(" · ")
                            : "—"}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {parsed.rows.length > 30 && (
                <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
                  {t("import.previewTrunc", {
                    n: (parsed.rows.length - 30).toString(),
                  })}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th
      style={{
        padding: "8px 10px",
        textAlign: "left",
        fontSize: 11,
        textTransform: "uppercase",
        letterSpacing: "0.06em",
        color: "var(--text-dim)",
        fontWeight: 600,
      }}
    >
      {children}
    </th>
  );
}

function Td({ children }: { children: React.ReactNode }) {
  return (
    <td
      style={{
        padding: "8px 10px",
        verticalAlign: "top",
        color: "var(--text)",
        maxWidth: 200,
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </td>
  );
}

function parseCsv(text: string): ParsedCsv {
  // Tiny RFC-4180-ish parser: handles ``"…"`` quoting, commas inside
  // quotes, escaped quotes (""), and \r\n / \n line endings. Good
  // enough for the "Excel export" CSV files users actually upload.
  const records: string[][] = [];
  let field = "";
  let row: string[] = [];
  let inQuotes = false;
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 2;
          continue;
        }
        inQuotes = false;
        i++;
        continue;
      }
      field += ch;
      i++;
      continue;
    }
    if (ch === '"') {
      inQuotes = true;
      i++;
      continue;
    }
    if (ch === ",") {
      row.push(field);
      field = "";
      i++;
      continue;
    }
    if (ch === "\n" || ch === "\r") {
      row.push(field);
      records.push(row);
      row = [];
      field = "";
      // Skip \r\n pair as one separator.
      if (ch === "\r" && text[i + 1] === "\n") i++;
      i++;
      continue;
    }
    field += ch;
    i++;
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    records.push(row);
  }

  if (records.length === 0) {
    return { headers: [], rows: [], raw_count: 0, skipped: 0 };
  }

  const headerRaw = records[0].map((h) => h.trim());
  const headers = headerRaw.map((h) => h.toLowerCase());
  const dataRows = records.slice(1);
  const out: CsvImportRow[] = [];
  let skipped = 0;
  let rawCount = 0;

  for (const r of dataRows) {
    if (r.every((c) => !c || !c.trim())) continue;
    rawCount++;
    const item: CsvImportRow = { name: "", extras: {} };
    for (let col = 0; col < headers.length; col++) {
      const key = headers[col];
      const value = (r[col] ?? "").trim();
      if (!value) continue;
      const standard = STANDARD_KEYS[key];
      if (standard) {
        // Type-safely assign to the matching field.
        switch (standard) {
          case "name":
            item.name = value;
            break;
          case "website":
            item.website = value;
            break;
          case "region":
            item.region = value;
            break;
          case "phone":
            item.phone = value;
            break;
          case "category":
            item.category = value;
            break;
          default:
            break;
        }
      } else {
        // Use the original-case header as the extras key so the
        // user keeps their column names.
        const origKey = (headerRaw[col] || key).slice(0, 64);
        if (origKey) {
          item.extras = { ...(item.extras ?? {}), [origKey]: value };
        }
      }
    }
    if (!item.name) {
      skipped++;
      continue;
    }
    out.push(item);
  }

  return { headers: headerRaw, rows: out, raw_count: rawCount, skipped };
}
