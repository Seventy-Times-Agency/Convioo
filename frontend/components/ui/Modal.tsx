"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children?: ReactNode;
  /** Footer row — usually the action buttons. */
  footer?: ReactNode;
  width?: number;
}

/** Centered dialog on a dimmed scrim. Esc / scrim click closes.
 * Replaces every native prompt()/confirm() surface per the etalon. */
export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  width = 440,
}: ModalProps) {
  const scrimRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      ref={scrimRef}
      onMouseDown={(e) => {
        if (e.target === scrimRef.current) onClose();
      }}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(30, 27, 22, 0.45)",
        zIndex: 120,
        display: "grid",
        placeItems: "center",
        padding: 16,
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="card"
        style={{
          width: "100%",
          maxWidth: width,
          padding: 24,
          boxShadow: "var(--shadow-lg)",
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
      >
        {title != null && (
          <div style={{ fontSize: 16, fontWeight: 700 }}>{title}</div>
        )}
        {children}
        {footer != null && (
          <div
            style={{
              display: "flex",
              gap: 8,
              justifyContent: "flex-end",
              flexWrap: "wrap",
            }}
          >
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
