import { BrandMark } from "@/components/BrandMark";
import { ptPT } from "@/i18n/pt-PT";

/** The product name, set in type next to its mark. A name, so it is the
 * same in every language. */
export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5 font-sans text-ink">
      <BrandMark size={compact ? 22 : 26} />
      <span className="whitespace-nowrap text-[0.9375rem] leading-none font-semibold tracking-[-0.015em]">
        {compact ? ptPT.productShort : ptPT.product}
      </span>
    </span>
  );
}
