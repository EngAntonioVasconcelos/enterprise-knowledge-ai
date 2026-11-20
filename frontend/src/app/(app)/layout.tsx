import type { ReactNode } from "react";

import { AppNav } from "@/components/shell/AppNav";
import { Wordmark } from "@/components/Wordmark";
import { LanguageSwitch } from "@/components/shell/LanguageSwitch";
import { getMessages } from "@/i18n/server";
import { auth0 } from "@/lib/auth0";

// The frame of every signed-in page: a quiet rail on wide screens, a top
// bar on small ones. The content is the point; the frame stays out of it.
export default async function AppLayout({ children }: { children: ReactNode }) {
  const [session, { t }] = await Promise.all([auth0.getSession(), getMessages()]);
  const name = session?.user.name ?? session?.user.email ?? "";

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[15rem_minmax(0,1fr)]">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-paper/95 px-5 py-3 backdrop-blur lg:static lg:h-dvh lg:flex-col lg:items-stretch lg:justify-start lg:border-r lg:border-b-0 lg:px-4 lg:py-6">
        <a href="/assistente" className="lg:px-2">
          <span className="lg:hidden">
            <Wordmark compact />
          </span>
          <span className="hidden lg:inline">
            <Wordmark />
          </span>
        </a>
        <AppNav />
        <div className="flex items-center gap-4 lg:mt-auto lg:flex-col lg:items-stretch lg:gap-2 lg:px-2">
          <span className="hidden truncate text-meta text-ink-soft lg:block" title={name}>
            {name}
          </span>
          <div className="flex items-center gap-3 lg:-ml-1.5 lg:justify-between">
            <LanguageSwitch />
            <a
              href="/auth/logout"
              className="text-meta font-medium text-ink-soft underline-offset-4 hover:text-ink hover:underline"
            >
              {t.nav.signOut}
            </a>
          </div>
        </div>
      </header>
      <main className="min-w-0">{children}</main>
    </div>
  );
}
