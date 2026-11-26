import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const push = vi.fn();
const refresh = vi.fn();
const setLocale = vi.fn().mockResolvedValue(undefined);
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
  usePathname: () => "/painel",
  useSearchParams: () => new URLSearchParams(""),
}));
vi.mock("@/i18n/actions", () => ({ setLocale: (value: string) => setLocale(value) }));

import { AssistantView } from "@/components/assistant/AssistantView";
import { AppFrame } from "@/components/shell/AppFrame";
import { ptPT } from "@/i18n/pt-PT";

const ORG = "11111111-1111-4111-8111-111111111111";
const OTHER = "22222222-2222-4222-8222-222222222222";
const organizations = [
  { id: ORG, name: "Atl\u00e2ntico Seguros", slug: "a", status: "active", role: "owner" as const },
  { id: OTHER, name: "Projeto Norte", slug: "b", status: "active", role: "member" as const },
];
const account = { name: "Antonio Vasconcelos", email: "antonio@atlantico.pt", picture: null };

afterEach(() => vi.clearAllMocks());

function frame(managed = [ORG]) {
  return render(
    <AppFrame t={ptPT} organizations={organizations} managed={managed} account={account}>
      <p>conte\u00fado</p>
    </AppFrame>,
  );
}

describe("the frame", () => {
  it("names the product, the organization and the person's role", () => {
    frame();
    const rail = screen.getByRole("complementary");
    expect(within(rail).getByRole("link", { name: "Enterprise Knowledge AI" })).toHaveAttribute("href", "/assistente");
    // The organization being worked in sits in the top bar, beside the commands.
    const [top] = screen.getAllByRole("banner", { name: "Organiza\u00e7\u00e3o e comandos" });
    expect(within(top!).getByRole("link", { name: "Enterprise Knowledge AI" })).toHaveAttribute("href", "/assistente");
    expect(within(top!).getByText("Atl\u00e2ntico Seguros")).toBeInTheDocument();
    expect(within(top!).getByText("Propriet\u00e1rio")).toBeInTheDocument();
    expect(within(top!).getByRole("button", { name: /Perguntar, procurar ou ir para/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Saltar para o conte\u00fado" })).toHaveAttribute("href", "#content");
  });

  it("groups the management screens apart, only for managers", () => {
    const { unmount } = frame();
    const rail = screen.getByRole("complementary");
    expect(within(rail).getByText("Administra\u00e7\u00e3o")).toBeInTheDocument();
    expect(within(rail).getByRole("link", { name: "Painel" })).toHaveAttribute("aria-current", "page");
    unmount();
    frame([]);
    expect(within(screen.getByRole("complementary")).queryByText("Administra\u00e7\u00e3o")).toBeNull();
  });

  it("switches organization and stays on the same screen", async () => {
    frame();
    const [top] = screen.getAllByRole("banner", { name: "Organiza\u00e7\u00e3o e comandos" });
    await userEvent.click(within(top!).getByRole("button", { name: /Mudar de organiza\u00e7\u00e3o/ }));
    await userEvent.click(screen.getByRole("menuitem", { name: /Projeto Norte/ }));
    expect(push).toHaveBeenCalledWith(`/painel?org=${OTHER}`);
  });

  it("keeps the language and signing out in the account menu", async () => {
    frame();
    const rail = screen.getByRole("complementary");
    await userEvent.click(within(rail).getByRole("button", { name: /A tua conta/ }));
    expect(screen.getByRole("menuitem", { name: "Sair" })).toHaveAttribute("href", "/auth/logout");
    await userEvent.click(screen.getByRole("menuitemradio", { name: "English" }));
    await vi.waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(setLocale).toHaveBeenCalledWith("en");
  });
});

describe("the command bar", () => {
  it("opens with Ctrl+K, finds screens without accents and asks the assistant", async () => {
    frame();
    await userEvent.keyboard("{Control>}k{/Control}");
    const input = await screen.findByRole("combobox");
    await userEvent.type(input, "defini");
    expect(screen.getByRole("option", { name: /Defini\u00e7\u00f5es/ })).toBeInTheDocument();
    await userEvent.clear(input);
    await userEvent.type(input, "ferias");
    // The question comes first: Enter asks it.
    expect(screen.getAllByRole("option")[0]).toHaveTextContent("Perguntar ao assistente: \u00abferias\u00bb");
    await userEvent.keyboard("{Enter}");
    expect(push).toHaveBeenCalledWith(`/assistente?org=${ORG}&q=ferias`);
  });

  it("lists management screens only for managers, and other organizations to switch to", async () => {
    frame([]);
    await userEvent.keyboard("{Control>}k{/Control}");
    await screen.findByRole("combobox");
    expect(screen.queryByRole("option", { name: "Painel" })).toBeNull();
    await userEvent.click(screen.getByRole("option", { name: "Mudar para Projeto Norte" }));
    expect(push).toHaveBeenCalledWith(`/painel?org=${OTHER}`);
  });
});

describe("the assistant before the first question", () => {
  it("greets the person and offers their latest questions", () => {
    render(
      <AssistantView
        organizationId={ORG}
        organizationName="Atl"
        firstName="Antonio"
        recent={[{ id: OTHER, question: "Quantos dias de f\u00e9rias tenho?", abstained: false, created_at: "2026-11-21T10:00:00Z" }]}
      />,
    );
    expect(screen.getByRole("heading", { name: "O que precisas de saber, Antonio?" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Quantos dias de f\u00e9rias tenho\?/ })).toHaveAttribute(
      "href",
      `/historico/${OTHER}?org=${ORG}`,
    );
  });
});
