import { expect, it } from "vitest";
import english from "@/locales/en.json";
import italian from "@/locales/it.json";

/** Every text path with its {placeholders}, so the two languages can be compared. */
function shape(value: unknown, path = ""): string[] {
  if (typeof value === "string")
    return [`${path} ${(value.match(/\{\w+\}/g) ?? []).sort().join(" ")}`];
  if (Array.isArray(value))
    return value.flatMap((item, index) => shape(item, `${path}[${index}]`));
  return Object.entries(value as object).flatMap(([key, item]) =>
    shape(item, path ? `${path}.${key}` : key),
  );
}

it("has the same texts and placeholders in English and Italian", () => {
  expect(shape(italian)).toEqual(shape(english));
});
