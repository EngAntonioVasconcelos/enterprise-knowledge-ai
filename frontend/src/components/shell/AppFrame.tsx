import { type ReactNode, Suspense } from "react";

import { AccountMenu } from "@/components/shell/AccountMenu";
import { AppNav } from "@/components/shell/AppNav";
import { OrganizationSwitch } from "@/components/shell/OrganizationSwitch";
import { Wordmark } from "@/components/Wordmark";
import type { Messages } from "@/i18n/pt-PT";
import type { Organization } from "@/lib/api-types";

type Account = { name: string | null | undefined; email: string; picture?: string | null };

// The frame of every signed-in page. On wide screens a rail that stays in
// place while the page scrolls: the product, the organization being worked
// in, the screens, and the account. On small screens the same in a top bar.
// The content is the point; the frame stays quiet.
export function AppFrame({
  t,
  organizations,
  managed,
  account,
  children,
}: {
  t: Messages;
  organizations: Organization[];
  /** Organizations where the person is an owner or an admin. */
  managed: string[];
  account: Account;
  children: ReactNode;
}) {
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[16rem_minmax(0,1fr)]">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-control focus:bg-surface focus:px-3 focus:py-2 focus:text-body focus:shadow"
      >
        {t.nav.skip}
      </a>

      {/* Wide screens: the rail. */}
      <aside className="hidden min-w-0 border-r border-line lg:sticky lg:top-0 lg:flex lg:h-dvh lg:flex-col lg:overflow-y-auto lg:px-3 lg:py-5">
        <a href="/assistente" className="flex h-9 items-center rounded-control px-2.5" aria-label={t.product}>
          <Wordmark />
        </a>
        {organizations.length ? (
          <div className="mt-5">
            <Suspense>
              <OrganizationSwitch organizations={organizations} />
            </Suspense>
          </div>
        ) : null}
        <div className="mt-6">
          <Suspense>
            <AppNav managed={managed} fallback={organizations[0]?.id ?? null} />
          </Suspense>
        </div>
        <div className="mt-auto border-t border-line pt-3">
          <AccountMenu {...account} />
        </div>
      </aside>

      {/* Small screens: a top bar. */}
      <header className="sticky top-0 z-20 border-b border-line bg-paper/95 px-4 pt-3 backdrop-blur lg:hidden">
        <div className="flex items-center gap-3">
          <a href="/assistente" aria-label={t.product} className="shrink-0">
            <Wordmark compact />
          </a>
          <div className="min-w-0 flex-1">
            {organizations.length ? (
              <Suspense>
                <OrganizationSwitch organizations={organizations} compact />
              </Suspense>
            ) : null}
          </div>
          <AccountMenu {...account} compact />
        </div>
        <div className="mt-2 pb-2">
          <Suspense>
            <AppNav managed={managed} fallback={organizations[0]?.id ?? null} />
          </Suspense>
        </div>
      </header>

      <main id="content" className="min-w-0">
        {children}
      </main>
    </div>
  );
}
