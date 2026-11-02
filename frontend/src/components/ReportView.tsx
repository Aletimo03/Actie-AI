/**
 * The report, laid out like a legal document: the result and why, then sections separated
 * by rules, the obligations as a list. Model text (quotes, claims, duties) is
 * shown as text, never as HTML: React escapes it, so an injected "<img onerror=...>" is
 * shown, not run.
 */
import { Ban, CircleCheck, Info, ShieldAlert, ShieldCheck, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Citation, Lang, Obligation, Report } from "@/api/client";
import { Button } from "@/components/ui/button";
import { LAW_VERSION, STRINGS, formatDate } from "@/i18n";
import { chunkLabel, uncertainLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";

const RISK_STYLE = {
  prohibited: { rule: "border-red-500", text: "text-red-300 print:text-red-800", Icon: Ban },
  high: { rule: "border-orange-400", text: "text-orange-300 print:text-orange-800", Icon: ShieldAlert },
  limited: { rule: "border-amber-400", text: "text-amber-300 print:text-amber-800", Icon: Info },
  minimal: { rule: "border-emerald-400", text: "text-emerald-300 print:text-emerald-800", Icon: ShieldCheck },
};

type Props = { report: Report; lang: Lang };

export function ReportView({ report, lang }: Props) {
  const t = STRINGS[lang];
  const label = (id: string) => chunkLabel(id, lang);
  const reasons = [
    ...report.banned.map((point) => t.bannedBy(`Art. 5(1)(${point})`)),
    ...report.high_risk_basis.map((id) => t.highRiskBy(label(id))),
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
    sections.push({ title: t.obligations, body: <ObligationsList obligations={report.obligations} lang={lang} /> });
  if (extraDuties.length) sections.push({ title: t.transparency, body: <Duties duties={extraDuties} lang={lang} /> });
  if (report.other_role_duties.length)
    sections.push({ title: t.otherRole, body: <Duties duties={report.other_role_duties} lang={lang} /> });
  if (report.citations.length)
    sections.push({
      title: t.citations,
      body: (
        <ol className="space-y-6">
          {report.citations.map((citation, index) => (
            <Source key={index} citation={citation} lang={lang} />
          ))}
        </ol>
      ),
    });

  if (report.notes.length) sections.push({ title: t.notes, body: <List items={report.notes} /> });

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
        {/* Why, in one or two lines: the provisions themselves are listed below. */}
        {reasons.map((reason) => (
          <p key={reason} className="mt-1 text-muted-foreground">
            {reason}
          </p>
        ))}
      </header>

      {report.unverified.length > 0 && (
        <div role="alert" className="mt-6 border-l-4 border-destructive bg-red-500/10 px-5 py-3 text-red-100 print:bg-transparent print:text-red-900">
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
        {t.lawAsOf(formatDate(LAW_VERSION, lang))} {t.aiNotice} {t.notAdvice}
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
      <dl className="divide-y divide-border/70 text-[0.95rem]">
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
        <ConfirmNew lang={lang} onConfirm={onNew} />
      </div>
      <p className="text-sm text-muted-foreground">{t.linkWarning}</p>
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

/** One entry per duty, gold-bulleted: what to do first, then who, from when, and where. */
function ObligationsList({ obligations, lang }: { obligations: Obligation[]; lang: Lang }) {
  const t = STRINGS[lang];
  return (
    <ul className="space-y-5">
      {merge(obligations).map((o, index) => (
        <li key={index} className="grid grid-cols-[0.5rem_minmax(0,1fr)] gap-x-3.5">
          <span aria-hidden className="mt-3 size-2 rounded-full bg-gold" />
          <div>
            <p className="text-lg font-medium">
              {o.text}
              {o.condition && <span className="font-normal text-muted-foreground"> ({o.condition})</span>}
            </p>
            {/* Three aligned columns, label over value: one row per duty, easy to scan down.
                On a phone, one row per fact instead, label beside value. */}
            <dl className="mt-2.5 grid gap-y-1 sm:grid-cols-3 sm:gap-x-5">
              <Fact term={t.colParty}>{o.roles.map((who) => t.who[who]).join(", ")}</Fact>
              <Fact term={t.colFrom}>
                <span className="whitespace-nowrap tabular-nums">{formatDate(o.applies_from, lang)}</span>
                {o.in_force && (
                  <span className="block text-sm text-emerald-300 print:text-emerald-800">{t.inForceTag}</span>
                )}
              </Fact>
              <Fact term={t.colProvision}>
                <span className="tabular-nums">{chunkLabel(o.chunk_id, lang)}</span>
                {o.verified === false && (
                  <span className="block text-sm">
                    <Unverified text={t.notFound} />
                  </span>
                )}
              </Fact>
            </dl>
          </div>
        </li>
      ))}
    </ul>
  );
}

function Fact({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 gap-3 sm:block">
      <dt className="w-32 shrink-0 pt-0.5 text-sm text-muted-foreground sm:w-auto sm:pt-0">{term}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

function Duties({ duties, lang }: { duties: Report["transparency_duties"]; lang: Lang }) {
  const t = STRINGS[lang];
  return (
    <ul className="space-y-2">
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

/** One provision: its number and whether the quote was found, what it supports, the quote. */
function Source({ citation, lang }: { citation: Citation; lang: Lang }) {
  const t = STRINGS[lang];
  const verified = citation.verified ?? false;
  return (
    <li className="border-t pt-6 first:border-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <p className="font-semibold text-gold-ink tabular-nums">{chunkLabel(citation.chunk_id, lang)}</p>
        {verified ? (
          <span className="inline-flex items-center gap-1.5 text-sm text-emerald-300 print:text-emerald-800">
            <CircleCheck aria-hidden className="size-3.5" />
            {t.verified}
          </span>
        ) : (
          <span className="text-sm">
            <Unverified text={t.notFound} />
          </span>
        )}
      </div>
      <p className="mt-2 max-w-prose">{citation.claim}</p>
      <blockquote className="mt-3 max-w-prose border-l-2 border-gold/60 pl-4 font-serif text-base leading-relaxed text-muted-foreground italic">
        “{citation.quote}”
      </blockquote>
      {citation.note && <p className="mt-2 text-sm text-muted-foreground">{citation.note}</p>}
    </li>
  );
}

/**
 * "New assessment" asks first: the result leaves the screen. A modal on the page's root
 * (the blurred panel around the button would otherwise contain it), focus kept inside it,
 * Escape or the backdrop cancels, and focus goes back to the button.
 */
function ConfirmNew({ lang, onConfirm }: { lang: Lang; onConfirm: () => void }) {
  const t = STRINGS[lang];
  const [open, setOpen] = useState(false);
  const opener = useRef<HTMLButtonElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const confirm = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);

  useEffect(() => {
    if (open) cancel.current?.focus();
    else if (wasOpen.current) opener.current?.focus();
    wasOpen.current = open;
  }, [open]);

  return (
    <>
      <Button ref={opener} variant="outline" onClick={() => setOpen(true)}>
        {t.newAssessment}
      </Button>
      {open &&
        createPortal(
          <div
            className="fixed inset-0 z-50 grid place-items-center bg-black/65 p-4 backdrop-blur-sm"
            onClick={(event) => event.target === event.currentTarget && setOpen(false)}
          >
            <div
              role="alertdialog"
              aria-modal="true"
              aria-labelledby="confirm-title"
              aria-describedby="confirm-text"
              className="ink-dark w-full max-w-md animate-[dialog-in_200ms_ease-out] rounded-2xl border border-white/15 bg-[#1b1916] p-6 shadow-[0_30px_80px_-20px_rgba(0,0,0,0.8)]"
              onKeyDown={(event) => {
                if (event.key === "Escape") setOpen(false);
                if (event.key === "Tab") {
                  // Two buttons: Tab and Shift+Tab move between them, never out.
                  event.preventDefault();
                  (document.activeElement === cancel.current ? confirm : cancel).current?.focus();
                }
              }}
            >
              <h2 id="confirm-title" className="text-xl font-semibold">
                {t.confirmTitle}
              </h2>
              <p id="confirm-text" className="mt-2 text-muted-foreground">
                {t.confirmText}
              </p>
              <div className="mt-6 flex flex-wrap justify-end gap-3">
                <Button ref={cancel} variant="outline" onClick={() => setOpen(false)}>
                  {t.cancel}
                </Button>
                <Button ref={confirm} onClick={onConfirm}>
                  {t.confirmYes}
                </Button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
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
