/**
 * The report, laid out like a legal document: the result, then numbered sections
 * separated by rules, the obligations as a table. Model text (quotes, claims, duties) is
 * shown as text, never as HTML: React escapes it, so an injected "<img onerror=...>" is
 * shown, not run.
 */
import { Ban, CircleCheck, Info, ShieldAlert, ShieldCheck, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Citation, Lang, Obligation, Report } from "@/api/client";
import { Button } from "@/components/ui/button";
import { LAW_VERSION, STRINGS, formatDate } from "@/i18n";
import { chunkLabel, uncertainLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";

const RISK_STYLE = {
  prohibited: { rule: "border-red-700", text: "text-red-800", Icon: Ban },
  high: { rule: "border-orange-600", text: "text-orange-800", Icon: ShieldAlert },
  limited: { rule: "border-amber-500", text: "text-amber-800", Icon: Info },
  minimal: { rule: "border-emerald-600", text: "text-emerald-800", Icon: ShieldCheck },
};

type Props = { report: Report; lang: Lang };

export function ReportView({ report, lang }: Props) {
  const t = STRINGS[lang];
  const label = (id: string) => chunkLabel(id, lang);
  const reasons = [
    ...report.banned.map((point) => `${t.bannedBy}: Art. 5(1)(${point})`),
    ...report.high_risk_basis.map((id) => `${t.highRiskBy}: ${label(id)}`),
    ...(report.exception ? [`${t.exception}: ${report.exception}`] : []),
    ...report.became_provider.map((point) => `${t.becameProvider}: Art. 25(1)(${point})`),
  ];
  const style = RISK_STYLE[report.risk];
  const heading = useRef<HTMLHeadingElement>(null);
  // The result replaced the steps: say so, without scrolling the page.
  useEffect(() => heading.current?.focus({ preventScroll: true }), []);
  // The Art. 50 duties are usually among the obligations already, with their dates.
  const listed = new Set(report.obligations.map((o) => `${o.chunk_id} ${o.who}`));
  const extraDuties = report.transparency_duties.filter((d) => !listed.has(`${d.chunk_id} ${d.who}`));
  const open = report.uncertain.length > 0 || report.assumed_unknown.length > 0;

  const sections: { title: string; body: React.ReactNode }[] = [];
  if (reasons.length) sections.push({ title: t.why, body: <List items={reasons} /> });
  if (open)
    sections.push({
      title: t.uncertainTitle,
      body: (
        <div className="space-y-3">
          {report.uncertain.length > 0 && (
            <Bullets intro={t.uncertainText} items={unique(report.uncertain.map((n) => uncertainLabel(n, lang)))} />
          )}
          {report.assumed_unknown.length > 0 && (
            <Bullets intro={t.assumedText} items={report.assumed_unknown.map((f) => t.facts[f] ?? f)} />
          )}
        </div>
      ),
    });
  if (report.obligations.length)
    sections.push({ title: t.obligations, body: <ObligationsTable obligations={report.obligations} lang={lang} /> });
  if (extraDuties.length) sections.push({ title: t.transparency, body: <Duties duties={extraDuties} lang={lang} /> });
  if (report.other_role_duties.length)
    sections.push({ title: t.otherRole, body: <Duties duties={report.other_role_duties} lang={lang} /> });
  if (report.notes.length) sections.push({ title: t.notes, body: <List items={report.notes} small /> });
  if (report.citations.length)
    sections.push({
      title: t.citations,
      body: (
        <ol className="space-y-5">
          {report.citations.map((citation, index) => (
            <Source key={index} citation={citation} lang={lang} />
          ))}
        </ol>
      ),
    });

  return (
    <article>
      <header className={cn("border-l-4 pl-5", style.rule)}>
        <h2
          ref={heading}
          tabIndex={-1}
          className={cn("flex items-center gap-3 text-3xl font-semibold outline-none", style.text)}
        >
          <style.Icon aria-hidden className="size-7 shrink-0" />
          {t.risk[report.risk]}
        </h2>
        <p className="mt-2 max-w-prose">{t.riskMeaning[report.risk]}</p>
        <p className="mt-1 font-bold">{t.role[report.role ?? "unknown"]}</p>
      </header>

      {report.unverified.length > 0 && (
        <div role="alert" className="mt-6 border-l-4 border-destructive bg-red-50 px-5 py-3 text-sm text-red-900">
          <p className="font-bold">{t.unverifiedTitle}</p>
          <Bullets intro={t.unverifiedText} items={unique(report.unverified.map(label))} />
        </div>
      )}

      {sections.map((section) => (
        <section key={section.title} className="mt-8 border-t pt-6">
          <h3 className="mb-4 text-xl font-semibold">{section.title}</h3>
          {section.body}
        </section>
      ))}

      <footer className="mt-10 border-t pt-4 text-sm text-muted-foreground">
        {t.lawAsOf(formatDate(LAW_VERSION, lang))} {t.notAdvice}
      </footer>
    </article>
  );
}

/** The right-hand panel next to a report: the result at a glance, and what to do with it. */
export function ReportSummary({ report, lang, onNew }: Props & { onNew: () => void }) {
  const t = STRINGS[lang];
  const rows = merge(report.obligations);
  const inForce = rows.filter((o) => o.in_force).length;
  const next = unique(rows.filter((o) => !o.in_force).map((o) => o.applies_from)).sort()[0];
  const verified = report.citations.filter((c) => c.verified).length;
  const facts: [string, string][] = [
    [t.summaryRisk, t.risk[report.risk]],
    [t.summaryRole, t.role[report.role ?? "unknown"].replace(/^[^:]+:\s*/, "")],
    [t.summaryObligations, String(rows.length)],
    [t.summaryInForce, String(inForce)],
    ...(next ? [[t.summaryNext, formatDate(next, lang)] as [string, string]] : []),
    [t.summaryVerified, `${verified} / ${report.citations.length}`],
  ];
  return (
    <section aria-labelledby="summary-title" className="space-y-4">
      <h2 id="summary-title" className="text-lg font-semibold">
        {t.summaryTitle}
      </h2>
      <dl className="divide-y divide-border/70 text-sm">
        {facts.map(([term, value]) => (
          <div key={term} className="flex justify-between gap-4 py-2">
            <dt className="text-muted-foreground">{term}</dt>
            <dd className="text-right font-medium tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="flex flex-col gap-2">
        <ShareLink lang={lang} />
        <Button variant="outline" onClick={() => window.print()}>
          {t.print}
        </Button>
        <Button variant="outline" onClick={onNew}>
          {t.newAssessment}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">{t.linkWarning}</p>
    </section>
  );
}

/** One row per duty, with every party it binds: provider and deployer often share one. */
function merge(obligations: Obligation[]) {
  const rows = new Map<string, Obligation & { roles: Obligation["who"][] }>();
  for (const o of obligations) {
    const key = [o.chunk_id, o.text, o.applies_from, o.condition].join("|");
    const row = rows.get(key);
    if (row) row.roles.push(o.who);
    else rows.set(key, { ...o, roles: [o.who] });
  }
  return [...rows.values()].sort((a, b) => a.applies_from.localeCompare(b.applies_from));
}

function ObligationsTable({ obligations, lang }: { obligations: Obligation[]; lang: Lang }) {
  const t = STRINGS[lang];
  // On narrow screens every row becomes a block with its own labels (no sideways scroll).
  const cell = "block px-0 py-1 md:table-cell md:px-3 md:py-3 md:align-top";
  const rows = merge(obligations);
  return (
    <table className="w-full border-collapse text-sm">
      <thead className="sr-only md:not-sr-only">
        <tr className="border-b text-left text-sm text-muted-foreground">
          <th className="px-3 py-2 font-medium">{t.colFrom}</th>
          <th className="px-3 py-2 font-medium">{t.colObligation}</th>
          <th className="px-3 py-2 font-medium">{t.colParty}</th>
          <th className="px-3 py-2 font-medium">{t.colProvision}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((o, index) => {
          // A date repeated from the row above is shown once per group, still read out per row.
          const repeat = index > 0 && rows[index - 1]!.applies_from === o.applies_from;
          return (
          <tr key={index} className="block border-b py-2 md:table-row md:py-0">
            <td className={cn(cell, "whitespace-nowrap tabular-nums")}>
              <span className={cn(repeat && "md:sr-only")}>{formatDate(o.applies_from, lang)}</span>
              {o.in_force && !repeat && <span className="ml-2 text-xs text-emerald-800">{t.inForceTag}</span>}
            </td>
            <td className={cell}>
              {o.text}
              {o.condition && <span className="text-muted-foreground"> ({o.condition})</span>}
            </td>
            <td className={cn(cell, "text-muted-foreground")}>{o.roles.map((who) => t.who[who]).join(", ")}</td>
            <td className={cn(cell, "whitespace-nowrap tabular-nums")}>
              {chunkLabel(o.chunk_id, lang)}
              {o.verified === false && (
                <span className="block">
                  <Unverified text={t.notFound} />
                </span>
              )}
            </td>
          </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Duties({ duties, lang }: { duties: Report["transparency_duties"]; lang: Lang }) {
  const t = STRINGS[lang];
  return (
    <ul className="space-y-2 text-sm">
      {duties.map((duty, index) => (
        <li key={index} className="flex flex-wrap justify-between gap-x-6 gap-y-1 border-b pb-2">
          <span>{duty.text}</span>
          <span className="text-muted-foreground tabular-nums">
            {t.who[duty.who]}, {chunkLabel(duty.chunk_id, lang)}
          </span>
        </li>
      ))}
    </ul>
  );
}

function Source({ citation, lang }: { citation: Citation; lang: Lang }) {
  const t = STRINGS[lang];
  const verified = citation.verified ?? false;
  return (
    <li className="grid gap-1 text-sm md:grid-cols-[10rem_minmax(0,1fr)] md:gap-6">
      <div className="space-y-1">
        <p className="font-semibold tabular-nums">{chunkLabel(citation.chunk_id, lang)}</p>
        {verified ? (
          <span className="inline-flex items-center gap-1 text-xs text-emerald-800">
            <CircleCheck aria-hidden className="size-3.5" />
            {t.verified}
          </span>
        ) : (
          <Unverified text={t.notFound} />
        )}
      </div>
      <div className="space-y-1">
        <p>{citation.claim}</p>
        <blockquote className="border-l-2 border-gold pl-3 font-serif text-base text-muted-foreground italic">
          “{citation.quote}”
        </blockquote>
        {citation.note && <p className="text-muted-foreground">{citation.note}</p>}
      </div>
    </li>
  );
}

function ShareLink({ lang }: { lang: Lang }) {
  const t = STRINGS[lang];
  const [copied, setCopied] = useState(false);
  return (
    <Button
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
  );
}

function List({ items, small }: { items: string[]; small?: boolean }) {
  return (
    <ul className={cn("list-disc space-y-1 pl-5 marker:text-gold-ink", small && "text-sm")}>
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function Bullets({ intro, items }: { intro: string; items: string[] }) {
  return (
    <div>
      <p>{intro}</p>
      <ul className="mt-1 list-disc pl-5">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
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
