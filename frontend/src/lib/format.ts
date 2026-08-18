// Formatting helpers. Payroll here is Indian (₹, PF/ESI/TDS), so money uses the
// Indian grouping (lakh/crore) via Intl 'en-IN'.

const INR0 = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0
});

export function inr(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return INR0.format(n);
}

/** Signed money with a true minus sign, for deltas. */
export function inrSigned(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const sign = n > 0 ? "+" : n < 0 ? "−" : "";
  return `${sign}${INR0.format(Math.abs(n))}`;
}

/** Compact money for headline tiles: ₹1.2L, ₹3.45Cr. */
export function inrCompact(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const abs = Math.abs(n);
  const sign = n < 0 ? "−" : "";
  if (abs >= 1e7) return `${sign}₹${(abs / 1e7).toFixed(2)}Cr`;
  if (abs >= 1e5) return `${sign}₹${(abs / 1e5).toFixed(2)}L`;
  if (abs >= 1e3) return `${sign}₹${(abs / 1e3).toFixed(1)}K`;
  return `${sign}₹${abs.toFixed(0)}`;
}

export function pct(n: number | null | undefined, decimals = 1): string {
  if (n === null || n === undefined || Number.isNaN(n) || !Number.isFinite(n)) return "—";
  const sign = n > 0 ? "+" : n < 0 ? "−" : "";
  return `${sign}${Math.abs(n).toFixed(decimals)}%`;
}

export function count(n: number): string {
  return new Intl.NumberFormat("en-IN").format(n);
}

export function displayCell(v: string | number | boolean | null): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return new Intl.NumberFormat("en-IN").format(v);
  return String(v);
}
