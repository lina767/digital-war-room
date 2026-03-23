export function formatDTG(date: Date): string {
  const day = String(date.getUTCDate()).padStart(2, "0");
  const hour = String(date.getUTCHours()).padStart(2, "0");
  const minute = String(date.getUTCMinutes()).padStart(2, "0");
  const month = date.toLocaleString("en-US", { month: "short", timeZone: "UTC" }).toUpperCase();
  const year = String(date.getUTCFullYear());
  return `${day}${hour}${minute}Z${month}${year}`;
}
