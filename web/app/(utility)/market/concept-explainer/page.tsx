"use client";

import Link from "next/link";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Lightbulb, Loader2 } from "lucide-react";
import { apiUrl } from "@/lib/api";

type Stage = "config" | "generating" | "result" | "error";

interface ConceptResult {
  concept: string;
  summary: string;
  analogy: string;
  key_points: string[];
  worked_example: string;
  common_mistakes: string[];
  check_question: string;
  grounded?: boolean;
}

export default function ConceptExplainerPage() {
  const { t, i18n } = useTranslation();
  const [stage, setStage] = useState<Stage>("config");
  const [concept, setConcept] = useState("");
  const [subject, setSubject] = useState("");
  const [kb, setKb] = useState("");
  const [result, setResult] = useState<ConceptResult | null>(null);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!concept.trim()) return;
    setError("");
    setStage("generating");
    try {
      const res = await fetch(apiUrl("/api/v1/market-tools/concept-explainer"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ concept, subject, kb_name: kb || undefined, language: i18n.language }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setResult(data);
      setStage("result");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("Generation failed"));
      setStage("error");
    }
  };

  const Block = ({ title, children }: { title: string; children: React.ReactNode }) => (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">{title}</p>
      {children}
    </div>
  );

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market" className="flex items-center gap-1.5 hover:text-[var(--foreground)]">
          <ArrowLeft size={14} /> {t("Market")}
        </Link>
        <span>/</span>
        <span className="text-[var(--foreground)]">{t("Concept Explainer")}</span>
      </div>

      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-yellow-500/10">
          <Lightbulb size={20} className="text-yellow-500" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-[var(--foreground)]">{t("Concept Explainer")}</h1>
          <p className="text-xs text-[var(--muted-foreground)]">{t("Understand any concept with analogies, examples, and pitfalls")}</p>
        </div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Concept")}</label>
            <input value={concept} onChange={(e) => setConcept(e.target.value)}
              placeholder={t("e.g. Conditional probability")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <div className="flex gap-4">
            <div className="flex-1 space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Subject (optional)")}</label>
              <input value={subject} onChange={(e) => setSubject(e.target.value)}
                placeholder={t("e.g. Mathematics")}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
            </div>
            <div className="flex-1 space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Knowledge Base (optional)")}</label>
              <input value={kb} onChange={(e) => setKb(e.target.value)}
                placeholder={t("e.g. hkdse-math")}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
            </div>
          </div>
          <button onClick={submit} className="flex w-full items-center justify-center gap-2 rounded-lg bg-yellow-500 px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90">
            {t("Explain")}
          </button>
        </div>
      )}

      {stage === "generating" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <Loader2 size={36} className="animate-spin text-yellow-500" />
          <p className="text-sm text-[var(--muted-foreground)]">{t("Thinking it through...")}</p>
        </div>
      )}

      {stage === "error" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <p className="text-sm text-red-400">{error}</p>
          <button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">{t("Back")}</button>
        </div>
      )}

      {stage === "result" && result && (
        <div className="max-w-3xl space-y-4">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-[var(--foreground)]">{result.concept}</h2>
            {result.grounded && (
              <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-400">{t("Grounded in knowledge base")}</span>
            )}
          </div>
          <Block title={t("Summary")}><p className="text-sm text-[var(--foreground)]">{result.summary}</p></Block>
          {result.analogy && <Block title={t("Analogy")}><p className="text-sm text-[var(--muted-foreground)]">{result.analogy}</p></Block>}
          {result.key_points?.length > 0 && (
            <Block title={t("Key Points")}>
              <ul className="list-disc space-y-1 pl-4 text-sm text-[var(--muted-foreground)]">
                {result.key_points.map((p, i) => (<li key={i}>{p}</li>))}
              </ul>
            </Block>
          )}
          {result.worked_example && (
            <Block title={t("Worked Example")}>
              <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-[var(--foreground)]">{result.worked_example}</pre>
            </Block>
          )}
          {result.common_mistakes?.length > 0 && (
            <Block title={t("Common Mistakes")}>
              <ul className="list-disc space-y-1 pl-4 text-sm text-[var(--muted-foreground)]">
                {result.common_mistakes.map((m, i) => (<li key={i}>{m}</li>))}
              </ul>
            </Block>
          )}
          {result.check_question && (
            <Block title={t("Quick Check")}><p className="text-sm text-[var(--foreground)]">{result.check_question}</p></Block>
          )}
          <button onClick={() => { setStage("config"); setResult(null); }} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">
            {t("Explain Another")}
          </button>
        </div>
      )}
    </div>
  );
}
