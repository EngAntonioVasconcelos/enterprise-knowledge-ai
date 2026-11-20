import { DICTIONARIES, LOCALES, resolveLocale } from "@/i18n/locales";

function shape(value: unknown): unknown {
  if (typeof value === "function") return "function";
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, shape((value as Record<string, unknown>)[key])]),
    );
  }
  return typeof value;
}

describe("interface languages", () => {
  it("has the same words to fill in every language", () => {
    const reference = shape(DICTIONARIES["pt-PT"]);
    for (const locale of LOCALES) {
      expect(shape(DICTIONARIES[locale])).toEqual(reference);
    }
  });

  it("leaves no word empty", () => {
    const empty: string[] = [];
    function walk(value: unknown, path: string) {
      if (typeof value === "string" && !value.trim()) empty.push(path);
      if (value && typeof value === "object") {
        for (const [key, child] of Object.entries(value)) walk(child, `${path}.${key}`);
      }
    }
    for (const locale of LOCALES) walk(DICTIONARIES[locale], locale);
    expect(empty).toEqual([]);
  });

  it("keeps the person's choice first", () => {
    expect(resolveLocale("fr", "en-GB,en;q=0.9")).toBe("fr");
  });

  it("otherwise follows the browser, in its order of preference", () => {
    expect(resolveLocale(undefined, "de-DE,fr;q=0.8,en;q=0.9")).toBe("en");
    expect(resolveLocale(undefined, "fr-CA")).toBe("fr");
    expect(resolveLocale(undefined, "pt-BR,pt;q=0.9")).toBe("pt-PT");
  });

  it("falls back to European Portuguese", () => {
    expect(resolveLocale(undefined, null)).toBe("pt-PT");
    expect(resolveLocale("xx", "de-DE,ja;q=0.5")).toBe("pt-PT");
    expect(resolveLocale(undefined, "en;q=0")).toBe("pt-PT");
  });
});
