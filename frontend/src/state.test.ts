import { describe, expect, it } from "vitest";
import report from "@/test/fixtures/credit-scoring.json";
import type { Assessment } from "@/api/client";
import { reduce, type View } from "./state";

const assessment = report as Assessment;

describe("reduce", () => {
  it("follows a run from the first step to the report", () => {
    let view: View = reduce({ kind: "describing" }, { type: "run", id: null });
    view = reduce(view, { type: "start", id: "a1" });
    view = reduce(view, { type: "step", step: "extract_facts", label: "Reading the description" });
    expect(view).toEqual({ kind: "running", id: "a1", steps: ["Reading the description"], last: "extract_facts" });
    expect(reduce(view, { type: "result", assessment }).kind).toBe("done");
  });

  it("asks when the run pauses, and keeps the id when a run fails", () => {
    const paused = { id: "a1", status: "needs_answers", description: "A bank scores credit.", answers: [], questions: [{ id: "role", text: "?" }] };
    const asking = reduce({ kind: "running", id: "a1", steps: [], last: null }, {
      type: "result",
      assessment: paused as Assessment,
    });
    expect(asking).toEqual({
      kind: "asking",
      id: "a1",
      questions: [{ id: "role", text: "?" }],
      submitted: { description: "A bank scores credit.", answers: [] },
    });

    const failed = reduce(asking, { type: "failed", message: "busy", retry: "continue", retryAfter: 60 });
    expect(failed).toMatchObject({ kind: "failed", id: "a1", retry: "continue", retryAfter: 60 });
  });

  it("offers to continue an assessment a provider error stopped", () => {
    const view = reduce({ kind: "loading", id: "a1" }, {
      type: "result",
      assessment: { id: "a1", status: "incomplete" } as Assessment,
    });
    expect(view).toMatchObject({ kind: "failed", id: "a1", retry: "continue" });
  });

  it("ignores a late step once the run is over", () => {
    const done = reduce({ kind: "running", id: "a1", steps: [], last: null }, { type: "result", assessment });
    expect(reduce(done, { type: "step", step: "report", label: "late" })).toBe(done);
  });
});
