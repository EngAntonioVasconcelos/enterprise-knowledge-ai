import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { DocumentsView } from "@/components/documents/DocumentsView";
import { AccessProblem } from "@/components/shell/AccessProblem";
import { getMessages } from "@/i18n/server";
import { loadDocuments } from "@/lib/documents";
import { loadOrganizations } from "@/lib/organizations";

type Notice = "connected" | "denied" | "expired" | "failed";
const NOTICES = new Set<string>(["connected", "denied", "expired", "failed"]);

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getMessages();
  return { title: t.documents.title };
}

export default async function DocumentsPage({
  searchParams,
}: {
  searchParams: Promise<{ org?: string; google?: string }>;
}) {
  const [{ org, google }, result, { t }] = await Promise.all([searchParams, loadOrganizations(), getMessages()]);
  if ("problem" in result) return <AccessProblem t={t} problem={result.problem} retry="/documentos" />;

  const { organizations } = result;
  const active = organizations.find((o) => o.id === org) ?? organizations[0];
  // Documents belong to an organization: without one, create it first.
  if (!active) redirect("/assistente");

  const data = await loadDocuments(active.id);
  if (!data) return <AccessProblem t={t} problem="unavailable" retry={`/documentos?org=${active.id}`} />;

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-8 sm:px-8 lg:px-12 lg:py-12">
      <DocumentsView organizationId={active.id} {...data} notice={NOTICES.has(google ?? "") ? (google as Notice) : null} />
    </div>
  );
}
