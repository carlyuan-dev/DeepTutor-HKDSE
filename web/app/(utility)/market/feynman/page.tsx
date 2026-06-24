"use client";

import Link from "next/link";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, GraduationCap, Loader2 } from "lucide-react";
import { apiUrl } from "@/lib/api";

type Stage = "config" | "loading" | "result" | "error";
interface Result { score: number; understood: string[]; gaps: string[]; feedback: string; follow_up_question: string; }

export default function FeynmanPage() {
  const { t, i18n } = useTranslation();
  const [stage, setStage] = useState<Stage>("config");
  const [concept, setConcept] = useState("");
  const [explanation, setExplanation] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!concept.trim() || !explanation.trim()) return;
    setError(""); setStage("loading");
    try {
      const res = await fetch(apiUrl("/api/v1/market-tools/feynman"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ concept, explanation, language: i18n.language }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setResult(data); setStage("result");
    } catch (e: unknown) { setError(e instanceof Error ? e.message : t("Generation failed")); setStage("error"); }
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market" className="flex items-center gap-1.5 hover:text-[var(--foreground)]"><ArrowLeft size={14} /> {t("Market")}</Link>
        <span>/</span><span className="text-[var(--foreground)]">{t("Feynman Self-Check")}</span>
      </div>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-violet-500/10"><GraduationCap size={20} className="text-violet-500" /></div>
        <div><h1 className="text-xl font-semibold text-[var(--foreground)]">{t("Feynman Self-Check")}</h1><p className="text-xs text-[var(--muted-foreground)]">{t("Explain it in your own words — find the gaps")}</p></div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Concept")}</label>
            <input value={concept} onChange={(e) => setConcept(e.target.value)} placeholder={t("e.g. Newton's Second Law")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Explain it in your own words")}</label>
            <textarea value={explanation} onChange={(e) => setExplanation(e.target.value)} rows={6} placeholder={t("Pretend you're teaching it to a younger student...")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <button onClick={submit} className="flex w-full items-center justify-center gap-2 rounded-lg bg-violet-500 px-4 py-2.5 text-sm font-medium text-white hover:opacity-90">{t("Check My Understanding")}</button>
        </div>
      )}
      {stage === "loading" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><Loader2 size={36} className="animate-spin text-violet-500" /><p className="text-sm text-[var(--muted-foreground)]">{t("Evaluating your explanation...")}</p></div>)}
      {stage === "error" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><p className="text-sm text-red-400">{error}</p><button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">{t("Back")}</button></div>)}
      {stage === "result" && result && (
        <div className="max-w-2xl space-y-4">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5 text-center">
            <p className="text-3xl font-bold text-[var(--foreground)]">{result.score}<span className="text-base text-[var(--muted-foreground)]">/100</span></p>
            <p className="text-xs text-[var(--muted-foreground)]">{t("Understanding score")}</p>
          </div>
          {result.understood?.length > 0 && <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4"><p className="mb-1 text-xs font-semibold text-emerald-400">{t("You understood")}</p><ul className="list-disc space-y-1 pl-4 text-sm text-[var(--foreground)]">{result.understood.map((x, i) => (<li key={i}>{x}</li>))}</ul></div>}
          {result.gaps?.length > 0 && <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4"><p className="mb-1 text-xs font-semibold text-amber-400">{t("Gaps to address")}</p><ul className="list-disc space-y-1 pl-4 text-sm text-[var(--foreground)]">{result.gaps.map((x, i) => (<li key={i}>{x}</li>))}</ul></div>}
          {result.feedback && <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4"><p className="text-sm text-[var(--foreground)]">{result.feedback}</p></div>}
          {result.follow_up_question && <div className="rounded-xl border border-violet-500/30 bg-violet-500/5 p-4"><p className="text-xs font-semibold text-violet-400">{t("Try this next")}</p><p className="mt-1 text-sm text-[var(--foreground)]">{result.follow_up_question}</p></div>}
          <button onClick={() => { setStage("config"); setResult(null); }} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">{t("Try Again")}</button>
        </div>
      )}
    </div>
  );
}
