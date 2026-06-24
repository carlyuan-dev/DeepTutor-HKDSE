"use client";

import Link from "next/link";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, CalendarClock, Loader2, Plus, X } from "lucide-react";
import { apiUrl } from "@/lib/api";

type Stage = "config" | "generating" | "result" | "error";

interface PlanDay {
  day: number;
  focus: string;
  subjects: string[];
  tasks: string[];
  milestone: string;
}
interface StudyPlan {
  overview: string;
  daily_hours: number;
  days: PlanDay[];
  tips: string[];
}

const LEVELS = ["beginner", "intermediate", "advanced"];

export default function StudyPlannerPage() {
  const { t, i18n } = useTranslation();
  const [stage, setStage] = useState<Stage>("config");
  const [subjects, setSubjects] = useState<string[]>(["Mathematics", "English"]);
  const [subjectInput, setSubjectInput] = useState("");
  const [days, setDays] = useState(14);
  const [hours, setHours] = useState(2);
  const [level, setLevel] = useState("intermediate");
  const [goals, setGoals] = useState("");
  const [plan, setPlan] = useState<StudyPlan | null>(null);
  const [error, setError] = useState("");

  const addSubject = () => {
    const v = subjectInput.trim();
    if (v && !subjects.includes(v)) setSubjects([...subjects, v]);
    setSubjectInput("");
  };

  const submit = async () => {
    if (subjects.length === 0) return;
    setError("");
    setStage("generating");
    try {
      const res = await fetch(apiUrl("/api/v1/market-tools/study-planner"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subjects,
          days_until_exam: days,
          hours_per_day: hours,
          current_level: level,
          goals,
          language: i18n.language,
        }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setPlan(data);
      setStage("result");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("Generation failed"));
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
        <span className="text-[var(--foreground)]">{t("Study Planner")}</span>
      </div>

      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-500/10">
          <CalendarClock size={20} className="text-indigo-500" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-[var(--foreground)]">{t("Study Planner")}</h1>
          <p className="text-xs text-[var(--muted-foreground)]">{t("Build a personalized day-by-day revision plan")}</p>
        </div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Subjects")}</label>
            <div className="flex flex-wrap gap-2">
              {subjects.map((s) => (
                <span key={s} className="flex items-center gap-1 rounded-full bg-indigo-500/10 px-3 py-1 text-xs text-indigo-400">
                  {s}
                  <button onClick={() => setSubjects(subjects.filter((x) => x !== s))}><X size={12} /></button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                value={subjectInput}
                onChange={(e) => setSubjectInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addSubject())}
                placeholder={t("Add a subject")}
                className="flex-1 rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none"
              />
              <button onClick={addSubject} className="flex items-center gap-1 rounded-lg border border-[var(--border)] px-3 py-2 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
                <Plus size={14} /> {t("Add")}
              </button>
            </div>
          </div>

          <div className="flex gap-4">
            <div className="flex-1 space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Days until exam")}</label>
              <input type="number" min={1} max={90} value={days} onChange={(e) => setDays(Math.max(1, Math.min(90, Number(e.target.value))))}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
            </div>
            <div className="flex-1 space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Hours per day")}</label>
              <input type="number" min={0.5} max={12} step={0.5} value={hours} onChange={(e) => setHours(Math.max(0.5, Math.min(12, Number(e.target.value))))}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Current level")}</label>
            <div className="flex gap-2">
              {LEVELS.map((l) => (
                <button key={l} onClick={() => setLevel(l)}
                  className={`rounded-lg border px-4 py-2 text-sm capitalize ${level === l ? "border-indigo-500/50 bg-indigo-500/10 text-indigo-400" : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"}`}>
                  {t(l.charAt(0).toUpperCase() + l.slice(1))}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Goals (optional)")}</label>
            <textarea value={goals} onChange={(e) => setGoals(e.target.value)} rows={2}
              placeholder={t("e.g. Improve weak topics in calculus, target level 5")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>

          <button onClick={submit} className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-500 px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90">
            {t("Generate Plan")}
          </button>
        </div>
      )}

      {stage === "generating" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <Loader2 size={36} className="animate-spin text-indigo-500" />
          <p className="text-sm text-[var(--muted-foreground)]">{t("Building your study plan...")}</p>
        </div>
      )}

      {stage === "error" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <p className="text-sm text-red-400">{error}</p>
          <button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">{t("Back")}</button>
        </div>
      )}

      {stage === "result" && plan && (
        <div className="max-w-3xl space-y-6">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
            <p className="text-sm text-[var(--foreground)]">{plan.overview}</p>
          </div>
          <div className="space-y-3">
            {plan.days.map((d) => (
              <div key={d.day} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
                <div className="mb-2 flex items-center gap-3">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-500/10 text-xs font-semibold text-indigo-400">{d.day}</span>
                  <p className="text-sm font-semibold text-[var(--foreground)]">{d.focus}</p>
                  <span className="ml-auto text-[11px] text-[var(--muted-foreground)]">{(d.subjects || []).join(" · ")}</span>
                </div>
                <ul className="ml-10 list-disc space-y-1 text-xs text-[var(--muted-foreground)]">
                  {(d.tasks || []).map((task, i) => (<li key={i}>{task}</li>))}
                </ul>
                {d.milestone && <p className="ml-10 mt-2 text-xs text-indigo-400">🎯 {d.milestone}</p>}
              </div>
            ))}
          </div>
          {plan.tips && plan.tips.length > 0 && (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
              <p className="mb-2 text-xs font-semibold text-[var(--foreground)]">{t("Tips")}</p>
              <ul className="list-disc space-y-1 pl-4 text-xs text-[var(--muted-foreground)]">
                {plan.tips.map((tip, i) => (<li key={i}>{tip}</li>))}
              </ul>
            </div>
          )}
          <button onClick={() => { setStage("config"); setPlan(null); }} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">
            {t("New Plan")}
          </button>
        </div>
      )}
    </div>
  );
}
