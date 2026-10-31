import { Check, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";
import type { Lang } from "@/api/client";
import { STRINGS } from "@/i18n";

/** The finished steps, announced to screen readers as they arrive, and the one under way. */
export function Progress({ steps, lang }: { steps: string[]; lang: Lang }) {
  const t = STRINGS[lang];
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <section aria-labelledby="progress-title" className="flex flex-col items-center gap-6 py-6 sm:flex-row sm:items-start">
      <img
        src="/actie-160.png"
        alt=""
        width={96}
        height={91}
        className="size-24 shrink-0 rounded-2xl motion-safe:animate-[bob_2.4s_ease-in-out_infinite]"
      />
      <div className="w-full space-y-3">
        <h2 id="progress-title" className="text-2xl font-semibold">
          {t.working}…
        </h2>
        <ol aria-live="polite" className="space-y-2">
          {steps.map((label, index) => (
            <li key={index} className="flex items-center gap-2">
              <Check aria-hidden className="size-4 text-gold-ink" strokeWidth={3} />
              {label}
            </li>
          ))}
        </ol>
        <p className="flex items-center gap-2 text-muted-foreground">
          <LoaderCircle aria-hidden className="size-4 motion-safe:animate-spin" />
          {t.nextStep}…
        </p>
        <p className="text-sm text-muted-foreground tabular-nums" aria-hidden>
          {t.elapsed(seconds)}
        </p>
      </div>
    </section>
  );
}
