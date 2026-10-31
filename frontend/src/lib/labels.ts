/** Readable names for the law's chunk ids: "en_art5_p1_c" -> "Art. 5(1)(c)". */
import type { Lang } from "@/api/client";

const ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII"];
const WORDS = {
  en: { annex: "Annex", section: "Section", recital: "Recital" },
  it: { annex: "Allegato", section: "Sezione", recital: "Considerando" },
};

export function chunkLabel(id: string, lang: Lang): string {
  const words = WORDS[lang];
  const [, ...parts] = id.split("_"); // drop the language prefix
  const head = parts.shift() ?? "";
  const points = (rest: string[]) => rest.map((p) => `(${p.replace(/^p/, "")})`).join("");

  let match: RegExpMatchArray | null;
  if ((match = head.match(/^art(\w+)$/))) return `Art. ${match[1]}${points(parts)}`;
  if ((match = head.match(/^rec(\d+)$/))) return `${words.recital} ${match[1]}`;
  if ((match = head.match(/^annex(\d+)$/))) {
    const label = [`${words.annex} ${ROMAN[Number(match[1])] ?? match[1]}`];
    if (parts[0]?.startsWith("sec")) {
      label.push(`${words.section} ${parts.shift()!.slice(3).toUpperCase()}`);
    }
    const [point, ...sub] = parts;
    return point ? `${label.join(", ")}, ${point}${points(sub)}` : label.join(", ");
  }
  return id;
}

const SITUATIONS = new Set([
  "interacts", "synthetic_content", "emotion_or_biometric", "deepfake", "public_interest_text",
]);

/** The report's `uncertain` names, which come from different checks. */
export function uncertainLabel(name: string, lang: Lang): string {
  if (/^[a-h]$|^b[ab]$/.test(name)) return `Art. 5(1)(${name})`;
  if (SITUATIONS.has(name)) return `Art. 50 (${name.replaceAll("_", " ")})`;
  const known: Record<string, string> = {
    annex_i: lang === "it" ? "Allegato I" : "Annex I",
    annex_iii: lang === "it" ? "Allegato III" : "Annex III",
    exception: "Art. 6(3)",
    profiling: "Art. 6(3)",
    influence: "Art. 6(3)",
    art25: "Art. 25",
  };
  return known[name] ?? name;
}
