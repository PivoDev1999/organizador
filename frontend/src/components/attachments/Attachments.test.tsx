import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { FileRead } from "@/api/types";
import { jsonResponse, mockApi, renderWithProviders } from "@/test/utils";
import { Attachments } from "./Attachments";

const TASK_ID = "22222222-2222-4222-8222-222222222222";

const file = (id: string, name: string, size: number): FileRead => ({
  id,
  entity_type: "task",
  entity_id: TASK_ID,
  original_name: name,
  content_type: "application/pdf",
  size_bytes: size,
  created_at: "2026-10-20T15:00:00Z",
});

describe("Attachments", () => {
  it("lists the files, shows the API message on 413 and uploads as multipart", async () => {
    let stored = [file("f1", "garantia.pdf", 2048)];
    let uploads = 0;
    const requests = mockApi({
      "GET /api/files": () => jsonResponse(stored),
      "POST /api/files": () => {
        uploads += 1;
        if (uploads === 1) return jsonResponse({ detail: "O conteúdo enviado é grande demais." }, 413);
        const created = file("f2", "nota.pdf", 512);
        stored = [created, ...stored];
        return jsonResponse(created, 201);
      },
    });
    renderWithProviders(<Attachments entityType="task" entityId={TASK_ID} />);
    const user = userEvent.setup();

    const list = await screen.findByRole("list");
    expect(within(list).getByRole("button", { name: "garantia.pdf" })).toBeInTheDocument();
    expect(within(list).getByText(/2 KB/)).toBeInTheDocument();
    expect(requests[0]?.url).toBe(`/api/files?entity_type=task&entity_id=${TASK_ID}`);

    const input = screen.getByLabelText("Anexar arquivo");
    await user.upload(input, new File(["x".repeat(10)], "enorme.pdf", { type: "application/pdf" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("O conteúdo enviado é grande demais.");

    await user.upload(input, new File(["%PDF-1.7"], "nota.pdf", { type: "application/pdf" }));
    expect(await within(list).findByRole("button", { name: "nota.pdf" })).toBeInTheDocument();
    expect(screen.queryByText("O conteúdo enviado é grande demais.")).not.toBeInTheDocument();

    const body = requests.filter((r) => r.method === "POST").at(-1)?.body as FormData;
    expect(body.get("entity_type")).toBe("task");
    expect(body.get("entity_id")).toBe(TASK_ID);
    expect((body.get("file") as File).name).toBe("nota.pdf");
    expect(requests.at(-1)?.headers.get("Authorization")).toBeNull(); // no token in this test
  });
});
