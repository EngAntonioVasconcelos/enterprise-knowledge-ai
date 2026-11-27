"use client";

import Link from "next/link";
import { Plus, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AddFilesPanel } from "@/components/documents/AddFilesPanel";
import { SourcesPanel } from "@/components/documents/SourcesPanel";
import { useI18n } from "@/i18n/client";
import type { Audience, Colleague, Connection, DocumentItem, Upload } from "@/lib/api-types";
import { plain } from "@/lib/text";
import { documentKind } from "@/lib/uploads";

const REFRESH_MS = 4000;

type Props = {
  organizationId: string;
  documents: DocumentItem[];
  canManage: boolean;
  /** Owners, admins and members send files; viewers only read. */
  canUpload?: boolean;
  /** Who a file can be shared with, for "Pessoas escolhidas". */
  colleagues?: Colleague[];
  waiting: Upload[];
  /** The person's own files, read or not: what "Substituir" can take out. */
  ownFiles?: Upload[];
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
  source: string | null;
  audience: Audience | null;
  /** Its own page, once it is a document (not a file still waiting). */
  href: string | null;
};

type Group = "all" | "ready" | "reading" | "failed";
const GROUPS: Group[] = ["all", "ready", "reading", "failed"];

function groupOf(status: Row["status"]): Exclude<Group, "all"> {
  if (status === "active") return "ready";
  if (status === "failed") return "failed";
  return "reading";
}

// A file still waiting to be read is shared as it was sent.
const SENT_AS: Record<string, Audience> = { organization: "organization", private: "only_you", people: "people" };

