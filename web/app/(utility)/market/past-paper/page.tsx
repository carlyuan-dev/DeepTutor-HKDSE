"use client";

import Link from "next/link";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Archive, Loader2 } from "lucide-react";
import { apiUrl } from "@/lib/api";

type Stage = "config" | "loading" | "result" | "error";
interface Q { id: string; topic: string; question: string; answer: string; marks: number; source_note: string; }
interface Result { questions: Q[]; grounded?: boolean; }

const KBS = ["hkdse-math", "hkdse-chinese", "hkdse-english", "hkdse-math-marking"];

export default function PastPaperPage() {
  const { t, i18n } = useTranslation();
  const [stage, setStage] = useState<Stage>("config");
  const [kb, setKb] = useState("hkdse-math");
  const [subject, setSubject] = useState("Mathematics");
  const [focus, setFocus] = useState("");
  const [num, setNum] = useState(5);
  const [result, setResult] = useState<Result | null>(null);
  const [reveal, setReveal] = useState<Record<string, boolean>>({});
  const [error, setError] = useState("");

  const submit = async () => {
    setError(""); setStage("loading"); setReveal({});
    try {
      const res = await fetch(apiUrl("/api/v1/market-tools/past-paper"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kb_name: kb, subject, topic_focus: focus, num_questions: num, language: i18n.language }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setResult(data); setStage("result");
    } catch (e: unknown) { setError(e instanceof Error ? e.message : t("Generation failed")); setStage("error"); }
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market" className="flex items-center gap-1.5 hover:text-[var(--foreground)]"><ArrowLeft size={14} /> {t("Market")}</Link>
        <span>/</span><span className="text-[var(--foreground)]">{t("Past Paper Practice")}</span>
      </div>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-stone-500/10"><Archive size={20} className="text-stone-500" /></div>
        <div><h1 className="text-xl font-semibold text-[var(--foreground)]">{t("Past Paper Practice")}</h1><p className="text-xs text-[var(--muted-foreground)]">{t("Practice questions grounded in real past papers")}</p></div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Knowledge Base")}</label>
            <select value={kb} onChange={(e) => setKb(e.target.value)}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none">
              {KBS.map((k) => (<option key={k} value={k}>{k}</option>))}
            </select>
            <p className="text-[11px] text-[var(--muted-foreground)]/60">{t("Ingest papers with scripts/ingest_hkdse_papers.py")}</p>
          </div>
          <div className="flex gap-4">
            <div className="flex-1 space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Subject")}</label>
              <input value={subject} onChange={(e) => setSubject(e.target.value)}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
            </div>
            <div className="flex-1 space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Topic focus (optional)")}</label>
              <input value={focus} onChange={(e) => setFocus(e.target.value)} placeholder={t("e.g. Probability")}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Number of Questions")}</label>
            <input type="number" min={3} max={12} value={num} onChange={(e) => setNum(Math.max(3, Math.min(12, Number(e.target.value))))}
              className="w-32 rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <button onClick={submit} className="flex w-full items-center justify-center gap-2 rounded-lg bg-stone-600 px-4 py-2.5 text-sm font-medium text-white hover:opacity-90">{t("Generate Practice")}</button>
        </div>
      )}
      {stage === "loading" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><Loader2 size={36} className="animate-spin text-stone-500" /><p className="text-sm text-[var(--muted-foreground)]">{t("Retrieving past papers...")}</p></div>)}
      {stage === "error" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><p className="text-sm text-red-400">{error}</p><button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">{t("Back")}</button></div>)}
      {stage === "result" && result && (
        <div className="max-w-2xl space-y-4">
          {result.grounded && <span className="inline-block rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-400">{t("Grounded in past papers")}</span>}
          {(result.questions || []).map((q, i) => (
            <div key={q.id} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--background)] text-xs font-medium text-[var(--foreground)]">{i + 1}</span>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-[var(--muted-foreground)]/60">{q.topic}</span>
                    {q.marks ? <span className="text-[10px] text-[var(--muted-foreground)]">{q.marks} {t("marks")}</span> : null}
                  </div>
                  <p className="mt-1 text-sm text-[var(--foreground)]">{q.question}</p>
                  <button onClick={() => setReveal((p) => ({ ...p, [q.id]: !p[q.id] }))} className="mt-2 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
                    {reveal[q.id] ? t("Hide answer") : t("Show answer")}
                  </button>
                  {reveal[q.id] && (
                    <div className="mt-2 rounded-lg bg-[var(--background)] p-3 text-xs text-[var(--foreground)]">
                      <p className="whitespace-pre-wrap">{q.answer}</p>
                      {q.source_note && <p className="mt-1 text-[var(--muted-foreground)]/70">📄 {q.source_note}</p>}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
          <button onClick={() => { setStage("config"); setResult(null); }} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">{t("New Practice")}</button>
        </div>
      )}
    </div>
  );
}
