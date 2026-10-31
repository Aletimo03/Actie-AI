// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, getAssessment, readEvents, startAssessment, type StreamEvent } from "./client";

function body(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function all(stream: AsyncIterable<StreamEvent>) {
  const events = [];
  for await (const event of stream) events.push(event);
  return events;
}

const START = 'event: start\ndata: {"id": "a1"}\n\n';
const STEP = 'event: step\ndata: {"step": "extract_facts", "label": "Reading the description"}\n\n';

describe("readEvents", () => {
  it("reads events in one chunk", async () => {
    expect(await all(readEvents(body(START + STEP)))).toEqual([
      { event: "start", data: { id: "a1" } },
      { event: "step", data: { step: "extract_facts", label: "Reading the description" } },
    ]);
  });

  it("joins an event the network split, even inside the JSON or the blank line", async () => {
    const whole = START + STEP;
    for (const at of [5, START.length - 1, START.length + 30]) {
      const events = await all(readEvents(body(whole.slice(0, at), whole.slice(at))));
      expect(events.map((e) => e.event)).toEqual(["start", "step"]);
    }
  });

  it("splits a multi-byte character across chunks correctly", async () => {
    const bytes = new TextEncoder().encode('event: step\ndata: {"label": "Verifica è"}\n\n');
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, bytes.length - 6)); // cuts "è" in half
        controller.enqueue(bytes.slice(bytes.length - 6));
        controller.close();
      },
    });
    expect((await all(readEvents(stream)))[0]?.data).toEqual({ label: "Verifica è" });
  });

  it("drops a last event that was cut off", async () => {
    expect(await all(readEvents(body(START, 'event: step\ndata: {"st')))).toHaveLength(1);
  });
});

describe("requests", () => {
  afterEach(() => vi.unstubAllGlobals());

  function respond(response: Response) {
    const fetch = vi.fn().mockResolvedValue(response);
    vi.stubGlobal("fetch", fetch);
    return fetch;
  }

  it("posts the description and streams the events", async () => {
    const fetch = respond(new Response(body(START), { status: 200 }));
    expect(await all(startAssessment("A tool that ranks CVs.", "it"))).toHaveLength(1);
    const [url, init] = fetch.mock.calls[0]!;
    expect(url).toBe("/api/assessments/stream");
    expect(JSON.parse(init.body)).toEqual({ description: "A tool that ranks CVs.", lang: "it" });
  });

  it("throws the limit and when to retry before any event", async () => {
    respond(
      Response.json({ detail: "limit of 10 new assessments an hour reached" }, {
        status: 429,
        headers: { "Retry-After": "3585" },
      }),
    );
    const error = await all(startAssessment("x".repeat(30), "en")).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 429, retryAfter: 3585 });
    expect(error.message).toContain("10 new assessments");
  });

  it("joins the messages of a 422", async () => {
    respond(Response.json({ detail: [{ msg: "too short" }, { msg: "bad lang" }] }, { status: 422 }));
    await expect(getAssessment("a1")).rejects.toThrow("too short; bad lang");
  });
});
