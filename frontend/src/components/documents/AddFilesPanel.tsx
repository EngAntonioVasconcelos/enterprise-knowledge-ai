"use client";

import { FileUp, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { Dialog } from "radix-ui";
import { type DragEvent, type ReactNode, useRef, useState } from "react";

import { useI18n } from "@/i18n/client";
import type { Colleague, Upload } from "@/lib/api-types";
import { plain } from "@/lib/text";
import {
  ACCEPTED_EXTENSIONS,
  checkFile,
  MAX_READERS,
  type UploadErrorKind,
  VISIBILITIES,
  type Visibility,
} from "@/lib/uploads";

type Choice = "replace" | "keep" | "skip";

/** A file whose name is already taken, and what to do with it. */
type Duplicate = { file: File; own: Upload[]; choice: Choice };

type Props = {
  organizationId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  canManage: boolean;
  colleagues: Colleague[];
  /** Names already in the list, to warn before a second copy. */
  existingNames: string[];
  /** The person's own files: only these can be replaced. */
  ownFiles: Upload[];
  /** Other ways to add documents (Google Drive), for owners and admins. */
  children?: ReactNode;
};

export async function sendFile(
  organizationId: string,
  sourceName: string,
  file: File,
  visibility: Visibility,
  readers: string[] = [],
): Promise<UploadErrorKind | null> {
  const body = new FormData();
  body.set("organizationId", organizationId);
  body.set("sourceName", sourceName);
  body.set("visibility", visibility);
  if (visibility === "people") for (const reader of readers) body.append("readers", reader);
  body.set("file", file);
  try {
    const response = await fetch("/api/uploads", { method: "POST", body });
    if (response.ok) return null;
    const data = (await response.json().catch(() => ({}))) as { error?: UploadErrorKind };
    return data.error ?? "unavailable";
  } catch {
    return "unavailable";
  }
}

/** Takes out one of the person's own files; true when it is gone. */
export async function removeFile(organizationId: string, upload: Upload): Promise<boolean> {
  try {
    const response = await fetch("/api/uploads", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ organizationId, connectionId: upload.connection_id, uploadId: upload.id }),
    });
    return response.ok;
  } catch {
    return false;
  }
}

