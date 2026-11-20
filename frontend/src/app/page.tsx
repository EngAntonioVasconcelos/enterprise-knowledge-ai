import { redirect } from "next/navigation";

import { Wordmark } from "@/components/Wordmark";
import { LanguageSwitch } from "@/components/shell/LanguageSwitch";
import { getMessages } from "@/i18n/server";
import type { Messages } from "@/i18n/pt-PT";
import { auth0 } from "@/lib/auth0";

// The entry page shows the product doing its one job: a question, an
// answer that cites, and the passage it came from.
export default async function SignInPage() {
  const session = await auth0.getSession();
  if (session) redirect("/assistente");
  const { t: all } = await getMessages();
  const t = all.signIn;

  return (
    <main className="mx-auto grid min-h-dvh max-w-6xl content-center gap-16 px-6 py-16 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:items-center lg:px-10">
      <section className="max-w-md">
        <div className="flex items-center justify-between gap-6">
          <Wordmark />
          <LanguageSwitch align="end" />
        </div>
        <h1 className="mt-10 text-[2.5rem] leading-[1.1] font-semibold tracking-[-0.025em] text-balance">
          {t.title}
        </h1>
        <p className="mt-5 text-lead text-ink-soft text-pretty">{t.body}</p>
        <a
          href="/auth/login"
          className="mt-9 inline-flex h-11 items-center rounded-control bg-ink px-6 text-body font-medium text-white transition-colors hover:bg-cobalt-deep"
        >
          {t.action}
        </a>
        <p className="mt-3 text-meta text-ink-faint">{t.note}</p>
      </section>

      <Specimen t={all.specimen} />
    </main>
  );
}

/** A real exchange from the evaluation set, as the assistant shows it. */
function Specimen({ t }: { t: Messages["specimen"] }) {
  return (
    <figure
      aria-label={t.label}
      className="grid gap-6 rounded-panel border border-line bg-surface p-7 sm:grid-cols-[minmax(0,1fr)_13rem] sm:p-9"
    >
      <div>
        <p className="text-lead font-semibold tracking-[-0.01em]">
          {t.question}
        </p>
        <p className="mt-4 font-reading text-answer text-ink">
          {t.answer}
          <sup className="ml-0.5 font-sans text-[0.7rem] font-semibold text-cobalt">1</sup>
          {"."}
        </p>
      </div>
      <figcaption className="border-l-2 border-cobalt pl-4 text-meta text-ink-soft">
        <span className="font-semibold text-ink">{`1 ${t.source}`}</span>
        <span className="mt-1 block">{t.section}</span>
        <span className="mt-2 block font-reading italic">
          {t.quoted(t.passage)}
        </span>
      </figcaption>
    </figure>
  );
}
