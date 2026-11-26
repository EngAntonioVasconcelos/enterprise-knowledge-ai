"use client";

import Link from "next/link";

import { useI18n } from "@/i18n/client";
import type { DocumentPage } from "@/lib/api-types";
import { documentKind } from "@/lib/uploads";

/** One document: what it is, where it comes from, who sees it, when it was
 *  read, and the first passages the assistant answers from. A document the
 *  person cannot open shows as not found, the same as one that never was. */
export function DocumentPageView({ organizationId, page }: { organizationId: string; page: DocumentPage | null }) {
  const { locale, t: all } = useI18n();
  const t = all.documentPage;
  const d = all.documents;
  const back = `/documentos?org=${encodeURIComponent(organizationId)}`;
  const date = new Intl.DateTimeFormat(locale, { dateStyle: "long", timeStyle: "short" });

  const nav = (
    <nav className="mb-8 text-meta">
      <Link href={back} className="font-medium text-cobalt underline-offset-4 hover:underline">
        {t.back}
      </Link>
    </nav>
  );

  if (!page) {
    return (
      <div>
        {nav}
        <section className="max-w-[36rem]">
          <h1 className="text-question font-semibold tracking-[-0.02em]">{t.missingTitle}</h1>
          <p className="mt-3 text-body text-ink-soft text-pretty">{t.missingBody}</p>
        </section>
      </div>
    );
  }

  const { document } = page;
  const status = (["pending", "active", "failed"].includes(document.status) ? document.status : "pending") as
    | "pending"
    | "active"
    | "failed";
  const source = document.source
    ? (d.origins[document.source.provider as keyof typeof d.origins] ?? document.source.name)
    : null;
  const facts: [string, string][] = [
    [t.kind, d.kinds[documentKind(document.mime_type)]],
    ...(source ? ([[t.source, source]] as [string, string][]) : []),
    ...(document.audience ? ([[t.audience, d.audiences[document.audience]]] as [string, string][]) : []),
    [t.status, d.status[status]],
    [t.readAt, page.read_at ? date.format(new Date(page.read_at)) : t.notReadYet],
  ];

  return (
    <div>
      {nav}
      <h1 className="max-w-[48rem] text-question font-semibold tracking-[-0.02em] text-balance break-words">
        {document.title}
      </h1>

      <dl className="mt-6 grid max-w-[48rem] grid-cols-[auto_1fr] gap-x-8 gap-y-2 text-body">
        {facts.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-ink-faint">{label}</dt>
            <dd className="text-ink">{value}</dd>
          </div>
        ))}
      </dl>

      {page.failure ? (
        <p role="status" className="mt-8 max-w-[48rem] border-l-2 border-caution pl-4 text-body text-ink">
          <span className="font-medium text-caution">{t.failed}</span> <span className="break-words">{page.failure}</span>
        </p>
      ) : null}

      <section aria-labelledby="excerpt-title" className="mt-12 max-w-[48rem] border-t border-line pt-8">
        <h2 id="excerpt-title" className="text-lead font-semibold">
          {t.excerptTitle}
        </h2>
        <p className="mt-1 text-meta text-ink-soft text-pretty">
          {page.passages ? t.excerptHint(page.passages) : t.noPassages}
        </p>
        {page.excerpt.length ? (
          <ol className="mt-6 space-y-6">
            {page.excerpt.map((passage, index) => (
              <li key={index} className="border-l-2 border-line-strong pl-4">
                {passage.heading ? <p className="text-meta font-medium text-ink-soft">{passage.heading}</p> : null}
                <p className="mt-1 font-reading text-body leading-relaxed text-ink whitespace-pre-line break-words">
                  {passage.content}
                </p>
              </li>
            ))}
          </ol>
        ) : null}
      </section>
    </div>
  );
}
