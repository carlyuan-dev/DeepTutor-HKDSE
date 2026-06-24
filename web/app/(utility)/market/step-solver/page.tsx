"use client";

import Link from "next/link";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, ListChecks, Loader2 } from "lucide-react";
import { apiUrl } from "@/lib/api";

type Stage = "config" | "loading" | "result" | "error";
interface Step { step: string; detail: string; }
interface Result { key_idea: string; steps: Step[]; final_answer: string; common_pitfall: string; }

export default function StepSolverPage() {
  const { t, i18n } = useTranslation();
  const [stage, setStage] = useState<Stage>("config");
  const [problem, setProblem] = useState("");
  const [subject, setSubject] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!problem.trim()) return;
    setError(""); setStage("loading");
    try {
      const res = await fetch(apiUrl("/api/v1/market-tools/step-solver"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ problem, subject, language: i18n.language }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setResult(data); setStage("result");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("Generation failed")); setStage("error");
    }
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market" className="flex items-center gap-1.5 hover:text-[var(--foreground)]"><ArrowLeft size={14} /> {t("Market")}</Link>
        <span>/</span><span className="text-[var(--foreground)]">{t("Step Solver")}</span>
      </div>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-500/10"><ListChecks size={20} className="text-cyan-500" /></div>
        <div><h1 className="text-xl font-semibold text-[var(--foreground)]">{t("Step Solver")}</h1><p className="text-xs text-[var(--muted-foreground)]">{t("See any problem solved step by step")}</p></div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Subject (optional)")}</label>
            <input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder={t("e.g. Mathematics")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Problem")}</label>
            <textarea value={problem} onChange={(e) => setProblem(e.target.value)} rows={4} placeholder={t("Paste the problem you want solved...")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <button onClick={submit} className="flex w-full items-center justify-center gap-2 rounded-lg bg-cyan-500 px-4 py-2.5 text-sm font-medium text-white hover:opacity-90">{t("Solve")}</button>
        </div>
      )}
      {stage === "loading" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><Loader2 size={36} className="animate-spin text-cyan-500" /><p className="text-sm text-[var(--muted-foreground)]">{t("Working through it...")}</p></div>)}
      {stage === "error" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><p className="text-sm text-red-400">{error}</p><button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">{t("Back")}</button></div>)}
      {stage === "result" && result && (
        <div className="max-w-2xl space-y-4">
          {result.key_idea && <div className="rounded-xl border border-cyan-500/30 bg-cyan-500/5 p-4"><p className="text-xs font-semibold text-cyan-400">{t("Key Idea")}</p><p className="mt-1 text-sm text-[var(--foreground)]">{result.key_idea}</p></div>}
          <ol className="space-y-3">
            {(result.steps || []).map((s, i) => (
              <li key={i} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-cyan-500/10 text-xs font-semibold text-cyan-400">{i + 1}</span>
                  <div><p className="text-sm font-medium text-[var(--foreground)]">{s.step}</p><p className="mt-1 text-xs text-[var(--muted-foreground)] whitespace-pre-wrap">{s.detail}</p></div>
                </div>
              </li>
            ))}
          </ol>
          {result.final_answer && <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4"><p className="text-xs font-semibold text-emerald-400">{t("Final Answer")}</p><p className="mt-1 text-sm text-[var(--foreground)]">{result.final_answer}</p></div>}
          {result.common_pitfall && <p className="text-xs text-[var(--muted-foreground)]">⚠️ {result.common_pitfall}</p>}
          <button onClick={() => { setStage("config"); setResult(null); }} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">{t("Solve Another")}</button>
        </div>
      )}
    </div>
  );
}
