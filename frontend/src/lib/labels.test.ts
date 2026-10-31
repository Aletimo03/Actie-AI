import { describe, expect, it } from "vitest";
import { chunkLabel, uncertainLabel } from "./labels";

describe("chunkLabel", () => {
  it.each([
    ["en_art4_p1", "Art. 4(1)"],
    ["en_art5_p1_c", "Art. 5(1)(c)"],
    ["en_art113_c_i", "Art. 113(c)(i)"],
    ["en_art6", "Art. 6"],
    ["en_art4a_p2", "Art. 4a(2)"],
    ["en_annex3_5_b", "Annex III, 5(b)"],
    ["en_annex3", "Annex III"],
    ["en_annex1_seca_2", "Annex I, Section A, 2"],
    ["en_rec12", "Recital 12"],
    ["en_something_else", "en_something_else"],
  ])("%s -> %s", (id, label) => {
    expect(chunkLabel(id, "en")).toBe(label);
  });

  it("speaks Italian", () => {
    expect(chunkLabel("it_annex3_5_b", "it")).toBe("Allegato III, 5(b)");
    expect(chunkLabel("it_rec12", "it")).toBe("Considerando 12");
  });
});

it("names the open points of each check", () => {
  expect(["h", "interacts", "annex_iii", "art25", "new_thing"].map((n) => uncertainLabel(n, "en")))
    .toEqual(["Art. 5(1)(h)", "Art. 50 (interacts)", "Annex III", "Art. 25", "new_thing"]);
});
