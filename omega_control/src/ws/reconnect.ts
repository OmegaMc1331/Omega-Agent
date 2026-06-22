export function reconnectDelay(attempt: number): number {
  const capped = Math.min(Math.max(attempt, 0), 6);
  return Math.min(1000 * 2 ** capped, 15000);
}
