import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("next/navigation", () => ({
  usePathname: () => "/painel",
  useSearchParams: () => new URLSearchParams(""),
}));

import { DashboardView } from "@/components/dashboard/DashboardView";
import { AppNav } from "@/components/shell/AppNav";
import type { DashboardData } from "@/lib/api-types";

const ORG = "11111111-1111-4111-8111-111111111111";

function days(): DashboardData["days"] {
  return Array.from({ length: 30 }, (_, index) => ({
    date: `2026-11-${String(index + 1).padStart(2, "0")}`,
    questions: index === 29 ? 4 : 0,
    unanswered: index === 29 ? 1 : 0,
  }));
}

const data: DashboardData = {
  days: days(),
  questions: 4,
  unanswered: 1,
  languages: { pt: 3, en: 1, fr: 0 },
  top_documents: [
    { document_id: "a", title: "Manual do Colaborador", citations: 3 },
    { document_id: "b", title: "Pol\u00edtica de Viagens", citations: 1 },
  ],
  documents: { active: 21, failed: 2 },
  members: 2,
};

describe("DashboardView", () => {
  it("shows the numbers, never who asked", () => {
    render(<DashboardView organizationId={ORG} data={data} />);
    expect(screen.getByText(/Nunca mostra quem perguntou/)).toBeInTheDocument();
    expect(screen.getByText("25%\u00a0das perguntas".replace("\u00a0", " "))).toBeInTheDocument();
    expect(screen.getByText("2 n\u00e3o foram lidos")).toBeInTheDocument();
    expect(screen.getByText("Manual do Colaborador")).toBeInTheDocument();
    expect(screen.getByText("3 cita\u00e7\u00f5es")).toBeInTheDocument();
  });

  it("points to Documents when questions go unanswered", () => {
    render(<DashboardView organizationId={ORG} data={data} />);
    expect(screen.getByRole("link", { name: "Adicionar documentos" })).toHaveAttribute("href", `/documentos?org=${ORG}`);
  });

  it("has the days as a table too", async () => {
    render(<DashboardView organizationId={ORG} data={data} />);
    await userEvent.click(screen.getByText("Ver como tabela"));
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows).toHaveLength(31);
    expect(rows[30]).toHaveTextContent("31");
  });

  it("says so when there were no questions", () => {
    render(
      <DashboardView
        organizationId={ORG}
        data={{ ...data, days: days().map((d) => ({ ...d, questions: 0, unanswered: 0 })), questions: 0, unanswered: 0, top_documents: [] }}
      />,
    );
    expect(screen.getByText("Ainda n\u00e3o houve perguntas nestes 30 dias.")).toBeInTheDocument();
    expect(screen.getByText("Ainda nenhuma resposta citou documentos.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Adicionar documentos" })).toBeNull();
  });

  it("is in the menu only for owners and admins", () => {
    const { rerender } = render(<AppNav managed={[ORG]} fallback={ORG} />);
    expect(screen.getByRole("link", { name: "Painel" })).toHaveAttribute("href", "/painel");
    rerender(<AppNav managed={[]} fallback={ORG} />);
    expect(screen.queryByRole("link", { name: "Painel" })).toBeNull();
  });
});
