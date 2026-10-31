/** The UI's own words. The questions, step labels and report texts come from the API. */
import type { Lang } from "@/api/client";

export const LAW_VERSION = "2026-07-27"; // consolidated text in the database (02024R1689-20260727)

const en = {
  title: "EU AI Act assessment",
  headline: "Assess an AI system under the EU AI Act",
  skip: "Skip to main content",
  flowLabel: "Assessment steps",
  flow: ["Description", "Analysis", "Questions", "Result"],
  nextStep: "Processing the next step",
  elapsed: (seconds: number) => `${seconds} s elapsed. An assessment usually takes 20–40 seconds.`,
  startOver: "Start again",
  connectionLost:
    "The connection was interrupted. The assessment may have been completed; select Retry to load it.",
  unreachable: "The service is currently unavailable. Check your connection or try again shortly.",
  intro:
    "Describe the system: its purpose, who uses it and who is affected by it. The assessment states the risk category, your role, your obligations with their application dates, and the provisions they are based on.",
  description: "Description of the AI system",
  placeholder:
    "Example: We develop a tool that ranks job applicants' CVs for recruiters and sell it to other companies.",
  tooShort: (n: number) => `Enter at least 20 characters (${n} entered).`,
  language: "Language of the assessment",
  check: "Start assessment",
  working: "Assessment in progress",
  questionsTitle: "Additional information required",
  questionsIntro:
    "The description does not settle the following points. Leave a field empty if the answer is not known.",
  continue: "Submit answers",
  risk: {
    prohibited: "Prohibited AI practice",
    high: "High-risk AI system",
    limited: "Limited risk",
    minimal: "Minimal risk",
  },
  riskMeaning: {
    prohibited: "The practice may not be placed on the market, put into service or used in the EU (Article 5).",
    high: "Permitted, subject to the requirements and obligations of Chapter III.",
    limited: "Permitted. The transparency obligations of Article 50 apply.",
    minimal: "No specific obligations beyond AI literacy (Article 4).",
  },
  role: {
    provider: "Role: provider",
    deployer: "Role: deployer",
    provider_and_deployer: "Role: provider and deployer",
    unknown: "Role: not determined from the description",
  },
  why: "Legal basis",
  bannedBy: "Prohibited practice",
  highRiskBy: "High-risk classification",
  exception: "Exception under Article 6(3)",
  becameProvider: "Provider obligations apply",
  uncertainTitle: "Open points",
  uncertainText:
    "The following points could not be determined. The assessment applies the stricter reading:",
  assumedText: "Not stated in the description:",
  obligations: "Obligations",
  inForce: (date: string) => `Applicable since ${date}`,
  from: (date: string) => `Applicable from ${date}`,
  who: { provider: "provider", deployer: "deployer" },
  transparency: "Transparency obligations (Article 50)",
  otherRole: "Obligations of the other party (for reference)",
  notes: "Notes",
  citations: "Provisions cited",
  verified: "Quotation verified against the legal text",
  notFound: "Quotation not found in the legal text",
  unverifiedTitle: "Unverified citations",
  unverifiedText: "Check the following against the legal text before relying on them:",
  lawAsOf: (date: string) => `Legal text: Regulation (EU) 2024/1689, consolidated version of ${date}.`,
  notAdvice: "This assessment is generated automatically and does not constitute legal advice.",
  copyLink: "Copy link",
  copied: "Link copied",
  linkWarning: "Anyone with this link can view this assessment.",
  newAssessment: "New assessment",
  failedTitle: "The assessment could not be completed",
  stopped: "The language model stopped responding. The completed steps have been saved.",
  notFoundTitle: "Assessment not found. It may have been deleted.",
  tryAgain: "Retry",
  tryAgainIn: (wait: string) => `Retry in ${wait}`,
  loading: "Loading the assessment",
  facts: {
    purpose: "the intended purpose",
    domain: "the area of use",
    affected_people: "the persons affected",
    role: "whether you develop or use the system",
    real_time: "whether identification takes place in real time",
  } as Record<string, string>,
};

type Strings = typeof en;

