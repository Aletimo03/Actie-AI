/**
 * The first screen is the tool itself, on the dark hero: a heading, then the description as
 * one composed object (text, examples, send). What it checks sits below.
 */
import { Briefcase, Info, Landmark, MessageSquare } from "lucide-react";
import { useId, useLayoutEffect, useRef, useState } from "react";
import type { Lang } from "@/api/client";
import { STRINGS } from "@/i18n";

const MIN = 20;
const MAX = 4000; // the API's limits (AssessRequest)
const NEAR = MAX * 0.9; // the count only shows from here
const EXAMPLE_ICONS = [Briefcase, MessageSquare, Landmark];

type Props = {
  lang: Lang;
  initial: string;
  error?: string;
  onSubmit: (description: string) => void;
};

export function DescribeForm({ lang, initial, error, onSubmit }: Props) {
  const t = STRINGS[lang];
  const [text, setText] = useState(initial);
  const [touched, setTouched] = useState(false);
  const field = useId();
  const area = useRef<HTMLTextAreaElement>(null);
  const length = text.trim().length;
  const tooShort = length < MIN;
  const message =
    error ?? (touched && tooShort ? t.tooShort(length) : undefined);

  // The field grows with the text (up to half the screen, then it scrolls). Its focus
  // shows on the box around it, so the field draws no outline of its own.
  useLayoutEffect(() => {
    const element = area.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${element.scrollHeight}px`;
  }, [text]);

  return (
    <form
      className="space-y-6"
      onSubmit={(event) => {
        event.preventDefault();
        setTouched(true);
        if (!tooShort) onSubmit(text.trim());
      }}
    >
      <div className="space-y-5">
        <h2 className="max-w-[24ch] text-[2.85rem] leading-[1.05] font-semibold text-balance lg:text-[4rem]">
          {t.headline}
        </h2>
        <p className="max-w-[56ch] text-lg text-primary-foreground/90">
          {t.intro}
        </p>
      </div>

      <div className="max-w-3xl rounded-2xl border border-white/25 bg-[#1b1916]/80 p-6 shadow-[0_20px_60px_-20px_rgba(0,0,0,0.7)] backdrop-blur-md transition-[border-color,box-shadow] duration-200 hover:border-gold-glow/60 hover:shadow-[0_20px_60px_-20px_rgba(0,0,0,0.7),0_0_28px_-6px_rgba(201,160,99,0.4)] focus-within:border-gold focus-within:ring-1 focus-within:ring-gold has-[textarea[aria-invalid=true]]:border-[#ffb4a8] sm:p-7">
        <textarea
          ref={area}
          id={field}
          aria-label={t.description}
          value={text}
          maxLength={MAX}
          placeholder={t.placeholder}
          aria-invalid={Boolean(message)}
          aria-describedby={`${field}-hint ${field}-count`}
          className="block max-h-[50vh] min-h-28 w-full resize-none overflow-y-auto bg-transparent text-lg leading-relaxed text-primary-foreground placeholder:text-primary-foreground/65 focus-visible:outline-none!"
          onChange={(event) => setText(event.target.value)}
        />
        {/* The box holds only what belongs to the text: its length and sending it. */}
        <div className="mt-4 flex items-center justify-between gap-4 border-t border-white/10 pt-4">
          <span
            id={`${field}-count`}
            className="text-sm text-primary-foreground/60 tabular-nums"
          >
            {text.length >= NEAR && `${text.length} / ${MAX}`}
          </span>
          <button
            type="submit"
            className="inline-flex h-11 items-center rounded-full bg-gold px-6 font-semibold text-primary transition-colors hover:bg-[#f0c27a] active:translate-y-px"
          >
            {t.check}
          </button>
        </div>
      </div>

      <div className="max-w-3xl space-y-5 text-[0.95rem]">
        <p
          id={`${field}-hint`}
          className="text-[#ffb4a8] empty:hidden"
          role={message ? "alert" : undefined}
        >
          {message}
        </p>
        {/* Examples on their own row: full-size targets, apart from the send button. */}
        <div
          role="group"
          aria-labelledby={`${field}-examples`}
          className="flex flex-wrap items-center gap-x-2.5 gap-y-3"
        >
          <span
            id={`${field}-examples`}
            className="mr-1.5 text-primary-foreground/70"
          >
            {t.examplesLabel}
          </span>
          {t.examples.map((example, index) => {
            const Icon = EXAMPLE_ICONS[index] ?? Briefcase;
            return (
              <button
                key={example.label}
                type="button"
                className="inline-flex h-11 items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 text-primary-foreground/90 transition-[border-color,box-shadow] duration-200 hover:border-gold-glow/70 hover:shadow-[0_0_18px_-4px_rgba(201,160,99,0.5)]"
                onClick={() => {
                  setText(example.text);
                  area.current?.focus();
                }}
              >
                <Icon
                  aria-hidden
                  className="size-4 text-primary-foreground/70"
                />
                {example.label}
              </button>
            );
          })}
        </div>
        <p className="text-primary-foreground/70">{t.durationHint}</p>
        <p className="flex gap-2 text-primary-foreground/70">
          <Info aria-hidden className="mt-1 size-4 shrink-0 text-gold" />
          {t.aiNotice}
        </p>
      </div>
    </form>
  );
}
