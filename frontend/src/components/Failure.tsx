import { useEffect, useState } from "react";
import type { Lang } from "@/api/client";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { STRINGS, formatWait } from "@/i18n";
import type { Retry } from "@/state";

type Props = {
  lang: Lang;
  message: string | null;
  retry: Retry;
  retryAfter: number | null;
  onRetry: () => void;
  onNew: () => void;
};

export function Failure({ lang, message, retry, retryAfter, onRetry, onNew }: Props) {
  const t = STRINGS[lang];
  const [wait, setWait] = useState(retryAfter ?? 0);
  useEffect(() => {
    if (wait <= 0) return;
    const timer = setTimeout(() => setWait(wait - 1), 1000);
    return () => clearTimeout(timer);
  }, [wait]);

  const title = retry === "new" ? t.notFoundTitle : t.failedTitle;
  return (
    <div className="space-y-4">
      <Alert variant="destructive">
        <AlertTitle>{title}</AlertTitle>
        <AlertDescription>
          {retry === "continue" && <p>{t.stopped}</p>}
          {message && retry !== "new" && <p>{message}</p>}
        </AlertDescription>
      </Alert>
      <div className="flex gap-3">
        {retry !== "new" && (
          <Button onClick={onRetry} disabled={wait > 0}>
            {wait > 0 ? t.tryAgainIn(formatWait(wait, lang)) : t.tryAgain}
          </Button>
        )}
        <Button variant="outline" onClick={onNew}>
          {t.newAssessment}
        </Button>
      </div>
    </div>
  );
}
