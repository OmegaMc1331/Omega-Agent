export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  });
  if (!response.ok) {
    const text = await response.text();
    try {
      const payload = JSON.parse(text);
      const detail = Array.isArray(payload.detail)
        ? payload.detail.map((item: { msg?: string }) => item.msg || JSON.stringify(item)).join(', ')
        : payload.detail || payload.message || text;
      throw new Error(detail);
    } catch (error) {
      if (error instanceof Error && error.message && error.message !== text) throw error;
      throw new Error(text || `HTTP ${response.status}`);
    }
  }
  return response.json() as Promise<T>;
}
