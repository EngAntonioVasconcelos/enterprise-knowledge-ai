import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth0", () => ({ auth0: { getAccessToken: vi.fn() } }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/historico",
  useSearchParams: () => new URLSearchParams(""),
}));

import { saveSettings } from "@/app/(app)/definicoes/actions";
import { deleteQuestions } from "@/app/(app)/historico/actions";
import { HistoryEntryView } from "@/components/history/HistoryEntryView";
import { HistoryList } from "@/components/history/HistoryList";
import { SettingsForm } from "@/components/settings/SettingsForm";
import { AssistantView } from "@/components/assistant/AssistantView";
import { AppNav } from "@/components/shell/AppNav";
import type { HistoryEntry } from "@/lib/api-types";
import { auth0 } from "@/lib/auth0";

const ORG = "11111111-1111-4111-8111-111111111111";
const ENTRY = "22222222-2222-4222-8222-222222222222";

function backend(...statuses: number[]) {
  vi.mocked(auth0.getAccessToken).mockResolvedValue({ token: "t" } as never);
  const fetchMock = vi.fn();
  for (const status of statuses) {
    fetchMock.mockResolvedValueOnce(new Response(status === 204 ? null : "{}", { status }));
  }
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function form(values: Record<string, string>) {
  const data = new FormData();
  for (const [key, value] of Object.entries(values)) data.set(key, value);
  return data;
}

const entry: HistoryEntry = {
  id: ENTRY,
  question: "Quantos dias de f\u00e9rias tenho?",
  answer: "Tens 25 dias \u00fateis [1].",
  abstained: false,
  verified: true,
  language: "pt",
  created_at: "2026-11-21T10:00:00Z",
  sources: [
    {
      number: 1,
      cited: true,
      chunk_id: "c",
      document_id: "d",
      version_id: "v",
      title: "Manual",
      heading: null,
      snippet: "Cada colaborador tem 25 dias \u00fateis.",
      start_char: 0,
      end_char: 10,
    },
  ],
  hidden: false,
  outdated: false,
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("history actions", () => {
  it("deletes one question, or all of them", async () => {
    const fetchMock = backend(204, 204);
    expect(await deleteQuestions({}, form({ organizationId: ORG, entryId: ENTRY }))).toEqual({ done: true });
    expect(fetchMock.mock.calls[0]![0]).toMatch(`/organizations/${ORG}/history/${ENTRY}`);
    expect(await deleteQuestions({}, form({ organizationId: ORG }))).toEqual({ done: true });
    expect(fetchMock.mock.calls[1]![0]).toMatch(new RegExp(`/history/$`));
  });

  it("refuses ids that are not ids", async () => {
    const fetchMock = backend();
    expect((await deleteQuestions({}, form({ organizationId: ORG, entryId: "../x" }))).error).toBe("unavailable");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("HistoryList", () => {
  it("says only you see the questions, and asks before deleting all", async () => {
    const action = vi.fn(async () => ({ done: true }));
    render(
      <HistoryList
        organizationId={ORG}
        retentionDays={90}
        items={[{ id: ENTRY, question: "Quantos dias?", abstained: true, created_at: "2026-11-21T10:00:00Z" }]}
        action={action}
      />,
    );
    expect(screen.getByText(/S\u00f3 tu as v\u00eas/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Quantos dias\?/ })).toHaveAttribute(
      "href",
      `/historico/${ENTRY}?org=${ORG}`,
    );
    expect(screen.getByText("Sem resposta segura")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Apagar todo o hist\u00f3rico" }));
    expect(action).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Apagar tudo" }));
    expect(action).toHaveBeenCalledTimes(1);
  });

  it("explains when the organization keeps no history", () => {
    render(<HistoryList organizationId={ORG} retentionDays={0} items={[]} />);
    expect(screen.getByText("A tua organiza\u00e7\u00e3o n\u00e3o guarda o hist\u00f3rico de perguntas.")).toBeInTheDocument();
  });
});

describe("HistoryEntryView", () => {
  it("shows the answer as it was, with a way to ask again", () => {
    render(<HistoryEntryView organizationId={ORG} entry={entry} />);
    expect(screen.getByRole("heading", { name: "Quantos dias de f\u00e9rias tenho?" })).toBeInTheDocument();
    expect(screen.getByText(/Tens 25 dias/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Perguntar de novo" })).toHaveAttribute(
      "href",
      `/assistente?org=${ORG}&q=${encodeURIComponent(entry.question)}`,
    );
  });

  it("hides an answer whose sources are no longer readable", () => {
    render(<HistoryEntryView organizationId={ORG} entry={{ ...entry, answer: null, sources: [], hidden: true }} />);
    expect(screen.queryByText(/Tens 25 dias/)).toBeNull();
    expect(screen.getByText(/deixaste de ter acesso/)).toBeInTheDocument();
  });

  it("goes back to the list after deleting", async () => {
    const action = vi.fn(async () => ({ done: true }));
    render(<HistoryEntryView organizationId={ORG} entry={entry} action={action} />);
    await userEvent.click(screen.getByRole("button", { name: "Apagar" }));
    expect(push).toHaveBeenCalledWith(`/historico?org=${ORG}`);
  });
});

describe("settings", () => {
  it("saves only what changed", async () => {
    const fetchMock = backend(200);
    const state = await saveSettings(
      {},
      form({ organizationId: ORG, name: "Atl\u00e2ntico", currentName: "Atl\u00e2ntico", retention: "30", currentRetention: "90" }),
    );
    expect(state).toEqual({ saved: true });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(`/organizations/${ORG}`);
    expect(init.body).toBe(JSON.stringify({ history_retention_days: 30 }));
  });

  it("checks the name and the period before calling the server", async () => {
    const fetchMock = backend();
    const short = form({ organizationId: ORG, name: "A", currentName: "Atl", retention: "90", currentRetention: "90" });
    expect((await saveSettings({}, short)).error).toBe("invalidName");
    const odd = form({ organizationId: ORG, name: "Atl", currentName: "Atl", retention: "7", currentRetention: "90" });
    expect((await saveSettings({}, odd)).error).toBe("unavailable");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("warns before a shorter period deletes questions", async () => {
    render(<SettingsForm organizationId={ORG} name="Atl" retentionDays={90} action={vi.fn(async () => ({}))} />);
    expect(screen.queryByRole("status")).toBeNull();
    await userEvent.click(screen.getByRole("radio", { name: "N\u00e3o guardar" }));
    expect(screen.getByRole("status")).toHaveTextContent("deixam de ser guardadas");
  });

  it("is in the menu only where the person manages the organization", () => {
    const { rerender } = render(<AppNav managed={[ORG]} fallback={ORG} />);
    expect(screen.getByRole("link", { name: "Defini\u00e7\u00f5es" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Hist\u00f3rico" })).toBeInTheDocument();
    rerender(<AppNav managed={[]} fallback={ORG} />);
    expect(screen.queryByRole("link", { name: "Defini\u00e7\u00f5es" })).toBeNull();
    expect(screen.getByRole("link", { name: "Hist\u00f3rico" })).toBeInTheDocument();
  });
});

describe("ask again", () => {
  it("asks the question once and takes it out of the address", async () => {
    window.history.replaceState(null, "", `/assistente?org=${ORG}&q=Quantos`);
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...entry, prompt_id: "", timings_ms: {} })));
    vi.stubGlobal("fetch", fetchMock);
    render(<AssistantView organizationId={ORG} organizationName="Atl" initialQuestion="Quantos" />);
    expect(await screen.findByText(/Tens 25 dias/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(JSON.parse((fetchMock.mock.calls[0]![1] as RequestInit).body as string).question).toBe("Quantos");
    expect(window.location.search).toBe(`?org=${ORG}`);
  });
});
