/** Preserve arbitrary supported monetary precision; never round through Number. */
export function money(value: unknown): string {
  if (typeof value !== "string" || !/^\d+(?:\.\d{1,2})?$/.test(value)) return "Amount unavailable";
  const [whole, fraction = ""] = value.split(".");
  return `PKR ${BigInt(whole).toLocaleString("en-US")}.${fraction.padEnd(2, "0")}`;
}
export function dateOnly(value: unknown): string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return "Date unavailable";
  const [year, month, day] = value.split("-");
  return `${day} ${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(month) - 1]} ${year}`;
}
export function timestamp(value: string): string {
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(value)) + " UTC";
}
export function identifier(value: string): string { return value.slice(0, 8).toUpperCase(); }
