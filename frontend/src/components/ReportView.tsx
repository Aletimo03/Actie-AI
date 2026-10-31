/**
 * The report. Model text (quotes, claims, duties) is shown as text, never as HTML:
 * React escapes it, so an injected "<img onerror=...>" is shown, not run.
 */
import { Ban, CircleCheck, Info, ShieldAlert, ShieldCheck, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Citation, Lang, Obligation, Report } from "@/api/client";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LAW_VERSION, STRINGS, formatDate } from "@/i18n";
import { chunkLabel, uncertainLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";

const RISK_STYLE = {
  prohibited: { box: "bg-red-50 text-red-950 border-red-300", Icon: Ban },
  high: { box: "bg-orange-50 text-orange-950 border-orange-300", Icon: ShieldAlert },
  limited: { box: "bg-amber-50 text-amber-950 border-amber-300", Icon: Info },
  minimal: { box: "bg-emerald-50 text-emerald-950 border-emerald-300", Icon: ShieldCheck },
};

type Props = { report: Report; lang: Lang; onNew: () => void };

export function ReportView({ report, lang, onNew }: Props) {
  const t = STRINGS[lang];
  const label = (id: string) => chunkLabel(id, lang);
  const reasons = [
    ...report.banned.map((point) => `${t.bannedBy}: Art. 5(1)(${point})`),
    ...report.high_risk_basis.map((id) => `${t.highRiskBy}: ${label(id)}`),
    ...(report.exception ? [`${t.exception}: ${report.exception}`] : []),
    ...report.became_provider.map((point) => `${t.becameProvider}: Art. 25(1)(${point})`),
  ];

  // The Art. 50 duties are usually among the obligations already, with their dates.
  const style = RISK_STYLE[report.risk];
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []); // the result replaced the steps: say so
  const listed = new Set(report.obligations.map((o) => `${o.chunk_id} ${o.who}`));
  const extraDuties = report.transparency_duties.filter((d) => !listed.has(`${d.chunk_id} ${d.who}`));

  return (
    <article className="space-y-6">
      <header className={cn("flex gap-4 rounded-xl border-2 p-5", style.box)}>
        <style.Icon aria-hidden className="mt-1 size-8 shrink-0" />
        <div className="space-y-1">
          <h2 ref={heading} tabIndex={-1} className="text-2xl font-semibold outline-none sm:text-3xl">
            {t.risk[report.risk]}
          </h2>
          <p>{t.riskMeaning[report.risk]}</p>
          <p className="font-bold">{t.role[report.role ?? "unknown"]}</p>
        </div>
      </header>

      {reasons.length > 0 && (
        <Section title={t.why}>
          <ul className="list-disc space-y-1 pl-5">
            {reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </Section>
      )}

      {(report.uncertain.length > 0 || report.assumed_unknown.length > 0) && (
        <Alert>
          <AlertTitle>{t.uncertainTitle}</AlertTitle>
          <AlertDescription>
            {report.uncertain.length > 0 && (
              <p>
                {t.uncertainText} {unique(report.uncertain.map((n) => uncertainLabel(n, lang))).join(", ")}
              </p>
            )}
            {report.assumed_unknown.length > 0 && (
              <p>
                {t.assumedText} {report.assumed_unknown.map((f) => t.facts[f] ?? f).join(", ")}.
              </p>
            )}
          </AlertDescription>
        </Alert>
      )}

      {report.unverified.length > 0 && (
        <Alert variant="destructive">
          <AlertTitle>{t.unverifiedTitle}</AlertTitle>
          <AlertDescription>
            {t.unverifiedText} {unique(report.unverified.map(label)).join(", ")}
          </AlertDescription>
        </Alert>
      )}

      {report.obligations.length > 0 && (
        <Section title={t.obligations}>
          <Timeline obligations={report.obligations} lang={lang} />
        </Section>
      )}

      {extraDuties.length > 0 && (
        <Section title={t.transparency}>
          <Duties duties={extraDuties} lang={lang} />
        </Section>
      )}

      {report.other_role_duties.length > 0 && (
        <Section title={t.otherRole}>
          <Duties duties={report.other_role_duties} lang={lang} />
        </Section>
      )}

      {report.notes.length > 0 && (
        <Section title={t.notes}>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {report.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </Section>
      )}

      {report.citations.length > 0 && (
        <Section title={t.citations}>
          <ul className="space-y-4">
            {report.citations.map((citation, index) => (
              <Source key={index} citation={citation} lang={lang} />
            ))}
          </ul>
        </Section>
      )}

      <footer className="space-y-3 border-t pt-4 text-sm text-muted-foreground">
        <p>
          {t.lawAsOf(formatDate(LAW_VERSION, lang))} {t.notAdvice}
        </p>
        <ShareLink lang={lang} />
        <Button variant="outline" onClick={onNew}>
          {t.newAssessment}
        </Button>
      </footer>
    </article>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h3 className="text-xl">{title}</h3>
        </CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

/** One row per duty, with a badge per role: provider and deployer often share one. */
function merge(obligations: Obligation[]) {
  const rows = new Map<string, Obligation & { roles: Obligation["who"][] }>();
  for (const o of obligations) {
    const key = [o.chunk_id, o.text, o.applies_from, o.condition].join("|");
    const row = rows.get(key);
    if (row) row.roles.push(o.who);
    else rows.set(key, { ...o, roles: [o.who] });
  }
  return [...rows.values()];
}

function Timeline({ obligations, lang }: { obligations: Obligation[]; lang: Lang }) {
  const t = STRINGS[lang];
  const rows = merge(obligations);
  const dates = unique(rows.map((o) => o.applies_from)).sort();
  return (
    <ol className="space-y-5">
      {dates.map((date) => {
        const group = rows.filter((o) => o.applies_from === date);
        const heading = group[0]?.in_force ? t.inForce : t.from;
        return (
          <li key={date}>
            <h4 className="mb-2 font-medium">{heading(formatDate(date, lang))}</h4>
            <ul className="space-y-2">
              {group.map((o, index) => (
                <li key={index} className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
                  <span className="flex-1 basis-64">
                    {o.text}
                    {o.condition && <span className="text-muted-foreground"> ({o.condition})</span>}
                  </span>
                  {o.roles.map((who) => (
                    <Badge key={who} variant="secondary">
                      {t.who[who]}
                    </Badge>
                  ))}
                  <span className="text-muted-foreground tabular-nums">{chunkLabel(o.chunk_id, lang)}</span>
                  {!o.verified && <Unverified text={t.notFound} />}
                </li>
              ))}
            </ul>
          </li>
        );
      })}
    </ol>
  );
}

function Duties({ duties, lang }: { duties: Report["transparency_duties"]; lang: Lang }) {
  const t = STRINGS[lang];
  return (
    <ul className="space-y-2 text-sm">
      {duties.map((duty, index) => (
        <li key={index} className="flex flex-wrap items-baseline gap-2">
          <span className="flex-1 basis-64">{duty.text}</span>
          <Badge variant="secondary">{t.who[duty.who]}</Badge>
          <span className="text-muted-foreground">{chunkLabel(duty.chunk_id, lang)}</span>
        </li>
      ))}
    </ul>
  );
}

function Source({ citation, lang }: { citation: Citation; lang: Lang }) {
  const t = STRINGS[lang];
  const verified = citation.verified ?? false;
  return (
    <li className="space-y-1 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{chunkLabel(citation.chunk_id, lang)}</span>
        {verified ? (
          <span className="inline-flex items-center gap-1 text-emerald-800">
            <CircleCheck aria-hidden className="size-4" />
            {t.verified}
          </span>
        ) : (
          <Unverified text={t.notFound} />
        )}
      </div>
      <p>{citation.claim}</p>
      <blockquote className="border-l-2 border-gold pl-3 font-serif text-base text-muted-foreground italic">
        “{citation.quote}”
      </blockquote>
      {citation.note && <p className="text-sm text-muted-foreground">{citation.note}</p>}
    </li>
  );
}

function ShareLink({ lang }: { lang: Lang }) {
  const t = STRINGS[lang];
  const [copied, setCopied] = useState(false);
  return (
    <p className="flex flex-wrap items-center gap-3">
      <Button
        variant="secondary"
        size="sm"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(location.href);
            setCopied(true);
          } catch {
            // no clipboard (insecure page, permission): the address bar still has the link
          }
        }}
      >
        {copied ? t.copied : t.copyLink}
      </Button>
      <span>{t.linkWarning}</span>
    </p>
  );
}

function Unverified({ text }: { text: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-destructive">
      <TriangleAlert aria-hidden className="size-4" />
      {text}
    </span>
  );
}

function unique<T>(items: T[]): T[] {
  return [...new Set(items)];
}
