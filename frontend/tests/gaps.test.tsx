import { render, screen } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  usePathname: () => "/lacunas",
  useSearchParams: () => new URLSearchParams(""),
}));

import { GapsView } from "@/components/dashboard/GapsView";
import { AppNav } from "@/components/shell/AppNav";
import type { GapsData } from "@/lib/api-types";

const ORG = "11111111-1111-4111-8111-111111111111";

const data: GapsData = {
  days: 30,
  unanswered: 6,
  reasons: { no_sources: 2, not_found: 3, checks: 0, not_relevant: 1 },
  documents: [{ document_id: "a", title: "Regulamento de F\u00e9rias", questions: 4 }],
  hidden_documents: 2,
  min_questions: 3,
};

describe("GapsView", () => {
  it("says why and where, never who or what", () => {
    render(<GapsView organizationId={ORG} data={data} />);
    expect(screen.getByText(/Nunca mostra quem perguntou/)).toBeInTheDocument();
    expect(screen.getByText("6 perguntas sem resposta segura")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Nenhum documento sobre o assunto" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Resposta sobre outro assunto" })).toBeInTheDocument();
    expect(screen.getByText("Regulamento de F\u00e9rias")).toBeInTheDocument();
    expect(screen.getByText("4 perguntas")).toBeInTheDocument();
    expect(screen.getByText(/a partir de 3 perguntas/)).toBeInTheDocument();
    expect(screen.getByText("Mais 2 documentos que n\u00e3o podes abrir.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Adicionar ou atualizar documentos" })).toHaveAttribute(
      "href",
      `/documentos?org=${ORG}`,
    );
  });

  it("is calm when there are no gaps", () => {
    render(
      <GapsView
        organizationId={ORG}
        data={{ ...data, unanswered: 0, reasons: { no_sources: 0, not_found: 0, checks: 0, not_relevant: 0 }, documents: [], hidden_documents: 0 }}
      />,
    );
    expect(screen.getByRole("heading", { name: "Sem lacunas nos \u00faltimos 30 dias" })).toBeInTheDocument();
    expect(screen.queryByText("Porqu\u00ea")).toBeNull();
  });

  it("says so when no document reached the minimum", () => {
    render(<GapsView organizationId={ORG} data={{ ...data, documents: [], hidden_documents: 0 }} />);
    expect(screen.getByText("Nenhum documento chegou a 3 perguntas sem resposta segura.")).toBeInTheDocument();
  });
});

describe("AppNav", () => {
  it("lists Gaps for owners and admins only", () => {
    const { rerender } = render(<AppNav managed={[ORG]} fallback={ORG} />);
    expect(screen.getByRole("link", { name: "Lacunas" })).toHaveAttribute("aria-current", "page");
    rerender(<AppNav managed={[]} fallback={ORG} />);
    expect(screen.queryByRole("link", { name: "Lacunas" })).toBeNull();
  });
});
