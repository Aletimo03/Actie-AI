/**
 * The page as a state machine: one value says what is on screen, so states that
 * can't happen together (a spinner over a report) can't be written down.
 */
import type { Answer, Assessment, Question, Report } from "@/api/client";

// What "try again" does: start over with the same text, run a stopped assessment on,
// or read it again (after a dropped connection, or a 409 from another tab).
export type Retry = "start" | "continue" | "reload" | "new";

export type View =
  | { kind: "describing"; error?: string }
  | { kind: "loading"; id: string }
  // `last` is the step that finished last (its name in the graph): it tells what runs now.
  | { kind: "running"; id: string | null; steps: string[]; last: string | null }
  | { kind: "asking"; id: string; questions: Question[]; submitted: Submitted }
  | { kind: "done"; id: string; report: Report; submitted: Submitted }
  | {
      kind: "failed";
      id: string | null;
      message: string | null;
      retry: Retry;
      retryAfter: number | null;
    };

/** What the user sent: the result is read next to it. */
export type Submitted = { description: string; answers: Answer[] };

export type Action =
  | { type: "run"; id: string | null }
  | { type: "start"; id: string }
  | { type: "step"; step: string; label: string }
  | { type: "result"; assessment: Assessment }
  | {
      type: "failed";
      message: string | null;
      retry: Retry;
      retryAfter?: number | null;
    }
  | { type: "invalid"; message: string }
  | { type: "load"; id: string }
  | { type: "new" };

const idOf = (view: View): string | null => ("id" in view ? view.id : null);

export function reduce(view: View, action: Action): View {
  switch (action.type) {
    case "run":
      return { kind: "running", id: action.id, steps: [], last: null };
    case "start":
      return view.kind === "running" ? { ...view, id: action.id } : view;
    case "step":
      return view.kind === "running"
        ? { ...view, steps: [...view.steps, action.label], last: action.step }
        : view;
    case "result":
      return fromAssessment(action.assessment);
    case "failed":
      return {
        kind: "failed",
        id: idOf(view),
        message: action.message,
        retry: action.retry,
        retryAfter: action.retryAfter ?? null,
      };
    case "invalid":
      return { kind: "describing", error: action.message };
    case "load":
      return { kind: "loading", id: action.id };
    case "new":
      return { kind: "describing" };
  }
}

export function fromAssessment({
  id,
  status,
  questions,
  report,
  description,
  answers,
}: Assessment): View {
  const submitted = { description, answers };
  if (status === "done" && report)
    return { kind: "done", id, report, submitted };
  if (status === "needs_answers")
    return { kind: "asking", id, questions: questions ?? [], submitted };
  return {
    kind: "failed",
    id,
    message: null,
    retry: "continue",
    retryAfter: null,
  };
}
