// Dates arrive as ISO strings (UTC). Formatting stays in UTC so a Monday never shifts a day.
export const shortDay = (iso: string) =>
  new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

export const longDay = (iso: string) =>
  new Date(iso).toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
