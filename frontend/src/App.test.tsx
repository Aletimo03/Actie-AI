import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import * as client from "@/api/client";
import type { StreamEvent } from "@/api/client";
import fixture from "@/test/fixtures/credit-scoring.json";
import { App } from "./App";

vi.mock("@/api/client", async (original) => ({
  ...(await original<typeof client>()),
  startAssessment: vi.fn(),
  sendAnswers: vi.fn(),
  continueAssessment: vi.fn(),
  getAssessment: vi.fn(),
}));

const ID = "67be72a5-f90b-4c4d-9ca7-0bbf1fe4103e";
const done = { ...(fixture as client.Assessment), id: ID };

async function* stream(...events: StreamEvent[]) {
  for (const event of events) yield event;
}

beforeEach(() => {
  history.replaceState(null, "", "/");
});
afterEach(() => vi.clearAllMocks());

const describeSystem = async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.type(screen.getByLabelText("Your AI system"), "A bank scores consumers' credit-worthiness.");
  await user.click(screen.getByRole("button", { name: "Check my system" }));
  return user;
};

it("goes from the description to the questions to the report, and keeps the id in the URL", async () => {
  vi.mocked(client.startAssessment).mockReturnValue(
    stream(
      { event: "start", data: { id: ID } },
      { event: "step", data: { step: "extract_facts", label: "Reading the description" } },
      { event: "result", data: { id: ID, status: "needs_answers", questions: [{ id: "role", text: "Did you build it?" }] } },
    ),
  );
  vi.mocked(client.sendAnswers).mockReturnValue(stream({ event: "result", data: done }));

  const user = await describeSystem();
  expect(client.startAssessment).toHaveBeenCalledWith("A bank scores consumers' credit-worthiness.", "en", expect.any(AbortSignal));
  expect(location.pathname).toBe(`/a/${ID}`);

  await user.type(await screen.findByLabelText("Did you build it?"), "Yes, and we use it.");
  await user.click(screen.getByRole("button", { name: "Continue" }));
  expect(client.sendAnswers).toHaveBeenCalledWith(ID, { role: "Yes, and we use it." }, expect.any(AbortSignal));
  expect(await screen.findByRole("heading", { level: 2, name: "High risk" })).toBeInTheDocument();
});

it("refuses a description that is too short without calling the API", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.type(screen.getByLabelText("Your AI system"), "A chatbot.");
  await user.click(screen.getByRole("button", { name: "Check my system" }));
  expect(screen.getByRole("alert")).toHaveTextContent("At least 20 characters (10 so far).");
  expect(client.startAssessment).not.toHaveBeenCalled();
});

it("waits out a limit before it lets the user try again", async () => {
  vi.mocked(client.startAssessment).mockImplementation(() => {
    throw new client.ApiError(429, "limit of 10 new assessments an hour reached", 3585);
  });
  await describeSystem();
  expect(await screen.findByText("limit of 10 new assessments an hour reached")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Try again in 60 minutes" })).toBeDisabled();
});

it("continues a run the model stopped, from where it stopped", async () => {
  vi.mocked(client.startAssessment).mockReturnValue(
    stream(
      { event: "start", data: { id: ID } },
      { event: "error", data: { message: "the language model is unavailable", retry_after: 0 } },
    ),
  );
  vi.mocked(client.continueAssessment).mockReturnValue(stream({ event: "result", data: done }));
  const user = await describeSystem();
  expect(await screen.findByText(/Your progress is saved/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(client.continueAssessment).toHaveBeenCalledWith(ID, expect.any(AbortSignal));
  expect(await screen.findByRole("heading", { level: 2, name: "High risk" })).toBeInTheDocument();
});

it("opens an assessment from its link", async () => {
  history.replaceState(null, "", `/a/${ID}`);
  vi.mocked(client.getAssessment).mockResolvedValue(done);
  render(<App />);
  expect(await screen.findByRole("heading", { level: 2, name: "High risk" })).toBeInTheDocument();
  await waitFor(() => expect(client.getAssessment).toHaveBeenCalledWith(ID));
});

it("names the page, with the logo as decoration", () => {
  render(<App />);
  expect(screen.getByRole("heading", { level: 1, name: "Actie AI" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Actie AI/ }).querySelector("img")).toHaveAttribute("alt", "");
});

it("shows where the user is, skips to the content and focuses the result", async () => {
  vi.mocked(client.startAssessment).mockReturnValue(stream({ event: "result", data: done }));
  render(<App />);
  expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main");
  expect(screen.getByRole("navigation", { name: "Progress" }).querySelector("[aria-current=step]"))
    .toHaveTextContent("Describe");

  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Your AI system"), "A bank scores consumers' credit-worthiness.");
  await user.click(screen.getByRole("button", { name: "Check my system" }));
  const result = await screen.findByRole("heading", { level: 2, name: "High risk" });
  expect(result).toHaveFocus();
  expect(screen.getByRole("navigation", { name: "Progress" }).querySelector("[aria-current=step]"))
    .toHaveTextContent("Report");
});

it("explains a dropped connection in words and offers to read the result", async () => {
  vi.mocked(client.startAssessment).mockReturnValue(
    (async function* () {
      yield { event: "start", data: { id: ID } } as StreamEvent;
      throw new TypeError("Failed to fetch");
    })(),
  );
  await describeSystem();
  expect(await screen.findByText(/The connection dropped/)).toBeInTheDocument();
  expect(screen.queryByText(/Failed to fetch/)).toBeNull();
  vi.mocked(client.getAssessment).mockResolvedValue(done);
  await userEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(client.getAssessment).toHaveBeenCalledWith(ID); // reads it, doesn't start (and pay) again
  expect(client.startAssessment).toHaveBeenCalledTimes(1);
});

it("lets the user start over from the questions", async () => {
  vi.mocked(client.startAssessment).mockReturnValue(
    stream({ event: "result", data: { id: ID, status: "needs_answers", questions: [{ id: "role", text: "Did you build it?" }] } }),
  );
  const user = await describeSystem();
  await user.click(await screen.findByRole("button", { name: "Start over" }));
  expect(screen.getByLabelText("Your AI system")).toBeInTheDocument();
  expect(location.pathname).toBe("/");
});
