"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  ClipboardCheck,
  Layers,
  Loader2,
  XCircle,
} from "lucide-react";
import { gradeSubmission } from "@/lib/market-api";
import type { ExamPaper, GradeResult, StudentAnswers } from "@/types/market";
import { STORAGE_KEYS } from "@/types/market";

type Stage = "loading" | "grading" | "result" | "error";

export default function ExamGraderPage() {
  const router = useRouter();
  const [stage, setStage] = useState<Stage>("loading");
  const [paper, setPaper] = useState<ExamPaper | null>(null);
  const [answers, setAnswers] = useState<StudentAnswers>({});
  const [result, setResult] = useState<GradeResult | null>(null);
  const [error, setError] = useState("");

  // Load paper + answers from localStorage, then auto-grade
  useEffect(() => {
    const rawPaper = localStorage.getItem(STORAGE_KEYS.paper);
    const rawAnswers = localStorage.getItem(STORAGE_KEYS.answers);
    if (!rawPaper || !rawAnswers) {
      setError("No submission found. Please go back to PaperForge.");
      setStage("error");
      return;
    }
    try {
      const p: ExamPaper = JSON.parse(rawPaper);
      const a: StudentAnswers = JSON.parse(rawAnswers);
      setPaper(p);
      setAnswers(a);
      setStage("grading");
      gradeSubmission(p.questions, a)
        .then((res) => {
          setResult(res);
          localStorage.setItem(STORAGE_KEYS.result, JSON.stringify(res));
          if (res.weak_topics?.length) {
            localStorage.setItem(STORAGE_KEYS.weakTopics, JSON.stringify(res.weak_topics));
          }
          setStage("result");
        })
        .catch((e: unknown) => {
          setError(e instanceof Error ? e.message : "Grading failed");
          setStage("error");
        });
    } catch {
      setError("Failed to parse submission data.");
      setStage("error");
    }
  }, []);

  const goFlashDeck = () => router.push("/market/flash-deck");
  const goRetake = () => router.push("/market/paper-forge");

  // ── Helpers ───────────────────────────────────────────────────────────────

  const scoreColor = (pct: number) =>
    pct >= 80 ? "text-emerald-400" : pct >= 60 ? "text-yellow-400" : "text-red-400";

  const scoreBg = (pct: number) =>
    pct >= 80 ? "bg-emerald-500/10 border-emerald-500/30" : pct >= 60 ? "bg-yellow-500/10 border-yellow-500/30" : "bg-red-500/10 border-red-500/30";

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      {/* Breadcrumb */}
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market" className="flex items-center gap-1.5 transition-colors hover:text-[var(--foreground)]">
          <ArrowLeft size={14} />
          Market
        </Link>
        <span>/</span>
        <span className="text-[var(--foreground)]">ExamGrader</span>
      </div>

      {/* Header */}
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-500/10">
          <ClipboardCheck size={20} className="text-emerald-500" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-[var(--foreground)]">ExamGrader</h1>
          <p className="text-xs text-[var(--muted-foreground)]">AI-powered grading with detailed feedback</p>
        </div>
      </div>

      {/* ── Grading stage ── */}
      {stage === "grading" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <Loader2 size={36} className="animate-spin text-emerald-500" />
          <p className="text-sm text-[var(--muted-foreground)]">Grading your answers...</p>
        </div>
      )}

      {/* ── Error stage ── */}
      {stage === "error" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <p className="text-sm text-red-400">{error}</p>
          <Link href="/market/paper-forge" className="flex items-center gap-1.5 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
            <ArrowLeft size={14} />
            Back to PaperForge
          </Link>
        </div>
      )}

      {/* ── Result stage ── */}
      {stage === "result" && result && paper && (
        <div className="max-w-2xl space-y-6">
          {/* Score card */}
          <div className={`rounded-xl border p-6 ${scoreBg(result.percentage)}`}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-[var(--muted-foreground)]">Total Score</p>
                <p className={`mt-1 text-4xl font-bold ${scoreColor(result.percentage)}`}>
                  {result.total_score}
                  <span className="text-xl font-normal text-[var(--muted-foreground)]">/{result.max_score}</span>
                </p>
                <p className={`mt-0.5 text-sm font-medium ${scoreColor(result.percentage)}`}>
                  {result.percentage}%
                </p>
              </div>
              <div className="text-right">
                <p className="text-xs text-[var(--muted-foreground)]">{paper.title}</p>
                <p className="mt-1 text-sm text-[var(--foreground)]">{paper.questions.length} questions</p>
              </div>
            </div>
            {result.summary && (
              <p className="mt-4 border-t border-[var(--border)]/30 pt-4 text-sm text-[var(--muted-foreground)]">
                {result.summary}
              </p>
            )}
          </div>

          {/* Weak topics */}
          {result.weak_topics?.length > 0 && (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
              <p className="mb-3 text-xs font-medium text-[var(--muted-foreground)] uppercase tracking-wide">Weak Areas to Review</p>
              <div className="flex flex-wrap gap-2">
                {result.weak_topics.map((t) => (
                  <span key={t} className="rounded-full border border-yellow-500/30 bg-yellow-500/10 px-3 py-1 text-xs text-yellow-400">
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Per-question feedback */}
          <div className="space-y-3">
            <p className="text-xs font-medium uppercase tracking-wide text-[var(--muted-foreground)]">Question Feedback</p>
            {result.results.map((fb, idx) => {
              const q = paper.questions.find((x) => x.id === fb.question_id);
              const studentAns = answers[fb.question_id] || "(no answer)";
              return (
                <div key={fb.question_id} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
                  <div className="flex items-start gap-3">
                    {fb.is_correct ? (
                      <CheckCircle size={16} className="mt-0.5 shrink-0 text-emerald-400" />
                    ) : (
                      <XCircle size={16} className="mt-0.5 shrink-0 text-red-400" />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-xs text-[var(--muted-foreground)]">Q{idx + 1} · {q?.topic}</p>
                        <span className={`shrink-0 text-xs font-medium ${fb.score >= fb.max_score ? "text-emerald-400" : fb.score > 0 ? "text-yellow-400" : "text-red-400"}`}>
                          {fb.score}/{fb.max_score} pts
                        </span>
                      </div>
                      {q && <p className="mt-1 text-sm text-[var(--foreground)]">{q.question}</p>}
                      <div className="mt-2 space-y-1 text-xs">
                        <p className="text-[var(--muted-foreground)]">
                          <span className="font-medium">Your answer: </span>{studentAns}
                        </p>
                        {!fb.is_correct && (
                          <p className="text-[var(--muted-foreground)]">
                            <span className="font-medium">Correct: </span>{fb.correct_answer}
                          </p>
                        )}
                        {fb.comment && (
                          <p className="text-[var(--muted-foreground)]/80 italic">{fb.comment}</p>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Action bar */}
          <div className="flex flex-wrap gap-3 pt-2">
            {result.weak_topics?.length > 0 && (
              <button
                onClick={goFlashDeck}
                className="flex items-center gap-2 rounded-lg bg-purple-500 px-5 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90"
              >
                <Layers size={15} />
                Review with FlashDeck
                <ArrowRight size={14} />
              </button>
            )}
            <button
              onClick={goRetake}
              className="flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] transition-colors hover:bg-[var(--background)]"
            >
              Retake Exam
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
