import { useEffect, useRef, useState } from "react";
import type { Lang, Question } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { STRINGS } from "@/i18n";

type Props = {
  questions: Question[];
  lang: Lang;
  onSubmit: (answers: Record<string, string>) => void;
  onNew: () => void;
};

export function Questions({ questions, lang, onSubmit, onNew }: Props) {
  const t = STRINGS[lang];
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []); // the page changed under the user: say so

  return (
    <form
      className="space-y-5"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(answers); // left out or blank: the backend skips the question
      }}
    >
      <div>
        <h2 ref={heading} tabIndex={-1} className="text-2xl font-semibold outline-none">
          {t.questionsTitle}
        </h2>
        <p className="max-w-prose text-muted-foreground">{t.questionsIntro}</p>
      </div>
      {questions.map((question) => (
        <div key={question.id} className="space-y-2">
          <Label htmlFor={`q-${question.id}`} className="leading-snug">
            {question.text}
          </Label>
          <Textarea
            id={`q-${question.id}`}
            rows={2}
            maxLength={1000}
            value={answers[question.id] ?? ""}
            onChange={(event) => setAnswers({ ...answers, [question.id]: event.target.value })}
          />
        </div>
      ))}
      <div className="flex flex-wrap gap-3">
        <Button type="submit">{t.continue}</Button>
        <Button type="button" variant="ghost" onClick={onNew}>
          {t.startOver}
        </Button>
      </div>
    </form>
  );
}
