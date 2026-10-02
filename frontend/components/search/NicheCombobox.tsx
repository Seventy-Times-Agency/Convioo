"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

interface NicheTaxonomyEntry {
  id: string;
  label: string;
  category: string | null;
}

interface NicheTaxonomyResponse {
  items: NicheTaxonomyEntry[];
  query: string;
  language: string;
}

interface Props {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  language?: string;
}

/**
 * Niche combobox: free-text input + suggestions dropdown driven by
 * ``GET /api/v1/niches``. The user can either pick a curated taxonomy
 * label or just type whatever — the field never blocks free input,
 * the dropdown is purely additive.
 */
export function NicheCombobox({
  value,
  onChange,
  placeholder,
  language,
}: Props) {
  const [items, setItems] = useState<NicheTaxonomyEntry[]>([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();

  // Cancel stale in-flight requests so out-of-order responses can't
  // overwrite the dropdown after the user typed past them.
  const lastFetchKey = useRef(0);

  const fetchSuggestions = useCallback(
    async (query: string) => {
      const myKey = ++lastFetchKey.current;
      const params = new URLSearchParams();
      if (query) params.set("q", query);
      if (language) params.set("lang", language);
      params.set("limit", "12");
      try {
        const res = await fetch(`/api/v1/niches?${params.toString()}`, {
          credentials: "include",
        });
        if (!res.ok) return;
        const body = (await res.json()) as NicheTaxonomyResponse;
        if (myKey !== lastFetchKey.current) return; // stale
        setItems(body.items);
        setHighlight(body.items.length > 0 ? 0 : -1);
      } catch {
        // Network blip — keep whatever the dropdown already shows.
      }
    },
    [language],
  );

  // Debounce the actual fetch so every keystroke isn't a roundtrip.
  useEffect(() => {
    if (!open) return;
    const handle = window.setTimeout(() => {
      void fetchSuggestions(value.trim());
    }, 180);
    return () => window.clearTimeout(handle);
  }, [value, open, fetchSuggestions]);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", handler);
    return () => window.removeEventListener("mousedown", handler);
  }, [open]);

  const pick = (entry: NicheTaxonomyEntry) => {
    onChange(entry.label);
    setOpen(false);
    setHighlight(-1);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      setHighlight((h) => Math.min(items.length - 1, h + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(0, h - 1));
    } else if (e.key === "Enter") {
      if (open && highlight >= 0 && items[highlight]) {
        e.preventDefault();
        pick(items[highlight]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div ref={containerRef} style={{ position: "relative" }}>
      <input
        ref={inputRef}
        className="input"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => {
          setOpen(true);
          if (items.length === 0) void fetchSuggestions(value.trim());
        }}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        aria-controls={listboxId}
        aria-activedescendant={
          open && highlight >= 0 ? `${listboxId}-${highlight}` : undefined
        }
      />
      {open && items.length > 0 && (
        <ul
          id={listboxId}
          role="listbox"
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            marginTop: 4,
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 10,
            boxShadow: "0 8px 24px rgba(15,15,20,0.10)",
            padding: 4,
            zIndex: 10,
            maxHeight: 280,
            overflowY: "auto",
            listStyle: "none",
            margin: 0,
            display: "flex",
            flexDirection: "column",
            gap: 2,
          }}
        >
          {items.map((entry, idx) => {
            const active = idx === highlight;
            return (
              <li
                id={`${listboxId}-${idx}`}
                key={entry.id}
                role="option"
                aria-selected={active}
                onMouseDown={(e) => {
                  // ``mousedown`` fires before ``blur`` — picking the
                  // entry without losing focus prevents the dropdown
                  // from disappearing in the gap.
                  e.preventDefault();
                  pick(entry);
                }}
                onMouseEnter={() => setHighlight(idx)}
                style={{
                  padding: "7px 10px",
                  borderRadius: 8,
                  cursor: "pointer",
                  background: active ? "var(--accent-soft)" : "transparent",
                  color: active ? "var(--accent)" : "var(--text)",
                  fontSize: 13.5,
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: 8,
                }}
              >
                <span>{entry.label}</span>
                {entry.category && (
                  <span
                    style={{
                      fontSize: 11,
                      color: "var(--text-dim)",
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    {entry.category}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
