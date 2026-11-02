import { Check } from "lucide-react";
import { useEffect, useState } from "react";
import type { Lang } from "@/api/client";
import { STRINGS } from "@/i18n";

// The step that runs after each one (backend/app/agent/graph.py); "" is before the first.
// A run that stops early (a prohibited practice, a question) just never reaches the rest.
const NEXT: Record<string, string> = {
  "": "extract_facts",
  extract_facts: "check_prohibited",
  check_prohibited: "check_high_risk",
  check_high_risk: "check_transparency",
  check_transparency: "determine_role",
  determine_role: "list_obligations",
  list_obligations: "verify_citations",
  verify_citations: "report",
};
const EVERY = 2600; // ms each message stays

type Props = { steps: string[]; last: string | null; lang: Lang };

/** The finished steps, announced to screen readers as they arrive, and what is under way. */
export function Progress({ steps, last, lang }: Props) {
  const t = STRINGS[lang];
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const step = NEXT[last ?? ""] ?? "report";
  const activity = t.activity[step as keyof typeof t.activity] ?? [t.nextStep];
  return (
    <section aria-labelledby="progress-title" className="py-2">
      <div className="space-y-3">
        <h2 id="progress-title" className="text-2xl font-semibold">
          {t.working}
        </h2>
        <ol aria-live="polite" className="space-y-2">
          {steps.map((label, index) => (
            <li key={index} className="flex items-center gap-2">
              <Check
                aria-hidden
                className="size-4 text-gold-ink"
                strokeWidth={3}
              />
              {label}
            </li>
          ))}
        </ol>
        {/* Keyed by step, so the messages start over when a new step begins. */}
        <Activity key={step} messages={activity} />
        <span className="sr-only">{t.nextStep}</span>
        <p className="text-sm text-muted-foreground tabular-nums" aria-hidden>
          {t.elapsed(seconds)}
        </p>
      </div>
    </section>
  );
}

/** What the step under way is doing, one line at a time: decoration, not read out. */
function Activity({ messages }: { messages: string[] }) {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    if (messages.length < 2) return;
    const timer = setInterval(
      () => setIndex((i) => (i + 1) % messages.length),
      EVERY,
    );
    return () => clearInterval(timer);
  }, [messages]);

  return (
    <p aria-hidden className="flex min-h-7 items-center gap-2.5">
      <span className="size-2 shrink-0 rounded-full bg-gold motion-safe:animate-pulse" />
      <span key={index} className="shimmer">
        {messages[index]}
      </span>
    </p>
  );
}
