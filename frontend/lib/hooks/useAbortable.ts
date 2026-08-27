"use client";

import { useEffect, useRef } from "react";

/**
 * Returns a function that allocates a fresh ``AbortController`` for the
 * current effect run, aborts any previous one, and cleans up on unmount.
 *
 * Use this to attach ``signal`` to API requests so stale responses from
 * a previous render (filter change, route change) don't overwrite fresh
 * state with old data.
 *
 * ```tsx
 * const newAbort = useAbortable();
 * useEffect(() => {
 *   const { signal } = newAbort();
 *   listLeads({ status }, { signal })
 *     .then(setLeads)
 *     .catch((err) => {
 *       if (err?.name === "AbortError") return;
 *       toast.error(String(err));
 *     });
 * }, [status, newAbort]);
 * ```
 */
export function useAbortable(): () => AbortController {
  const ctrlRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      ctrlRef.current?.abort();
      ctrlRef.current = null;
    };
  }, []);

  return () => {
    ctrlRef.current?.abort();
    const next = new AbortController();
    ctrlRef.current = next;
    return next;
  };
}

export function isAbortError(err: unknown): boolean {
  return (
    err instanceof DOMException
      ? err.name === "AbortError"
      : err instanceof Error && err.name === "AbortError"
  );
}
