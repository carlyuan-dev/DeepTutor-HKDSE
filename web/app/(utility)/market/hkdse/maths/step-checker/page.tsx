"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowLeft, Calculator, CheckCircle, Loader2, XCircle } from "lucide-react";
import { checkMathSteps } from "@/lib/market-api";
import type { StepCheckResult } from "@/types/market";

type Stage = "config" | "checking" | "result" | "error";

export default function StepCheckerPage() {
  const [stage, setStage] = useState<Stage>("config");
  const [question, setQuestion] = useState("");
  const [stepsText, setStepsText] = useState("");
  const [result, setResult] = useState<StepCheckResult | null>(null);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    const steps = stepsText.split("\n").filter((s) => s.trim());
    if (!question.trim() || steps.length === 0) return;
    setError("");
    setStage("checking");
    try {
      const res = await checkMathSteps({ question, student_steps: steps });
      setResult(res);
      setStage("result");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Check failed");
      setStage("error");
    }
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market/hkdse/maths" className="flex items-center gap-1.5 transition-colors hover:text-[var(--foreground)]"><ArrowLeft size={14} /> Mathematics</Link>
        <span>/</span>
        <span className="text-[var(--foreground)]">Step Checker</span>
      </div>

      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-500/10"><Calculator size={20} className="text-amber-500" /></div>
        <div>
          <h1 className="text-xl font-semibold text-[var(--foreground)]">Step-by-Step Solution Checker</h1>
          <p className="text-xs text-[var(--muted-foreground)]">HKDSE Mathematics · 逐行檢查解題步驟</p>
        </div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">Question</label>
            <textarea className="w-full resize-y rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-amber-500/50" rows={3}
              value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="e.g. Find the vertex of y = x² + 6x + 8" />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">Student's Steps <span className="text-[var(--muted-foreground)]/50">(one per line)</span></label>
            <textarea className="w-full resize-y rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-3 text-sm text-[var(--foreground)] outline-none focus:border-amber-500/50 font-mono" rows={8}
              value={stepsText} onChange={(e) => setStepsText(e.target.value)} placeholder={"Step 1: y = x² + 6x + 8\nStep 2: x = -6/2 = -3\nStep 3: y = (-3)² + 6(-3) + 8 = 9 - 18 + 8 = -1\nStep 4: vertex is (-3, -1)"} />
          </div>
          <button onClick={handleSubmit} disabled={!question.trim() || !stepsText.trim()} className="flex w-full items-center justify-center gap-2 rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40">
            Check Steps
          </button>
        </div>
      )}

      {stage === "checking" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4"><Loader2 size={36} className="animate-spin text-amber-500" /><p className="text-sm text-[var(--muted-foreground)]">Checking each step...</p></div>
      )}

      {stage === "error" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <p className="text-sm text-red-400">{error}</p>
          <button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">Back</button>
        </div>
      )}

      {stage === "result" && result && (
        <div className="max-w-2xl space-y-6">
          {/* Overall verdict */}
          <div className={`rounded-xl border p-5 ${result.overall_correct ? "bg-emerald-500/10 border-emerald-500/30" : "bg-red-500/10 border-red-500/30"}`}>
            <div className="flex items-center gap-3">
              {result.overall_correct ? <CheckCircle size={24} className="text-emerald-400" /> : <XCircle size={24} className="text-red-400" />}
              <div>
                <p className={`text-lg font-semibold ${result.overall_correct ? "text-emerald-400" : "text-red-400"}`}>
                  {result.overall_correct ? "All Correct!" : `Error at Step ${(result.first_error_index ?? 0) + 1}`}
                </p>
                <p className="text-xs text-[var(--muted-foreground)]">{result.summary}</p>
              </div>
            </div>
          </div>

          {/* Step-by-step */}
          <div className="space-y-3">
            <p className="text-xs font-medium uppercase tracking-wide text-[var(--muted-foreground)]">Step-by-Step Analysis</p>
            {result.steps.map((step) => (
              <div key={step.step_index} className={`rounded-xl border p-4 ${step.is_correct ? "border-emerald-500/20 bg-emerald-500/5" : "border-red-500/20 bg-red-500/5"}`}>
                <div className="flex items-start gap-3">
                  {step.is_correct ? <CheckCircle size={16} className="mt-0.5 shrink-0 text-emerald-400" /> : <XCircle size={16} className="mt-0.5 shrink-0 text-red-400" />}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-medium text-[var(--muted-foreground)]">Step {step.step_index + 1}</p>
                      <span className={`text-xs font-medium ${step.is_correct ? "text-emerald-400" : "text-red-400"}`}>{step.is_correct ? "✓ Correct" : "✗ Incorrect"}</span>
                    </div>
                    <p className="mt-1 text-sm font-mono text-[var(--foreground)]">{step.student_step}</p>
                    <p className="mt-1 text-xs text-[var(--muted-foreground)]">{step.comment}</p>
                    {step.corrected_step && (
                      <p className="mt-1 rounded bg-amber-500/10 px-2 py-1 text-xs font-mono text-amber-400">
                        Correct: {step.corrected_step}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Full solution */}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
            <p className="mb-2 text-xs font-medium text-[var(--muted-foreground)] uppercase tracking-wide">Full Correct Solution</p>
            <pre className="text-sm text-[var(--foreground)] whitespace-pre-wrap font-mono leading-relaxed">{result.full_solution}</pre>
          </div>

          <div className="flex gap-3 pt-2">
            <button onClick={() => { setStage("config"); setResult(null); setStepsText(""); }} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">Check Another</button>
            <Link href="/market/hkdse/maths" className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">Back to Maths</Link>
          </div>
        </div>
      )}
    </div>
  );
}
