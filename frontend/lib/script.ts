/**
 * Нарезка скрипта воронки на секции и подстановка данных лида.
 *
 * Скрипт пишется свободным текстом; секцией считается строка, целиком
 * в ВЕРХНЕМ РЕГИСТРЕ (с пояснением в скобках или после точки:
 * «ПРИНЦИПЫ. Слушать больше…», «ВОПРОСЫ (слушать, не перебивать):»).
 * Без таких строк — одна секция.
 */

export interface ScriptSection {
  title: string;
  /** Короткая подпись из скобок/после точки в заголовке. */
  hint: string | null;
  lines: string[];
}

export interface ScriptPlaceholders {
  /** Имя ЛПР — первое `[Имя]` в скрипте. */
  contactName?: string | null;
  company?: string | null;
  /** Боль/заход из анализа — подставляется вместо `[боль]`. */
  pain?: string | null;
}

// Заголовок — непрерывный ряд ЗАГЛАВНЫХ слов в начале строки, дальше
// необязательная скобка-подсказка, точка или двоеточие и текст.
const HEADER_RE =
  /^\s*([A-ZА-ЯЁІЇЄҐ][A-ZА-ЯЁІЇЄҐ\-–]*(?:\s+[A-ZА-ЯЁІЇЄҐ][A-ZА-ЯЁІЇЄҐ\-–]*)*)(?:\s*\(([^)]*)\))?\s*[.:]?\s*(.*)$/;

function isUpper(s: string): boolean {
  const letters = s.replace(/[^A-Za-zА-Яа-яЁёІіЇїЄєҐґ]/g, "");
  return letters.length >= 3 && letters === letters.toUpperCase();
}

function titleCase(s: string): string {
  const t = s.trim().toLowerCase();
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export function parseScript(script: string | null | undefined): ScriptSection[] {
  if (!script) return [];
  const sections: ScriptSection[] = [];
  let cur: ScriptSection | null = null;
  for (const raw of script.split("\n")) {
    const line = raw.replace(/^\s*\d+[.)]\s*/, "").trimEnd();
    if (!line.trim()) continue;
    const m = HEADER_RE.exec(line);
    if (m && isUpper(m[1])) {
      cur = { title: titleCase(m[1]), hint: m[2]?.trim() || null, lines: [] };
      sections.push(cur);
      const rest = (m[3] ?? "").trim();
      if (rest) cur.lines.push(rest);
      continue;
    }
    if (!cur) {
      cur = { title: "", hint: null, lines: [] };
      sections.push(cur);
    }
    cur.lines.push(line.trim());
  }
  return sections;
}

export type ScriptChunk = { text: string; mark: boolean };

/** Разбить строку на обычный текст и подставленные куски. */
export function fillLine(line: string, ph: ScriptPlaceholders, state: { nameUsed: boolean }): ScriptChunk[] {
  const out: ScriptChunk[] = [];
  const re = /\[(Имя|имя|Компания|компания|боль|Боль|день|День)\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(line)) !== null) {
    if (m.index > last) out.push({ text: line.slice(last, m.index), mark: false });
    const key = m[1].toLowerCase();
    let val: string | null = null;
    if (key === "имя" && !state.nameUsed && ph.contactName) {
      val = ph.contactName;
      state.nameUsed = true;
    } else if (key === "компания" && ph.company) {
      val = ph.company;
    } else if (key === "боль" && ph.pain) {
      val = ph.pain;
    }
    out.push(val ? { text: val, mark: true } : { text: m[0], mark: false });
    last = m.index + m[0].length;
  }
  if (last < line.length) out.push({ text: line.slice(last), mark: false });
  return out;
}
