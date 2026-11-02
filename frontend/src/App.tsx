import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import {
  ApiError,
  type Lang,
  type StreamEvent,
  continueAssessment,
  getAssessment,
  sendAnswers,
  startAssessment,
} from "@/api/client";
import { DescribeForm } from "@/components/DescribeForm";
import { Failure } from "@/components/Failure";
import { Progress } from "@/components/Progress";
import { Questions } from "@/components/Questions";
import { Steps } from "@/components/Steps";
import { Submitted } from "@/components/Submitted";
import { ReportSummary, ReportView } from "@/components/ReportView";
import { Scope } from "@/components/Scope";
import { STRINGS, initialLang } from "@/i18n";
import { cn } from "@/lib/utils";
import { type Action, type View, reduce } from "@/state";

// An assessment's address is /assessment/<id>: reloading or sharing it opens the same one.
// /a/<id> was the first address: links shared with it still open, under the new one.
const PATH = /^\/(?:assessment|a)\/([0-9a-f-]{36})$/;

function idInUrl(): string | null {
  return location.pathname.match(PATH)?.[1] ?? null;
}

function showId(id: string | null) {
  const path = id ? `/assessment/${id}` : "/";
  if (location.pathname !== path) history.pushState(null, "", path);
}

export function App() {
  const [lang, setLang] = useState<Lang>(initialLang);
  const [description, setDescription] = useState("");
  const [view, dispatch] = useReducer(reduce, null, (): View => {
    const id = idInUrl();
    return id ? { kind: "loading", id } : { kind: "describing" };
  });
  const abort = useRef<AbortController | null>(null);
  const t = STRINGS[lang];
  const home = view.kind === "describing";

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const changeLang = (next: Lang) => {
    setLang(next);
    try {
      localStorage.setItem("lang", next);
    } catch {
      // storage blocked: the choice lasts for this visit
    }
  };

  /** Runs one request: its events drive the view, its errors become a "failed" view. */
  const follow = useCallback(
    async (
      id: string | null,
      open: (signal: AbortSignal) => AsyncIterable<StreamEvent>,
    ) => {
      abort.current?.abort();
      const controller = new AbortController();
      abort.current = controller;
      dispatch({ type: "run", id });
      let current = id; // known once the `start` event arrives
      try {
        for await (const event of open(controller.signal)) {
          if (event.event === "start") {
            current = event.data.id;
            showId(current);
          }
          dispatch(toAction(event));
          if (event.event === "result" || event.event === "error") return;
        }
        // Closed without a result (a proxy timeout, a restart): never leave the steps
        // spinning. The run may have finished on the server, so offer to read it.
        if (!controller.signal.aborted) dispatch(failure(null, current));
      } catch (error) {
        if (!controller.signal.aborted) dispatch(failure(error, current));
      }
    },
    [],
  );

  const load = useCallback(async (id: string) => {
    dispatch({ type: "load", id });
    try {
      dispatch({ type: "result", assessment: await getAssessment(id) });
    } catch (error) {
      dispatch(failure(error, id));
    }
  }, []);

  useEffect(() => {
    // Only for an id in the URL at first render; later loads come from the handlers below.
    const id = idInUrl();
    if (!id) return;
    history.replaceState(null, "", `/assessment/${id}`); // an old /a/ link: show the new address
    void load(id);
  }, [load]);

  useEffect(() => {
    const onBack = () => {
      const id = idInUrl();
      if (id) void load(id);
      else dispatch({ type: "new" });
    };
    addEventListener("popstate", onBack);
    return () => removeEventListener("popstate", onBack);
  }, [load]);

  const start = (text: string) => {
    setDescription(text);
    void follow(null, (signal) => startAssessment(text, lang, signal));
  };

  const newAssessment = () => {
    abort.current?.abort();
    showId(null);
    dispatch({ type: "new" });
  };

  const retry = () => {
    if (view.kind !== "failed") return;
    const id = view.id;
    if (view.retry === "start" || !id) start(description);
    else if (view.retry === "continue")
      void follow(id, (signal) => continueAssessment(id, signal));
    else void load(id);
  };

  return (
    <div className="min-h-svh">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-card font-bold focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:px-4 focus:py-3"
      >
        {t.skip}
      </a>
      {/* The header lies over the picture on every page. */}
      <header className="absolute inset-x-0 top-0 z-10 border-b border-white/10 text-primary-foreground [--focus:var(--gold)] print:hidden">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-6 px-4 sm:px-8">
          <a
            href="/"
            className="flex items-center gap-3 rounded-lg"
            onClick={(event) => (event.preventDefault(), newAssessment())}
          >
            <img
              src="/actie-160.png"
              alt=""
              width={40}
              height={40}
              className="size-10 rounded-lg"
            />
            <h1 className="text-[1.375rem] leading-none font-semibold">
              Actie AI
            </h1>
            <span
              aria-hidden
              className="mx-2 hidden h-5 w-px bg-primary-foreground/20 sm:block"
            />
            <span className="hidden text-sm text-primary-foreground/75 sm:inline">
              {t.title}
            </span>
          </a>
          {/* The language is chosen before an assessment starts: the report is written in it. */}
          {home && (
            <div
              role="group"
              aria-label={t.languageLabel}
              className="relative inline-flex rounded-full border border-primary-foreground/15 p-0.5"
            >
              {/* The grey pill slides to the chosen language. */}
              <span
                aria-hidden
                className={cn(
                  "absolute inset-y-0.5 left-0.5 w-11 rounded-full bg-primary-foreground/10 transition-transform duration-300 ease-out",
                  lang === "it" && "translate-x-full",
                )}
              />
              {(["en", "it"] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  aria-pressed={option === lang}
                  aria-label={option === "en" ? "English" : "Italiano"}
                  onClick={() => changeLang(option)}
                  className={cn(
                    "relative w-11 rounded-full py-1 text-sm font-semibold transition-colors duration-300",
                    option === lang
                      ? "text-gold"
                      : "text-primary-foreground/70 hover:text-primary-foreground",
                  )}
                >
                  {option.toUpperCase()}
                </button>
              ))}
            </div>
          )}
        </div>
      </header>

      {home ? (
        <main id="main" tabIndex={-1} className="outline-none">
          {/* The first screen: the tool itself over a picture, then what it checks. */}
          <div className="relative isolate overflow-hidden bg-primary text-primary-foreground [--focus:var(--gold)]">
            <Backdrop />
            <div className="mx-auto max-w-7xl px-4 pt-36 pb-24 sm:px-8 lg:pt-44 lg:pb-40">
              <DescribeForm
                lang={lang}
                initial={description}
                error={view.error}
                onSubmit={start}
              />
            </div>
          </div>
          <div className="bg-primary text-primary-foreground [--focus:var(--gold)] [--gold-ink:var(--gold)] [--muted-foreground:rgba(250,246,238,0.72)]">
            <Scope
              lang={lang}
              className="mx-auto grid max-w-7xl gap-10 space-y-0 border-t border-white/10 px-4 pt-16 pb-20 sm:px-8 md:grid-cols-3"
            />
          </div>
        </main>
      ) : (
        <main
          id="main"
          tabIndex={-1}
          className="ink-dark relative isolate min-h-svh outline-none"
        >
          <Backdrop short />
          {/* The work on a dark glass sheet, the summary beside it, as on the first screen. */}
          <div className="relative mx-auto grid max-w-7xl gap-8 px-4 pt-28 pb-20 sm:px-8 lg:grid-cols-[minmax(0,1fr)_21rem] lg:pt-32 print:block print:p-0">
            <section className="min-w-0 overflow-hidden rounded-2xl border border-white/15 bg-[#1b1916]/90 shadow-[0_20px_60px_-20px_rgba(0,0,0,0.7)] backdrop-blur-md print:border-0 print:bg-transparent print:shadow-none">
              {view.kind !== "loading" && view.kind !== "failed" && (
                <div className="border-b px-6 py-5 sm:px-10 print:hidden">
                  <Steps view={view} lang={lang} />
                </div>
              )}
              <div className="space-y-8 px-6 py-8 sm:px-10">
                {view.kind === "loading" && <p aria-busy>{t.loading}</p>}
                {view.kind === "running" && (
                  <Progress steps={view.steps} last={view.last} lang={lang} />
                )}
                {view.kind === "asking" && (
                  <Questions
                    key={view.questions.map((q) => q.id).join()}
                    questions={view.questions}
                    lang={lang}
                    onSubmit={(answers) =>
                      follow(view.id, (signal) =>
                        sendAnswers(view.id, answers, signal),
                      )
                    }
                  />
                )}
                {view.kind === "done" && (
                  <ReportView report={view.report} lang={lang} />
                )}
                {view.kind === "failed" && (
                  <Failure
                    key={`${view.retry}-${view.retryAfter}`}
                    lang={lang}
                    message={view.message}
                    retry={view.retry}
                    retryAfter={view.retryAfter}
                    onRetry={retry}
                    onNew={newAssessment}
                  />
                )}
              </div>
            </section>
            {/* Beside the work on a desktop, below it on a phone. */}
            <aside className="space-y-10 rounded-2xl border border-white/15 bg-[#1b1916]/90 px-7 py-7 shadow-[0_20px_60px_-20px_rgba(0,0,0,0.7)] backdrop-blur-md lg:sticky lg:top-8 lg:self-start print:hidden">
              {view.kind === "done" && (
                <ReportSummary
                  report={view.report}
                  lang={lang}
                  onNew={newAssessment}
                />
              )}
              {(view.kind === "asking" || view.kind === "done") && (
                <Submitted submitted={view.submitted} lang={lang} />
              )}
              {view.kind !== "done" && view.kind !== "asking" && (
                <Scope lang={lang} />
              )}
            </aside>
          </div>
        </main>
      )}
    </div>
  );
}

