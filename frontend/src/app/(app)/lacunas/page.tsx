import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { GapsView } from "@/components/dashboard/GapsView";
import { AccessProblem } from "@/components/shell/AccessProblem";
import { getMessages } from "@/i18n/server";
import { loadGaps } from "@/lib/dashboard";
import { loadOrganizations } from "@/lib/organizations";
import { managesPeople } from "@/lib/roles";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getMessages();
  return { title: t.gaps.title };
}

export default async function GapsPage({ searchParams }: { searchParams: Promise<{ org?: string }> }) {
  const [{ org }, result, { t }] = await Promise.all([searchParams, loadOrganizations(), getMessages()]);
  if ("problem" in result) return <AccessProblem t={t} problem={result.problem} retry="/lacunas" />;

  const { organizations } = result;
  const active = organizations.find((o) => o.id === org) ?? organizations[0];
  if (!active) redirect("/assistente");
  if (!managesPeople(active.role)) redirect(`/assistente?org=${active.id}`);

  const data = await loadGaps(active.id);
  if (!data) return <AccessProblem t={t} problem="unavailable" retry={`/lacunas?org=${active.id}`} />;

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-8 sm:px-8 lg:px-12 lg:py-12">
      <GapsView organizationId={active.id} data={data} />
    </div>
  );
}
