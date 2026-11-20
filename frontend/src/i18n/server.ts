import "server-only";

import { cookies, headers } from "next/headers";

import { DICTIONARIES, LOCALE_COOKIE, type Locale, resolveLocale } from "@/i18n/locales";
import type { Messages } from "@/i18n/pt-PT";

/** The interface language of the current request (server components). */
export async function getLocale(): Promise<Locale> {
  const [cookieStore, headerList] = await Promise.all([cookies(), headers()]);
  return resolveLocale(cookieStore.get(LOCALE_COOKIE)?.value, headerList.get("accept-language"));
}

export async function getMessages(): Promise<{ locale: Locale; t: Messages }> {
  const locale = await getLocale();
  return { locale, t: DICTIONARIES[locale] };
}
