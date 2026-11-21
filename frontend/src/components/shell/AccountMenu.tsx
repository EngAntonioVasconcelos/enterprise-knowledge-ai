"use client";

import { Check, ChevronsUpDown, LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { DropdownMenu } from "radix-ui";
import { useTransition } from "react";

import { Avatar } from "@/components/shell/Avatar";
import { setLocale } from "@/i18n/actions";
import { useI18n } from "@/i18n/client";
import { LANGUAGE_NAMES, LOCALES, isLocale } from "@/i18n/locales";

/**
 * Who is signed in, with what belongs to the person and not to the
 * organization: the interface language and signing out. One quiet row at
 * the bottom of the frame (or the photo alone on small screens).
 */
export function AccountMenu({
  name,
  email,
  picture,
  compact = false,
}: {
  name: string | null | undefined;
  email: string;
  picture?: string | null;
  compact?: boolean;
}) {
  const { locale, t } = useI18n();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const shown = name || email;

  function choose(value: string) {
    if (!isLocale(value) || value === locale) return;
    startTransition(async () => {
      await setLocale(value);
      router.refresh();
    });
  }

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        aria-label={`${t.nav.account}: ${shown}`}
        disabled={pending}
        className={
          "flex min-w-0 items-center gap-2.5 rounded-control transition-colors outline-none hover:bg-surface focus-visible:ring-2 focus-visible:ring-cobalt data-[state=open]:bg-surface disabled:opacity-60 " +
          (compact ? "p-1" : "w-full px-2 py-2")
        }
      >
        <Avatar name={name} email={email} picture={picture} size="sm" />
        {compact ? null : (
          <>
            <span className="min-w-0 flex-1 text-left">
              <span className="block truncate text-meta leading-tight font-medium text-ink">{shown}</span>
              {email && email !== shown ? (
                <span className="block truncate text-[0.75rem] leading-tight text-ink-faint">{email}</span>
              ) : null}
            </span>
            <ChevronsUpDown aria-hidden className="size-4 shrink-0 text-ink-faint" />
          </>
        )}
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align={compact ? "end" : "start"}
          side={compact ? "bottom" : "top"}
          sideOffset={6}
          className="z-50 w-60 rounded-control border border-line bg-surface p-1 shadow-[0_8px_24px_-12px_rgb(23_32_51/0.35)]"
        >
          <div className="px-2.5 pt-2 pb-2">
            <p className="truncate text-meta font-medium text-ink">{shown}</p>
            {email && email !== shown ? <p className="truncate text-[0.75rem] text-ink-faint">{email}</p> : null}
          </div>
          <DropdownMenu.Separator className="my-1 h-px bg-line" />
          <DropdownMenu.Label className="px-2.5 pt-1.5 pb-1 text-meta text-ink-faint">{t.language.label}</DropdownMenu.Label>
          <DropdownMenu.RadioGroup value={locale} onValueChange={choose}>
            {LOCALES.map((code) => (
              <DropdownMenu.RadioItem
                key={code}
                value={code}
                lang={code}
                className="relative flex cursor-default items-center rounded-[4px] py-1.5 pr-2.5 pl-7 text-body text-ink outline-none select-none data-[highlighted]:bg-cobalt-wash data-[highlighted]:text-cobalt-deep"
              >
                <DropdownMenu.ItemIndicator className="absolute left-2 inline-flex">
                  <Check aria-hidden className="size-3.5 text-cobalt" strokeWidth={2.5} />
                </DropdownMenu.ItemIndicator>
                {LANGUAGE_NAMES[code]}
              </DropdownMenu.RadioItem>
            ))}
          </DropdownMenu.RadioGroup>
          <DropdownMenu.Separator className="my-1 h-px bg-line" />
          <DropdownMenu.Item asChild>
            <a
              href="/auth/logout"
              className="flex cursor-default items-center gap-2 rounded-[4px] px-2.5 py-1.5 text-body text-ink outline-none select-none data-[highlighted]:bg-cobalt-wash data-[highlighted]:text-cobalt-deep"
            >
              <LogOut aria-hidden className="size-4 text-ink-soft" />
              {t.nav.signOut}
            </a>
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
