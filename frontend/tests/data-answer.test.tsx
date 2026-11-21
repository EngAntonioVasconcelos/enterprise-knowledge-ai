import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AnswerDocument } from "@/components/assistant/AnswerDocument";
import type { Answer } from "@/lib/api-types";
import { splitAnswer } from "@/lib/citations";

const answer: Answer = {
  question: "Qual foi o total das vendas em novembro?",
  answer: "O total das vendas em novembro foi 35,75 euros [D1].",
  abstained: false,
  verified: true,
  sources: [],
  prompt_id: "answer-v3-abc",
  model: "test",
  note: null,
  timings_ms: { data: 12, model: 2 },
  data: {
    connection_id: "c1",
    connection_name: "Vendas",
    sql: "SELECT sum(amount) AS total FROM public.orders",
    columns: ["customer", "total"],
    rows: [
      ["Ana", "15.75"],
      ["Rui", null],
    ],
    truncated: true,
  },
};

describe("database answers", () => {
  it("cuts the [D1] citation out of the text", () => {
    expect(splitAnswer("Foram 35,75 euros [D1].")).toEqual([
      { kind: "text", text: "Foram 35,75 euros" },
      { kind: "data" },
      { kind: "text", text: "." },
    ]);
  });

  it("shows the rows read and the query, so every number can be checked", async () => {
    render(<AnswerDocument answer={answer} />);
    expect(screen.getByRole("link", { name: "Dados da base" })).toHaveAttribute("href", "#dados");
    expect(screen.getByText("Verificada nos dados")).toBeInTheDocument();
    const panel = screen.getByRole("complementary", { name: "Dados" });
    expect(within(panel).getByText("Da base de dados Vendas")).toBeInTheDocument();
    expect(within(panel).getByText("2 linhas lidas")).toBeInTheDocument();
    expect(within(panel).getByRole("columnheader", { name: "total" })).toBeInTheDocument();
    expect(within(panel).getByText("15.75")).toBeInTheDocument();
    expect(within(panel).getByText("vazio")).toBeInTheDocument();
    expect(within(panel).getByText(/Havia mais linhas/)).toBeInTheDocument();
    await userEvent.click(within(panel).getByText("Ver a consulta"));
    expect(within(panel).getByText(answer.data!.sql)).toBeInTheDocument();
  });

  it("never shows rows next to a refused answer", () => {
    render(<AnswerDocument answer={{ ...answer, abstained: true, answer: "Sem resposta." }} />);
    expect(screen.queryByRole("complementary", { name: "Dados" })).toBeNull();
    expect(screen.queryByText("15.75")).toBeNull();
  });
});
