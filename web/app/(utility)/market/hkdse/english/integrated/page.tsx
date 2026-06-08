"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowLeft, Globe, Loader2 } from "lucide-react";
import { apiUrl } from "@/lib/api";

type Stage = "config" | "submitting" | "result" | "error";

const STAGES = [
  { value: "note_making", label: "Note-making" },
  { value: "summary", label: "Summary Writing" },
  { value: "output", label: "Output Text" },
];

const TASK_TYPES = ["letter", "report", "article"];

interface FeedbackResult {
  stage: string;
  feedback: { score: number; max_score: number; comment: string };
  strengths: string[];
  improvements: string[];
  model_answer: string;
}

export default function IntegratedSkillsPage() {
  const [stage, setStage] = useState<Stage>("config");
  const [workStage, setWorkStage] = useState("note_making");
  const [taskType, setTaskType] = useState("letter");
  const [input1, setInput1] = useState("");
  const [input2, setInput2] = useState("");
  const [response, setResponse] = useState("");
  const [result, setResult] = useState<FeedbackResult | null>(null);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    if (!response.trim()) return;
    setError("");
    setStage("submitting");
    try {
      const res = await fetch(apiUrl("/api/v1/hkdse/english/integrated-skills"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stage: workStage, task_type: taskType, input_texts: [input1, input2].filter(Boolean), student_response: response }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setResult(data);
      setStage("result");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Feedback failed");
      setStage("error");
    }
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market/hkdse/english" className="flex items-center gap-1.5 hover:text-[var(--foreground)]"><ArrowLeft size={14} /> English Language</Link>
        <span>/</span><span className="text-[var(--foreground)]">Integrated Skills</span>
      </div>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-violet-500/10"><Globe size={20} className="text-violet-500" /></div>
        <div><h1 className="text-xl font-semibold text-[var(--foreground)]">Integrated Skills Simulator</h1><p className="text-xs text-[var(--muted-foreground)]">HKDSE Paper 3 · Note-making → Summary → Output</p></div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="flex gap-2">
            {STAGES.map((s) => (
              <button key={s.value} onClick={() => setWorkStage(s.value)} className={`rounded-lg border px-4 py-2 text-sm ${workStage === s.value ? "border-violet-500/50 bg-violet-500/10 text-violet-400" : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"}`}>{s.label}</button>
            ))}
          </div>
          {workStage === "output" && (
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">Output Type</label>
              <div className="flex gap-2">
                {TASK_TYPES.map((t) => (
                  <button key={t} onClick={() => setTaskType(t)} className={`rounded-lg border px-3 py-1.5 text-xs capitalize ${taskType === t ? "border-violet-500/50 bg-violet-500/10 text-violet-400" : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"}`}>{t}</button>
                ))}
              </div>
            </div>
          )}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">Input Text 1</label>
            <textarea className="w-full resize-y rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-violet-500/50" rows={4} value={input1} onChange={(e) => setInput1(e.target.value)} placeholder="Paste the first input text..." />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">Input Text 2</label>
            <textarea className="w-full resize-y rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-violet-500/50" rows={4} value={input2} onChange={(e) => setInput2(e.target.value)} placeholder="Paste the second input text..." />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">Your Response</label>
            <textarea className="w-full resize-y rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-3 text-sm text-[var(--foreground)] outline-none focus:border-violet-500/50" rows={6} value={response} onChange={(e) => setResponse(e.target.value)} placeholder={`Write your ${STAGES.find(s => s.value === workStage)?.label} response...`} />
          </div>
          <button onClick={handleSubmit} disabled={!response.trim()} className="flex w-full items-center justify-center gap-2 rounded-lg bg-violet-500 px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40">Get Feedback</button>
        </div>
      )}

      {stage === "submitting" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4"><Loader2 size={36} className="animate-spin text-violet-500" /><p className="text-sm text-[var(--muted-foreground)]">Getting AI feedback...</p></div>
      )}
      {stage === "error" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4"><p className="text-sm text-red-400">{error}</p><button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">Back</button></div>
      )}

      {stage === "result" && result && (
        <div className="max-w-2xl space-y-6">
          <div className="rounded-xl border border-violet-500/20 bg-violet-500/5 p-5">
            <div className="flex items-center justify-between">
              <p className="text-xs text-[var(--muted-foreground)]">Score</p>
              <p className="text-2xl font-bold text-violet-400">{result.feedback.score}<span className="text-base font-normal text-[var(--muted-foreground)]">/{result.feedback.max_score}</span></p>
            </div>
            <p className="mt-2 text-sm text-[var(--foreground)]">{result.feedback.comment}</p>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
              <p className="mb-2 text-xs font-medium text-emerald-400">Strengths</p>
              <ul className="space-y-1">{result.strengths.map((s, i) => <li key={i} className="text-xs text-[var(--foreground)]">{s}</li>)}</ul>
            </div>
            <div className="rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-4">
              <p className="mb-2 text-xs font-medium text-yellow-400">Improvements</p>
              <ul className="space-y-1">{result.improvements.map((s, i) => <li key={i} className="text-xs text-[var(--foreground)]">{s}</li>)}</ul>
            </div>
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
            <p className="mb-2 text-xs font-medium text-[var(--muted-foreground)] uppercase tracking-wide">Model Answer</p>
            <p className="text-sm text-[var(--foreground)] whitespace-pre-wrap">{result.model_answer}</p>
          </div>
          <button onClick={() => { setStage("config"); setResult(null); setResponse(""); }} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">New Submission</button>
        </div>
      )}
    </div>
  );
}
