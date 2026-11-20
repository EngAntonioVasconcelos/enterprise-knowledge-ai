import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const refresh = vi.fn();
const setLocale = vi.fn().mockResolvedValue(undefined);

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
vi.mock("@/i18n/actions", () => ({ setLocale: (value: string) => setLocale(value) }));

import { LanguageSwitch } from "@/components/shell/LanguageSwitch";
import { AssistantView } from "@/components/assistant/AssistantView";
import { I18nProvider } from "@/i18n/client";

afterEach(() => vi.clearAllMocks());

describe("LanguageSwitch", () => {
  it("offers each language in its own name and saves the choice", async () => {
    render(<LanguageSwitch />);

    await userEvent.click(screen.getByRole("button", { name: /Idioma da interface: Portugu\u00eas/ }));
    expect(screen.getByRole("menuitemradio", { name: "Portugu\u00eas" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("menuitemradio", { name: "Fran\u00e7ais" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("menuitemradio", { name: "English" }));

    await vi.waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(setLocale).toHaveBeenCalledWith("en");
  });

  it("does nothing when the current language is chosen again", async () => {
    render(<LanguageSwitch />);
    await userEvent.click(screen.getByRole("button", { name: /Idioma da interface/ }));
    await userEvent.click(screen.getByRole("menuitemradio", { name: "Portugu\u00eas" }));
    expect(setLocale).not.toHaveBeenCalled();
  });
});

describe("the interface in another language", () => {
  it("shows the assistant in French", () => {
    render(
      <I18nProvider locale="fr">
        <AssistantView organizationId="11111111-1111-4111-8111-111111111111" organizationName="Atlantico" />
      </I18nProvider>,
    );
    expect(screen.getByRole("heading", { name: "Que souhaitez-vous savoir\u00a0?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Demander" })).toBeInTheDocument();
  });
});
