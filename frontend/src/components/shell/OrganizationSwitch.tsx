"use client";

import { Check, ChevronsUpDown } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { DropdownMenu } from "radix-ui";

import { useI18n } from "@/i18n/client";
import type { Organization } from "@/lib/api-types";

function monogram(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const first = words[0] ?? "";
  const second = words[1] ?? "";
  return ((first.charAt(0) + (second.charAt(0) || first.charAt(1))) || "?").toUpperCase();
}

/**
 * The organization the person is working in: always visible at the top of
 * the frame, so every screen says whose documents these are. With more
 * than one organization it is also where the person switches, staying on
 * the same screen.
 */
export function OrganizationSwitch({
  organizations,
  compact = false,
}: {
  organizations: Organization[];
  compact?: boolean;
}) {
  const { t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  const org = useSearchParams().get("org");
  const active = organizations.find((o) => o.id === org) ?? organizations[0];
  if (!active) return null;

  const role = active.role ? t.people.roles[active.role] : null;
  const card = (
    <>
      <span
        aria-hidden
        className={
          "inline-flex shrink-0 items-center justify-center rounded-[6px] bg-surface font-semibold text-ink shadow-[0_0_0_1px_var(--color-line-strong)] " +
          (compact ? "size-7 text-[0.6875rem]" : "size-8 text-meta")
        }
      >
        {monogram(active.name)}
      </span>
      <span className="min-w-0 flex-1 text-left">
        <span className="block truncate text-meta leading-tight font-semibold text-ink">{active.name}</span>
        {role && !compact ? (
          <span className="block truncate text-[0.75rem] leading-tight text-ink-faint">{role}</span>
        ) : null}
      </span>
    </>
  );

  if (organizations.length < 2) {
    return <div className="flex min-w-0 items-center gap-2.5 rounded-control px-2 py-1.5">{card}</div>;
  }

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        aria-label={`${t.nav.switchOrganization}: ${active.name}`}
        className="flex w-full min-w-0 items-center gap-2.5 rounded-control px-2 py-1.5 transition-colors outline-none hover:bg-surface focus-visible:ring-2 focus-visible:ring-signal data-[state=open]:bg-surface"
      >
        {card}
        <ChevronsUpDown aria-hidden className="size-4 shrink-0 text-ink-faint" />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="start"
          sideOffset={6}
          className="z-50 w-64 rounded-control border border-line bg-surface p-1 shadow-[0_8px_24px_-12px_rgb(23_32_51/0.35)]"
        >
          <DropdownMenu.Label className="px-2.5 pt-1.5 pb-1 text-meta text-ink-faint">
            {t.nav.organization}
          </DropdownMenu.Label>
          {organizations.map((organization) => (
            <DropdownMenu.Item
              key={organization.id}
              onSelect={() => router.push(`${pathname}?org=${organization.id}`)}
              className="flex cursor-default items-center gap-2.5 rounded-[4px] px-2.5 py-2 text-body text-ink outline-none select-none data-[highlighted]:bg-signal-wash"
            >
              <span aria-hidden className="inline-flex size-6 shrink-0 items-center justify-center rounded-[5px] bg-paper text-[0.6875rem] font-semibold text-ink-soft">
                {monogram(organization.name)}
              </span>
              <span className="min-w-0 flex-1 truncate">{organization.name}</span>
              {organization.id === active.id ? (
                <Check aria-hidden className="size-4 shrink-0 text-signal" strokeWidth={2.5} />
              ) : null}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
