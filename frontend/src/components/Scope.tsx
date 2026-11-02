import { ExternalLink } from "lucide-react";
import type { Lang } from "@/api/client";
import { LAW_VERSION, STRINGS, formatDate } from "@/i18n";
import { cn } from "@/lib/utils";

/** Beside the description: what is checked, the legal text, the data. */
export function Scope({ lang, className }: { lang: Lang; className?: string }) {
  const t = STRINGS[lang];
  return (
    <div className={cn("space-y-9 text-[0.95rem]", className)}>
      <section aria-labelledby="scope-title">
        <h2 id="scope-title" className="mb-3 text-lg font-semibold">
          {t.scopeTitle}
        </h2>
        <ul className="list-disc space-y-1.5 pl-5 marker:text-gold-ink">
          {t.scope.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="source-title" className="space-y-1">
        <h2 id="source-title" className="text-base font-semibold">
          {t.sourceTitle}
        </h2>
        <p className="text-muted-foreground">{t.consolidated(formatDate(LAW_VERSION, lang))}</p>
        <a
          className="inline-flex items-center gap-1 text-gold-ink underline underline-offset-2"
          href="https://eur-lex.europa.eu/eli/reg/2024/1689/oj"
          target="_blank"
          rel="noreferrer"
        >
          {t.regulation}
          <ExternalLink aria-hidden className="size-3.5" />
        </a>
      </section>

      <section aria-labelledby="data-title" className="space-y-1">
        <h2 id="data-title" className="text-base font-semibold">
          {t.privacyTitle}
        </h2>
        <p className="text-muted-foreground">{t.privacyText}</p>
        <p className="text-muted-foreground">{t.notAdvice}</p>
      </section>
    </div>
  );
}
