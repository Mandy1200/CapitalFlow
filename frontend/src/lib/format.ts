import type { Money } from "../types";

/**
 * Format a decimal string as US dollars without going through floating point:
 * "25000.00" -> "$25,000.00", "-25" -> "-$25.00".
 */
export function formatMoney(value: Money): string {
  const trimmed = value.trim();
  const negative = trimmed.startsWith("-");
  const [whole = "0", fraction = ""] = trimmed.replace(/^[-+]/, "").split(".");
  const grouped = whole.replace(/^0+(?=\d)/, "").replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const cents = (fraction + "00").slice(0, 2);
  return `${negative ? "-" : ""}$${grouped}.${cents}`;
}

/** Sum decimal strings exactly using integer cents (BigInt). */
export function sumMoney(values: Money[]): Money {
  const total = values.reduce((acc, value) => acc + toCents(value), 0n);
  const negative = total < 0n;
  const abs = negative ? -total : total;
  const whole = abs / 100n;
  const cents = (abs % 100n).toString().padStart(2, "0");
  return `${negative ? "-" : ""}${whole}.${cents}`;
}

export function toCents(value: Money): bigint {
  const trimmed = value.trim();
  const negative = trimmed.startsWith("-");
  const [whole = "0", fraction = ""] = trimmed.replace(/^[-+]/, "").split(".");
  const cents = BigInt(whole || "0") * 100n + BigInt((fraction + "00").slice(0, 2));
  return negative ? -cents : cents;
}

export function formatDate(iso: string): string {
  // Dates are calendar dates (YYYY-MM-DD); format without timezone shifts.
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}
