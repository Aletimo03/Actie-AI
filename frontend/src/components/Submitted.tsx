import type { Lang } from "@/api/client";
import { STRINGS } from "@/i18n";
import type { Submitted as SubmittedData } from "@/state";

/** The description and the answers the assessment is based on, as the user wrote them. */
export function Submitted({ submitted, lang }: { submitted: SubmittedData; lang: Lang }) {
  const t = STRINGS[lang];
  return (
    <section aria-labelledby="submitted-title" className="space-y-3 rounded-lg border bg-card p-5">
      <h2 id="submitted-title" className="text-lg font-semibold">
        {t.submittedTitle}
      </h2>
      <p className="whitespace-pre-wrap [overflow-wrap:anywhere]">{submitted.description}</p>
      {submitted.answers.length > 0 && (
        <div className="space-y-2 border-t pt-3">
          <h3 className="font-semibold">{t.answersTitle}</h3>
          <dl className="space-y-2">
            {submitted.answers.map(({ question, answer }) => (
              <div key={question}>
                <dt className="text-sm text-muted-foreground">{question}</dt>
                <dd className="whitespace-pre-wrap [overflow-wrap:anywhere]">{answer}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </section>
  );
}
