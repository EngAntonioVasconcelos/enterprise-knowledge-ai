"use server";

import { cookies } from "next/headers";

import { isLocale, LOCALE_COOKIE } from "@/i18n/locales";

const ONE_YEAR = 60 * 60 * 24 * 365;

/** Keeps the person's interface language in a cookie for a year. */
export async function setLocale(value: string): Promise<void> {
  if (!isLocale(value)) return;
  const cookieStore = await cookies();
  cookieStore.set(LOCALE_COOKIE, value, {
    path: "/",
    maxAge: ONE_YEAR,
    sameSite: "lax",
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
  });
}
