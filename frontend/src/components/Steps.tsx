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
                index < current && "bg-gold-ink",
                index === current && "bg-gold",
                index > current && "bg-border",
              )}
            />
            <span
              className={cn(
                "block text-sm",
                index === current && "font-bold text-foreground",
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
