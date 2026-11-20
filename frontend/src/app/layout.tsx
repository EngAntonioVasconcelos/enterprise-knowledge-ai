import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { I18nProvider } from "@/i18n/client";
import { getMessages } from "@/i18n/server";

import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getMessages();
  return {
    title: { default: t.product, template: `%s | ${t.productShort}` },
    description: t.signIn.body,
    robots: { index: false, follow: false },
  };
}

export const viewport: Viewport = { themeColor: "#f5f6f8" };

export default async function RootLayout({ children }: { children: ReactNode }) {
  const { locale } = await getMessages();
  return (
    <html lang={locale}>
      <body className="min-h-dvh">
        <I18nProvider locale={locale}>{children}</I18nProvider>
      </body>
    </html>
  );
}
