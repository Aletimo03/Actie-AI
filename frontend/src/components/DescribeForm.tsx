import { useId, useState } from "react";
import type { Lang } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { STRINGS } from "@/i18n";

const MIN = 20;
const MAX = 4000; // the API's limits (AssessRequest)

type Props = {
  lang: Lang;
  onLang: (lang: Lang) => void;
  initial: string;
  error?: string;
  onSubmit: (description: string) => void;
};

export function DescribeForm({ lang, onLang, initial, error, onSubmit }: Props) {
  const t = STRINGS[lang];
  const [text, setText] = useState(initial);
  const [touched, setTouched] = useState(false);
  const field = useId();
  const length = text.trim().length;
  const tooShort = length < MIN;
  const message = error ?? (touched && tooShort ? t.tooShort(length) : undefined);

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        setTouched(true);
        if (!tooShort) onSubmit(text.trim());
      }}
    >
      <p className="text-muted-foreground">{t.intro}</p>
      <div className="space-y-2">
        <Label htmlFor={field}>{t.description}</Label>
        <Textarea
          id={field}
          value={text}
          maxLength={MAX}
          rows={7}
          placeholder={t.placeholder}
          aria-invalid={Boolean(message)}
          aria-describedby={`${field}-hint`}
          onChange={(event) => setText(event.target.value)}
        />
        <div id={`${field}-hint`} className="flex justify-between text-sm">
          <span className="text-destructive" role={message ? "alert" : undefined}>
            {message}
          </span>
          <span className="text-muted-foreground tabular-nums">
            {text.length}/{MAX}
          </span>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <fieldset className="flex items-center gap-2 text-sm">
          <legend className="sr-only">{t.language}</legend>
          {(["en", "it"] as const).map((option) => (
            <Button
              key={option}
              type="button"
              size="sm"
              variant={option === lang ? "secondary" : "ghost"}
              aria-pressed={option === lang}
              onClick={() => onLang(option)}
            >
              {option === "en" ? "English" : "Italiano"}
            </Button>
          ))}
        </fieldset>
        <Button type="submit">{t.check}</Button>
      </div>
    </form>
  );
}
