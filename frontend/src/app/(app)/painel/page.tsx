import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { DashboardView } from "@/components/dashboard/DashboardView";
import { AccessProblem } from "@/components/shell/AccessProblem";
import { OrganizationSwitch } from "@/components/shell/OrganizationSwitch";
import { getMessages } from "@/i18n/server";
import { loadDashboard } from "@/lib/dashboard";
import { loadOrganizations } from "@/lib/organizations";
import { managesPeople } from "@/lib/roles";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getMessages();
  return { title: t.dashboard.title };
}

export default async function DashboardPage({ searchParams }: { searchParams: Promise<{ org?: string }> }) {
  const [{ org }, result, { t }] = await Promise.all([searchParams, loadOrganizations(), getMessages()]);
  if ("problem" in result) return <AccessProblem t={t} problem={result.problem} retry="/painel" />;

  const { organizations } = result;
  const active = organizations.find((o) => o.id === org) ?? organizations[0];
  if (!active) redirect("/assistente");
  if (!managesPeople(active.role)) redirect(`/assistente?org=${active.id}`);

  const data = await loadDashboard(active.id);
  if (!data) return <AccessProblem t={t} problem="unavailable" retry={`/painel?org=${active.id}`} />;

  return (
    <div className="mx-auto max-w-5xl px-5 py-8 lg:px-10 lg:py-12">
      {organizations.length > 1 ? (
        <OrganizationSwitch organizations={organizations} activeId={active.id} basePath="/painel" />
      ) : null}
      <DashboardView organizationId={active.id} data={data} />
    </div>
  );
}
