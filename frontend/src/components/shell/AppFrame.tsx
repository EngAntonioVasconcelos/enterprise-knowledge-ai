import { type ReactNode, Suspense } from "react";

import { BrandMark } from "@/components/BrandMark";
import { AccountMenu } from "@/components/shell/AccountMenu";
import { AppNav } from "@/components/shell/AppNav";
import { CommandPalette, CommandTrigger } from "@/components/shell/CommandPalette";
import { OrganizationSwitch } from "@/components/shell/OrganizationSwitch";
import { Wordmark } from "@/components/Wordmark";
import type { Messages } from "@/i18n/pt-PT";
import type { Organization } from "@/lib/api-types";

type Account = { name: string | null | undefined; email: string; picture?: string | null };

// The frame of every signed-in page, the Bancada. On wide screens a dark
// rail of icons with their names that stays in place (the product, the screens, the
// account) and a top bar with the organization being worked in and the
// command bar (Ctrl+K); the content gets the rest. On small screens the
// same in a top bar. The frame stays quiet: the answer and its evidence
// carry the page.
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
    <div className="min-h-dvh lg:grid lg:grid-cols-[5rem_minmax(0,1fr)] lg:grid-rows-[3.75rem_minmax(0,1fr)]">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-control focus:bg-surface focus:px-3 focus:py-2 focus:text-body focus:shadow"
      >
        {t.nav.skip}
      </a>

      {/* Wide screens: the product in a dark corner, then the organization
          and the command bar, across the top. */}
      <header
        aria-label={t.nav.topbar}
        className="hidden lg:sticky lg:top-0 lg:z-30 lg:col-span-2 lg:flex lg:h-15 lg:bg-paper"
      >
        <a
          href="/assistente"
          className="flex w-60 shrink-0 items-center gap-3 bg-rail px-4 text-[0.9375rem] font-semibold tracking-[-0.015em] whitespace-nowrap text-white"
        >
          <BrandMark size={32} />
          {t.product}
        </a>
        <div className="flex min-w-0 flex-1 items-center gap-4 border-b border-line px-7">
          {organizations.length ? (
            <div className="min-w-0 max-w-xs">
              <Suspense>
                <OrganizationSwitch organizations={organizations} />
              </Suspense>
            </div>
          ) : null}
          <div className="flex-1" />
          <CommandTrigger />
        </div>
      </header>

      {/* Wide screens: the rail of screens below the corner. */}
      <aside
        aria-label={t.nav.rail}
        className="hidden bg-rail lg:sticky lg:top-15 lg:z-20 lg:flex lg:h-[calc(100dvh-3.75rem)] lg:flex-col lg:items-center lg:pt-3 lg:pb-4"
      >
        <Suspense>
          <AppNav managed={managed} fallback={organizations[0]?.id ?? null} variant="rail" />
        </Suspense>
        <div className="mt-auto">
          <AccountMenu {...account} compact side="right" />
        </div>
      </aside>

      <div className="flex min-w-0 flex-col">
        {/* Small screens: one top bar. */}
        <header aria-label={t.nav.topbar} className="sticky top-0 z-20 border-b border-line bg-paper/95 px-4 pt-3 backdrop-blur lg:hidden">
          <div className="flex items-center gap-2">
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
            <CommandTrigger compact />
            <AccountMenu {...account} compact />
          </div>
          <div className="mt-2 pb-2">
            <Suspense>
              <AppNav managed={managed} fallback={organizations[0]?.id ?? null} />
            </Suspense>
          </div>
        </header>

        <main id="content" className="min-w-0 flex-1">
          {children}
        </main>
      </div>

      <Suspense>
        <CommandPalette organizations={organizations} managed={managed} />
      </Suspense>
    </div>
  );
}
