"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useI18n } from "@/i18n/client";

export function AppNav() {
  const pathname = usePathname();
  const { t } = useI18n();
  // Only screens that exist are listed: no "coming soon" entries.
  const items = [{ href: "/assistente", label: t.nav.assistant }];
  return (
    <nav aria-label={t.nav.main} className="lg:mt-10">
      <ul className="flex gap-1 lg:flex-col">
        {items.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
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
