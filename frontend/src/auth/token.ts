// The only module that touches localStorage. Everything else reads the session token through here.
const TOKEN_KEY = "organizador.token";

type Listener = () => void;
const listeners = new Set<Listener>();

function notify(): void {
  for (const listener of listeners) listener();
}

function onStorage(event: StorageEvent): void {
  // Login or logout in another tab.
  if (event.key === TOKEN_KEY || event.key === null) notify();
}

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    // Storage blocked (private mode, browser policy): behave as logged out.
    return null;
  }
}

export function setToken(token: string): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } finally {
    notify();
  }
}

export function clearToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } finally {
    notify();
  }
}

/** Subscribes to token changes (this tab and others). Shaped for `useSyncExternalStore`. */
export function subscribeToken(listener: Listener): () => void {
  if (listeners.size === 0) window.addEventListener("storage", onStorage);
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) window.removeEventListener("storage", onStorage);
  };
}
