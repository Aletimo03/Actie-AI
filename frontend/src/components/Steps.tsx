import type { Lang } from "@/api/client";
import { STRINGS } from "@/i18n";
import { cn } from "@/lib/utils";
import type { View } from "@/state";

// No bar while describing: the steps start once an assessment does.
const CURRENT: Partial<Record<View["kind"], number>> = { running: 1, asking: 2, done: 3 };

/** Where the user is in describe → analysis → questions → result: a segmented bar. */
export function Steps({ view, lang }: { view: View; lang: Lang }) {
  const current = CURRENT[view.kind];
  if (current === undefined) return null; // describing, loading, failed
  const t = STRINGS[lang];
  // Still working (or waiting for answers): the current step breathes; a result does not.
  const live = view.kind === "running" || view.kind === "asking";
  return (
    <nav aria-label={t.flowLabel} className="space-y-3">
      <p className="text-sm text-muted-foreground">{t.stepOf(current + 1, t.flow.length)}</p>
      <ol className="grid grid-cols-4 gap-2">
        {t.flow.map((label, index) => (
          <li key={label} aria-current={index === current ? "step" : undefined} className="space-y-2">
            <span
              aria-hidden
              className={cn(
                "block h-1 rounded-full",
                index < current && "bg-gold-ink/70",
                index === current && "h-1.5 -translate-y-px bg-gold",
                index === current && live && "step-live",
                index > current && "bg-border",
              )}
            />
            <span
              className={cn(
                "block text-sm",
                index === current && "font-bold text-gold",
                index < current && "text-muted-foreground",
                index > current && "text-muted-soft",
              )}
            >
              {label}
            </span>
          </li>
        ))}
      </ol>
    </nav>
  );
}
