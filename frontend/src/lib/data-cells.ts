// Database values as people read them: 19209.94 is "19 209,94" in
// Portuguese and "19,209.94" in English. Codes with a leading zero
// ("018") and text stay as they came.

const NUMBER = /^-?(0|[1-9]\d*)(\.\d+)?$/;

export type Cell = string | number | boolean | null;

export function isNumberCell(value: Cell): boolean {
  if (typeof value === "number") return Number.isFinite(value);
  return typeof value === "string" && NUMBER.test(value.trim());
}

export function cellText(value: Cell, locale: string): string {
  if (value === null) return "";
  if (!isNumberCell(value)) return String(value);
  const text = String(value).trim();
  const decimals = text.includes(".") ? text.split(".")[1]!.length : 0;
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(Number(text));
}

/** Columns whose values are all numbers are aligned to the right. */
export function numberColumns(rows: Cell[][], width: number): boolean[] {
  return Array.from({ length: width }, (_, index) => {
    const values = rows.map((row) => row[index] ?? null).filter((value) => value !== null && value !== "");
    return values.length > 0 && values.every(isNumberCell);
  });
}
