import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { HistoryList } from "@/components/history/HistoryList";
import { AccessProblem } from "@/components/shell/AccessProblem";
import { OrganizationSwitch } from "@/components/shell/OrganizationSwitch";
import { getMessages } from "@/i18n/server";
import { loadHistory } from "@/lib/history";
import { loadOrganizations } from "@/lib/organizations";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getMessages();
  return { title: t.history.title };
}

export default async function HistoryPage({ searchParams }: { searchParams: Promise<{ org?: string }> }) {
  const [{ org }, result, { t }] = await Promise.all([searchParams, loadOrganizations(), getMessages()]);
  if ("problem" in result) return <AccessProblem t={t} problem={result.problem} retry="/historico" />;

  const { organizations } = result;
  const active = organizations.find((o) => o.id === org) ?? organizations[0];
  if (!active) redirect("/assistente");

  const items = await loadHistory(active.id);
  if (!items) return <AccessProblem t={t} problem="unavailable" retry={`/historico?org=${active.id}`} />;

  return (
    <div className="mx-auto max-w-4xl px-5 py-8 lg:px-10 lg:py-12">
      {organizations.length > 1 ? (
        <OrganizationSwitch organizations={organizations} activeId={active.id} basePath="/historico" />
      ) : null}
      <HistoryList
        organizationId={active.id}
        retentionDays={active.history_retention_days ?? 90}
        items={items}
      />
    </div>
  );
}
