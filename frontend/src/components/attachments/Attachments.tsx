import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileImage, FileText, LoaderCircle, Paperclip, Trash2, Upload } from "lucide-react";
import { useId, useState, type ChangeEvent } from "react";
import { errorMessage } from "@/api/errors";
import { deleteFile, downloadFile, listFiles, uploadFile } from "@/api/files";
import type { FileEntityType, FileRead } from "@/api/types";
import { Button } from "@/components/Button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { SkeletonList } from "@/components/Spinner";
import { useToast } from "@/components/toast/useToast";
import { cn } from "@/lib/cn";
import { formatDateTime, formatFileSize } from "@/lib/format";
import { isPreviewable, saveBlob } from "./blob";
import { FilePreviewDialog } from "./FilePreviewDialog";

export interface AttachmentsProps {
  entityType: FileEntityType;
  entityId: string;
  title?: string;
}

export const filesQueryKey = (entityType: FileEntityType, entityId: string) =>
  ["files", entityType, entityId] as const;

interface Preview {
  name: string;
  blob: Blob;
}

/** Attachments of one record: list, upload, preview/download and delete. */
export function Attachments({ entityType, entityId, title = "Anexos" }: AttachmentsProps) {
  const queryKey = filesQueryKey(entityType, entityId);
  const queryClient = useQueryClient();
  const toast = useToast();
  const inputId = useId();
  const headingId = useId();
  const [preview, setPreview] = useState<Preview | null>(null);
  const [pendingDelete, setPendingDelete] = useState<FileRead | null>(null);
  const [openingId, setOpeningId] = useState<string | null>(null);

  const files = useQuery({ queryKey, queryFn: () => listFiles(entityType, entityId) });

  const upload = useMutation({
    mutationFn: (file: File) => uploadFile(entityType, entityId, file),
    onSuccess: (created) => {
      toast.success(`"${created.original_name}" anexado.`);
      return queryClient.invalidateQueries({ queryKey });
    },
  });

  const remove = useMutation({
    mutationFn: (file: FileRead) => deleteFile(file.id),
    onSuccess: () => toast.success("Anexo excluído."),
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: () => {
      setPendingDelete(null);
      return queryClient.invalidateQueries({ queryKey });
    },
  });

  function onFileChosen(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // Allows choosing the same file again.
    if (file) upload.mutate(file);
  }

  async function open(file: FileRead, mode: "view" | "download") {
    setOpeningId(file.id);
    try {
      const blob = await downloadFile(file.id);
      if (mode === "view" && isPreviewable(blob)) setPreview({ name: file.original_name, blob });
      else saveBlob(blob, file.original_name);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setOpeningId(null);
    }
  }

  let content;
  if (files.isPending) {
    content = <SkeletonList rows={2} label="Carregando anexos..." />;
  } else if (files.isError) {
    content = (
      <ErrorState
        title="Não foi possível carregar os anexos"
        message={errorMessage(files.error)}
        onRetry={() => void files.refetch()}
      />
    );
  } else if (files.data.length === 0) {
    content = <EmptyState icon={Paperclip} title="Nenhum anexo." description="Anexe fotos, notas ou PDFs." />;
  } else {
    content = (
      <ul className="divide-y divide-slate-200">
        {files.data.map((file) => {
          const Icon = file.content_type.startsWith("image/") ? FileImage : FileText;
          const busy = openingId === file.id;
          return (
            <li key={file.id} className="flex items-center gap-2 py-2">
              <Icon aria-hidden="true" className="size-5 shrink-0 text-slate-500" />
              <div className="min-w-0 flex-1">
                <button
                  type="button"
                  onClick={() => void open(file, "view")}
                  disabled={busy}
                  className="block max-w-full truncate text-left font-medium text-brand-800 underline-offset-2 hover:underline"
                >
                  {file.original_name}
                </button>
                <p className="text-xs text-slate-600">
                  {formatFileSize(file.size_bytes)} · {formatDateTime(file.created_at)}
                </p>
              </div>
              {busy && <LoaderCircle aria-label="Abrindo..." className="size-4 animate-spin text-slate-500" />}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void open(file, "download")}
                disabled={busy}
                aria-label={`Baixar ${file.original_name}`}
              >
                <Download aria-hidden="true" className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setPendingDelete(file)}
                aria-label={`Excluir ${file.original_name}`}
                className="text-red-700 hover:bg-red-50"
              >
                <Trash2 aria-hidden="true" className="size-4" />
              </Button>
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <section aria-labelledby={headingId} className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={headingId} className="text-lg font-semibold">
          {title}
        </h2>
        {/* Native file input (keyboard and screen readers) with its label styled as the button. */}
        <div>
          <input
            id={inputId}
            type="file"
            className="peer sr-only"
            onChange={onFileChosen}
            disabled={upload.isPending}
          />
          <label
            htmlFor={inputId}
            className={cn(
              "inline-flex min-h-9 cursor-pointer items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm font-medium text-slate-800 hover:bg-slate-100",
              "peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-brand-700",
              "peer-disabled:cursor-not-allowed peer-disabled:text-slate-500",
            )}
          >
            {upload.isPending ? (
              <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
            ) : (
              <Upload aria-hidden="true" className="size-4" />
            )}
            {upload.isPending ? "Enviando..." : "Anexar arquivo"}
          </label>
        </div>
      </div>

      {upload.isError && (
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm font-medium text-red-800">
          {errorMessage(upload.error)}
        </p>
      )}

      {content}

      {preview && <FilePreviewDialog name={preview.name} blob={preview.blob} onClose={() => setPreview(null)} />}

      {pendingDelete && (
        <ConfirmDialog
          title="Excluir anexo?"
          message={`"${pendingDelete.original_name}" será excluído e não poderá ser recuperado.`}
          loading={remove.isPending}
          onConfirm={() => remove.mutate(pendingDelete)}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </section>
  );
}
