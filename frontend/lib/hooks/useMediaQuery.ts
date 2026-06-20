"use client";

import { useEffect, useState } from "react";

/**
 * SSR-safe media-query hook. Returns ``false`` during server render and
 * before the first client mount, then subscribes to ``matchMedia`` and
 * tracks changes. Cleans up its listener on unmount.
 *
 * The codebase styles with inline ``style`` objects rather than Tailwind
 * breakpoint classes, so responsive behaviour is driven by this hook plus
 * conditional inline styles.
 *
 * ```tsx
 * const isMobile = useIsMobile();
 * <div style={{ gridTemplateColumns: isMobile ? "1fr" : "1.6fr 1fr" }} />
 * ```
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia(query);
    const update = () => setMatches(mql.matches);
    update();
    mql.addEventListener("change", update);
    return () => {
      mql.removeEventListener("change", update);
    };
  }, [query]);

  return matches;
}

/** Convenience wrapper for the phone breakpoint (<= 768px). */
export function useIsMobile(): boolean {
  return useMediaQuery("(max-width: 768px)");
}
