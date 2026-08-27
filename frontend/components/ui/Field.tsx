"use client";

import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

interface FieldChrome {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
}

function FieldWrap({
  id,
  label,
  hint,
  error,
  children,
}: FieldChrome & { id: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {label != null && (
        <label
          htmlFor={id}
          style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-muted)" }}
        >
          {label}
        </label>
      )}
      {children}
      {error != null ? (
        <div style={{ fontSize: 12, color: "var(--cold)" }}>{error}</div>
      ) : hint != null ? (
        <div style={{ fontSize: 12, color: "var(--text-dim)" }}>{hint}</div>
      ) : null}
    </div>
  );
}

export interface InputProps
  extends InputHTMLAttributes<HTMLInputElement>,
    FieldChrome {}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, className, id: idProp, ...rest },
  ref,
) {
  const autoId = useId();
  const id = idProp ?? autoId;
  return (
    <FieldWrap id={id} label={label} hint={hint} error={error}>
      <input
        ref={ref}
        id={id}
        className={["input", className ?? ""].filter(Boolean).join(" ")}
        style={error != null ? { borderColor: "var(--cold)" } : undefined}
        {...rest}
      />
    </FieldWrap>
  );
});

export interface SelectProps
  extends SelectHTMLAttributes<HTMLSelectElement>,
    FieldChrome {}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  function Select({ label, hint, error, className, id: idProp, children, ...rest }, ref) {
    const autoId = useId();
    const id = idProp ?? autoId;
    return (
      <FieldWrap id={id} label={label} hint={hint} error={error}>
        <select
          ref={ref}
          id={id}
          className={["select", className ?? ""].filter(Boolean).join(" ")}
          {...rest}
        >
          {children}
        </select>
      </FieldWrap>
    );
  },
);

export interface TextareaProps
  extends TextareaHTMLAttributes<HTMLTextAreaElement>,
    FieldChrome {}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  function Textarea({ label, hint, error, className, id: idProp, ...rest }, ref) {
    const autoId = useId();
    const id = idProp ?? autoId;
    return (
      <FieldWrap id={id} label={label} hint={hint} error={error}>
        <textarea
          ref={ref}
          id={id}
          className={["textarea", className ?? ""].filter(Boolean).join(" ")}
          {...rest}
        />
      </FieldWrap>
    );
  },
);