// Impersonal register, as in Italian administrative texts; the agent's questions use "voi".
const it: Strings = {
  title: "Valutazione AI Act",
  headline: "Valutazione di un sistema di IA ai sensi dell'AI Act",
  skip: "Vai al contenuto principale",
  flowLabel: "Fasi della valutazione",
  flow: ["Descrizione", "Analisi", "Domande", "Esito"],
  nextStep: "Elaborazione del passaggio successivo",
  elapsed: (seconds: number) => `${seconds} s trascorsi. Una valutazione richiede di norma 20–40 secondi.`,
  startOver: "Ricomincia",
  connectionLost:
    "La connessione si è interrotta. La valutazione potrebbe essere stata completata; selezionare Riprova per caricarla.",
  unreachable: "Il servizio non è al momento disponibile. Verificare la connessione o riprovare a breve.",
  intro:
    "Indicare la finalità del sistema, chi lo utilizza e quali persone ne sono interessate. La valutazione riporta la categoria di rischio, il ruolo, gli obblighi con le date di applicazione e le disposizioni su cui si basano.",
  description: "Descrizione del sistema di IA",
  placeholder:
    "Esempio: sviluppiamo uno strumento che ordina i CV dei candidati per i selezionatori e lo vendiamo ad altre aziende.",
  tooShort: (n: number) => `Inserire almeno 20 caratteri (${n} inseriti).`,
  language: "Lingua della valutazione",
  check: "Avvia la valutazione",
  working: "Valutazione in corso",
  questionsTitle: "Informazioni aggiuntive richieste",
  questionsIntro:
    "La descrizione non chiarisce i punti seguenti. Lasciare il campo vuoto se la risposta non è nota.",
  continue: "Invia le risposte",
  risk: {
    prohibited: "Pratica di IA vietata",
    high: "Sistema di IA ad alto rischio",
    limited: "Rischio limitato",
    minimal: "Rischio minimo",
  },
  riskMeaning: {
    prohibited: "La pratica non può essere immessa sul mercato, messa in servizio o utilizzata nell'UE (articolo 5).",
    high: "Consentito, nel rispetto dei requisiti e degli obblighi del capo III.",
    limited: "Consentito. Si applicano gli obblighi di trasparenza dell'articolo 50.",
    minimal: "Nessun obbligo specifico oltre all'alfabetizzazione in materia di IA (articolo 4).",
  },
  role: {
    provider: "Ruolo: fornitore",
    deployer: "Ruolo: deployer",
    provider_and_deployer: "Ruolo: fornitore e deployer",
    unknown: "Ruolo: non determinabile dalla descrizione",
  },
  why: "Base giuridica",
  bannedBy: "Pratica vietata",
  highRiskBy: "Classificazione ad alto rischio",
  exception: "Eccezione ai sensi dell'articolo 6(3)",
  becameProvider: "Si applicano gli obblighi del fornitore",
  uncertainTitle: "Punti aperti",
  uncertainText:
    "Non è stato possibile determinare i punti seguenti. La valutazione adotta l'interpretazione più rigorosa:",
  assumedText: "Non indicato nella descrizione:",
  obligations: "Obblighi",
  inForce: (date: string) => `Applicabile dal ${date}`,
  from: (date: string) => `Applicabile a partire dal ${date}`,
  who: { provider: "fornitore", deployer: "deployer" },
  transparency: "Obblighi di trasparenza (articolo 50)",
  otherRole: "Obblighi dell'altra parte (per riferimento)",
  notes: "Note",
  citations: "Disposizioni citate",
  verified: "Citazione verificata sul testo di legge",
  notFound: "Citazione non trovata nel testo di legge",
  unverifiedTitle: "Citazioni non verificate",
  unverifiedText: "Verificare quanto segue sul testo di legge prima di farvi affidamento:",
  lawAsOf: (date: string) => `Testo di riferimento: regolamento (UE) 2024/1689, versione consolidata del ${date}.`,
  notAdvice: "La valutazione è generata automaticamente e non costituisce consulenza legale.",
  copyLink: "Copia il link",
  copied: "Link copiato",
  linkWarning: "Chiunque disponga di questo link può consultare la valutazione.",
  newAssessment: "Nuova valutazione",
  failedTitle: "Non è stato possibile completare la valutazione",
  stopped: "Il modello linguistico ha smesso di rispondere. I passaggi completati sono stati salvati.",
  notFoundTitle: "Valutazione non trovata. Potrebbe essere stata eliminata.",
  tryAgain: "Riprova",
  tryAgainIn: (wait: string) => `Riprova tra ${wait}`,
  loading: "Caricamento della valutazione",
  facts: {
    purpose: "la finalità prevista",
    domain: "il settore di utilizzo",
    affected_people: "le persone interessate",
    role: "se l'organizzazione sviluppa o utilizza il sistema",
    real_time: "se l'identificazione avviene in tempo reale",
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
