"use client";

/**
 * Minimal pure-SVG charts for the analytics dashboards. We deliberately
 * avoid pulling in recharts/uPlot — the volume of data is small (≤30
 * days, ≤10 buckets) and the bundle hit isn't worth it. Two flavours:
 *
 *   <BarList>  — horizontal bars for "top X by Y" tables.
 *   <DualLine> — two-series line chart for daily timeseries.
 */

export interface BarListItem {
  label: string;
  value: number;
  hint?: string;
}

export function BarList({
  items,
  formatValue,
  emptyLabel = "—",
}: {
  items: BarListItem[];
  formatValue?: (n: number) => string;
  emptyLabel?: string;
}) {
  if (items.length === 0) {
    return (
      <div style={{ fontSize: 12, color: "var(--text-dim)", padding: "4px 0" }}>
        {emptyLabel}
      </div>
    );
  }
  const max = Math.max(1, ...items.map((i) => i.value));
  const fmt = formatValue ?? ((n: number) => n.toLocaleString());
  return (
    <div
      style={{ display: "flex", flexDirection: "column", gap: 6 }}
    >
      {items.map((item) => {
        const pct = (item.value / max) * 100;
        return (
          <div key={item.label} style={{ display: "grid", gap: 2 }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 12,
                color: "var(--text-muted)",
              }}
            >
              <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
                {item.label}
              </span>
              <span
                style={{
                  fontVariantNumeric: "tabular-nums",
                  color: "var(--text)",
                  fontWeight: 600,
                }}
                title={item.hint}
              >
                {fmt(item.value)}
              </span>
            </div>
            <div
              style={{
                height: 6,
                borderRadius: 3,
                background: "var(--surface-2, rgba(127,127,127,0.12))",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${pct}%`,
                  height: "100%",
                  background: "var(--accent)",
                  borderRadius: 3,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export interface DualLinePoint {
  label: string;
  a: number;
  b: number;
}

export function DualLine({
  points,
  aLabel,
  bLabel,
  height = 140,
}: {
  points: DualLinePoint[];
  aLabel: string;
  bLabel: string;
  height?: number;
}) {
  if (points.length === 0) {
    return (
      <div style={{ fontSize: 12, color: "var(--text-dim)" }}>—</div>
    );
  }
  const w = 560;
  const padX = 20;
  const padY = 18;
  const innerW = w - padX * 2;
  const innerH = height - padY * 2;
  const maxA = Math.max(1, ...points.map((p) => p.a));
  const maxB = Math.max(1, ...points.map((p) => p.b));
  const max = Math.max(maxA, maxB);
  const xStep = points.length > 1 ? innerW / (points.length - 1) : 0;
  const toY = (v: number) => padY + innerH - (v / max) * innerH;
  const path = (key: "a" | "b") =>
    points
      .map((p, i) => {
        const x = padX + i * xStep;
        const y = toY(p[key]);
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  return (
    <div>
      <svg
        viewBox={`0 0 ${w} ${height}`}
        width="100%"
        height={height}
        style={{ display: "block" }}
      >
        {/* baseline grid */}
        <line
          x1={padX}
          x2={w - padX}
          y1={padY + innerH}
          y2={padY + innerH}
          stroke="var(--border)"
        />
        <path
          d={path("a")}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={1.6}
        />
        <path
          d={path("b")}
          fill="none"
          stroke="#16A34A"
          strokeWidth={1.6}
          strokeDasharray="4 3"
        />
      </svg>
      <div
        style={{
          display: "flex",
          gap: 16,
          fontSize: 11,
          color: "var(--text-dim)",
          marginTop: 6,
        }}
      >
        <span>
          <span
            style={{
              display: "inline-block",
              width: 10,
              height: 2,
              background: "var(--accent)",
              verticalAlign: "middle",
              marginRight: 6,
            }}
          />
          {aLabel}
        </span>
        <span>
          <span
            style={{
              display: "inline-block",
              width: 10,
              height: 2,
              background: "#16A34A",
              verticalAlign: "middle",
              marginRight: 6,
            }}
          />
          {bLabel}
        </span>
      </div>
    </div>
  );
}
