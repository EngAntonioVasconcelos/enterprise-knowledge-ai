import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AnswerDocument } from "@/components/assistant/AnswerDocument";
import type { Answer, AnswerSource } from "@/lib/api-types";

function source(number: number, cited: boolean, title: string): AnswerSource {
  return {
    number,
    cited,
    chunk_id: `chunk-${number}`,
    document_id: `doc-${number}`,
    version_id: `ver-${number}`,
    title,
    heading: "1. Ferias",
    snippet: `Trecho ${number}`,
    start_char: 0,
    end_char: 10,
  };
}

const answer: Answer = {
  question: "Quantos dias de ferias tenho?",
  answer: "Tens direito a 25 dias uteis [1].",
  abstained: false,
  verified: true,
  sources: [source(1, true, "Manual do Colaborador"), source(2, false, "Calendario de Feriados")],
  prompt_id: "answer-v3-abc",
  model: "test",
  note: null,
  timings_ms: { search: 1, model: 2 },
};

describe("AnswerDocument", () => {
  it("shows the answer, its citation and the sources apart from the consulted ones", () => {
    render(<AnswerDocument answer={answer} />);

    expect(screen.getByRole("heading", { name: answer.question })).toBeInTheDocument();
    const citation = screen.getByRole("link", { name: "Fonte 1" });
    expect(citation).toHaveAttribute("href", "#fonte-1");
    expect(screen.getByText("Manual do Colaborador")).toBeInTheDocument();
    expect(screen.getByText("Trecho 1")).toBeInTheDocument();
    expect(screen.getByText("Consultadas, n\u00e3o citadas")).toBeInTheDocument();
    expect(screen.queryByText("Trecho 2")).not.toBeInTheDocument();
    expect(screen.getByText("Verificada nas fontes")).toBeInTheDocument();
  });

  it("lights up the cited passage when the citation is focused", async () => {
    render(<AnswerDocument answer={answer} />);
    const passage = document.getElementById("fonte-1");
    expect(passage).toHaveClass("border-line-strong");

    await userEvent.tab();
    expect(screen.getByRole("link", { name: "Fonte 1" })).toHaveFocus();
    expect(passage).toHaveClass("border-cobalt");
  });

  it("presents an honest no-answer without a verified mark", () => {
    render(
      <AnswerDocument
        answer={{ ...answer, abstained: true, answer: "N\u00e3o encontrei uma resposta segura.", sources: [] }}
      />,
    );
    expect(screen.getByText("Sem resposta segura")).toBeInTheDocument();
    expect(screen.queryByText("Verificada nas fontes")).not.toBeInTheDocument();
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });
});
