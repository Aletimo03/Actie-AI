/** The UI's own words. The questions, step labels and report texts come from the API. */
import type { Lang } from "@/api/client";

export const LAW_VERSION = "2026-07-27"; // consolidated text in the database (02024R1689-20260727)

const en = {
  title: "EU AI Act check",
  headline: "What does the AI Act ask of your system?",
  intro:
    "Describe your AI system: what it does, who uses it, who it affects. You get its risk level under the AI Act, your duties with their dates, and the articles behind each conclusion.",
  description: "Your AI system",
  placeholder:
    "e.g. We built a tool that ranks job applicants' CVs for our recruiters, and we sell it to other companies.",
  tooShort: (n: number) => `At least 20 characters (${n} so far).`,
  language: "Language of the report",
  check: "Check my system",
  working: "Checking",
  questionsTitle: "A few questions",
  questionsIntro: "The description leaves these open. Leave a field blank if you don't know.",
  continue: "Continue",
  risk: {
    prohibited: "Prohibited",
    high: "High risk",
    limited: "Limited risk",
    minimal: "Minimal risk",
  },
  riskMeaning: {
    prohibited: "This practice is banned in the EU (Art. 5).",
    high: "Allowed, with strict requirements before and while it is used.",
    limited: "Allowed; people must be told about the AI (Art. 50).",
    minimal: "No specific duties beyond AI literacy (Art. 4).",
  },
  role: {
    provider: "You are its provider",
    deployer: "You are its deployer",
    provider_and_deployer: "You are its provider and deployer",
    unknown: "Your role is not clear from the description",
  },
  why: "Why",
  bannedBy: "Banned by",
  highRiskBy: "High-risk under",
  exception: "Art. 6(3) exception",
  becameProvider: "You become its provider under",
  uncertainTitle: "Not settled",
  uncertainText:
    "These points could not be settled from your answers; the report assumes the stricter reading.",
  assumedText: "The description did not say:",
  obligations: "Your obligations",
  inForce: (date: string) => `In force since ${date}`,
  from: (date: string) => `From ${date}`,
  who: { provider: "provider", deployer: "deployer" },
  transparency: "Transparency duties (Art. 50)",
  otherRole: "Duties of the other party, for context",
  notes: "Notes",
  citations: "Sources",
  verified: "Verified in the law text",
  notFound: "Not found in the law text",
  unverifiedTitle: "Some sources could not be verified",
  unverifiedText: "Check these against the law before relying on them.",
  lawAsOf: (date: string) => `Law as of ${date} (consolidated text).`,
  notAdvice: "This is an automated assessment, not legal advice.",
  copyLink: "Copy link",
  copied: "Copied",
  linkWarning: "Anyone with this link can read this assessment.",
  newAssessment: "New assessment",
  failedTitle: "Something went wrong",
  stopped: "The language model stopped before the report. Your progress is saved.",
  notFoundTitle: "This assessment doesn't exist or was deleted.",
  tryAgain: "Try again",
  tryAgainIn: (wait: string) => `Try again in ${wait}`,
  loading: "Loading the assessment",
  facts: {
    purpose: "what it is for",
    domain: "the area it is used in",
    affected_people: "who it affects",
    role: "whether you built it or use it",
    real_time: "whether it identifies people in real time",
  } as Record<string, string>,
};

type Strings = typeof en;

const it: Strings = {
  title: "Verifica AI Act",
  headline: "Cosa chiede l'AI Act al tuo sistema?",
  intro:
    "Descrivi il tuo sistema di IA: cosa fa, chi lo usa, chi riguarda. Ottieni il livello di rischio secondo l'AI Act, i tuoi obblighi con le date e gli articoli dietro ogni conclusione.",
  description: "Il tuo sistema di IA",
  placeholder:
    "es. Abbiamo sviluppato uno strumento che ordina i CV dei candidati per i nostri selezionatori e lo vendiamo ad altre aziende.",
  tooShort: (n: number) => `Almeno 20 caratteri (finora ${n}).`,
  language: "Lingua del rapporto",
  check: "Verifica il mio sistema",
  working: "Verifica in corso",
  questionsTitle: "Qualche domanda",
  questionsIntro: "La descrizione lascia aperti questi punti. Lascia vuoto un campo se non lo sai.",
  continue: "Continua",
  risk: {
    prohibited: "Vietato",
    high: "Alto rischio",
    limited: "Rischio limitato",
    minimal: "Rischio minimo",
  },
  riskMeaning: {
    prohibited: "Questa pratica è vietata nell'UE (art. 5).",
    high: "Consentito, con requisiti rigorosi prima e durante l'uso.",
    limited: "Consentito; le persone devono sapere che c'è l'IA (art. 50).",
    minimal: "Nessun obbligo specifico oltre l'alfabetizzazione in materia di IA (art. 4).",
  },
  role: {
    provider: "Sei il fornitore",
    deployer: "Sei il deployer",
    provider_and_deployer: "Sei fornitore e deployer",
    unknown: "Il tuo ruolo non è chiaro dalla descrizione",
  },
  why: "Perché",
  bannedBy: "Vietato da",
  highRiskBy: "Alto rischio secondo",
  exception: "Eccezione dell'art. 6(3)",
  becameProvider: "Diventi fornitore secondo",
  uncertainTitle: "Punti aperti",
  uncertainText:
    "Questi punti non si sono potuti chiarire dalle risposte; il rapporto adotta la lettura più rigorosa.",
  assumedText: "La descrizione non diceva:",
  obligations: "I tuoi obblighi",
  inForce: (date: string) => `In vigore dal ${date}`,
  from: (date: string) => `Dal ${date}`,
  who: { provider: "fornitore", deployer: "deployer" },
  transparency: "Obblighi di trasparenza (art. 50)",
  otherRole: "Obblighi dell'altra parte, per contesto",
  notes: "Note",
  citations: "Fonti",
  verified: "Verificata nel testo di legge",
  notFound: "Non trovata nel testo di legge",
  unverifiedTitle: "Alcune fonti non sono state verificate",
  unverifiedText: "Controllale sul testo di legge prima di farvi affidamento.",
  lawAsOf: (date: string) => `Testo di legge al ${date} (versione consolidata).`,
  notAdvice: "Questa è una valutazione automatica, non una consulenza legale.",
  copyLink: "Copia link",
  copied: "Copiato",
  linkWarning: "Chiunque abbia questo link può leggere questa valutazione.",
  newAssessment: "Nuova valutazione",
  failedTitle: "Qualcosa è andato storto",
  stopped: "Il modello linguistico si è fermato prima del rapporto. I progressi sono salvati.",
  notFoundTitle: "Questa valutazione non esiste o è stata cancellata.",
  tryAgain: "Riprova",
  tryAgainIn: (wait: string) => `Riprova tra ${wait}`,
  loading: "Caricamento della valutazione",
  facts: {
    purpose: "a cosa serve",
    domain: "il settore in cui si usa",
    affected_people: "chi riguarda",
    role: "se l'avete sviluppato o lo usate",
    real_time: "se identifica le persone in tempo reale",
  },
};

export const STRINGS: Record<Lang, Strings> = { en, it };

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
  return new Intl.DateTimeFormat(lang, { dateStyle: "long", timeZone: "UTC" }).format(
    new Date(`${iso}T00:00:00Z`),
  );
}

export function formatWait(seconds: number, lang: Lang): string {
  const unit = seconds >= 90 ? "minute" : "second";
  const value = unit === "minute" ? Math.ceil(seconds / 60) : seconds;
  return new Intl.NumberFormat(lang, { style: "unit", unit, unitDisplay: "long" }).format(value);
}
