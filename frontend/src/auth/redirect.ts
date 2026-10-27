/** Login URL that brings the user back to `from` afterwards. */
export function loginPath(from: string): string {
  return from === "/" ? "/login" : `/login?next=${encodeURIComponent(from)}`;
}

/** Only same-app paths are accepted as `next` ("/tarefas"), never "//host" or "https://...". */
export function safeNext(next: string | null): string {
  // Browsers drop tabs/newlines and treat a backslash as "/", so "/<tab>/evil.com" becomes "//evil.com".
  if (!next || !next.startsWith("/") || next.startsWith("//") || /[\t\r\n\\]/.test(next)) return "/";
  return next;
}