export function AddFilesPanel({
  organizationId,
  open,
  onOpenChange,
  canManage,
  colleagues,
  existingNames,
  ownFiles,
  children,
}: Props) {
  const { t: all } = useI18n();
  const t = all.documents;
  const d = t.duplicates;
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [sending, setSending] = useState<string | null>(null);
  const [messages, setMessages] = useState<{ done: string[]; failures: string[]; sent: number }>({
    done: [],
    failures: [],
    sent: 0,
  });
  // Files waiting for a decision because their name is taken.
  const [review, setReview] = useState<{ clean: File[]; duplicates: Duplicate[] } | null>(null);
  // Members share with the whole organization only when they choose to.
  const [visibility, setVisibility] = useState<Visibility>(canManage ? "organization" : "private");
  const [readers, setReaders] = useState<string[]>([]);
  const [filter, setFilter] = useState("");
  // Sharing with chosen people needs at least one person chosen.
  const blocked = visibility === "people" && !readers.length;
  const shown = colleagues.filter((colleague) => plain(colleague.full_name).includes(plain(filter.trim())));
  const taken = new Set(existingNames.map((name) => plain(name.trim())));

  function toggle(userId: string) {
    setReaders((chosen) =>
      chosen.includes(userId)
        ? chosen.filter((id) => id !== userId)
        : chosen.length < MAX_READERS
          ? [...chosen, userId]
          : chosen,
    );
  }

  async function choose(files: File[]) {
    if (!files.length || sending || blocked) return;
    const failures: string[] = [];
    const clean: File[] = [];
    const duplicates: Duplicate[] = [];
    for (const file of files) {
      const local = checkFile(file);
      if (local) {
        failures.push(t.failedFile(file.name, t.errors[local]));
        continue;
      }
      const name = plain(file.name.trim());
      if (!taken.has(name)) {
        clean.push(file);
        continue;
      }
      const own = ownFiles.filter((upload) => plain(upload.filename.trim()) === name);
      // Replacing is the usual wish, but only a file of one's own can go.
      duplicates.push({ file, own, choice: own.length ? "replace" : "keep" });
    }
    setMessages({ done: [], failures, sent: 0 });
    if (duplicates.length) setReview({ clean, duplicates });
    else await send(clean, [], failures);
  }

  async function send(clean: File[], duplicates: Duplicate[], failures: string[] = messages.failures) {
    setReview(null);
    const problems = [...failures];
    const done: string[] = [];
    let sent = 0;
    const plan = [
      ...clean.map((file) => ({ file, own: [] as Upload[] })),
      ...duplicates
        .filter((item) => item.choice !== "skip")
        .map((item) => ({ file: item.file, own: item.choice === "replace" ? item.own : [] })),
    ];
    for (const { file, own } of plan) {
      setSending(file.name);
      const error = await sendFile(organizationId, t.sourceName, file, visibility, readers);
      if (error) {
        problems.push(t.failedFile(file.name, t.errors[error]));
        continue;
      }
      sent += 1;
      if (own.length) {
        // The new version is in: only now does the old one go.
        const gone = await Promise.all(own.map((upload) => removeFile(organizationId, upload)));
        if (gone.every(Boolean)) done.push(d.replaced(file.name));
        else problems.push(d.notReplaced(file.name));
      }
    }
    setSending(null);
    setMessages({ done, failures: problems, sent });
    if (sent) router.refresh();
  }

  function pick(index: number, choice: Choice) {
    setReview((current) =>
      current
        ? {
            ...current,
            duplicates: current.duplicates.map((item, i) => (i === index ? { ...item, choice } : item)),
          }
        : current,
    );
  }

  function onDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setDragging(false);
    void choose(Array.from(event.dataTransfer.files));
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-rail/35" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[30rem] flex-col border-l border-line bg-surface shadow-[-24px_0_60px_rgb(10_12_14/0.18)] outline-none">
          <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-5">
            <div>
              <Dialog.Title className="text-lead font-semibold text-ink">{t.add}</Dialog.Title>
              <Dialog.Description className="mt-1 text-meta text-ink-soft text-pretty">{t.addLead}</Dialog.Description>
            </div>
            <Dialog.Close
              aria-label={t.close}
              className="-mr-2 grid size-9 shrink-0 place-items-center rounded-control text-ink-soft hover:bg-paper hover:text-ink focus-visible:outline-2 focus-visible:outline-signal"
            >
              <X aria-hidden className="size-5" strokeWidth={1.75} />
            </Dialog.Close>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-6">
            <fieldset>
              <legend className="font-medium text-ink">{t.visibilityLabel}</legend>
              <div className="mt-2 grid gap-2">
                {VISIBILITIES.map((option) => (
                  <label
                    key={option}
                    className={
                      "flex cursor-pointer items-start gap-2.5 rounded-control border px-3.5 py-3 transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-signal " +
                      (visibility === option ? "border-signal bg-signal-wash" : "border-line-strong bg-surface hover:border-ink-soft")
                    }
                  >
                    <input
                      type="radio"
                      name="visibility"
                      value={option}
                      checked={visibility === option}
                      onChange={() => setVisibility(option)}
                      className="mt-1 accent-[var(--color-signal)]"
                    />
                    <span>
                      <span className="block text-body text-ink">{t.visibility[option]}</span>
                      <span className="block text-meta text-ink-soft text-pretty">{t.visibilityHint[option]}</span>
                    </span>
                  </label>
                ))}
              </div>
              {visibility === "people" ? (
                <div className="mt-3 rounded-control border border-line-strong px-3.5 py-3">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <p className="text-meta text-ink-soft">{t.chosen(readers.length)}</p>
                    {colleagues.length > 8 ? (
                      <input
                        type="search"
                        value={filter}
                        onChange={(event) => setFilter(event.target.value)}
                        placeholder={t.findPerson}
                        aria-label={t.findPerson}
                        className="h-9 w-full rounded-control border border-line-strong bg-surface px-3 text-body text-ink outline-none focus:border-signal"
                      />
                    ) : null}
                  </div>
                  {colleagues.length ? (
                    <ul className="mt-2 grid max-h-56 gap-1 overflow-y-auto">
                      {shown.map((colleague) => (
                        <li key={colleague.user_id}>
                          <label className="flex cursor-pointer items-center gap-2.5 rounded-control px-2 py-1.5 hover:bg-signal-wash">
                            <input
                              type="checkbox"
                              checked={readers.includes(colleague.user_id)}
                              onChange={() => toggle(colleague.user_id)}
                              className="accent-[var(--color-signal)]"
                            />
                            <span className="min-w-0 truncate text-body text-ink">{colleague.full_name}</span>
                            <span className="text-meta text-ink-faint">{all.people.roles[colleague.role]}</span>
                          </label>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-2 text-meta text-ink-soft">{t.noColleagues}</p>
                  )}
                </div>
              ) : null}
            </fieldset>

            {review ? (
              <section aria-labelledby="duplicates-title" className="mt-6 rounded-panel border border-caution/50 px-4 py-4">
                <h3 id="duplicates-title" className="font-semibold text-ink">
                  {d.title(review.duplicates.length)}
                </h3>
                <p className="mt-1 text-meta text-ink-soft text-pretty">{d.hint}</p>
                <ul className="mt-3 divide-y divide-line">
                  {review.duplicates.map((item, index) => (
                    <li key={`${item.file.name}-${index}`} className="py-3">
                      <fieldset>
                        <legend className="truncate text-body font-medium text-ink" title={item.file.name}>
                          {item.file.name}
                        </legend>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {(["replace", "keep", "skip"] as const).map((choice) => {
                            const unavailable = choice === "replace" && !item.own.length;
                            return (
                              <label
                                key={choice}
                                className={
                                  "rounded-control border px-3 py-1.5 text-meta has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-signal " +
                                  (unavailable
                                    ? "cursor-not-allowed border-line text-ink-faint"
                                    : item.choice === choice
                                      ? "cursor-pointer border-signal bg-signal-wash text-signal-deep"
                                      : "cursor-pointer border-line-strong text-ink-soft hover:border-ink-soft")
                                }
                              >
                                <input
                                  type="radio"
                                  className="sr-only"
                                  name={`duplicate-${index}`}
                                  checked={item.choice === choice}
                                  disabled={unavailable}
                                  onChange={() => pick(index, choice)}
                                />
                                {d[choice]}
                              </label>
                            );
                          })}
                        </div>
                        <p className="mt-1.5 text-meta text-ink-faint text-pretty">
                          {item.own.length ? (item.choice === "replace" ? d.replaceHint : null) : d.notYours}
                        </p>
                      </fieldset>
                    </li>
                  ))}
                </ul>
                <div className="mt-3 flex gap-2">
                  <button
                    type="button"
                    onClick={() => void send(review.clean, review.duplicates)}
                    className="h-10 rounded-control bg-ink px-4 font-medium text-white transition-colors hover:bg-signal-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal"
                  >
                    {d.send}
                  </button>
                  <button
                    type="button"
                    onClick={() => setReview(null)}
                    className="h-10 rounded-control px-4 font-medium text-ink-soft hover:bg-paper hover:text-ink focus-visible:outline-2 focus-visible:outline-signal"
                  >
                    {d.cancel}
                  </button>
                </div>
              </section>
            ) : (
              <section
                aria-label={t.drop}
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                className={
                  "mt-6 flex flex-col items-center gap-3 rounded-panel border border-dashed px-6 py-8 text-center transition-colors " +
                  (dragging ? "border-signal bg-signal-wash" : "border-line-strong")
                }
              >
                <FileUp aria-hidden className="size-6 text-signal" strokeWidth={1.75} />
                <p className="font-medium text-ink">
                  {dragging ? t.dropActive : t.drop}{" "}
                  <button
                    type="button"
                    onClick={() => input.current?.click()}
                    disabled={Boolean(sending) || blocked}
                    className="font-medium text-signal underline underline-offset-4 hover:text-signal-deep disabled:opacity-60"
                  >
                    {t.choose}
                  </button>
                </p>
                <p className="text-meta text-ink-faint">{t.formats}</p>
                {blocked ? <p className="text-meta text-caution">{t.chooseFirst}</p> : null}
                <input
                  ref={input}
                  type="file"
                  multiple
                  accept={ACCEPTED_EXTENSIONS.join(",")}
                  className="sr-only"
                  tabIndex={-1}
                  aria-hidden
                  onChange={(event) => {
                    void choose(Array.from(event.target.files ?? []));
                    event.target.value = "";
                  }}
                />
              </section>
            )}

            <div aria-live="polite" className="mt-4 space-y-1 text-meta">
              {sending ? <p className="text-ink-soft">{t.sending(sending)}</p> : null}
              {!sending && messages.sent ? <p className="text-checked">{t.sent(messages.sent)}</p> : null}
              {messages.done.map((line) => (
                <p key={line} className="text-checked">
                  {line}
                </p>
              ))}
              {messages.failures.map((failure) => (
                <p key={failure} role="alert" className="text-danger">
                  {failure}
                </p>
              ))}
            </div>

            {children}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
