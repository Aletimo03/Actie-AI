/**
 * The assessment API: typed calls, and the progress stream read from a POST.
 *
 * The browser's EventSource only does GET, and starting an assessment sends a body,
 * so streams are read with fetch: chunk by chunk, an event ends at a blank line.
 * Errors found before a stream opens (422, 404, 409, 429) are HTTP statuses and
 * throw ApiError; after that a failure arrives as an `error` event.
 */
import type { components } from "./schema";

type Schemas = components["schemas"];
export type Assessment = Schemas["AssessmentOut"];
export type Report = Schemas["Report"];
export type Obligation = Schemas["ObligationOut"];
export type Citation = Schemas["Citation"];
export type Question = Schemas["QuestionOut"];
export type Lang = Schemas["AssessRequest"]["lang"] & string;

// The stream's events are text, not in the OpenAPI spec: these mirror backend/app/api.py.
export type StreamEvent =
  | { event: "start"; data: { id: string } }
  | { event: "step"; data: { step: string; label: string } }
  | { event: "result"; data: Assessment }
  | { event: "error"; data: { message: string; retry_after: number } };

const BASE = "/api";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly retryAfter: number | null = null, // seconds, from the Retry-After header
  ) {
    super(message);
  }
}

async function failure(response: Response): Promise<ApiError> {
  let message = ""; // no JSON body (a proxy's 502, say): the UI explains it in words
  try {
    const { detail } = await response.json();
    // FastAPI: a string for our errors, a list of {loc, msg} for a 422.
    message = typeof detail === "string" ? detail : detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    // not from our API
  }
  const retry = Number(response.headers.get("Retry-After"));
  return new ApiError(response.status, message, retry > 0 ? retry : null);
}

export async function getAssessment(id: string, signal?: AbortSignal): Promise<Assessment> {
  const response = await fetch(`${BASE}/assessments/${id}`, { signal });
  if (!response.ok) throw await failure(response);
  return response.json();
}

/** The events of a Server-Sent Events body, however the network splits it into chunks. */
export async function* readEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<StreamEvent> {
  // A reader, not `for await` over the stream: not every browser can iterate streams.
  const reader = body.getReader();
  const decoder = new TextDecoder(); // stream: true keeps a character split across chunks
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replaceAll("\r\n", "\n");
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      let name = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) name = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (data.length) yield { event: name, data: JSON.parse(data.join("\n")) } as StreamEvent;
    }
  }
  // A block with no blank line after it was cut off: dropped, as the SSE spec says.
}

async function* post(path: string, body: unknown, signal?: AbortSignal) {
  const response = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) throw await failure(response);
  yield* readEvents(response.body);
}

export function startAssessment(description: string, lang: Lang, signal?: AbortSignal) {
  return post("/assessments/stream", { description, lang }, signal);
}

/** Questions left out are sent blank: the backend skips them. */
export function sendAnswers(id: string, answers: Record<string, string>, signal?: AbortSignal) {
  return post(`/assessments/${id}/answers/stream`, { answers }, signal);
}

/** Runs an assessment a provider error stopped on from the failed step. */
export function continueAssessment(id: string, signal?: AbortSignal) {
  return post(`/assessments/${id}/continue/stream`, undefined, signal);
}
