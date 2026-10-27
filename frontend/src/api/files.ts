import { apiFetch, apiFetchBlob } from "./client";
import type { FileEntityType, FileRead } from "./types";

export function listFiles(entityType: FileEntityType, entityId: string): Promise<FileRead[]> {
  return apiFetch("/api/files", { query: { entity_type: entityType, entity_id: entityId } });
}

export function uploadFile(entityType: FileEntityType, entityId: string, file: File): Promise<FileRead> {
  const form = new FormData();
  form.append("entity_type", entityType);
  form.append("entity_id", entityId);
  form.append("file", file);
  return apiFetch("/api/files", { method: "post", body: form });
}

/**
 * Downloads the content. `inline=true` makes the API report the real type (checked by the file's
 * first bytes) only for JPEG, PNG, GIF, WebP and PDF; anything else comes as application/octet-stream.
 */
export function downloadFile(fileId: string): Promise<Blob> {
  return apiFetchBlob("/api/files/{file_id}/download", {
    params: { file_id: fileId },
    query: { inline: true },
  });
}

export function deleteFile(fileId: string): Promise<undefined> {
  return apiFetch("/api/files/{file_id}", { method: "delete", params: { file_id: fileId } });
}
