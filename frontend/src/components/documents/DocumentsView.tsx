"use client";

import { FileUp } from "lucide-react";
import { useRouter } from "next/navigation";
import { type DragEvent, useEffect, useRef, useState } from "react";

import { SourcesPanel } from "@/components/documents/SourcesPanel";
import { useI18n } from "@/i18n/client";
import type { Connection, DocumentItem, Upload } from "@/lib/api-types";
import {
  ACCEPTED_EXTENSIONS,
  checkFile,
  documentKind,
  type UploadErrorKind,
  VISIBILITIES,
  type Visibility,
} from "@/lib/uploads";

const REFRESH_MS = 4000;

type Props = {
  organizationId: string;
  documents: DocumentItem[];
  canManage: boolean;
  /** Owners, admins and members send files; viewers only read. */
  canUpload?: boolean;
  waiting: Upload[];
  lastError: string | null;
  drive?: Connection | null;
  /** The outcome of connecting Google Drive, after Google sends the person back. */
  notice?: "connected" | "denied" | "expired" | "failed" | null;
};

type Row = {
  key: string;
  title: string;
  kind: ReturnType<typeof documentKind>;
  status: "waiting" | "pending" | "active" | "failed";
  at: string;
};

export async function sendFile(
  organizationId: string,
  sourceName: string,
  file: File,
  visibility: Visibility,
): Promise<UploadErrorKind | null> {
  const body = new FormData();
  body.set("organizationId", organizationId);
  body.set("sourceName", sourceName);
  body.set("visibility", visibility);
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

export function DocumentsView({
  organizationId,
  documents,
  canManage,
  canUpload = canManage,
  waiting,
  lastError,
  drive = null,
  notice = null,
}: Props) {
  const { locale, t: all } = useI18n();
  const t = all.documents;
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [sending, setSending] = useState<string | null>(null);
  const [failures, setFailures] = useState<string[]>([]);
  const [sent, setSent] = useState(0);
  // Members share with the whole organization only when they choose to.
  const [visibility, setVisibility] = useState<Visibility>(canManage ? "organization" : "private");

  const rows: Row[] = [
    ...waiting.map((upload) => ({
      key: `u-${upload.id}`,
      title: upload.filename,
      kind: documentKind(upload.mime_type),
      status: "waiting" as const,
      at: upload.created_at,
    })),
    ...documents.map((document) => ({
      key: document.id,
      title: document.title,
      kind: documentKind(document.mime_type),
      status: (["pending", "active", "failed"].includes(document.status)
        ? document.status
        : "pending") as Row["status"],
      at: document.updated_at,
    })),
  ];
  // The first reading of a new source counts as work in progress too.
  const firstSync = Boolean(drive && drive.status === "active" && !drive.last_synced_at);
  const busy = firstSync || rows.some((row) => row.status === "waiting" || row.status === "pending");

  // While something is being read, look again every few seconds.
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(() => router.refresh(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [busy, router]);

  async function upload(files: File[]) {
    if (!files.length || sending) return;
    const problems: string[] = [];
    let done = 0;
    for (const file of files) {
      const local = checkFile(file);
      if (local) {
        problems.push(t.failedFile(file.name, t.errors[local]));
        continue;
      }
      setSending(file.name);
      const error = await sendFile(organizationId, t.sourceName, file, visibility);
      if (error) problems.push(t.failedFile(file.name, t.errors[error]));
      else done += 1;
    }
    setSending(null);
    setFailures(problems);
    setSent(done);
    if (done) router.refresh();
  }

  function onDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setDragging(false);
    void upload(Array.from(event.dataTransfer.files));
  }

  const date = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" });

  return (
    <div>
      <h1 className="text-question font-semibold tracking-[-0.02em]">{t.title}</h1>
      <p className="mt-3 max-w-[40rem] text-lead text-ink-soft text-pretty">{t.lead}</p>
      {notice ? (
        <p
          role="status"
          className={
            "mt-6 max-w-[40rem] border-l-2 pl-4 text-body " +
            (notice === "connected" ? "border-checked text-checked" : "border-caution text-caution")
          }
        >
          {t.notice[notice]}
        </p>
      ) : null}

      {canUpload ? (
        <fieldset className="mt-8">
          <legend className="font-medium text-ink">{t.visibilityLabel}</legend>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {VISIBILITIES.map((option) => (
              <label
                key={option}
                className={
                  "flex cursor-pointer items-start gap-2.5 rounded-control border px-3.5 py-3 transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-cobalt " +
                  (visibility === option ? "border-cobalt bg-cobalt-wash" : "border-line-strong bg-surface hover:border-ink-soft")
                }
              >
                <input
                  type="radio"
                  name="visibility"
                  value={option}
                  checked={visibility === option}
                  onChange={() => setVisibility(option)}
                  className="mt-1 accent-[var(--color-cobalt)]"
                />
                <span>
                  <span className="block text-body text-ink">{t.visibility[option]}</span>
                  <span className="block text-meta text-ink-soft text-pretty">{t.visibilityHint[option]}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
      ) : null}

      {canUpload ? (
        <section
          aria-label={t.drop}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={
            "mt-4 flex flex-col items-start gap-4 rounded-panel border px-6 py-6 transition-colors sm:flex-row sm:items-center " +
            (dragging ? "border-cobalt bg-cobalt-wash" : "border-line-strong bg-surface")
          }
        >
          <FileUp aria-hidden className="size-6 shrink-0 text-cobalt" strokeWidth={1.75} />
          <div className="min-w-0 flex-1">
            <p className="font-medium text-ink">
              {dragging ? t.dropActive : t.drop}{" "}
              <button
                type="button"
                onClick={() => input.current?.click()}
                disabled={Boolean(sending)}
                className="font-medium text-cobalt underline underline-offset-4 hover:text-cobalt-deep disabled:opacity-60"
              >
                {t.choose}
              </button>
            </p>
            <p className="mt-1 text-meta text-ink-faint">{t.formats}</p>
          </div>
          <input
            ref={input}
            type="file"
            multiple
            accept={ACCEPTED_EXTENSIONS.join(",")}
            className="sr-only"
            tabIndex={-1}
            aria-hidden
            onChange={(event) => {
              void upload(Array.from(event.target.files ?? []));
              event.target.value = "";
            }}
          />
        </section>
      ) : (
        <p className="mt-8 border-l-2 border-line pl-4 text-meta text-ink-soft">{t.readOnly}</p>
      )}

      <div aria-live="polite" className="mt-4 space-y-1 text-meta">
        {sending ? <p className="text-ink-soft">{t.sending(sending)}</p> : null}
        {!sending && sent ? <p className="text-checked">{t.sent(sent)}</p> : null}
        {failures.map((failure) => (
          <p key={failure} role="alert" className="text-danger">
            {failure}
          </p>
        ))}
        {lastError ? (
          <p className="text-caution">
            {t.lastError} {lastError}
          </p>
        ) : null}
      </div>

      {canManage ? <SourcesPanel organizationId={organizationId} drive={drive} /> : null}

      {rows.length ? (
        <table className="mt-10 w-full table-fixed border-collapse text-left">
          <thead>
            <tr className="border-b border-line text-meta text-ink-faint">
              <th scope="col" className="py-2 pr-4 font-medium">{t.columns.name}</th>
              <th scope="col" className="hidden w-24 py-2 pr-4 font-medium sm:table-cell">{t.columns.kind}</th>
              <th scope="col" className="w-36 py-2 pr-4 font-medium sm:w-44">{t.columns.status}</th>
              <th scope="col" className="hidden w-44 py-2 font-medium md:table-cell">{t.columns.updated}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} className="border-b border-line align-baseline">
                <td className="py-3 pr-4">
                  <span className="block truncate text-ink" title={row.title}>
                    {row.title}
                  </span>
                </td>
                <td className="hidden py-3 pr-4 text-meta text-ink-soft sm:table-cell">{t.kinds[row.kind]}</td>
                <td className="py-3 pr-4">
                  <Status status={row.status} label={t.status[row.status]} />
                </td>
                <td className="hidden py-3 text-meta text-ink-soft tabular-nums md:table-cell">
                  {date.format(new Date(row.at))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <section className="mt-12 max-w-[36rem]">
          <h2 className="text-lead font-semibold">{t.emptyTitle}</h2>
          <p className="mt-2 text-ink-soft text-pretty">{canUpload ? t.emptyBody : t.emptyReadOnly}</p>
        </section>
      )}
    </div>
  );
}

function Status({ status, label }: { status: Row["status"]; label: string }) {
  const tone = {
    waiting: "text-ink-soft",
    pending: "text-cobalt-deep",
    active: "text-checked",
    failed: "text-danger",
  }[status];
  return (
    <span className={`inline-flex items-center gap-2 text-meta font-medium whitespace-nowrap ${tone}`}>
      <span
        aria-hidden
        className={
          "size-1.5 rounded-full bg-current " + (status === "pending" || status === "waiting" ? "eka-pulse" : "")
        }
      />
      {label}
    </span>
  );
}
