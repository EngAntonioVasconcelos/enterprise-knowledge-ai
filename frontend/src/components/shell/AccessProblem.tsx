import type { Messages } from "@/i18n/pt-PT";
import type { AccessProblem as Problem } from "@/lib/organizations";

/** Why a page could not load, and the way out. Never an empty state. */
export function AccessProblem({ t, problem, retry }: { t: Messages; problem: Problem; retry: string }) {
  const words = t.access[problem];
  const href = problem === "unavailable" ? retry : "/auth/login";
  return (
    <section role="alert" className="mx-auto max-w-xl px-6 py-24">
      <h1 className="text-lead font-semibold">{words.title}</h1>
      <p className="mt-3 text-ink-soft text-pretty">{words.body}</p>
      <a
        href={href}
        className="mt-6 inline-flex h-10 items-center rounded-control bg-ink px-5 text-body font-medium text-white transition-colors hover:bg-cobalt-deep"
      >
        {words.action}
      </a>
    </section>
  );
}
