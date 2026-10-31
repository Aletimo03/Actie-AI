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
import { ReportView } from "@/components/ReportView";
import { STRINGS, initialLang } from "@/i18n";
import { type Action, type View, reduce } from "@/state";

// An assessment's address is /a/<id>: reloading or sharing it opens the same one.
const PATH = /^\/a\/([0-9a-f-]{36})$/;

function idInUrl(): string | null {
  return location.pathname.match(PATH)?.[1] ?? null;
}

function showId(id: string | null) {
  const path = id ? `/a/${id}` : "/";
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
    async (id: string | null, open: (signal: AbortSignal) => AsyncIterable<StreamEvent>) => {
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
        }
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
    if (id) void load(id);
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
    else if (view.retry === "continue") void follow(id, (signal) => continueAssessment(id, signal));
    else void load(id);
  };

  return (
    <div className="min-h-svh">
      <header className="border-b-2 border-gold bg-primary text-primary-foreground">
        <div className="mx-auto flex max-w-3xl items-center gap-4 px-4 py-4 sm:px-6">
          <a
            href="/"
            className="flex items-center gap-3 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-gold"
            onClick={(event) => (event.preventDefault(), newAssessment())}
          >
            <img src="/actie-160.png" alt="" width={56} height={53} className="size-14 rounded-xl" />
            <span>
              <h1 className="text-3xl leading-none font-semibold">Actie AI</h1>
              <span className="text-sm text-gold">{t.title}</span>
            </span>
          </a>
        </div>
      </header>
      <main className="mx-auto max-w-3xl space-y-6 px-4 py-8 sm:px-6">
        {view.kind === "describing" && (
          <DescribeForm lang={lang} onLang={changeLang} initial={description} error={view.error} onSubmit={start} />
        )}
        {view.kind === "loading" && <p aria-busy>{t.loading}…</p>}
        {view.kind === "running" && <Progress steps={view.steps} lang={lang} />}
        {view.kind === "asking" && (
          <Questions
            key={view.questions.map((q) => q.id).join()}
            questions={view.questions}
            lang={lang}
            onSubmit={(answers) => follow(view.id, (signal) => sendAnswers(view.id, answers, signal))}
          />
        )}
        {view.kind === "done" && <ReportView report={view.report} lang={lang} onNew={newAssessment} />}
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
      </main>
    </div>
  );
}

function toAction(event: StreamEvent): Action {
  switch (event.event) {
    case "start":
      return { type: "start", id: event.data.id };
    case "step":
      return { type: "step", label: event.data.label };
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
    return { type: "failed", message: String(error), retry: id ? "reload" : "start" };
  }
  if (error.status === 422) return { type: "invalid", message: error.message };
  if (error.status === 404) return { type: "failed", message: error.message, retry: "new" };
  if (error.status === 409) return { type: "failed", message: error.message, retry: "reload" };
  return {
    type: "failed",
    message: error.message,
    retry: id ? "continue" : "start",
    retryAfter: error.retryAfter,
  };
}
