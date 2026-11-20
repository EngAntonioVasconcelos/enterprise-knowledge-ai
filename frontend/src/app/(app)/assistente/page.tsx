import type { Metadata } from "next";

import { AssistantView } from "@/components/assistant/AssistantView";
import { OrganizationSwitch } from "@/components/shell/OrganizationSwitch";
import { messages } from "@/i18n/pt-PT";
import type { Organization } from "@/lib/api-types";
import { backendFetch } from "@/lib/backend";

export const metadata: Metadata = { title: messages.assistant.title };

async function loadOrganizations(): Promise<Organization[]> {
  const response = await backendFetch("/organizations/");
  if (!response.ok) return [];
  const all = (await response.json()) as Organization[];
  return all.filter((organization) => organization.status === "active");
}

export default async function AssistantPage({
  searchParams,
}: {
  searchParams: Promise<{ org?: string }>;
}) {
  const [{ org }, organizations] = await Promise.all([searchParams, loadOrganizations()]);
  const active = organizations.find((o) => o.id === org) ?? organizations[0];

  if (!active) {
    return (
      <section className="mx-auto max-w-xl px-6 py-24">
        <h1 className="text-lead font-semibold">{messages.noOrganization.title}</h1>
        <p className="mt-3 text-ink-soft text-pretty">{messages.noOrganization.body}</p>
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
