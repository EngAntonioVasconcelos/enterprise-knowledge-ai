"use client";

import { Check, ChevronDown, Languages } from "lucide-react";
import { useRouter } from "next/navigation";
import { DropdownMenu } from "radix-ui";
import { useTransition } from "react";

import { setLocale } from "@/i18n/actions";
import { useI18n } from "@/i18n/client";
import { LANGUAGE_NAMES, LOCALES, isLocale } from "@/i18n/locales";

// The interface language. Saved for the person (cookie) and applied at
// once: the server renders the page again in the new language.
export function LanguageSwitch({ align = "start" }: { align?: "start" | "end" }) {
  const { locale, t } = useI18n();
  const router = useRouter();
  const [pending, startTransition] = useTransition();

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
        aria-label={`${t.language.label}: ${LANGUAGE_NAMES[locale]}`}
        disabled={pending}
        className="inline-flex items-center gap-1.5 rounded-control px-1.5 py-1 text-meta font-medium text-ink-soft transition-colors outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-signal data-[state=open]:text-ink disabled:opacity-60"
      >
        <Languages aria-hidden className="size-3.5" strokeWidth={2} />
        <span lang={locale} className="hidden sm:inline lg:inline">
          {LANGUAGE_NAMES[locale]}
        </span>
        <ChevronDown aria-hidden className="size-3" strokeWidth={2.25} />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align={align}
          sideOffset={6}
          className="z-50 min-w-44 rounded-control border border-line bg-surface p-1 shadow-[0_8px_24px_-12px_rgb(23_32_51/0.35)]"
        >
          <DropdownMenu.Label className="px-2.5 pt-1.5 pb-1 text-meta text-ink-faint">
            {t.language.label}
          </DropdownMenu.Label>
          <DropdownMenu.RadioGroup value={locale} onValueChange={choose}>
            {LOCALES.map((code) => (
              <DropdownMenu.RadioItem
                key={code}
                value={code}
                lang={code}
                className="relative flex cursor-default items-center rounded-[4px] py-1.5 pr-2.5 pl-7 text-body text-ink outline-none select-none data-[highlighted]:bg-signal-wash data-[highlighted]:text-signal-deep"
              >
                <DropdownMenu.ItemIndicator className="absolute left-2 inline-flex">
                  <Check aria-hidden className="size-3.5 text-signal" strokeWidth={2.5} />
                </DropdownMenu.ItemIndicator>
                {LANGUAGE_NAMES[code]}
              </DropdownMenu.RadioItem>
            ))}
          </DropdownMenu.RadioGroup>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
