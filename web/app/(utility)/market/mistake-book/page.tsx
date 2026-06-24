"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, BookMarked, Loader2, Plus, Sparkles, Trash2 } from "lucide-react";
import { apiUrl } from "@/lib/api";

interface Analysis {
  topic: string;
  error_type: string;
  explanation: string;
  correct_answer: string;
  similar_question: { question: string; answer: string };
  review_tip: string;
}
interface MistakeEntry {
  id: string;
  subject: string;
  question: string;
  wrong_answer: string;
  correct_answer: string;
  createdAt: number;
  analysis?: Analysis;
}

const STORAGE_KEY = "deeptutor.mistake-book";

export default function MistakeBookPage() {
  const { t, i18n } = useTranslation();
  const [entries, setEntries] = useState<MistakeEntry[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [subject, setSubject] = useState("");
  const [question, setQuestion] = useState("");
  const [wrong, setWrong] = useState("");
  const [correct, setCorrect] = useState("");
  const [analyzingId, setAnalyzingId] = useState<string | null>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setEntries(JSON.parse(raw));
    } catch { /* ignore */ }
  }, []);

  const persist = (next: MistakeEntry[]) => {
    setEntries(next);
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch { /* ignore */ }
  };

  const addEntry = () => {
    if (!question.trim()) return;
    const entry: MistakeEntry = {
      id: `m-${Date.now()}`,
      subject, question, wrong_answer: wrong, correct_answer: correct,
      createdAt: Date.now(),
    };
    persist([entry, ...entries]);
    setSubject(""); setQuestion(""); setWrong(""); setCorrect(""); setShowForm(false);
  };

  const remove = (id: string) => persist(entries.filter((e) => e.id !== id));

  const analyze = async (entry: MistakeEntry) => {
    setAnalyzingId(entry.id);
    try {
      const res = await fetch(apiUrl("/api/v1/market-tools/mistake-book/analyze"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: entry.question, wrong_answer: entry.wrong_answer,
          correct_answer: entry.correct_answer, subject: entry.subject, language: i18n.language,
        }),
      });
      const data = await res.json();
      if (!data.error) {
        persist(entries.map((e) => (e.id === entry.id ? { ...e, analysis: data } : e)));
      }
    } catch { /* ignore */ }
    setAnalyzingId(null);
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market" className="flex items-center gap-1.5 hover:text-[var(--foreground)]">
          <ArrowLeft size={14} /> {t("Market")}
        </Link>
        <span>/</span>
        <span className="text-[var(--foreground)]">{t("Mistake Notebook")}</span>
      </div>

      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-orange-500/10">
          <BookMarked size={20} className="text-orange-500" />
        </div>
        <div className="flex-1">
          <h1 className="text-xl font-semibold text-[var(--foreground)]">{t("Mistake Notebook")}</h1>
          <p className="text-xs text-[var(--muted-foreground)]">{t("Collect mistakes, understand them, and practice similar questions")}</p>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="flex items-center gap-1.5 rounded-lg bg-orange-500 px-4 py-2 text-sm font-medium text-white hover:opacity-90">
          <Plus size={14} /> {t("Add Mistake")}
        </button>
      </div>

      <p className="mb-4 text-[11px] text-[var(--muted-foreground)]/60">{t("Saved locally on this device — nothing is uploaded.")}</p>

      {showForm && (
        <div className="mb-6 max-w-2xl space-y-3 rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
          <input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder={t("Subject (optional)")}
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          <textarea value={question} onChange={(e) => setQuestion(e.target.value)} rows={3} placeholder={t("The question you got wrong")}
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          <div className="flex gap-3">
            <input value={wrong} onChange={(e) => setWrong(e.target.value)} placeholder={t("Your answer (optional)")}
              className="flex-1 rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
            <input value={correct} onChange={(e) => setCorrect(e.target.value)} placeholder={t("Correct answer (optional)")}
              className="flex-1 rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <button onClick={addEntry} className="rounded-lg bg-orange-500 px-4 py-2 text-sm font-medium text-white hover:opacity-90">{t("Save")}</button>
        </div>
      )}

      {entries.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center">
          <BookMarked size={32} className="text-[var(--muted-foreground)]/40" />
          <p className="text-sm text-[var(--muted-foreground)]">{t("No mistakes yet. Add one to get started.")}</p>
        </div>
      ) : (
        <div className="max-w-3xl space-y-4">
          {entries.map((e) => (
            <div key={e.id} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  {e.subject && <span className="rounded-full bg-orange-500/10 px-2 py-0.5 text-[10px] text-orange-400">{e.subject}</span>}
                  <p className="mt-1.5 text-sm text-[var(--foreground)]">{e.question}</p>
                  {(e.wrong_answer || e.correct_answer) && (
                    <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                      {e.wrong_answer && <span className="text-rose-400">✗ {e.wrong_answer}</span>}
                      {e.wrong_answer && e.correct_answer && " · "}
                      {e.correct_answer && <span className="text-emerald-400">✓ {e.correct_answer}</span>}
                    </p>
                  )}
                </div>
                <button onClick={() => remove(e.id)} className="text-[var(--muted-foreground)]/50 hover:text-rose-400"><Trash2 size={14} /></button>
              </div>

              {!e.analysis ? (
                <button onClick={() => analyze(e)} disabled={analyzingId === e.id}
                  className="mt-3 flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)] disabled:opacity-50">
                  {analyzingId === e.id ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                  {analyzingId === e.id ? t("Analyzing...") : t("Analyze with AI")}
                </button>
              ) : (
                <div className="mt-3 space-y-2 rounded-lg bg-[var(--background)] p-4 text-xs">
                  <p><span className="text-orange-400">{t("Topic")}:</span> <span className="text-[var(--foreground)]">{e.analysis.topic}</span> · <span className="text-[var(--muted-foreground)]">{e.analysis.error_type}</span></p>
                  <p className="text-[var(--muted-foreground)]">{e.analysis.explanation}</p>
                  {e.analysis.correct_answer && <p><span className="text-emerald-400">{t("Correct")}:</span> <span className="text-[var(--foreground)]">{e.analysis.correct_answer}</span></p>}
                  {e.analysis.similar_question?.question && (
                    <div className="mt-2 rounded-md border border-[var(--border)] p-2.5">
                      <p className="text-[10px] font-semibold uppercase text-[var(--muted-foreground)]/60">{t("Practice this")}</p>
                      <p className="mt-1 text-[var(--foreground)]">{e.analysis.similar_question.question}</p>
                      <p className="mt-1 text-[var(--muted-foreground)]">{t("Answer")}: {e.analysis.similar_question.answer}</p>
                    </div>
                  )}
                  {e.analysis.review_tip && <p className="text-indigo-400">💡 {e.analysis.review_tip}</p>}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
