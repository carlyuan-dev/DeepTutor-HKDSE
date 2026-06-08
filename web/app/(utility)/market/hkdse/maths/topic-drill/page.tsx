"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowLeft, Calculator, Loader2 } from "lucide-react";
import { apiUrl } from "@/lib/api";

type Stage = "config" | "generating" | "result" | "error";

const TOPICS = [
  "Quadratic Equations", "Quadratic Functions", "Exponential & Logarithmic Functions",
  "Polynomials", "Sequences (AS & GS)", "Trigonometry", "Coordinate Geometry",
  "Equations of Circles", "Probability", "Statistics", "Differentiation", "Integration",
];

const DIFFICULTIES = [
  { value: "basic", label: "Basic" },
  { value: "applied", label: "Applied" },
  { value: "challenge", label: "Challenge" },
];

interface DrillQuestion { id: string; question: string; answer: string; worked_solution: string; tips: string; }

interface DrillResult { topic: string; difficulty: string; questions: DrillQuestion[]; }

export default function TopicDrillPage() {
  const [stage, setStage] = useState<Stage>("config");
  const [topic, setTopic] = useState(TOPICS[0]);
  const [difficulty, setDifficulty] = useState("basic");
  const [numQuestions, setNumQuestions] = useState(5);
  const [result, setResult] = useState<DrillResult | null>(null);
  const [error, setError] = useState("");
  const [showSolution, setShowSolution] = useState<Record<string, boolean>>({});

  const handleSubmit = async () => {
    setError("");
    setStage("generating");
    try {
      const res = await fetch(apiUrl("/api/v1/hkdse/maths/topic-drill"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, difficulty, num_questions: numQuestions }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setResult(data);
      setStage("result");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Generation failed");
      setStage("error");
    }
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market/hkdse/maths" className="flex items-center gap-1.5 hover:text-[var(--foreground)]"><ArrowLeft size={14} /> Mathematics</Link>
        <span>/</span><span className="text-[var(--foreground)]">Topic Drill</span>
      </div>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-500/10"><Calculator size={20} className="text-amber-500" /></div>
        <div><h1 className="text-xl font-semibold text-[var(--foreground)]">Topic Drill</h1><p className="text-xs text-[var(--muted-foreground)]">HKDSE Mathematics · 專題練習</p></div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">Topic</label>
            <select className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" value={topic} onChange={(e) => setTopic(e.target.value)}>
              {TOPICS.map((t) => (<option key={t} value={t}>{t}</option>))}
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">Difficulty</label>
            <div className="flex gap-2">
              {DIFFICULTIES.map((d) => (
                <button key={d.value} onClick={() => setDifficulty(d.value)} className={`rounded-lg border px-4 py-2 text-sm ${difficulty === d.value ? "border-amber-500/50 bg-amber-500/10 text-amber-400" : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"}`}>{d.label}</button>
              ))}
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">Number of Questions</label>
            <input type="number" min={5} max={15} className="w-32 rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" value={numQuestions} onChange={(e) => setNumQuestions(Math.max(5, Math.min(15, Number(e.target.value))))} />
          </div>
          <button onClick={handleSubmit} className="flex w-full items-center justify-center gap-2 rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90">Generate Questions</button>
        </div>
      )}

      {stage === "generating" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4"><Loader2 size={36} className="animate-spin text-amber-500" /><p className="text-sm text-[var(--muted-foreground)]">Generating practice questions...</p></div>
      )}
      {stage === "error" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4"><p className="text-sm text-red-400">{error}</p><button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">Back</button></div>
      )}

      {stage === "result" && result && (
        <div className="max-w-2xl space-y-6">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
            <p className="text-sm font-semibold text-[var(--foreground)]">{result.topic} · {result.difficulty}</p>
            <p className="text-xs text-[var(--muted-foreground)]">{result.questions.length} questions</p>
          </div>
          {result.questions.map((q, idx) => (
            <div key={q.id} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--background)] text-xs font-medium text-[var(--foreground)]">{idx + 1}</span>
                <div className="flex-1">
                  <p className="text-sm text-[var(--foreground)]">{q.question}</p>
                  <p className="mt-1 text-xs font-medium text-amber-400">Answer: {q.answer}</p>
                  {q.tips && <p className="mt-1 text-xs text-[var(--muted-foreground)]">💡 {q.tips}</p>}
                  <button onClick={() => setShowSolution((p) => ({ ...p, [q.id]: !p[q.id] }))}
                    className="mt-2 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
                    {showSolution[q.id] ? "Hide" : "Show"} Worked Solution
                  </button>
                  {showSolution[q.id] && (
                    <pre className="mt-2 rounded-lg bg-[var(--background)] p-3 text-xs text-[var(--foreground)] whitespace-pre-wrap font-mono leading-relaxed">{q.worked_solution}</pre>
                  )}
                </div>
              </div>
            </div>
          ))}
          <button onClick={() => { setStage("config"); setResult(null); }} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">New Drill</button>
        </div>
      )}
    </div>
  );
}
