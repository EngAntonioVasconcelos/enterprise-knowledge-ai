"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import { useI18n } from "@/i18n/client";

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
  // Only screens that exist, and that this person may use, are listed.
  const items = [
    { href: "/assistente", label: t.nav.assistant },
    { href: "/documentos", label: t.nav.documents },
    ...(current && managed.includes(current) ? [{ href: "/pessoas", label: t.nav.people }] : []),
  ];
  return (
    <nav aria-label={t.nav.main} className="order-last w-full lg:order-none lg:mt-10 lg:w-auto">
      <ul className="flex gap-1 lg:flex-col">
        {items.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <li key={item.href}>
              <Link
                href={`${item.href}${query}`}
                aria-current={active ? "page" : undefined}
                className={
                  "block rounded-control px-2 py-1.5 text-body transition-colors " +
                  (active
                    ? "bg-surface font-medium text-ink shadow-[inset_2px_0_0_var(--color-cobalt)]"
                    : "text-ink-soft hover:text-ink")
                }
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