/** The courtroom picture behind the header: the whole first screen, or a band above the work. */
function Backdrop({ short = false }: { short?: boolean }) {
  return (
    <div
      aria-hidden
      className={cn(
        "absolute inset-x-0 top-0 -z-10 bg-[url(/hero.webp)] bg-cover bg-[position:75%_center] print:hidden",
        // The band fades out by a mask, so it has no bottom edge to see.
        short
          ? "h-[34rem] [mask-image:linear-gradient(to_bottom,black_35%,transparent)]"
          : "bottom-0",
      )}
    >
      {/* A faint warm light behind the heading, so the left is not flat black. */}
      <div className="absolute inset-0 z-10 bg-[radial-gradient(ellipse_at_22%_38%,rgba(232,173,84,0.13),transparent_55%)]" />
      {/* Dark where the text sits, the scales left visible on the right. */}
      <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(12,11,14,0.94)_0%,rgba(12,11,14,0.8)_45%,rgba(12,11,14,0.3)_100%)]" />
      <div
        className={cn(
          "absolute inset-x-0 bottom-0 z-20 bg-gradient-to-b from-transparent to-[#0c0b0e]",
          short ? "hidden" : "h-40",
        )}
      />
      {/* On narrow screens the text runs over the scales: darken all of it. */}
      <div className="absolute inset-0 bg-[#0c0b0e]/55 lg:hidden" />
    </div>
  );
}

function toAction(event: StreamEvent): Action {
  switch (event.event) {
    case "start":
      return { type: "start", id: event.data.id };
    case "step":
      return { type: "step", step: event.data.step, label: event.data.label };
    case "result":
      return { type: "result", assessment: event.data };
    case "error":
      return {
        type: "failed",
        message: event.data.message,
        retry: "continue", // the checkpoint has the finished steps
        retryAfter: event.data.retry_after,
      };
  }
}

/** What the user can do about an error thrown before or during a stream. */
function failure(error: unknown, id: string | null): Action {
  if (!(error instanceof ApiError)) {
    // The connection dropped: the run may have finished on the server, so read it.
    return { type: "failed", message: null, retry: id ? "reload" : "start" };
  }
  if (error.status === 422) return { type: "invalid", message: error.message };
  if (error.status === 404)
    return { type: "failed", message: error.message, retry: "new" };
  if (error.status === 409)
    return { type: "failed", message: error.message, retry: "reload" };
  return {
    type: "failed",
    message: error.message || null,
    retry: id ? "continue" : "start",
    retryAfter: error.retryAfter,
  };
}