export function DocumentsView({
  organizationId,
  documents,
  canManage,
  canUpload = canManage,
  colleagues = [],
  waiting,
  ownFiles = [],
  lastError,
  drive = null,
  notice = null,
}: Props) {
  const { locale, t: all } = useI18n();
  const t = all.documents;
  const router = useRouter();
  const [adding, setAdding] = useState(false);
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState<Group>("all");
  const [origin, setOrigin] = useState("");

  const rows: Row[] = [
    ...waiting.map((upload) => ({
      key: `u-${upload.id}`,
      title: upload.filename,
      kind: documentKind(upload.mime_type),
      status: "waiting" as const,
      at: upload.created_at,
      source: t.origins.file_upload,
      audience: upload.visibility ? (SENT_AS[upload.visibility] ?? null) : null,
      href: null,
    })),
    ...documents.map((document) => ({
      key: document.id,
      title: document.title,
      kind: documentKind(document.mime_type),
      status: (["pending", "active", "failed"].includes(document.status)
        ? document.status
        : "pending") as Row["status"],
      at: document.updated_at,
      source: document.source
        ? (t.origins[document.source.provider as keyof typeof t.origins] ?? document.source.name)
        : null,
      audience: document.audience ?? null,
      href: `/documentos/${document.id}?org=${encodeURIComponent(organizationId)}`,
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

  const counts: Record<Group, number> = { all: rows.length, ready: 0, reading: 0, failed: 0 };
  for (const row of rows) counts[groupOf(row.status)] += 1;
  const origins = [...new Set(rows.map((row) => row.source).filter((source): source is string => Boolean(source)))];
  const wanted = plain(query.trim());
  const shown = rows.filter(
    (row) =>
      (group === "all" || groupOf(row.status) === group) &&
      (!origin || row.source === origin) &&
      (!wanted || plain(row.title).includes(wanted)),
  );
  const filtered = shown.length !== rows.length;

  function clearFilters() {
    setQuery("");
    setGroup("all");
    setOrigin("");
  }

  const date = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" });

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
        <div className="min-w-0">
          <h1 className="text-question font-semibold tracking-[-0.02em]">{t.title}</h1>
          <p className="mt-3 max-w-[40rem] text-lead text-ink-soft text-pretty">{t.lead}</p>
        </div>
        {canUpload ? (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="inline-flex h-10 shrink-0 items-center gap-2 rounded-control bg-ink px-4 font-medium text-white transition-colors hover:bg-signal-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal"
          >
            <Plus aria-hidden className="size-4.5" strokeWidth={2} />
            {t.add}
          </button>
        ) : null}
      </div>

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
      {canUpload ? null : <p className="mt-6 border-l-2 border-line pl-4 text-meta text-ink-soft">{t.readOnly}</p>}
      {lastError ? (
        <p className="mt-4 text-meta text-caution">
          {t.lastError} {lastError}
        </p>
      ) : null}

      {rows.length ? (
        <>
          <div className="mt-8 flex flex-wrap items-center gap-x-4 gap-y-3 border-b border-line pb-3">
            <label className="relative w-full sm:w-72">
              <span className="sr-only">{t.search}</span>
              <Search
                aria-hidden
                className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-faint"
                strokeWidth={1.75}
              />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={t.search}
                className="h-9 w-full rounded-control border border-line-strong bg-surface pr-3 pl-9 text-body text-ink outline-none placeholder:text-ink-faint focus:border-signal"
              />
            </label>
            <fieldset className="flex flex-wrap gap-1">
              <legend className="sr-only">{t.groupsLabel}</legend>
              {GROUPS.filter((option) => option === "all" || counts[option]).map((option) => (
                <label
                  key={option}
                  className={
                    "inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-control px-3 text-meta font-medium has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-signal " +
                    (group === option ? "bg-ink text-white" : "text-ink-soft hover:bg-surface hover:text-ink")
                  }
                >
                  <input
                    type="radio"
                    name="document-group"
                    className="sr-only"
                    checked={group === option}
                    onChange={() => setGroup(option)}
                  />
                  {t.groups[option]}
                  <span className={"tabular-nums " + (group === option ? "text-white/70" : "text-ink-faint")}>
                    {counts[option]}
                  </span>
                </label>
              ))}
            </fieldset>
            {origins.length > 1 ? (
              <select
                aria-label={t.originLabel}
                value={origin}
                onChange={(event) => setOrigin(event.target.value)}
                className="h-9 rounded-control border border-line-strong bg-surface px-2.5 text-meta text-ink outline-none focus:border-signal"
              >
                <option value="">{t.originAll}</option>
                {origins.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            ) : null}
            <p aria-live="polite" className="text-meta text-ink-faint tabular-nums sm:ml-auto">
              {filtered ? t.showing(shown.length, rows.length) : t.count(rows.length)}
            </p>
          </div>

          {shown.length ? (
            <table className="w-full table-fixed border-collapse text-left">
              <thead>
                <tr className="border-b border-line text-meta text-ink-faint">
                  <th scope="col" className="py-2 pr-4 font-medium">{t.columns.name}</th>
                  <th scope="col" className="hidden w-20 py-2 pr-4 font-medium sm:table-cell">{t.columns.kind}</th>
                  <th scope="col" className="hidden w-48 py-2 pr-4 font-medium lg:table-cell">{t.columns.audience}</th>
                  <th scope="col" className="w-36 py-2 pr-4 font-medium sm:w-44">{t.columns.status}</th>
                  <th scope="col" className="hidden w-40 py-2 font-medium md:table-cell">{t.columns.updated}</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((row) => (
                  <tr key={row.key} className="border-b border-line align-baseline hover:bg-surface/70">
                    <td className="py-2.5 pr-4">
                      {row.href ? (
                        <Link
                          href={row.href}
                          title={row.title}
                          className="block truncate text-ink underline-offset-4 hover:text-signal-deep hover:underline"
                        >
                          {row.title}
                        </Link>
                      ) : (
                        <span className="block truncate text-ink" title={row.title}>
                          {row.title}
                        </span>
                      )}
                      {row.source ? <span className="block truncate text-meta text-ink-faint">{row.source}</span> : null}
                    </td>
                    <td className="hidden py-2.5 pr-4 text-meta text-ink-soft sm:table-cell">{t.kinds[row.kind]}</td>
                    <td className="hidden py-2.5 pr-4 text-meta text-ink-soft lg:table-cell">
                      {row.audience ? t.audiences[row.audience] : null}
                    </td>
                    <td className="py-2.5 pr-4">
                      <Status status={row.status} label={t.status[row.status]} />
                    </td>
                    <td className="hidden py-2.5 text-meta text-ink-soft tabular-nums md:table-cell">
                      {date.format(new Date(row.at))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="py-10">
              <p className="text-ink-soft">{t.noMatch}</p>
              <button
                type="button"
                onClick={clearFilters}
                className="mt-2 font-medium text-signal underline underline-offset-4 hover:text-signal-deep"
              >
                {t.clearFilters}
              </button>
            </div>
          )}
        </>
      ) : (
        <section className="mt-12 max-w-[36rem]">
          <h2 className="text-lead font-semibold">{t.emptyTitle}</h2>
          <p className="mt-2 text-ink-soft text-pretty">{canUpload ? t.emptyBody : t.emptyReadOnly}</p>
        </section>
      )}

      {canUpload ? (
        <AddFilesPanel
          organizationId={organizationId}
          open={adding}
          onOpenChange={setAdding}
          canManage={canManage}
          colleagues={colleagues}
          existingNames={rows.map((row) => row.title)}
          ownFiles={ownFiles}
        >
          {canManage ? <SourcesPanel organizationId={organizationId} drive={drive} /> : null}
        </AddFilesPanel>
      ) : null}
    </div>
  );
}

function Status({ status, label }: { status: Row["status"]; label: string }) {
  const tone = {
    waiting: "text-ink-soft",
    pending: "text-signal-deep",
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
