import type { Metadata } from "next";

import { AssistantView } from "@/components/assistant/AssistantView";
import { CreateOrganization } from "@/components/onboarding/CreateOrganization";
import { AccessProblem } from "@/components/shell/AccessProblem";
import { getMessages } from "@/i18n/server";
import { auth0 } from "@/lib/auth0";
import { loadHistory } from "@/lib/history";
import { loadOrganizations } from "@/lib/organizations";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getMessages();
  return { title: t.assistant.title };
}

export default async function AssistantPage({
  searchParams,
}: {
  searchParams: Promise<{ org?: string; q?: string }>;
}) {
  const [{ org, q }, result, { t }] = await Promise.all([
    searchParams,
    loadOrganizations(),
    getMessages(),
  ]);

  if ("problem" in result) return <AccessProblem t={t} problem={result.problem} retry="/assistente" />;

  const { organizations } = result;
  const active = organizations.find((o) => o.id === org) ?? organizations[0];

  if (!active) {
    return (
      <section className="mx-auto max-w-xl px-6 py-24">
        <h1 className="text-question font-semibold tracking-[-0.02em] text-balance">
          {t.noOrganization.title}
        </h1>
        <p className="mt-3 text-lead text-ink-soft text-pretty">{t.noOrganization.body}</p>
        <CreateOrganization />
        <p className="mt-10 max-w-md border-l-2 border-line pl-4 text-meta text-ink-soft text-pretty">
          {t.noOrganization.invited}
        </p>
      </section>
    );
  }

  // The greeting and the latest questions: where the person left off.
  const [session, recent] = await Promise.all([
    auth0.getSession(),
    (active.history_retention_days ?? 90) > 0 ? loadHistory(active.id, 5) : Promise.resolve([]),
  ]);
  const firstName = session?.user.given_name ?? session?.user.name?.split(/\s+/)[0] ?? null;

  return (
    <div className="w-full">
      <AssistantView
        key={active.id}
        organizationId={active.id}
        organizationName={active.name}
        initialQuestion={q && q.trim().length <= 500 ? q.trim() : null}
        firstName={typeof firstName === "string" ? firstName : null}
        recent={recent ?? []}
      />
    </div>
  );
}
