"use client";

import { useEffect, useState } from "react";

// Module-level subscribers list. We avoid Context here because the
// hamburger button lives in the topbar (rendered inside a /app page)
// and the sidebar lives in the /app/layout — wrapping both in a
// provider would require touching every page. A pub/sub keeps the
// dependency one-directional and tiny.
let _open = false;
const _listeners = new Set<(open: boolean) => void>();

function _publish() {
  for (const fn of _listeners) fn(_open);
}

export function openMobileNav(): void {
  if (_open) return;
  _open = true;
  _publish();
}

export function closeMobileNav(): void {
  if (!_open) return;
  _open = false;
  _publish();
}

export function toggleMobileNav(): void {
  _open = !_open;
  _publish();
}

/**
 * Subscribe to mobile-nav open state. Returns the current value.
 * Components that need to render differently when the drawer is open
 * (sidebar slide-in, scrim) read this; components that drive it
 * (hamburger button) call ``toggleMobileNav`` / ``closeMobileNav``.
 */
export function useMobileNav(): boolean {
  const [open, setOpen] = useState(_open);
  useEffect(() => {
    _listeners.add(setOpen);
    return () => {
      _listeners.delete(setOpen);
    };
  }, []);
  return open;
}
