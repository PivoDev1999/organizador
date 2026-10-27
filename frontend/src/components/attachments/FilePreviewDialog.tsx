import { Download } from "lucide-react";
import { Button } from "@/components/Button";
import { Modal } from "@/components/Modal";
import { blobSource, mediaType, saveBlob } from "./blob";

export interface FilePreviewDialogProps {
  name: string;
  blob: Blob;
  onClose: () => void;
}

/**
 * Shows an image or PDF from a blob URL. The blob carries none of the response headers (such as the
 * API's `Content-Security-Policy: sandbox`), so Chrome's PDF viewer is not blocked.
 */
export function FilePreviewDialog({ name, blob, onClose }: FilePreviewDialogProps) {
  const isPdf = mediaType(blob) === "application/pdf";
  return (
    <Modal
      title={name}
      onClose={onClose}
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={() => saveBlob(blob, name)}>
            <Download aria-hidden="true" className="size-4" />
            Baixar
          </Button>
          <Button onClick={onClose}>Fechar</Button>
        </>
      }
    >
      {isPdf ? (
        <iframe ref={blobSource(blob)} title={`Pré-visualização de ${name}`} className="h-[70dvh] w-full rounded border" />
      ) : (
        <img ref={blobSource(blob)} alt={name} className="mx-auto max-h-[70dvh] max-w-full object-contain" />
      )}
    </Modal>
  );
}
