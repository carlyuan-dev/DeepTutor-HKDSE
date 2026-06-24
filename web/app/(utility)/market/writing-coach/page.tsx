"use client";

import Link from "next/link";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, SpellCheck, Loader2 } from "lucide-react";
import { apiUrl } from "@/lib/api";

type Stage = "config" | "loading" | "result" | "error";
interface Issue { original: string; suggestion: string; reason: string; }
interface Result { improved_text: string; issues: Issue[]; score: number; summary: string; }

const FOCUS = [
  { v: "all", l: "All" },
  { v: "grammar", l: "Grammar" },
  { v: "style", l: "Style" },
  { v: "clarity", l: "Clarity" },
];

export default function WritingCoachPage() {
  const { t, i18n } = useTranslation();
  const [stage, setStage] = useState<Stage>("config");
  const [text, setText] = useState("");
  const [focus, setFocus] = useState("all");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!text.trim()) return;
    setError(""); setStage("loading");
    try {
      const res = await fetch(apiUrl("/api/v1/market-tools/writing-coach"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, focus, language: i18n.language }),
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
        <span>/</span><span className="text-[var(--foreground)]">{t("Writing Coach")}</span>
      </div>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-pink-500/10"><SpellCheck size={20} className="text-pink-500" /></div>
        <div><h1 className="text-xl font-semibold text-[var(--foreground)]">{t("Writing Coach")}</h1><p className="text-xs text-[var(--muted-foreground)]">{t("Polish your writing and learn from each fix")}</p></div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Your writing")}</label>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={7} placeholder={t("Paste a paragraph or essay to improve...")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Focus")}</label>
            <div className="flex gap-2">
              {FOCUS.map((x) => (
                <button key={x.v} onClick={() => setFocus(x.v)}
                  className={`rounded-lg border px-3 py-2 text-xs ${focus === x.v ? "border-pink-500/50 bg-pink-500/10 text-pink-400" : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"}`}>{t(x.l)}</button>
              ))}
            </div>
          </div>
          <button onClick={submit} className="flex w-full items-center justify-center gap-2 rounded-lg bg-pink-500 px-4 py-2.5 text-sm font-medium text-white hover:opacity-90">{t("Improve Writing")}</button>
        </div>
      )}
      {stage === "loading" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><Loader2 size={36} className="animate-spin text-pink-500" /><p className="text-sm text-[var(--muted-foreground)]">{t("Reviewing your writing...")}</p></div>)}
      {stage === "error" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><p className="text-sm text-red-400">{error}</p><button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">{t("Back")}</button></div>)}
      {stage === "result" && result && (
        <div className="max-w-2xl space-y-4">
          <div className="flex items-center gap-4 rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
            <p className="text-3xl font-bold text-[var(--foreground)]">{result.score}<span className="text-base text-[var(--muted-foreground)]">/100</span></p>
            <p className="flex-1 text-sm text-[var(--muted-foreground)]">{result.summary}</p>
          </div>
          {result.improved_text && (
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
              <p className="mb-2 text-xs font-semibold text-emerald-400">{t("Improved Version")}</p>
              <p className="text-sm leading-relaxed text-[var(--foreground)] whitespace-pre-wrap">{result.improved_text}</p>
            </div>
          )}
          {result.issues?.length > 0 && (
            <div className="space-y-2">
              {result.issues.map((it, i) => (
                <div key={i} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-3 text-xs">
                  <p><span className="text-rose-400 line-through">{it.original}</span> → <span className="text-emerald-400">{it.suggestion}</span></p>
                  {it.reason && <p className="mt-1 text-[var(--muted-foreground)]">{it.reason}</p>}
                </div>
              ))}
            </div>
          )}
          <button onClick={() => { setStage("config"); setResult(null); }} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">{t("Revise Another")}</button>
        </div>
      )}
    </div>
  );
}
