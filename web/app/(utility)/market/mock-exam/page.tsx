"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Timer, Loader2 } from "lucide-react";
import { generatePaper, gradeSubmission } from "@/lib/market-api";
import type { ExamPaper, GradeResult, StudentAnswers } from "@/types/market";

type Stage = "config" | "generating" | "exam" | "grading" | "result" | "error";

function fmt(sec: number) {
  const m = Math.floor(sec / 60).toString().padStart(2, "0");
  const s = (sec % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

export default function MockExamPage() {
  const { t, i18n } = useTranslation();
  const [stage, setStage] = useState<Stage>("config");
  const [kb, setKb] = useState("");
  const [title, setTitle] = useState("");
  const [topic, setTopic] = useState("");
  const [num, setNum] = useState(8);
  const [minutes, setMinutes] = useState(20);
  const [progress, setProgress] = useState("");
  const [paper, setPaper] = useState<ExamPaper | null>(null);
  const [answers, setAnswers] = useState<StudentAnswers>({});
  const [result, setResult] = useState<GradeResult | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [error, setError] = useState("");
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopTimer = () => { if (timerRef.current) clearInterval(timerRef.current); timerRef.current = null; };
  useEffect(() => () => stopTimer(), []);

  const start = async () => {
    setError(""); setStage("generating"); setProgress("");
    try {
      const p = await generatePaper(
        { kb_name: kb || undefined, title: title || "Mock Exam", topic_focus: topic, num_questions: num,
          question_types: ["mcq", "short_answer"], difficulty: "medium" },
        (m) => setProgress(m)
      );
      setPaper(p); setAnswers({}); setStage("exam");
      setRemaining(minutes * 60);
      stopTimer();
      timerRef.current = setInterval(() => {
        setRemaining((r) => {
          if (r <= 1) { stopTimer(); void submit(p, {}); return 0; }
          return r - 1;
        });
      }, 1000);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : t("Generation failed")); setStage("error"); }
  };

  const submit = async (p?: ExamPaper, forcedAnswers?: StudentAnswers) => {
    stopTimer();
    const usePaper = p || paper;
    if (!usePaper) return;
    setStage("grading");
    try {
      const res = await gradeSubmission(usePaper.questions, forcedAnswers && Object.keys(forcedAnswers).length ? forcedAnswers : answers);
      setResult(res); setStage("result");
    } catch (e: unknown) { setError(e instanceof Error ? e.message : t("Grading failed")); setStage("error"); }
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market" className="flex items-center gap-1.5 hover:text-[var(--foreground)]"><ArrowLeft size={14} /> {t("Market")}</Link>
        <span>/</span><span className="text-[var(--foreground)]">{t("Timed Mock Exam")}</span>
      </div>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-red-500/10"><Timer size={20} className="text-red-500" /></div>
        <div><h1 className="text-xl font-semibold text-[var(--foreground)]">{t("Timed Mock Exam")}</h1><p className="text-xs text-[var(--muted-foreground)]">{t("Simulate real exam pressure, then get graded")}</p></div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="flex gap-4">
            <div className="flex-1 space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Exam title (optional)")}</label>
              <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t("e.g. Maths Mock")}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
            </div>
            <div className="flex-1 space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Knowledge Base (optional)")}</label>
              <input value={kb} onChange={(e) => setKb(e.target.value)} placeholder={t("e.g. hkdse-math")}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Topic focus (optional)")}</label>
            <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder={t("e.g. Algebra")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <div className="flex gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Number of Questions")}</label>
              <input type="number" min={4} max={20} value={num} onChange={(e) => setNum(Math.max(4, Math.min(20, Number(e.target.value))))}
                className="w-32 rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Time limit (minutes)")}</label>
              <input type="number" min={1} max={180} value={minutes} onChange={(e) => setMinutes(Math.max(1, Math.min(180, Number(e.target.value))))}
                className="w-32 rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
            </div>
          </div>
          <button onClick={start} className="flex w-full items-center justify-center gap-2 rounded-lg bg-red-500 px-4 py-2.5 text-sm font-medium text-white hover:opacity-90">{t("Start Mock Exam")}</button>
        </div>
      )}
      {stage === "generating" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><Loader2 size={36} className="animate-spin text-red-500" /><p className="text-sm text-[var(--muted-foreground)]">{progress || t("Preparing your exam...")}</p></div>)}
      {stage === "grading" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><Loader2 size={36} className="animate-spin text-red-500" /><p className="text-sm text-[var(--muted-foreground)]">{t("Grading your paper...")}</p></div>)}
      {stage === "error" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><p className="text-sm text-red-400">{error}</p><button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">{t("Back")}</button></div>)}

      {stage === "exam" && paper && (
        <div className="max-w-2xl space-y-5">
          <div className="sticky top-0 z-10 -mx-2 flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--background)]/90 px-4 py-2 backdrop-blur">
            <span className="text-sm font-semibold text-[var(--foreground)]">{paper.title}</span>
            <span className={`font-mono text-sm font-bold ${remaining < 60 ? "text-red-500" : "text-[var(--foreground)]"}`}>⏱ {fmt(remaining)}</span>
          </div>
          {paper.questions.map((q, idx) => (
            <div key={q.id} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
              <div className="flex items-start gap-2">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--background)] text-xs font-medium text-[var(--foreground)]">{idx + 1}</span>
                <div className="flex-1">
                  <p className="text-sm text-[var(--foreground)]">{q.question}</p>
                  {q.options && q.options.length > 0 ? (
                    <div className="mt-2 space-y-1.5">
                      {q.options.map((opt) => {
                        const l = opt.trim().charAt(0);
                        return (<button key={opt} onClick={() => setAnswers({ ...answers, [q.id]: l })}
                          className={`block w-full rounded-lg border px-3 py-2 text-left text-sm ${answers[q.id] === l ? "border-red-500/50 bg-red-500/10 text-red-300" : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"}`}>{opt}</button>);
                      })}
                    </div>
                  ) : (
                    <textarea value={answers[q.id] || ""} onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })} rows={2}
                      placeholder={t("Your answer...")}
                      className="mt-2 w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
                  )}
                </div>
              </div>
            </div>
          ))}
          <button onClick={() => submit()} className="flex w-full items-center justify-center gap-2 rounded-lg bg-red-500 px-4 py-2.5 text-sm font-medium text-white hover:opacity-90">{t("Submit Exam")}</button>
        </div>
      )}

      {stage === "result" && result && (
        <div className="max-w-2xl space-y-5">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-6 text-center">
            <p className="text-4xl font-bold text-[var(--foreground)]">{result.percentage}%</p>
            <p className="mt-1 text-xs text-[var(--muted-foreground)]">{result.total_score} / {result.max_score}</p>
          </div>
          {result.summary && <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4"><p className="text-sm text-[var(--foreground)]">{result.summary}</p></div>}
          {result.weak_topics?.length > 0 && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
              <p className="text-xs font-semibold text-amber-400">{t("Focus Areas")}</p>
              <p className="mt-1 text-sm text-[var(--foreground)]">{result.weak_topics.join(", ")}</p>
            </div>
          )}
          <div className="flex gap-3">
            <button onClick={() => { setStage("config"); setResult(null); setPaper(null); }} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">{t("New Mock Exam")}</button>
            <Link href="/market/flash-deck" className="rounded-lg bg-purple-500 px-5 py-2.5 text-sm font-medium text-white hover:opacity-90">{t("Review with FlashDeck")}</Link>
          </div>
        </div>
      )}
    </div>
  );
}
