import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { DocumentPageView } from "@/components/documents/DocumentPageView";
import { AccessProblem } from "@/components/shell/AccessProblem";
import { getMessages } from "@/i18n/server";
import { loadDocumentPage } from "@/lib/documents";
import { loadOrganizations } from "@/lib/organizations";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getMessages();
  return { title: t.documents.title };
}

export default async function DocumentPage({
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
  if ("problem" in result) return <AccessProblem t={t} problem={result.problem} retry="/documentos" />;
  const active = result.organizations.find((o) => o.id === org) ?? result.organizations[0];
  if (!active) redirect("/assistente");

  const page = UUID.test(id) ? await loadDocumentPage(active.id, id) : "missing";
  if (!page) return <AccessProblem t={t} problem="unavailable" retry={`/documentos/${id}?org=${active.id}`} />;

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-8 sm:px-8 lg:px-12 lg:py-12">
      <DocumentPageView organizationId={active.id} page={page === "missing" ? null : page} />
    </div>
  );
}
