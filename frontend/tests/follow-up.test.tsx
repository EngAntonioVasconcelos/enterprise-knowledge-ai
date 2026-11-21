import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth0", () => ({ auth0: { getAccessToken: vi.fn() } }));

import { POST } from "@/app/api/answers/route";
import { AssistantView } from "@/components/assistant/AssistantView";
import { auth0 } from "@/lib/auth0";

const ORG = "11111111-1111-4111-8111-111111111111";

function answer(question: string) {
  return new Response(
    JSON.stringify({
      question,
      answer: "Tens 25 dias [1].",
      abstained: false,
      verified: true,
      sources: [],
      prompt_id: "p",
      model: "m",
      note: null,
      timings_ms: {},
      language: "pt",
    }),
    { status: 200 },
  );
}

function sent(fetchMock: ReturnType<typeof vi.fn>, call: number) {
  return JSON.parse((fetchMock.mock.calls[call]![1] as RequestInit).body as string);
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("follow-up questions", () => {
  it("sends the earlier questions of the conversation, never the answers", async () => {
    const fetchMock = vi.fn((_url: string, init: RequestInit) =>
      Promise.resolve(answer(JSON.parse(init.body as string).question)),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<AssistantView organizationId={ORG} organizationName="Atl" />);

    const box = screen.getByRole("textbox");
    await userEvent.type(box, "Quantos dias de ferias tenho?{Enter}");
    await screen.findByRole("heading", { name: "Quantos dias de ferias tenho?" });
    expect(sent(fetchMock, 0).previous).toBeUndefined();
    expect(screen.getByText("Nesta conversa:")).toBeInTheDocument();

    await userEvent.clear(box);
    await userEvent.type(box, "e os estagiarios?{Enter}");
    await screen.findByRole("heading", { name: "e os estagiarios?" });
    expect(sent(fetchMock, 1).previous).toEqual(["Quantos dias de ferias tenho?"]);
    expect(JSON.stringify(sent(fetchMock, 1))).not.toContain("Tens 25 dias");

    await userEvent.clear(box);
    await userEvent.type(box, "e em part-time?{Enter}");
    await screen.findByRole("heading", { name: "e em part-time?" });
    await userEvent.clear(box);
    await userEvent.type(box, "e depois?{Enter}");
    await screen.findByRole("heading", { name: "e depois?" });
    expect(sent(fetchMock, 3).previous).toEqual(["e os estagiarios?", "e em part-time?"]);
  });

  it("starts over with a new conversation", async () => {
    const fetchMock = vi.fn((_url: string, init: RequestInit) =>
      Promise.resolve(answer(JSON.parse(init.body as string).question)),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<AssistantView organizationId={ORG} organizationName="Atl" />);
    await userEvent.type(screen.getByRole("textbox"), "Quantos dias?{Enter}");
    await screen.findByRole("heading", { name: "Quantos dias?" });

    await userEvent.click(screen.getByRole("button", { name: "Nova conversa" }));
    expect(screen.queryByText("Nesta conversa:")).toBeNull();
    expect(screen.getByRole("textbox")).toHaveValue("");
    await userEvent.type(screen.getByRole("textbox"), "Outra coisa?{Enter}");
    await screen.findByRole("heading", { name: "Outra coisa?" });
    expect(sent(fetchMock, 1).previous).toBeUndefined();
  });

  it("forwards at most two earlier questions to the backend, checked", async () => {
    vi.stubEnv("EKA_API_URL", "http://backend.test:8000");
    vi.mocked(auth0.getAccessToken).mockResolvedValue({ token: "t" } as never);
    const backend = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", backend);
    const call = (body: unknown) =>
      POST(new Request("http://localhost/api/answers", { method: "POST", body: JSON.stringify(body) }));

    await call({ organizationId: ORG, question: "e depois?", previous: [" Quantos dias? "] });
    expect(JSON.parse((backend.mock.calls[0]![1] as RequestInit).body as string)).toEqual({
      question: "e depois?",
      previous_questions: ["Quantos dias?"],
    });
    expect((await call({ organizationId: ORG, question: "x", previous: ["a", "b", "c"] })).status).toBe(400);
    expect((await call({ organizationId: ORG, question: "x", previous: [42] })).status).toBe(400);
    expect((await call({ organizationId: ORG, question: "x", previous: "a" })).status).toBe(400);
    expect(backend).toHaveBeenCalledTimes(1);
  });
});
