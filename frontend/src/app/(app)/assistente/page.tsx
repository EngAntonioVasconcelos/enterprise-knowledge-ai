import type { Metadata } from "next";

import { AssistantView } from "@/components/assistant/AssistantView";
import { CreateOrganization } from "@/components/onboarding/CreateOrganization";
import { AccessProblem } from "@/components/shell/AccessProblem";
import { OrganizationSwitch } from "@/components/shell/OrganizationSwitch";
import { getMessages } from "@/i18n/server";
import { loadOrganizations } from "@/lib/organizations";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getMessages();
  return { title: t.assistant.title };
}

export default async function AssistantPage({
  searchParams,
}: {
  searchParams: Promise<{ org?: string }>;
}) {
  const [{ org }, result, { t }] = await Promise.all([
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

  return (
    <div className="mx-auto max-w-6xl px-5 py-8 lg:px-10 lg:py-12">
      {organizations.length > 1 ? (
        <OrganizationSwitch organizations={organizations} activeId={active.id} />
      ) : null}
      <AssistantView key={active.id} organizationId={active.id} organizationName={active.name} />
    </div>
  );
}
