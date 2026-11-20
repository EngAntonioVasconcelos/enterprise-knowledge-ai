import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AssistantView } from "@/components/assistant/AssistantView";

const ORG = "11111111-1111-4111-8111-111111111111";

function mockFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("AssistantView", () => {
  it("asks through this server, never the backend directly, and shows the answer", async () => {
    const fetchMock = mockFetch(200, {
      question: "Quantos dias?",
      answer: "Tens 25 dias [1].",
      abstained: false,
      verified: true,
      sources: [],
      prompt_id: "p",
      model: "m",
      note: null,
      timings_ms: {},
    });
    render(<AssistantView organizationId={ORG} organizationName="Atlantico" />);

    await userEvent.type(screen.getByRole("textbox"), "Quantos dias?{Enter}");

    expect(await screen.findByRole("heading", { name: "Quantos dias?" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/answers",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ organizationId: ORG, question: "Quantos dias?", language: "pt" }),
      }),
    );
    expect(screen.getByRole("link", { name: "Fonte 1" })).toBeInTheDocument();
  });

  it("explains an unavailable model and offers to try again", async () => {
    mockFetch(503, { detail: "Answers are unavailable" });
    render(<AssistantView organizationId={ORG} organizationName="Atlantico" />);

    await userEvent.type(screen.getByRole("textbox"), "Pergunta{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent("n\u00e3o est\u00e1 dispon\u00edvel");
    expect(screen.getByRole("button", { name: "Tentar de novo" })).toBeInTheDocument();
  });

  it("does not send an empty question, and Shift+Enter starts a new line", async () => {
    const fetchMock = mockFetch(200, {});
    render(<AssistantView organizationId={ORG} organizationName="Atlantico" />);

    await userEvent.type(screen.getByRole("textbox"), "   {Enter}");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Perguntar" })).toBeDisabled();

    await userEvent.type(screen.getByRole("textbox"), "linha{Shift>}{Enter}{/Shift}dois");
    expect(screen.getByRole("textbox")).toHaveValue("   linha\ndois");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
