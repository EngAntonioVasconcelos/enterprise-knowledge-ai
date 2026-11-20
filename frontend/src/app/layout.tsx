import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { messages } from "@/i18n/pt-PT";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: messages.product, template: `%s | ${messages.productShort}` },
  description: messages.signIn.body,
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { themeColor: "#f5f6f8" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="pt-PT">
      <body className="min-h-dvh">{children}</body>
    </html>
  );
}
