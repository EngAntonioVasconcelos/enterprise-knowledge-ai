import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { SettingsForm } from "@/components/settings/SettingsForm";
import { AccessProblem } from "@/components/shell/AccessProblem";
import { getMessages } from "@/i18n/server";
import { loadOrganizations } from "@/lib/organizations";
import { managesPeople } from "@/lib/roles";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getMessages();
  return { title: t.settings.title };
}

export default async function SettingsPage({ searchParams }: { searchParams: Promise<{ org?: string }> }) {
  const [{ org }, result, { t }] = await Promise.all([searchParams, loadOrganizations(), getMessages()]);
  if ("problem" in result) return <AccessProblem t={t} problem={result.problem} retry="/definicoes" />;

  const { organizations } = result;
  const active = organizations.find((o) => o.id === org) ?? organizations[0];
  if (!active) redirect("/assistente");
  // Members and viewers have no settings screen.
  if (!managesPeople(active.role)) redirect(`/assistente?org=${active.id}`);

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-8 sm:px-8 lg:px-12 lg:py-12">
      <SettingsForm
        key={`${active.id}-${active.name}-${active.history_retention_days}`}
        organizationId={active.id}
        name={active.name}
        retentionDays={active.history_retention_days ?? 90}
      />
    </div>
  );
}
