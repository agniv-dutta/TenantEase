/** Small formatting helpers. Numbers are formatted with the en-IN locale. */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function formatINR(value: number): string {
  return "₹" + value.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

export function formatDate(iso: string): string {
  const d = new Date(iso + (iso.length === 10 ? "T00:00:00" : ""));
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

export function monthShort(iso: string): string {
  const d = new Date(iso + (iso.length === 10 ? "T00:00:00" : ""));
  return MONTHS[d.getMonth()];
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function weekdayDate(iso: string): string {
  const d = new Date(iso + (iso.length === 10 ? "T00:00:00" : ""));
  return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

export function percent(p: number): string {
  return `${Math.round(p * 100)}%`;
}

export function roundedPercent5(p: number): number {
  return Math.max(0, Math.min(100, Math.round((p * 100) / 5) * 5));
}

export function aboutPercentText(p: number): string {
  return `about ${roundedPercent5(p)} percent`;
}
