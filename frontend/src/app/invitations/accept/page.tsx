import type { Metadata } from "next";

import { AcceptInvitation } from "@/components/invitations/AcceptInvitation";
import { LanguageSwitch } from "@/components/shell/LanguageSwitch";
import { Wordmark } from "@/components/Wordmark";
import { getMessages } from "@/i18n/server";
import { auth0 } from "@/lib/auth0";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getMessages();
  return { title: t.invitation.title };
}

// Where the invitation link lands. The token is in the part of the address
// after #, which never reaches a server; the page reads it in the browser.
export default async function AcceptInvitationPage() {
  const session = await auth0.getSession();
  return (
    <main className="mx-auto min-h-dvh max-w-xl px-6 py-12">
      <div className="flex items-center justify-between gap-6">
        <Wordmark />
        <LanguageSwitch align="end" />
      </div>
      <AcceptInvitation email={session?.user.email ?? null} />
    </main>
  );
}
