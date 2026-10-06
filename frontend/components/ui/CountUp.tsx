"use client";

import { useEffect, useRef, useState } from "react";

const reducedMotion = () =>
  typeof window !== "undefined" &&
  !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Число, которое досчитывает до значения: с нуля при первом показе,
 * от прежнего значения при обновлении. */
export function CountUp({
  value,
  format = (n) => Math.round(n).toLocaleString("ru-RU"),
  duration = 1000,
}: {
  value: number;
  format?: (n: number) => string;
  duration?: number;
}) {
  const [shown, setShown] = useState(0);
  const shownRef = useRef(shown);
  const first = useRef(true);

  useEffect(() => {
    if (reducedMotion()) {
      shownRef.current = value;
      setShown(value);
      return;
    }
    const from = shownRef.current;
    const dur = first.current ? duration : 600;
    first.current = false;
    if (from === value) return;
    const t0 = performance.now();
    let raf = 0;
    const step = (t: number) => {
      const p = Math.min(1, (t - t0) / dur);
      const e = 1 - Math.pow(1 - p, 3);
      const v = from + (value - from) * e;
      shownRef.current = v;
      setShown(v);
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);

  return <span style={{ fontVariantNumeric: "tabular-nums" }}>{format(shown)}</span>;
}
