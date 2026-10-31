import type { Lang } from "@/api/client";
import { STRINGS } from "@/i18n";

/** The finished steps, announced to screen readers as they arrive. */
export function Progress({ steps, lang }: { steps: string[]; lang: Lang }) {
  return (
    <section aria-labelledby="progress-title" className="space-y-3">
      <h2 id="progress-title" className="flex items-center gap-2 font-medium">
        <span className="size-3 animate-pulse rounded-full bg-primary" aria-hidden />
        {STRINGS[lang].working}…
      </h2>
      <ol aria-live="polite" className="space-y-1 text-sm">
        {steps.map((label, index) => (
          <li key={index} className="flex gap-2">
            <span aria-hidden className="text-green-700">
              ✓
            </span>
            {label}
          </li>
        ))}
      </ol>
    </section>
  );
}
