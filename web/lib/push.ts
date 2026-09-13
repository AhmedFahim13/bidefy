export type Filter = { q?: string; ministry?: string; status?: string; district?: string; category?: string };
export type SavedSubscription = { id: string; filters: Filter[] };
const KEY = "bidefy.sub";

export function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

export function loadSaved(): SavedSubscription | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as SavedSubscription) : null;
  } catch {
    return null;
  }
}

export function pushSupported(): boolean {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

export async function subscribeToPush(apiBase: string, filters: Filter[]): Promise<SavedSubscription> {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Notifications were not allowed in the browser.");
  const reg = await navigator.serviceWorker.ready;
  const { key } = (await (await fetch(`${apiBase}/api/v1/push/public-key`)).json()) as { key: string };
  if (!key) throw new Error("The alert service has no public key configured.");
  const existing = await reg.pushManager.getSubscription();
  const sub = existing ?? (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(key) as BufferSource }));
  const r = await fetch(`${apiBase}/api/v1/subscriptions`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ subscription: sub.toJSON(), filters }),
  });
  if (!r.ok) {
    const err = (await r.json().catch(() => ({}))) as { error?: string };
    throw new Error(err.error ?? "The alert service rejected the subscription.");
  }
  const data = (await r.json()) as { id: string };
  const saved = { id: data.id, filters };
  try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch { /* private mode */ }
  return saved;
}

export async function unsubscribeFromPush(apiBase: string): Promise<void> {
  const saved = loadSaved();
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  if (sub) await sub.unsubscribe();
  if (saved) await fetch(`${apiBase}/api/v1/subscriptions/${saved.id}`, { method: "DELETE" }).catch(() => undefined);
  try { localStorage.removeItem(KEY); } catch { /* ignore */ }
}
