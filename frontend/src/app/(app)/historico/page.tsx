import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { HistoryList } from "@/components/history/HistoryList";
import { AccessProblem } from "@/components/shell/AccessProblem";
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
    <div className="mx-auto w-full max-w-6xl px-5 py-8 sm:px-8 lg:px-12 lg:py-12">
      <HistoryList
        organizationId={active.id}
        retentionDays={active.history_retention_days ?? 90}
        items={items}
      />
    </div>
  );
}
