"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowLeft, FileText, Loader2 } from "lucide-react";
import { gradeEnglishEssay } from "@/lib/market-api";
import type { EnglishEssayRequest } from "@/types/market";
import type { EnglishEssayResult, DimensionScore } from "@/types/market";

type Stage = "config" | "grading" | "result" | "error";

const GENRES = [
  { value: "argument", label: "Argumentative Essay" },
  { value: "letter", label: "Formal Letter" },
  { value: "report", label: "Report" },
  { value: "article", label: "Feature Article" },
];

function scoreColor(s: DimensionScore) {
  const pct = (s.score / s.max_score) * 100;
  return pct >= 80 ? "text-emerald-400" : pct >= 60 ? "text-yellow-400" : "text-red-400";
}

export default function EnglishEssayCoachPage() {
  const [stage, setStage] = useState<Stage>("config");
  const [title, setTitle] = useState("");
  const [essay, setEssay] = useState("");
  const [genre, setGenre] = useState<EnglishEssayRequest["genre"]>("argument");
  const [result, setResult] = useState<EnglishEssayResult | null>(null);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    if (!essay.trim()) return;
    setError("");
    setStage("grading");
    try {
      const res = await gradeEnglishEssay({ title, essay, genre });
      setResult(res);
      setStage("result");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Grading failed");
      setStage("error");
    }
  };

  const totalScoreColor = result
    ? result.percentage >= 80 ? "text-emerald-400" : result.percentage >= 60 ? "text-yellow-400" : "text-red-400"
    : "";
  const totalScoreBg = result
    ? result.percentage >= 80 ? "bg-emerald-500/10 border-emerald-500/30"
      : result.percentage >= 60 ? "bg-yellow-500/10 border-yellow-500/30"
      : "bg-red-500/10 border-red-500/30"
    : "";

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market/hkdse/english" className="flex items-center gap-1.5 transition-colors hover:text-[var(--foreground)]">
          <ArrowLeft size={14} /> English Language
        </Link>
        <span>/</span>
        <span className="text-[var(--foreground)]">Essay Coach</span>
      </div>

      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sky-500/10">
          <FileText size={20} className="text-sky-500" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-[var(--foreground)]">English Essay Coach</h1>
          <p className="text-xs text-[var(--muted-foreground)]">HKDSE Paper 2 · Content / Language / Organisation</p>
        </div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">Genre</label>
            <div className="flex flex-wrap gap-2">
              {GENRES.map((g) => (
                <button key={g.value} onClick={() => setGenre(g.value as EnglishEssayRequest["genre"])}
                  className={`rounded-lg border px-4 py-2 text-sm transition-colors ${
                    genre === g.value ? "border-sky-500/50 bg-sky-500/10 text-sky-400"
                    : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                  }`}>{g.label}</button>
              ))}
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">Topic <span className="text-[var(--muted-foreground)]/50">(optional)</span></label>
            <input className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-sky-500/50 focus:ring-1 focus:ring-sky-500/20"
              value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Should school uniforms be abolished?" />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">Student Essay</label>
            <textarea className="w-full resize-y rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-3 text-sm text-[var(--foreground)] outline-none focus:border-sky-500/50 focus:ring-1 focus:ring-sky-500/20"
              rows={14} value={essay} onChange={(e) => setEssay(e.target.value)} placeholder="Paste the student's full essay here..." />
            <p className="text-right text-[10px] text-[var(--muted-foreground)]/50">{essay.length} chars</p>
          </div>
          <button onClick={handleSubmit} disabled={!essay.trim()}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-sky-500 px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40">
            Grade Essay
          </button>
        </div>
      )}

      {stage === "grading" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <Loader2 size={36} className="animate-spin text-sky-500" />
          <p className="text-sm text-[var(--muted-foreground)]">Grading in progress...</p>
        </div>
      )}

      {stage === "error" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <p className="text-sm text-red-400">{error}</p>
          <button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">Back</button>
        </div>
      )}

      {stage === "result" && result && (
        <div className="max-w-2xl space-y-6">
          <div className={`rounded-xl border p-6 ${totalScoreBg}`}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-[var(--muted-foreground)]">Total Score</p>
                <p className={`mt-1 text-4xl font-bold ${totalScoreColor}`}>{result.total_score}<span className="text-xl font-normal text-[var(--muted-foreground)]">/{result.max_score}</span></p>
                <p className={`mt-0.5 text-sm font-medium ${totalScoreColor}`}>{result.percentage}%</p>
              </div>
              <div className="text-right text-xs text-[var(--muted-foreground)]">
                <p>Content · Language · Organisation</p><p className="mt-1">HKDSE Paper 2</p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            {([{key: "content", label: "Content", full: 7}, {key: "language", label: "Language", full: 7}, {key: "organisation", label: "Organisation", full: 7}] as const).map((dim) => {
              const d = result[dim.key as "content" | "language" | "organisation"];
              return (
                <div key={dim.key} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4 text-center">
                  <p className="text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]/60">{dim.label}</p>
                  <p className={`mt-2 text-2xl font-bold ${scoreColor(d)}`}>{d.score}<span className="text-sm font-normal text-[var(--muted-foreground)]">/{d.max_score}</span></p>
                  <p className="mt-1 text-[11px] leading-relaxed text-[var(--muted-foreground)]">{d.comment}</p>
                </div>
              );
            })}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
              <p className="mb-2 text-xs font-medium text-emerald-400">Strengths</p>
              <ul className="space-y-1.5">{result.strengths.map((s, i) => <li key={i} className="text-xs leading-relaxed text-[var(--foreground)]">{s}</li>)}</ul>
            </div>
            <div className="rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-4">
              <p className="mb-2 text-xs font-medium text-yellow-400">Improvements</p>
              <ul className="space-y-1.5">{result.improvements.map((s, i) => <li key={i} className="text-xs leading-relaxed text-[var(--foreground)]">{s}</li>)}</ul>
            </div>
          </div>

          <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
            <p className="mb-2 text-xs font-medium text-[var(--muted-foreground)] uppercase tracking-wide">Overall Comment</p>
            <p className="text-sm leading-relaxed text-[var(--foreground)]">{result.overall_comment}</p>
          </div>

          <div className="flex gap-3 pt-2">
            <button onClick={() => { setStage("config"); setResult(null); setEssay(""); }} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] transition-colors hover:bg-[var(--background)]">New Essay</button>
            <Link href="/market/hkdse/english" className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] transition-colors hover:bg-[var(--background)]">Back to English</Link>
          </div>
        </div>
      )}
    </div>
  );
}
