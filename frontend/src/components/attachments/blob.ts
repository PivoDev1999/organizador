/** Types the browser may show in the preview. Anything else (SVG, HTML...) is only downloaded. */
const PREVIEWABLE = new Set(["image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf"]);

// Time to keep a download's blob URL alive: revoking right after click() can cancel the download in
// some browsers. The blob is freed after that.
const DOWNLOAD_REVOKE_DELAY_MS = 10_000;

export function mediaType(blob: Blob): string {
  return blob.type.split(";")[0]?.trim().toLowerCase() ?? "";
}

/**
 * Previewable only if the API sent a safe type. Downloads use `?inline=true`, so the API reports the
 * type checked by the file's first bytes for JPEG/PNG/GIF/WebP/PDF and octet-stream for the rest.
 */
export function isPreviewable(blob: Blob): boolean {
  return PREVIEWABLE.has(mediaType(blob));
}

/** Saves the blob through a temporary `<a download>` link and revokes its URL afterwards. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), DOWNLOAD_REVOKE_DELAY_MS);
}

/**
 * React 19 ref callback that points an <img>/<iframe> at a blob URL and revokes it on unmount.
 * Created per element, so StrictMode's double mount gets a fresh URL instead of a revoked one.
 */
export function blobSource(blob: Blob) {
  return (element: HTMLImageElement | HTMLIFrameElement | null) => {
    if (!element) return;
    const url = URL.createObjectURL(blob);
    element.src = url;
    return () => URL.revokeObjectURL(url);
  };
}
