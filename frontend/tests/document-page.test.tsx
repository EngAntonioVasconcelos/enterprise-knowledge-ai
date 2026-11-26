import { render, screen } from "@testing-library/react";

import { DocumentPageView } from "@/components/documents/DocumentPageView";
import type { DocumentPage } from "@/lib/api-types";

const ORG = "11111111-1111-4111-8111-111111111111";

const PAGE: DocumentPage = {
  document: {
    id: "d1",
    connection_id: "c",
    title: "Manual do Colaborador.pdf",
    mime_type: "application/pdf",
    status: "active",
    last_synced_at: null,
    updated_at: "2026-11-20T09:00:00Z",
    source: { provider: "google_drive", name: "Drive" },
    audience: "source",
  },
  read_at: "2026-11-20T09:00:00Z",
  passages: 12,
  excerpt: [{ heading: "1. F\u00e9rias", content: "Cada colaborador tem direito a 25 dias \u00fateis de f\u00e9rias." }],
  failure: null,
};

describe("DocumentPageView", () => {
  it("shows what it is, where it comes from, who sees it and how it was read", () => {
    render(<DocumentPageView organizationId={ORG} page={PAGE} />);
    expect(screen.getByRole("heading", { level: 1, name: "Manual do Colaborador.pdf" })).toBeInTheDocument();
    expect(screen.getByText("Google Drive")).toBeInTheDocument();
    expect(screen.getByText("Como na origem")).toBeInTheDocument();
    expect(screen.getByText(/de 12 excertos/)).toBeInTheDocument();
    expect(screen.getByText(/25 dias \u00fateis/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voltar aos documentos" })).toHaveAttribute("href", `/documentos?org=${ORG}`);
  });

  it("says why the last reading failed", () => {
    render(<DocumentPageView organizationId={ORG} page={{ ...PAGE, failure: "The PDF could not be read" }} />);
    expect(screen.getByText("A \u00faltima leitura falhou:")).toBeInTheDocument();
    expect(screen.getByText("The PDF could not be read")).toBeInTheDocument();
  });

  it("shows a document the person cannot open as not found", () => {
    render(<DocumentPageView organizationId={ORG} page={null} />);
    expect(screen.getByText("Documento n\u00e3o encontrado")).toBeInTheDocument();
    expect(screen.queryByText("Manual do Colaborador.pdf")).not.toBeInTheDocument();
  });
});
