import { Check } from "lucide-react";
import type { Lang } from "@/api/client";
import { STRINGS } from "@/i18n";
import { cn } from "@/lib/utils";
import type { View } from "@/state";

const CURRENT: Partial<Record<View["kind"], number>> = { describing: 0, running: 1, asking: 2, done: 3 };

/** Where the user is in describe → check → answer → report. */
export function Steps({ view, lang }: { view: View; lang: Lang }) {
  const current = CURRENT[view.kind];
  if (current === undefined) return null; // loading, failed: the message says what happened
  const steps = STRINGS[lang].flow;
  return (
    <nav aria-label={STRINGS[lang].flowLabel}>
      <ol className="flex flex-wrap gap-x-3 gap-y-2 text-sm sm:gap-x-6">
        {steps.map((label, index) => (
          <li
            key={label}
            aria-current={index === current ? "step" : undefined}
            className={cn(
              "flex items-center gap-2",
              index === current ? "font-bold text-foreground" : "text-muted-foreground",
            )}
          >
            <span
              aria-hidden
              className={cn(
                "flex size-5 items-center justify-center rounded-full border text-xs",
                index < current && "border-gold-ink bg-gold-ink text-primary-foreground",
                index === current && "border-foreground bg-foreground text-primary-foreground",
              )}
            >
              {index < current ? <Check className="size-3" strokeWidth={3} /> : index + 1}
            </span>
            {label}
          </li>
        ))}
      </ol>
    </nav>
  );
}
