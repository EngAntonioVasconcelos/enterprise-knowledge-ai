import { en } from "@/i18n/en";
import { fr } from "@/i18n/fr";
import { type Messages, ptPT } from "@/i18n/pt-PT";

// The interface languages. Each is named in its own language, so a person
// who cannot read the current one still finds theirs.
export const LOCALES = ["pt-PT", "en", "fr"] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "pt-PT";
export const LOCALE_COOKIE = "eka_locale";

export const LANGUAGE_NAMES: Record<Locale, string> = {
  "pt-PT": "Portugu\u00eas",
  en: "English",
  fr: "Fran\u00e7ais",
};

export const DICTIONARIES: Record<Locale, Messages> = { "pt-PT": ptPT, en, fr };

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

/**
 * The interface language for a request: the person's choice (cookie) if
 * there is one, otherwise the first browser language we have, otherwise
 * European Portuguese.
 */
export function resolveLocale(cookie: string | undefined, acceptLanguage: string | null): Locale {
  if (isLocale(cookie)) return cookie;
  const wanted = (acceptLanguage ?? "")
    .split(",")
    .map((part) => {
      const [tag = "", ...params] = part.trim().split(";");
      const q = params.map((p) => p.trim()).find((p) => p.startsWith("q="));
      return { tag: tag.toLowerCase(), q: q ? Number(q.slice(2)) : 1 };
    })
    .filter((item) => item.tag && !Number.isNaN(item.q) && item.q > 0)
    .sort((a, b) => b.q - a.q);
  for (const { tag } of wanted) {
    const base = tag.split("-")[0];
    if (base === "pt") return "pt-PT";
    if (base === "en") return "en";
    if (base === "fr") return "fr";
  }
  return DEFAULT_LOCALE;
}
