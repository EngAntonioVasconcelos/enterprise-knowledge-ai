"use client";

import {
  ChartColumn,
  FileText,
  History,
  type LucideIcon,
  MessageSquareText,
  SearchX,
  Settings,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import { useI18n } from "@/i18n/client";

type Item = { href: string; label: string; icon: LucideIcon };

export function AppNav({
  managed = [],
  fallback = null,
  variant = "bar",
}: {
  /** Organizations where the person is an owner or an admin. */
  managed?: string[];
  /** The organization screens open on when none is chosen. */
  fallback?: string | null;
  /** "rail": icons with their names in the dark rail of wide screens; "bar": a row on small ones. */
  variant?: "rail" | "bar";
}) {
  const pathname = usePathname();
  const { t } = useI18n();
  // The chosen organization follows the person from screen to screen.
  const org = useSearchParams().get("org");
  const query = org ? `?org=${encodeURIComponent(org)}` : "";
  const current = org ?? fallback;
  const manages = Boolean(current && managed.includes(current));

  // Only screens that exist, and that this person may use, are listed;
  // management screens form their own group.
  const work: Item[] = [
    { href: "/assistente", label: t.nav.assistant, icon: MessageSquareText },
    { href: "/documentos", label: t.nav.documents, icon: FileText },
    { href: "/historico", label: t.nav.history, icon: History },
  ];
  const admin: Item[] = manages
    ? [
        { href: "/painel", label: t.nav.dashboard, icon: ChartColumn },
        { href: "/lacunas", label: t.nav.gaps, icon: SearchX },
        { href: "/pessoas", label: t.nav.people, icon: Users },
        { href: "/definicoes", label: t.nav.settings, icon: Settings },
      ]
    : [];

  function railLink(item: Item) {
    const active = pathname.startsWith(item.href);
    const Icon = item.icon;
    // The name stays under the icon: a screen is found by reading, not by guessing.
    return (
      <li key={item.href}>
        <Link
          href={`${item.href}${query}`}
          aria-current={active ? "page" : undefined}
          className={
            "flex w-[4.5rem] flex-col items-center gap-1 rounded-control px-1 pt-2 pb-1.5 text-center transition-colors focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-white " +
            (active ? "bg-rail-raised text-white" : "text-rail-ink hover:bg-rail-raised/60 hover:text-white")
          }
        >
          <Icon aria-hidden className="size-5" strokeWidth={1.8} />
          <span className="text-[0.6875rem] leading-tight font-medium text-balance">{item.label}</span>
        </Link>
      </li>
    );
  }

  function barLink(item: Item) {
    const active = pathname.startsWith(item.href);
    const Icon = item.icon;
    return (
      <li key={item.href} className="shrink-0">
        <Link
          href={`${item.href}${query}`}
          aria-current={active ? "page" : undefined}
          className={
            "group flex items-center gap-2 rounded-control px-2.5 py-2 text-body whitespace-nowrap transition-colors " +
            (active ? "bg-surface font-medium text-ink shadow-[0_0_0_1px_var(--color-line)]" : "text-ink-soft hover:text-ink")
          }
        >
          <Icon aria-hidden className={"size-[1.125rem] shrink-0 " + (active ? "text-signal" : "text-ink-faint")} strokeWidth={1.75} />
          {item.label}
        </Link>
      </li>
    );
  }

  if (variant === "rail") {
    return (
      <nav aria-label={t.nav.main} className="flex flex-col items-center gap-1.5">
        <ul className="flex flex-col gap-1">{work.map(railLink)}</ul>
        {admin.length ? (
          <div className="mt-2 flex w-full flex-col items-center gap-1 border-t border-rail-raised pt-2">
            <p className="sr-only">{t.nav.admin}</p>
            <ul className="flex flex-col gap-1">{admin.map(railLink)}</ul>
          </div>
        ) : null}
      </nav>
    );
  }

  return (
    <nav aria-label={t.nav.main} className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1">
      <ul className="flex gap-1">{work.map(barLink)}</ul>
      {admin.length ? (
        <div className="flex items-center gap-1 border-l border-line pl-1">
          <p className="sr-only">{t.nav.admin}</p>
          <ul className="flex gap-1">{admin.map(barLink)}</ul>
        </div>
      ) : null}
    </nav>
  );
}
