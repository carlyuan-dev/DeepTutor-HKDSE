"use client";

import Link from "next/link";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, CalendarClock, Loader2, Network, Stethoscope } from "lucide-react";
import { apiUrl } from "@/lib/api";

type Stage = "config" | "generating" | "quiz" | "grading" | "result" | "error";

interface DQuestion {
  id: string;
  topic: string;
  difficulty: string;
  question: string;
  options: string[];
  answer: string;
}
interface TopicProfile { topic: string; correct: number; total: number; mastery: number; }
interface DResult {
  subject: string;
  score: number;
  total: number;
  percentage: number;
  profile: TopicProfile[];
  weak_topics: string[];
  recommendation: string;
}

export default function DiagnosticPage() {
  const { t, i18n } = useTranslation();
  const [stage, setStage] = useState<Stage>("config");
  const [subject, setSubject] = useState("Mathematics");
  const [topicsText, setTopicsText] = useState("");
  const [num, setNum] = useState(6);
  const [kb, setKb] = useState("");
  const [questions, setQuestions] = useState<DQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<DResult | null>(null);
  const [error, setError] = useState("");

  // Cross-tool pipeline states
  const [planResult, setPlanResult] = useState<any>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [conceptResult, setConceptResult] = useState<any>(null);
  const [conceptLoading, setConceptLoading] = useState(false);

  const generatePlan = async () => {
    if (!result) return;
    setPlanLoading(true);
    try {
      const res = await fetch(apiUrl("/api/v1/market-tools/diagnostic/to-plan"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subject, weak_topics: result.weak_topics, profile: result.profile,
          days_until_exam: 14, hours_per_day: 2.0, language: i18n.language,
        }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setPlanResult(data);
    } catch { setPlanResult(null); }
    setPlanLoading(false);
  };

  const generateConceptMap = async () => {
    if (!result) return;
    setConceptLoading(true);
    try {
      const topicSummary = result.profile
        .filter((p: TopicProfile) => p.mastery < 70)
        .map((p: TopicProfile) => [p.topic, p.total - p.correct]);
      const res = await fetch(apiUrl("/api/v1/market-tools/mistake-book/to-concept-map"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic_summary: topicSummary, subject, language: i18n.language }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setConceptResult(data);
    } catch { setConceptResult(null); }
    setConceptLoading(false);
  };

  const generate = async () => {
    setError("");
    setStage("generating");
    try {
      const topics = topicsText.split(",").map((s) => s.trim()).filter(Boolean);
      const res = await fetch(apiUrl("/api/v1/market-tools/diagnostic/generate"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject, topics, num_questions: num, kb_name: kb || undefined, language: i18n.language }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setQuestions(data.questions || []);
      setAnswers({});
      setStage("quiz");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("Generation failed"));
      setStage("error");
    }
  };

  const grade = async () => {
    setError("");
    setStage("grading");
    try {
      const res = await fetch(apiUrl("/api/v1/market-tools/diagnostic/grade"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject, questions, answers, language: i18n.language }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setResult(data);
      setStage("result");
      // Log to teacher dashboard
      fetch(apiUrl("/api/v1/market-tools/dashboard/log-diagnostic"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subject, score: data.score, total: data.total,
          percentage: data.percentage, weak_topics: data.weak_topics, profile: data.profile,
        }),
      }).catch(() => {});
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("Grading failed"));
      setStage("error");
    }
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market" className="flex items-center gap-1.5 hover:text-[var(--foreground)]">
          <ArrowLeft size={14} /> {t("Market")}
        </Link>
        <span>/</span>
        <span className="text-[var(--foreground)]">{t("Diagnostic Quiz")}</span>
      </div>

      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-rose-500/10">
          <Stethoscope size={20} className="text-rose-500" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-[var(--foreground)]">{t("Diagnostic Quiz")}</h1>
          <p className="text-xs text-[var(--muted-foreground)]">{t("Pinpoint your weak topics in minutes")}</p>
        </div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Subject")}</label>
            <input value={subject} onChange={(e) => setSubject(e.target.value)}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Topics (comma-separated, optional)")}</label>
            <input value={topicsText} onChange={(e) => setTopicsText(e.target.value)}
              placeholder={t("e.g. Algebra, Trigonometry, Probability")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <div className="flex gap-4">
            <div className="flex-1 space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Number of Questions")}</label>
              <input type="number" min={4} max={15} value={num} onChange={(e) => setNum(Math.max(4, Math.min(15, Number(e.target.value))))}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
            </div>
            <div className="flex-1 space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Knowledge Base (optional)")}</label>
              <input value={kb} onChange={(e) => setKb(e.target.value)}
                placeholder={t("e.g. hkdse-math")}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
            </div>
          </div>
          <button onClick={generate} className="flex w-full items-center justify-center gap-2 rounded-lg bg-rose-500 px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90">
            {t("Start Diagnostic")}
          </button>
        </div>
      )}

      {(stage === "generating" || stage === "grading") && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <Loader2 size={36} className="animate-spin text-rose-500" />
          <p className="text-sm text-[var(--muted-foreground)]">{stage === "generating" ? t("Preparing your diagnostic...") : t("Analyzing your answers...")}</p>
        </div>
      )}

      {stage === "error" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <p className="text-sm text-red-400">{error}</p>
          <button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">{t("Back")}</button>
        </div>
      )}

      {stage === "quiz" && (
        <div className="max-w-2xl space-y-5">
          {questions.map((q, idx) => (
            <div key={q.id} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
              <div className="mb-3 flex items-start gap-2">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--background)] text-xs font-medium text-[var(--foreground)]">{idx + 1}</span>
                <div className="flex-1">
                  <p className="text-sm text-[var(--foreground)]">{q.question}</p>
                  <span className="text-[10px] text-[var(--muted-foreground)]/60">{q.topic} · {q.difficulty}</span>
                </div>
              </div>
              <div className="ml-8 space-y-1.5">
                {(q.options || []).map((opt) => {
                  const letter = opt.trim().charAt(0);
                  const selected = answers[q.id] === letter;
                  return (
                    <button key={opt} onClick={() => setAnswers({ ...answers, [q.id]: letter })}
                      className={`block w-full rounded-lg border px-3 py-2 text-left text-sm ${selected ? "border-rose-500/50 bg-rose-500/10 text-rose-300" : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"}`}>
                      {opt}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
          <button onClick={grade} disabled={Object.keys(answers).length < questions.length}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-rose-500 px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40">
            {t("Submit Answers")}
          </button>
        </div>
      )}

      {stage === "result" && result && (
        <div className="max-w-2xl space-y-5">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5 text-center">
            <p className="text-3xl font-bold text-[var(--foreground)]">{result.percentage}%</p>
            <p className="text-xs text-[var(--muted-foreground)]">{result.score} / {result.total} {t("correct")}</p>
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">{t("Topic Mastery")}</p>
            <div className="space-y-2.5">
              {result.profile.map((p) => (
                <div key={p.topic}>
                  <div className="mb-1 flex justify-between text-xs">
                    <span className="text-[var(--foreground)]">{p.topic}</span>
                    <span className="text-[var(--muted-foreground)]">{p.correct}/{p.total} · {p.mastery}%</span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--background)]">
                    <div className={`h-full rounded-full ${p.mastery < 60 ? "bg-rose-500" : p.mastery < 80 ? "bg-amber-500" : "bg-emerald-500"}`} style={{ width: `${p.mastery}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
          {result.weak_topics?.length > 0 && (
            <div className="rounded-xl border border-rose-500/30 bg-rose-500/5 p-4">
              <p className="text-xs font-semibold text-rose-400">{t("Focus Areas")}</p>
              <p className="mt-1 text-sm text-[var(--foreground)]">{result.weak_topics.join(", ")}</p>
            </div>
          )}
          {result.recommendation && (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
              <p className="text-xs font-semibold text-[var(--muted-foreground)]">{t("Recommendation")}</p>
              <p className="mt-1 text-sm text-[var(--foreground)]">{result.recommendation}</p>
            </div>
          )}
          {/* ── Cross-tool pipeline buttons ── */}
          <div className="space-y-4">
            <div className="flex flex-wrap gap-3">
              <button onClick={() => { setStage("config"); setResult(null); setPlanResult(null); setConceptResult(null); }}
                className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">
                {t("New Diagnostic")}
              </button>
              <button onClick={generatePlan} disabled={planLoading}
                className={`flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 ${planLoading ? "bg-indigo-400" : "bg-indigo-500"}`}>
                {planLoading ? <Loader2 size={14} className="animate-spin" /> : <CalendarClock size={14} />}
                {planLoading ? t("Generating...") : t("一鍵生成複習計劃")}
              </button>
              <button onClick={generateConceptMap} disabled={conceptLoading}
                className={`flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 ${conceptLoading ? "bg-violet-400" : "bg-violet-500"}`}>
                {conceptLoading ? <Loader2 size={14} className="animate-spin" /> : <Network size={14} />}
                {conceptLoading ? t("Generating...") : t("弱項概念圖")}
              </button>
              <Link href="/market/study-planner"
                className="rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-5 py-2.5 text-sm text-indigo-400 hover:bg-indigo-500/20">
                {t("手動制定計劃 →")}
              </Link>
            </div>

            {/* Inline study plan result */}
            {planResult && (
              <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/5 p-5 space-y-3">
                <p className="text-xs font-medium text-indigo-400">📅 {planResult.diagnostic_summary || "Personalised Study Plan"}</p>
                {planResult.priority_areas?.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {planResult.priority_areas.map((a: string, i: number) => (
                      <span key={i} className="rounded-full bg-indigo-500/20 px-2.5 py-1 text-xs text-indigo-400">⭐ {a}</span>
                    ))}
                  </div>
                )}
                <div className="max-h-60 overflow-y-auto space-y-2">
                  {planResult.days?.slice(0, 5).map((d: any) => (
                    <div key={d.day} className="rounded-lg bg-[var(--background)] p-3">
                      <p className="text-xs font-medium text-[var(--foreground)]">Day {d.day}: {d.focus}</p>
                      <ul className="mt-1 space-y-0.5">
                        {d.tasks?.slice(0, 3).map((t: string, i: number) => (
                          <li key={i} className="text-[11px] text-[var(--muted-foreground)]">· {t}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
                {planResult.days?.length > 5 && (
                  <p className="text-center text-[10px] text-[var(--muted-foreground)]">... and {planResult.days.length - 5} more days</p>
                )}
              </div>
            )}

            {/* Inline concept map result */}
            {conceptResult && (
              <div className="rounded-xl border border-violet-500/20 bg-violet-500/5 p-5 space-y-3">
                <p className="text-xs font-medium text-violet-400">🧠 Knowledge Gap Map</p>
                <p className="text-xs text-[var(--foreground)]">{conceptResult.analysis}</p>
                {conceptResult.weak_nodes?.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {conceptResult.weak_nodes.map((n: string, i: number) => (
                      <span key={i} className="rounded-full bg-violet-500/20 px-2.5 py-1 text-xs text-violet-400">🔴 {n}</span>
                    ))}
                  </div>
                )}
                {conceptResult.prerequisites?.length > 0 && (
                  <div className="space-y-1">
                    <p className="text-[10px] text-[var(--muted-foreground)]">Prerequisite Dependencies:</p>
                    {conceptResult.prerequisites.map((p: any, i: number) => (
                      <p key={i} className="text-[11px] text-[var(--foreground)]">
                        <span className="text-violet-400 font-medium">{p.topic}</span> depends on {p.depends_on?.join(", ")}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
