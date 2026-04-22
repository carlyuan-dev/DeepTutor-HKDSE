"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, CheckCircle, FileText, Loader2 } from "lucide-react";
import { generatePaper } from "@/lib/market-api";
import { listKnowledgeBases } from "@/lib/knowledge-api";
import type { ExamPaper, Question, StudentAnswers } from "@/types/market";
import { STORAGE_KEYS } from "@/types/market";

type Stage = "config" | "generating" | "answer" | "submitting";

const QUESTION_TYPES = [
  { value: "mcq", label: "Multiple Choice" },
  { value: "fill_blank", label: "Fill in the Blank" },
  { value: "short_answer", label: "Short Answer" },
];

const DIFFICULTIES = [
  { value: "easy", label: "Easy" },
  { value: "medium", label: "Medium" },
  { value: "hard", label: "Hard" },
];

export default function PaperForgePage() {
  const router = useRouter();

  // Config
  const [kbName, setKbName] = useState("");
  const [kbList, setKbList] = useState<string[]>([]);
  const [title, setTitle] = useState("Examination Paper");
  const [selectedTypes, setSelectedTypes] = useState<string[]>(["mcq", "short_answer"]);
  const [numQuestions, setNumQuestions] = useState(10);
  const [difficulty, setDifficulty] = useState("medium");
  const [topicFocus, setTopicFocus] = useState("");

  // State
  const [stage, setStage] = useState<Stage>("config");
  const [progressMsg, setProgressMsg] = useState("");
  const [paper, setPaper] = useState<ExamPaper | null>(null);
  const [answers, setAnswers] = useState<StudentAnswers>({});
  const [error, setError] = useState("");
  const answerRefs = useRef<Record<string, HTMLTextAreaElement | null>>({});

  useEffect(() => {
    listKnowledgeBases().then((kbs) => {
      const names = kbs.map((kb: { name: string }) => kb.name);
      setKbList(names);
      if (names.length > 0) setKbName(names[0]);
    });
  }, []);

  // Handle retake: pre-fill topics from weak_topics in localStorage
  useEffect(() => {
    const topics = localStorage.getItem(STORAGE_KEYS.weakTopics);
    if (topics) {
      try {
        const arr: string[] = JSON.parse(topics);
        setTopicFocus(arr.join(", "));
      } catch {}
    }
  }, []);

  const toggleType = (t: string) => {
    setSelectedTypes((prev) =>
      prev.includes(t) ? (prev.length > 1 ? prev.filter((x) => x !== t) : prev) : [...prev, t]
    );
  };

  const handleGenerate = async () => {
    if (selectedTypes.length === 0) return;
    setError("");
    setStage("generating");
    setProgressMsg("Starting...");
    try {
      const result = await generatePaper(
        {
          kb_name: kbName || undefined,
          title,
          question_types: selectedTypes,
          num_questions: numQuestions,
          difficulty,
          topic_focus: topicFocus,
        },
        (msg) => setProgressMsg(msg)
      );
      setPaper(result);
      const initAnswers: StudentAnswers = {};
      result.questions.forEach((q) => (initAnswers[q.id] = ""));
      setAnswers(initAnswers);
      setStage("answer");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Generation failed");
      setStage("config");
    }
  };

  const handleSubmit = () => {
    if (!paper) return;
    setStage("submitting");
    localStorage.setItem(STORAGE_KEYS.paper, JSON.stringify(paper));
    localStorage.setItem(STORAGE_KEYS.answers, JSON.stringify(answers));
    localStorage.removeItem(STORAGE_KEYS.weakTopics);
    router.push("/market/exam-grader");
  };

  const answeredCount = Object.values(answers).filter((a) => a.trim()).length;
  const totalQ = paper?.questions.length ?? 0;

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      {/* Breadcrumb */}
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market" className="flex items-center gap-1.5 transition-colors hover:text-[var(--foreground)]">
          <ArrowLeft size={14} />
          Market
        </Link>
        <span>/</span>
        <span className="text-[var(--foreground)]">PaperForge</span>
      </div>

      {/* Header */}
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-500/10">
          <FileText size={20} className="text-blue-500" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-[var(--foreground)]">PaperForge</h1>
          <p className="text-xs text-[var(--muted-foreground)]">Generate customized exam papers from your knowledge base</p>
        </div>
      </div>

      {/* ── Config stage ── */}
      {stage === "config" && (
        <div className="max-w-xl space-y-5">
          {error && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
              {error}
            </div>
          )}

          {/* Paper title */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">Paper Title</label>
            <input
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Chapter 3 Review"
            />
          </div>

          {/* Knowledge base */}
          {kbList.length > 0 && (
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">Knowledge Base</label>
              <select
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none"
                value={kbName}
                onChange={(e) => setKbName(e.target.value)}
              >
                <option value="">None (LLM only)</option>
                {kbList.map((kb) => (
                  <option key={kb} value={kb}>{kb}</option>
                ))}
              </select>
            </div>
          )}

          {/* Topic focus */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">Topic Focus <span className="text-[var(--muted-foreground)]/50">(optional)</span></label>
            <input
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20"
              value={topicFocus}
              onChange={(e) => setTopicFocus(e.target.value)}
              placeholder="e.g. Newton's Laws, Thermodynamics"
            />
          </div>

          {/* Question types */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">Question Types</label>
            <div className="flex flex-wrap gap-2">
              {QUESTION_TYPES.map((t) => (
                <button
                  key={t.value}
                  onClick={() => toggleType(t.value)}
                  className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${
                    selectedTypes.includes(t.value)
                      ? "border-blue-500/50 bg-blue-500/10 text-blue-400"
                      : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          {/* Number of questions + difficulty */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">Number of Questions</label>
              <input
                type="number"
                min={3}
                max={30}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-blue-500/50"
                value={numQuestions}
                onChange={(e) => setNumQuestions(Math.max(3, Math.min(30, Number(e.target.value))))}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">Difficulty</label>
              <div className="flex gap-1.5">
                {DIFFICULTIES.map((d) => (
                  <button
                    key={d.value}
                    onClick={() => setDifficulty(d.value)}
                    className={`flex-1 rounded-lg border py-2 text-xs transition-colors ${
                      difficulty === d.value
                        ? "border-blue-500/50 bg-blue-500/10 text-blue-400"
                        : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                    }`}
                  >
                    {d.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <button
            onClick={handleGenerate}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-500 px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90"
          >
            Generate Paper
            <ArrowRight size={15} />
          </button>
        </div>
      )}

      {/* ── Generating stage ── */}
      {stage === "generating" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <Loader2 size={36} className="animate-spin text-blue-500" />
          <p className="text-sm text-[var(--muted-foreground)]">{progressMsg}</p>
        </div>
      )}

      {/* ── Answer stage ── */}
      {stage === "answer" && paper && (
        <div className="max-w-2xl space-y-6">
          {/* Paper header */}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] px-5 py-4">
            <h2 className="text-base font-semibold text-[var(--foreground)]">{paper.title}</h2>
            <p className="mt-0.5 text-xs text-[var(--muted-foreground)]">
              {paper.questions.length} questions · {paper.questions.reduce((s, q) => s + q.points, 0)} points total
            </p>
          </div>

          {/* Questions */}
          {paper.questions.map((q: Question, idx: number) => (
            <div key={q.id} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
              <div className="mb-3 flex items-start gap-3">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--background)] text-xs font-medium text-[var(--foreground)]">
                  {idx + 1}
                </span>
                <div className="flex-1">
                  <p className="text-sm text-[var(--foreground)]">{q.question}</p>
                  <div className="mt-1 flex items-center gap-2">
                    <span className="text-[10px] text-[var(--muted-foreground)]/60 uppercase tracking-wide">{q.type.replace("_", " ")}</span>
                    <span className="text-[var(--muted-foreground)]/40">·</span>
                    <span className="text-[10px] text-[var(--muted-foreground)]/60">{q.topic}</span>
                    <span className="text-[var(--muted-foreground)]/40">·</span>
                    <span className="text-[10px] text-[var(--muted-foreground)]/60">{q.points} pts</span>
                  </div>
                </div>
              </div>

              {/* MCQ options */}
              {q.type === "mcq" && q.options ? (
                <div className="ml-9 space-y-1.5">
                  {q.options.map((opt) => (
                    <button
                      key={opt}
                      onClick={() => setAnswers((prev) => ({ ...prev, [q.id]: opt }))}
                      className={`flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                        answers[q.id] === opt
                          ? "border-blue-500/50 bg-blue-500/10 text-blue-400"
                          : "border-[var(--border)] text-[var(--foreground)] hover:bg-[var(--background)]"
                      }`}
                    >
                      {answers[q.id] === opt && <CheckCircle size={14} className="shrink-0" />}
                      <span>{opt}</span>
                    </button>
                  ))}
                </div>
              ) : (
                <textarea
                  ref={(el) => { answerRefs.current[q.id] = el; }}
                  className="ml-9 w-[calc(100%-2.25rem)] resize-none rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20"
                  rows={3}
                  placeholder="Your answer..."
                  value={answers[q.id] ?? ""}
                  onChange={(e) => setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))}
                />
              )}
            </div>
          ))}

          {/* Submit bar */}
          <div className="sticky bottom-0 -mx-8 border-t border-[var(--border)] bg-[var(--background)] px-8 py-4">
            <div className="flex items-center justify-between">
              <p className="text-xs text-[var(--muted-foreground)]">
                {answeredCount} / {totalQ} answered
              </p>
              <button
                onClick={handleSubmit}
                disabled={answeredCount === 0}
                className="flex items-center gap-2 rounded-lg bg-emerald-500 px-5 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                Submit & Grade
                <ArrowRight size={15} />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Submitting stage ── */}
      {stage === "submitting" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <Loader2 size={36} className="animate-spin text-emerald-500" />
          <p className="text-sm text-[var(--muted-foreground)]">Sending to ExamGrader...</p>
        </div>
      )}
    </div>
  );
}
