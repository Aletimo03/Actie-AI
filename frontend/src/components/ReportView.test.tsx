import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Assessment, Report } from "@/api/client";
import fixture from "@/test/fixtures/credit-scoring.json";
import { ReportView } from "./ReportView";

const real = (fixture as Assessment).report!; // a real Haiku 5.5 report: bank credit scoring

function show(report: Report, lang: "en" | "it" = "en") {
  return render(<ReportView report={report} lang={lang} onNew={() => {}} />);
}

describe("ReportView", () => {
  it("leads with the risk, the role and why", () => {
    show(real);
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("High risk");
    expect(screen.getByText("You are its provider and deployer")).toBeInTheDocument();
    expect(screen.getByText("High-risk under Annex III, 5(b)")).toBeInTheDocument();
  });

  it("groups the obligations by the date they apply from", () => {
    show(real);
    const section = screen.getByRole("heading", { name: "Your obligations" }).closest("[data-slot=card]")!;
    const dates = within(section as HTMLElement).getAllByRole("heading", { level: 4 });
    expect(dates.map((d) => d.textContent)).toEqual([
      "In force since February 2, 2025",
      "From December 2, 2027",
    ]);
    // AI literacy is a duty of both roles: one row with two badges, not two rows.
    const literacy = within(section as HTMLElement).getAllByText(/sufficient AI literacy/);
    expect(literacy).toHaveLength(1);
    const row = within(literacy[0]!.closest("li")!);
    expect(row.getByText("provider")).toBeInTheDocument();
    expect(row.getByText("deployer")).toBeInTheDocument();
  });

  it("lists a transparency duty once, under the obligations when it is there", () => {
    const duty = { situation: "interacts", chunk_id: "en_art50_p1", who: "provider" as const, text: "Tell people." };
    const dated = { chunk_id: "en_art50_p1", who: "provider" as const, text: "Tell people.", applies_from: "2026-08-02", in_force: true, condition: null, verified: true };
    show({ ...real, transparency_duties: [duty], obligations: [dated] });
    expect(screen.getAllByText("Tell people.")).toHaveLength(1);
    expect(screen.queryByText("Transparency duties (Art. 50)")).toBeNull();
  });

  it("shows every source with whether it was verified, and flags the ones that were not", () => {
    const report = {
      ...real,
      citations: [...real.citations, { chunk_id: "en_art99_p1", quote: "invented", claim: "c", verified: false, note: "quote not found" }],
      unverified: ["en_art99_p1"],
    };
    show(report);
    expect(screen.getAllByText("✓ Verified in the law text")).toHaveLength(real.citations.length);
    expect(screen.getAllByText("⚠ Not found in the law text")).toHaveLength(1);
    expect(screen.getByText("Some sources could not be verified")).toBeInTheDocument();
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
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Vietato");
    expect(screen.getByText("Vietato da Art. 5(1)(h)")).toBeInTheDocument();
    expect(screen.getByText(/Art\. 5\(1\)\(h\), Allegato III/)).toBeInTheDocument();
    expect(screen.getByText(/se l'avete sviluppato o lo usate/)).toBeInTheDocument();
  });
});
