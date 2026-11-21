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
}: {
  /** Organizations where the person is an owner or an admin. */
  managed?: string[];
  /** The organization screens open on when none is chosen. */
  fallback?: string | null;
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

  function link(item: Item) {
    const active = pathname.startsWith(item.href);
    const Icon = item.icon;
    return (
      <li key={item.href} className="shrink-0">
        <Link
          href={`${item.href}${query}`}
          aria-current={active ? "page" : undefined}
          className={
            "group flex items-center gap-2.5 rounded-control px-2.5 py-2 text-body whitespace-nowrap transition-colors " +
            (active
              ? "bg-surface font-medium text-ink shadow-[0_1px_2px_rgb(23_32_51/0.06),0_0_0_1px_var(--color-line)]"
              : "text-ink-soft hover:bg-surface/60 hover:text-ink")
          }
        >
          <Icon
            aria-hidden
            className={"size-[1.125rem] shrink-0 " + (active ? "text-cobalt" : "text-ink-faint group-hover:text-ink-soft")}
            strokeWidth={1.75}
          />
          {item.label}
        </Link>
      </li>
    );
  }

  return (
    <nav aria-label={t.nav.main} className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1 lg:mx-0 lg:block lg:overflow-visible lg:px-0 lg:pb-0">
      <ul className="flex gap-1 lg:flex-col">{work.map(link)}</ul>
      {admin.length ? (
        <div className="flex items-center gap-1 border-l border-line pl-1 lg:mt-6 lg:block lg:border-0 lg:pl-0">
          <p className="hidden px-2.5 pb-1.5 text-[0.75rem] font-medium text-ink-faint lg:block">{t.nav.admin}</p>
          <ul className="flex gap-1 lg:flex-col">{admin.map(link)}</ul>
        </div>
      ) : null}
    </nav>
  );
}
