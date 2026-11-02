import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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
    expect(screen.getByText("Role: provider and deployer")).toBeInTheDocument();
    expect(screen.getByText("High-risk classification: Annex III, 5(b)")).toBeInTheDocument();
  });

  it("lists the obligations in a table, by the date they apply from", () => {
    show(real);
    const table = screen.getByRole("table");
    const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Applicable from", "Obligation", "Party", "Provision"]);
    const rows = within(table).getAllByRole("row").slice(1);
    const dates = rows.map((r) => within(r).getAllByRole("cell")[0]!.textContent);
    expect(dates[0]).toBe("February 2, 2025already applicable");
    expect(dates.at(-1)).toBe("December 2, 2027");
    // AI literacy binds both roles: one row naming both parties, not two rows.
    const literacy = rows.filter((r) => /sufficient AI literacy/.test(r.textContent ?? ""));
    expect(literacy).toHaveLength(1);
    expect(within(literacy[0]!).getAllByRole("cell")[2]).toHaveTextContent("deployer, provider");
  });

  it("sums the result up beside it", () => {
    render(<ReportSummary report={real} lang="en" onNew={() => {}} />);
    const summary = screen.getByRole("region", { name: "Summary" });
    expect(summary).toHaveTextContent("Risk categoryHigh-risk AI system");
    expect(summary).toHaveTextContent("Roleprovider and deployer");
    expect(summary).toHaveTextContent("Next application dateDecember 2, 2027");
    expect(screen.getByRole("button", { name: "Copy link" })).toBeInTheDocument();
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
    expect(screen.getAllByText("Quotation verified against the legal text")).toHaveLength(real.citations.length);
    expect(screen.getAllByText("Quotation not found in the legal text")).toHaveLength(1);
    expect(screen.getByText("Unverified citations")).toBeInTheDocument();
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
    expect(screen.getByText("Pratica vietata: Art. 5(1)(h)")).toBeInTheDocument();
    expect(screen.getByText("Art. 5(1)(h)", { selector: "li" })).toBeInTheDocument();
    expect(screen.getByText("Allegato III", { selector: "li" })).toBeInTheDocument();
    expect(screen.getByText(/se l'organizzazione sviluppa o utilizza il sistema/)).toBeInTheDocument();
  });
});
