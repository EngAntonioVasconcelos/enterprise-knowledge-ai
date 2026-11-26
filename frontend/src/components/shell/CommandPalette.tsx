"use client";

import {
  ArrowRightLeft,
  ChartColumn,
  FileText,
  History,
  type LucideIcon,
  MessageSquareText,
  Search,
  SearchX,
  Settings,
  Users,
} from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Dialog } from "radix-ui";
import { type KeyboardEvent, useEffect, useMemo, useState } from "react";

import { useI18n } from "@/i18n/client";
import type { Organization } from "@/lib/api-types";
import { plain } from "@/lib/text";

/** Asks the one palette on the page to open (from any trigger button). */
export const OPEN_COMMANDS = "eka:commands";

export function openCommands() {
  window.dispatchEvent(new Event(OPEN_COMMANDS));
}

type Command = { id: string; group: "ask" | "go" | "organizations"; label: string; hint?: string; icon: LucideIcon; run: () => void };


/**
 * One place to ask, go to a screen or change organization, from the
 * keyboard (Ctrl+K, or Cmd+K on a Mac). It lists only what this person
 * may open, the same as the navigation.
 */
export function CommandPalette({
  organizations,
  managed = [],
}: {
  organizations: Organization[];
  /** Organizations where the person is an owner or an admin. */
  managed?: string[];
}) {
  const { t } = useI18n();
  const c = t.commands;
  const router = useRouter();
  const pathname = usePathname();
  const org = useSearchParams().get("org");
  const current = organizations.find((o) => o.id === org) ?? organizations[0] ?? null;
  const query = current ? `?org=${encodeURIComponent(current.id)}` : "";
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [index, setIndex] = useState(0);

  useEffect(() => {
    function onKey(event: globalThis.KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      }
    }
    function onOpen() {
      setOpen(true);
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_COMMANDS, onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_COMMANDS, onOpen);
    };
  }, []);

  const commands = useMemo<Command[]>(() => {
    const go = (href: string) => () => router.push(`${href}${query}`);
    const manages = Boolean(current && managed.includes(current.id));
    const screens: Command[] = [
      { id: "assistente", group: "go", label: t.nav.assistant, icon: MessageSquareText, run: go("/assistente") },
      { id: "documentos", group: "go", label: t.nav.documents, icon: FileText, run: go("/documentos") },
      { id: "historico", group: "go", label: t.nav.history, icon: History, run: go("/historico") },
      ...(manages
        ? ([
            { id: "painel", group: "go", label: t.nav.dashboard, icon: ChartColumn, run: go("/painel") },
            { id: "lacunas", group: "go", label: t.nav.gaps, icon: SearchX, run: go("/lacunas") },
            { id: "pessoas", group: "go", label: t.nav.people, icon: Users, run: go("/pessoas") },
            { id: "definicoes", group: "go", label: t.nav.settings, icon: Settings, run: go("/definicoes") },
          ] as Command[])
        : []),
    ];
    const others: Command[] =
      organizations.length > 1
        ? organizations
            .filter((o) => o.id !== current?.id)
            .map((o) => ({
              id: `org-${o.id}`,
              group: "organizations" as const,
              label: c.switchTo(o.name),
              icon: ArrowRightLeft,
              run: () => router.push(`${pathname}?org=${encodeURIComponent(o.id)}`),
            }))
        : [];
    const wanted = plain(text.trim());
    const found = [...screens, ...others].filter((command) => !wanted || plain(command.label).includes(wanted));
    const ask: Command[] = text.trim()
      ? [
          {
            id: "ask",
            group: "ask",
            label: c.ask(text.trim()),
            icon: MessageSquareText,
            run: () =>
              router.push(`/assistente${query ? `${query}&` : "?"}q=${encodeURIComponent(text.trim())}`),
          },
        ]
      : [];
    return [...ask, ...found];
  }, [text, current, managed, organizations, pathname, query, router, t, c]);

  const chosen = Math.min(index, Math.max(commands.length - 1, 0));

  function close(value: boolean) {
    setOpen(value);
    if (!value) {
      setText("");
      setIndex(0);
    }
  }

  function run(command: Command | undefined) {
    if (!command) return;
    close(false);
    command.run();
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setIndex((chosen + 1) % Math.max(commands.length, 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setIndex((chosen - 1 + commands.length) % Math.max(commands.length, 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      run(commands[chosen]);
    }
  }

  const groups: { key: Command["group"]; title: string }[] = [
    { key: "ask", title: c.groups.ask },
    { key: "go", title: c.groups.go },
    { key: "organizations", title: c.groups.organizations },
  ];

  return (
    <Dialog.Root open={open} onOpenChange={close}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-rail/45" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed top-[12vh] left-1/2 z-50 w-[min(40rem,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden rounded-panel bg-surface shadow-[0_24px_60px_rgb(10_12_14/0.28),0_2px_6px_rgb(10_12_14/0.12)]"
        >
          <Dialog.Title className="sr-only">{c.title}</Dialog.Title>
          <div className="flex items-center gap-3 border-b border-line px-4 py-3.5">
            <Search aria-hidden className="size-[1.125rem] text-ink-faint" strokeWidth={2} />
            <input
              autoFocus
              value={text}
              onChange={(event) => {
                setText(event.target.value);
                setIndex(0);
              }}
              onKeyDown={onKeyDown}
              placeholder={c.placeholder}
              aria-label={c.placeholder}
              role="combobox"
              aria-expanded="true"
              aria-controls="eka-commands"
              aria-activedescendant={commands[chosen] ? `eka-command-${commands[chosen].id}` : undefined}
              className="min-w-0 flex-1 bg-transparent text-lead text-ink outline-none placeholder:text-ink-faint"
            />
            <kbd className="rounded-[5px] border border-line-strong px-1.5 py-0.5 font-sans text-[0.75rem] text-ink-soft">Esc</kbd>
          </div>

          <div id="eka-commands" role="listbox" aria-label={c.title} className="max-h-[50vh] overflow-y-auto p-2">
            {commands.length ? (
              groups.map((group) => {
                const items = commands.filter((command) => command.group === group.key);
                if (!items.length) return null;
                return (
                  <div key={group.key} role="group" aria-label={group.title}>
                    <p aria-hidden className="px-2.5 pt-2 pb-1.5 text-[0.75rem] font-semibold text-ink-faint">
                      {group.title}
                    </p>
                    {items.map((command) => {
                      const selected = commands[chosen]?.id === command.id;
                      const Icon = command.icon;
                      return (
                        <div
                          key={command.id}
                          id={`eka-command-${command.id}`}
                          role="option"
                          aria-selected={selected}
                          onMouseEnter={() => setIndex(commands.indexOf(command))}
                          onClick={() => run(command)}
                          className={
                            "flex cursor-pointer items-center gap-3 rounded-control px-3 py-2.5 text-body " +
                            (selected ? "bg-signal-wash text-ink" : "text-ink")
                          }
                        >
                          <Icon aria-hidden className={"size-[1.125rem] shrink-0 " + (selected ? "text-signal" : "text-ink-faint")} strokeWidth={1.8} />
                          <span className="min-w-0 flex-1 truncate">{command.label}</span>
                          {selected ? <kbd className="font-sans text-[0.75rem] text-ink-soft">Enter</kbd> : null}
                        </div>
                      );
                    })}
                  </div>
                );
              })
            ) : (
              <p className="px-3 py-6 text-center text-body text-ink-soft">{c.nothing}</p>
            )}
          </div>

          <div className="flex flex-wrap gap-x-5 gap-y-1 border-t border-line px-4 py-2.5 text-[0.75rem] text-ink-faint">
            <span>{c.keys}</span>
            <span className="ml-auto">{c.onlyYours}</span>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** The wide button that opens the palette, with its shortcut. */
export function CommandTrigger({ compact = false }: { compact?: boolean }) {
  const { t } = useI18n();
  // The server cannot know the keyboard; the browser corrects the label.
  const mac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);
  if (compact) {
    return (
      <button
        type="button"
        onClick={openCommands}
        aria-label={t.commands.open}
        className="flex size-10 shrink-0 items-center justify-center rounded-control text-ink-soft hover:bg-surface hover:text-ink"
      >
        <Search aria-hidden className="size-5" strokeWidth={1.9} />
      </button>
    );
  }
  return (
    <button
      type="button"
      onClick={openCommands}
      className="flex h-10 w-[min(24rem,100%)] items-center gap-2.5 rounded-control border border-line-strong bg-surface/70 px-3 text-body text-ink-faint transition-colors hover:border-ink-faint hover:text-ink-soft"
    >
      <Search aria-hidden className="size-4" strokeWidth={2} />
      <span className="flex-1 truncate text-left">{t.commands.open}</span>
      <kbd
        suppressHydrationWarning
        className="rounded-[5px] border border-line-strong bg-surface px-1.5 py-0.5 font-sans text-[0.75rem] text-ink-soft"
      >
        {mac ? "\u2318 K" : "Ctrl K"}
      </kbd>
    </button>
  );
}
