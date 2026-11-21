import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { PeopleView } from "@/components/people/PeopleView";
import { AccessProblem } from "@/components/shell/AccessProblem";
import { getMessages } from "@/i18n/server";
import { auth0 } from "@/lib/auth0";
import { loadOrganizations } from "@/lib/organizations";
import { loadPeople } from "@/lib/people";
import { managesPeople } from "@/lib/roles";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getMessages();
  return { title: t.people.title };
}

export default async function PeoplePage({ searchParams }: { searchParams: Promise<{ org?: string }> }) {
  const [{ org }, result, { t }, session] = await Promise.all([
    searchParams,
    loadOrganizations(),
    getMessages(),
    auth0.getSession(),
  ]);
  if ("problem" in result) return <AccessProblem t={t} problem={result.problem} retry="/pessoas" />;

  const { organizations } = result;
  const active = organizations.find((o) => o.id === org) ?? organizations[0];
  if (!active) redirect("/assistente");
  // Members and viewers have no people screen: back to the assistant.
  if (!active.role || !managesPeople(active.role)) redirect(`/assistente?org=${active.id}`);

  const data = await loadPeople(active.id);
  if (!data) return <AccessProblem t={t} problem="unavailable" retry={`/pessoas?org=${active.id}`} />;

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-8 sm:px-8 lg:px-12 lg:py-12">
      <PeopleView
        organizationId={active.id}
        actorRole={active.role}
        selfEmail={session?.user.email?.toLowerCase() ?? ""}
        selfPicture={session?.user.picture ?? null}
        {...data}
      />
    </div>
  );
}
