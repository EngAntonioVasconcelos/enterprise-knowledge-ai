"use client";

import { createContext, type ReactNode, useContext } from "react";

import { DEFAULT_LOCALE, DICTIONARIES, type Locale } from "@/i18n/locales";
import type { Messages } from "@/i18n/pt-PT";

// The server decides the language and passes only its code; the words
// come from the dictionaries bundled here (they hold functions, which
// cannot cross from server to client).
const I18nContext = createContext<Locale>(DEFAULT_LOCALE);

export function I18nProvider({ locale, children }: { locale: Locale; children: ReactNode }) {
  return <I18nContext.Provider value={locale}>{children}</I18nContext.Provider>;
}

export function useI18n(): { locale: Locale; t: Messages } {
  const locale = useContext(I18nContext);
  return { locale, t: DICTIONARIES[locale] };
}
