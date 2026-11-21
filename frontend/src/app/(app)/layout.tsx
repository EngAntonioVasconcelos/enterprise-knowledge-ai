import { type ReactNode, Suspense } from "react";

import { AppNav } from "@/components/shell/AppNav";
import { Avatar } from "@/components/shell/Avatar";
import { Wordmark } from "@/components/Wordmark";
import { LanguageSwitch } from "@/components/shell/LanguageSwitch";
import { getMessages } from "@/i18n/server";
import { auth0 } from "@/lib/auth0";
import { loadOrganizations } from "@/lib/organizations";
import { managesPeople } from "@/lib/roles";

// The frame of every signed-in page: a quiet rail on wide screens, a top
// bar on small ones. The content is the point; the frame stays out of it.
export default async function AppLayout({ children }: { children: ReactNode }) {
  const [session, { t }, result] = await Promise.all([auth0.getSession(), getMessages(), loadOrganizations()]);
  const name = session?.user.name ?? session?.user.email ?? "";
  const email = session?.user.email ?? "";
  const organizations = "organizations" in result ? result.organizations : [];
  const managed = organizations.filter((o) => managesPeople(o.role)).map((o) => o.id);

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[15rem_minmax(0,1fr)]">
      <header className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-y-2 border-b border-line bg-paper/95 px-5 py-3 backdrop-blur lg:static lg:h-dvh lg:flex-col lg:items-stretch lg:justify-start lg:border-r lg:border-b-0 lg:px-4 lg:py-6">
        <a href="/assistente" className="lg:px-2">
          <span className="lg:hidden">
            <Wordmark compact />
          </span>
          <span className="hidden lg:inline">
            <Wordmark />
          </span>
        </a>
        <Suspense>
          <AppNav managed={managed} fallback={organizations[0]?.id ?? null} />
        </Suspense>
        <div className="flex items-center gap-4 lg:mt-auto lg:flex-col lg:items-stretch lg:gap-2 lg:px-2">
          <div className="hidden min-w-0 items-center gap-2.5 lg:flex">
            <Avatar name={session?.user.name} email={email} picture={session?.user.picture} size="sm" />
            <div className="min-w-0">
              <p className="truncate text-meta font-medium text-ink" title={name}>
                {name}
              </p>
              {email && email !== name ? (
                <p className="truncate text-[0.75rem] text-ink-faint" title={email}>
                  {email}
                </p>
              ) : null}
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-3 lg:-ml-1.5 lg:justify-between">
            <span className="lg:hidden" title={name}>
              <Avatar name={session?.user.name} email={email} picture={session?.user.picture} size="sm" />
            </span>
            <LanguageSwitch />
            <a
              href="/auth/logout"
              className="text-meta font-medium whitespace-nowrap text-ink-soft underline-offset-4 hover:text-ink hover:underline"
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
