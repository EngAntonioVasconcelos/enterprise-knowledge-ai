import { ptPT } from "@/i18n/pt-PT";

/** The product name, set in type: no logo image to load or to get wrong.
 * A name, so it is the same in every language. */
export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-baseline gap-1.5 font-sans text-ink">
      <span aria-hidden className="size-2.5 translate-y-[-1px] rounded-[2px] bg-cobalt" />
      <span className="whitespace-nowrap text-[0.9375rem] font-semibold tracking-[-0.01em]">
        {compact ? ptPT.productShort : ptPT.product}
      </span>
    </span>
  );
}
