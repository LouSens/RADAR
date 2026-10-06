export function formatPrice(value: number): string {
  const digits = value >= 1000 ? 0 : value >= 10 ? 2 : 4;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

/** A signed percentage such as "+1.24%". The input is a fraction (0.0124). */
export function formatChange(fraction: number): string {
  const sign = fraction > 0 ? "+" : fraction < 0 ? "−" : "";
  return `${sign}${Math.abs(fraction * 100).toFixed(2)}%`;
}

export function formatShare(fraction: number, digits = 2): string {
  return `${(fraction * 100).toFixed(digits)}%`;
}

/** An amount of money, as opposed to a price: always cents, or whole dollars when large. */
export function formatMoney(value: number): string {
  const digits = Math.abs(value) >= 1000 ? 0 : 2;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}
