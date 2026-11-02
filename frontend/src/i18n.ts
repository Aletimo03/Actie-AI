/**
 * The UI's own words, kept in src/locales/<lang>.json so they can be edited without touching
 * code. {name} in a text is filled in here. The questions, step labels and report texts
 * come from the API.
 */
import type { Lang } from "@/api/client";
import en from "@/locales/en.json";
import it from "@/locales/it.json";

export const LAW_VERSION = "2026-07-27"; // consolidated text in the database (02024R1689-20260727)

type Messages = typeof en;

function fill(
  template: string,
  values: Record<string, string | number>,
): string {
  return template.replace(/\{(\w+)\}/g, (_, name: string) =>
    String(values[name]),
  );
}

function build(m: Messages) {
  return {
    ...m,
    facts: m.facts as Record<string, string>,
    stepOf: (n: number, total: number) => fill(m.stepOf, { n, total }),
    consolidated: (date: string) => fill(m.consolidated, { date }),
    elapsed: (seconds: number) => fill(m.elapsed, { seconds }),
    tooShort: (n: number) => fill(m.tooShort, { n }),
    lawAsOf: (date: string) => fill(m.lawAsOf, { date }),
    tryAgainIn: (wait: string) => fill(m.tryAgainIn, { wait }),
    bannedBy: (provision: string) => fill(m.bannedBy, { provision }),
    highRiskBy: (provision: string) => fill(m.highRiskBy, { provision }),
  };
}

// Typed as English: a key missing from it.json fails the build (locales.test.ts also
// catches extra keys and placeholders that differ).
const italian: Messages = it;

export const STRINGS: Record<Lang, ReturnType<typeof build>> = {
  en: build(en),
  it: build(italian),
};

export function initialLang(): Lang {
  try {
    const saved = localStorage.getItem("lang");
    if (saved === "en" || saved === "it") return saved;
  } catch {
    // storage blocked: fall back to the browser's language
  }
  return navigator.language.startsWith("it") ? "it" : "en";
}

export function formatDate(iso: string, lang: Lang): string {
  // A calendar date: format it in UTC, or a browser west of UTC shows the day before.
  return new Intl.DateTimeFormat(lang, {
    dateStyle: "long",
    timeZone: "UTC",
  }).format(new Date(`${iso}T00:00:00Z`));
}

export function formatWait(seconds: number, lang: Lang): string {
  const unit = seconds >= 90 ? "minute" : "second";
  const value = unit === "minute" ? Math.ceil(seconds / 60) : seconds;
  return new Intl.NumberFormat(lang, {
    style: "unit",
    unit,
    unitDisplay: "long",
  }).format(value);
}
