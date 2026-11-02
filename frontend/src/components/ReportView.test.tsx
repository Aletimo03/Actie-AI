import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Assessment, Report } from "@/api/client";
import fixture from "@/test/fixtures/credit-scoring.json";
import { ReportSummary, ReportView } from "./ReportView";

const real = (fixture as Assessment).report!; // a real Haiku 5.5 report: bank credit scoring

function show(report: Report, lang: "en" | "it" = "en") {
  return render(<ReportView report={report} lang={lang} />);
}

describe("ReportView", () => {
  it("leads with the risk, the role and why", () => {
    show(real);
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("High-risk AI system");
    expect(screen.getByText("Role: Provider & Deployer")).toBeInTheDocument();
    expect(screen.getByText("High-risk classification under Annex III, 5(b)")).toBeInTheDocument();
  });

  it("lists each obligation, then its party, date and provision, by date", () => {
    show(real);
    const list = screen.getByRole("heading", { name: "Obligations" }).nextElementSibling as HTMLElement;
    const items = within(list).getAllByRole("listitem");
    const terms = within(items[0]!).getAllByRole("term").map((term) => term.textContent);
    expect(terms).toEqual(["Responsible party", "Applicable from", "Legal provision"]);
    expect(items[0]).toHaveTextContent("February 2, 2025currently applicable");
    expect(items.at(-1)).toHaveTextContent("December 2, 2027");
    // AI literacy binds both roles: one entry naming both parties, not two.
    const literacy = items.filter((item) => /sufficient AI literacy/.test(item.textContent ?? ""));
    expect(literacy).toHaveLength(1);
    expect(literacy[0]).toHaveTextContent("Responsible partydeployer, provider");
  });

  it("puts the notes after the provisions cited", () => {
    show({ ...real, notes: ["A note."] });
    const titles = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(titles.indexOf("Operational notes")).toBeGreaterThan(titles.indexOf("Cited legal provisions"));
  });

  it("sums the result up beside it", () => {
    render(<ReportSummary report={real} lang="en" onNew={() => {}} />);
    const summary = screen.getByRole("region", { name: "Summary" });
    expect(summary).toHaveTextContent("Risk tierHigh-risk AI system");
    expect(summary).toHaveTextContent("Organizational roleProvider & Deployer");
    expect(summary).toHaveTextContent("Next compliance deadlineDecember 2, 2027");
    expect(screen.getByRole("button", { name: "Copy link" })).toBeInTheDocument();
  });

  it("asks before leaving the result for a new assessment", async () => {
    const user = userEvent.setup();
    const onNew = vi.fn();
    render(<ReportSummary report={real} lang="en" onNew={onNew} />);
    const open = screen.getByRole("button", { name: "Start new assessment" });
    await user.click(open);
    const dialog = screen.getByRole("alertdialog", { name: "Start a new assessment?" });
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(open).toHaveFocus();
    expect(onNew).not.toHaveBeenCalled();
    await user.click(open);
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Start new assessment" }));
    expect(onNew).toHaveBeenCalledOnce();
  });

  it("lists a transparency duty once, under the obligations when it is there", () => {
    const duty = { situation: "interacts", chunk_id: "en_art50_p1", who: "provider" as const, text: "Tell people." };
    const dated = { chunk_id: "en_art50_p1", who: "provider" as const, text: "Tell people.", applies_from: "2026-08-02", in_force: true, condition: null, verified: true };
    show({ ...real, transparency_duties: [duty], obligations: [dated] });
    expect(screen.getAllByText("Tell people.")).toHaveLength(1);
    expect(screen.queryByText("Transparency obligations (Article 50)")).toBeNull();
  });

  it("shows every source with whether it was verified, and flags the ones that were not", () => {
    const report = {
      ...real,
      citations: [...real.citations, { chunk_id: "en_art99_p1", quote: "invented", claim: "c", verified: false, note: "quote not found" }],
      unverified: ["en_art99_p1"],
    };
    show(report);
    expect(screen.getAllByText("Reference verified against official text")).toHaveLength(real.citations.length);
    expect(screen.getAllByText("Reference not found in official text")).toHaveLength(1);
    expect(screen.getByText("Unverified references")).toBeInTheDocument();
  });

  it("shows model text as text, never as HTML", () => {
    const attack = '<img src=x onerror="alert(1)">';
    const { container } = show({
      ...real,
      citations: [{ chunk_id: "en_art5_p1", quote: attack, claim: attack, verified: true, note: "" }],
    });
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText(attack)).toBeInTheDocument();
  });

  it("names what was assumed and what stayed open, in Italian too", () => {
    show({ ...real, risk: "prohibited", banned: ["h"], uncertain: ["h", "annex_iii"], assumed_unknown: ["role"] }, "it");
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Pratica di IA vietata");
    expect(screen.getByText("Pratica vietata ai sensi di Art. 5(1)(h)")).toBeInTheDocument();
    expect(screen.getByText("Art. 5(1)(h)", { selector: "li" })).toBeInTheDocument();
    expect(screen.getByText("Allegato III", { selector: "li" })).toBeInTheDocument();
    expect(screen.getByText(/la distinzione tra sviluppo ed utilizzo del sistema/)).toBeInTheDocument();
  });
});
