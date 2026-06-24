"use client";

import Link from "next/link";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Zap, Loader2 } from "lucide-react";
import { apiUrl } from "@/lib/api";

type Stage = "config" | "loading" | "quiz" | "done" | "error";
interface Q { id: string; question: string; options: string[]; answer: string; explanation: string; }

export default function FlashQuizPage() {
  const { t, i18n } = useTranslation();
  const [stage, setStage] = useState<Stage>("config");
  const [topic, setTopic] = useState("");
  const [num, setNum] = useState(8);
  const [difficulty, setDifficulty] = useState("medium");
  const [questions, setQuestions] = useState<Q[]>([]);
  const [idx, setIdx] = useState(0);
  const [picked, setPicked] = useState<string | null>(null);
  const [score, setScore] = useState(0);
  const [error, setError] = useState("");

  const DIFFS = [{ v: "easy", l: "Easy" }, { v: "medium", l: "Medium" }, { v: "hard", l: "Hard" }];

  const start = async () => {
    if (!topic.trim()) return;
    setError(""); setStage("loading");
    try {
      const res = await fetch(apiUrl("/api/v1/market-tools/flash-quiz/generate"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, num_questions: num, difficulty, language: i18n.language }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setQuestions(data.questions || []); setIdx(0); setScore(0); setPicked(null); setStage("quiz");
    } catch (e: unknown) { setError(e instanceof Error ? e.message : t("Generation failed")); setStage("error"); }
  };

  const q = questions[idx];
  const letterOf = (opt: string) => opt.trim().charAt(0).toUpperCase();
  const correctLetter = q ? (q.answer || "").trim().charAt(0).toUpperCase() : "";

  const pick = (opt: string) => {
    if (picked) return;
    const l = letterOf(opt);
    setPicked(l);
    if (l === correctLetter) setScore((s) => s + 1);
  };
  const next = () => {
    if (idx + 1 >= questions.length) { setStage("done"); return; }
    setIdx(idx + 1); setPicked(null);
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market" className="flex items-center gap-1.5 hover:text-[var(--foreground)]"><ArrowLeft size={14} /> {t("Market")}</Link>
        <span>/</span><span className="text-[var(--foreground)]">{t("Flash Quiz")}</span>
      </div>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-yellow-500/10"><Zap size={20} className="text-yellow-500" /></div>
        <div><h1 className="text-xl font-semibold text-[var(--foreground)]">{t("Flash Quiz")}</h1><p className="text-xs text-[var(--muted-foreground)]">{t("Rapid-fire questions with instant feedback")}</p></div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Topic")}</label>
            <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder={t("e.g. Photosynthesis")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <div className="flex gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Number of Questions")}</label>
              <input type="number" min={4} max={20} value={num} onChange={(e) => setNum(Math.max(4, Math.min(20, Number(e.target.value))))}
                className="w-32 rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Difficulty")}</label>
              <div className="flex gap-2">
                {DIFFS.map((d) => (
                  <button key={d.v} onClick={() => setDifficulty(d.v)}
                    className={`rounded-lg border px-3 py-2 text-xs ${difficulty === d.v ? "border-yellow-500/50 bg-yellow-500/10 text-yellow-500" : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"}`}>{t(d.l)}</button>
                ))}
              </div>
            </div>
          </div>
          <button onClick={start} className="flex w-full items-center justify-center gap-2 rounded-lg bg-yellow-500 px-4 py-2.5 text-sm font-medium text-white hover:opacity-90">{t("Start Quiz")}</button>
        </div>
      )}
      {stage === "loading" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><Loader2 size={36} className="animate-spin text-yellow-500" /><p className="text-sm text-[var(--muted-foreground)]">{t("Loading questions...")}</p></div>)}
      {stage === "error" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><p className="text-sm text-red-400">{error}</p><button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">{t("Back")}</button></div>)}
      {stage === "quiz" && q && (
        <div className="max-w-2xl space-y-5">
          <div className="flex items-center justify-between text-xs text-[var(--muted-foreground)]">
            <span>{idx + 1} / {questions.length}</span>
            <span>{t("Score")}: {score}</span>
          </div>
          <p className="text-sm text-[var(--foreground)]">{q.question}</p>
          <div className="space-y-2">
            {(q.options || []).map((opt) => {
              const l = letterOf(opt);
              let cls = "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]";
              if (picked) {
                if (l === correctLetter) cls = "border-emerald-500/50 bg-emerald-500/10 text-emerald-400";
                else if (l === picked) cls = "border-rose-500/50 bg-rose-500/10 text-rose-400";
              }
              return (<button key={opt} onClick={() => pick(opt)} disabled={!!picked} className={`block w-full rounded-lg border px-3 py-2 text-left text-sm ${cls}`}>{opt}</button>);
            })}
          </div>
          {picked && (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
              <p className="text-sm font-medium text-[var(--foreground)]">{picked === correctLetter ? `✓ ${t("Correct")}` : `✗ ${t("Correct answer")}: ${correctLetter}`}</p>
              {q.explanation && <p className="mt-1 text-xs text-[var(--muted-foreground)]">{q.explanation}</p>}
              <button onClick={next} className="mt-3 rounded-lg bg-yellow-500 px-4 py-2 text-sm font-medium text-white hover:opacity-90">{idx + 1 >= questions.length ? t("Finish") : t("Next")}</button>
            </div>
          )}
        </div>
      )}
      {stage === "done" && (
        <div className="max-w-md space-y-5">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-6 text-center">
            <p className="text-4xl font-bold text-[var(--foreground)]">{score} / {questions.length}</p>
            <p className="mt-1 text-xs text-[var(--muted-foreground)]">{Math.round((score / Math.max(1, questions.length)) * 100)}% {t("correct")}</p>
          </div>
          <button onClick={() => setStage("config")} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">{t("New Quiz")}</button>
        </div>
      )}
    </div>
  );
}
