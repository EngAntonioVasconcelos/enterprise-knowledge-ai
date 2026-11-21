import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { HistoryEntryView } from "@/components/history/HistoryEntryView";
import { AccessProblem } from "@/components/shell/AccessProblem";
import { getMessages } from "@/i18n/server";
import { loadEntry } from "@/lib/history";
import { loadOrganizations } from "@/lib/organizations";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getMessages();
  return { title: t.history.title };
}

export default async function HistoryEntryPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ org?: string }>;
}) {
  const [{ id }, { org }, result, { t }] = await Promise.all([
    params,
    searchParams,
    loadOrganizations(),
    getMessages(),
  ]);
  if ("problem" in result) return <AccessProblem t={t} problem={result.problem} retry="/historico" />;
  const active = result.organizations.find((o) => o.id === org) ?? result.organizations[0];
  if (!active) redirect("/assistente");
  const back = `/historico?org=${active.id}`;
  if (!UUID.test(id)) redirect(back);

  const entry = await loadEntry(active.id, id);
  if (entry === "missing") redirect(back);
  if (!entry) return <AccessProblem t={t} problem="unavailable" retry={`/historico/${id}?org=${active.id}`} />;

  return (
    <div className="mx-auto max-w-6xl px-5 py-8 lg:px-10 lg:py-12">
      <HistoryEntryView organizationId={active.id} entry={entry} />
    </div>
  );
}
