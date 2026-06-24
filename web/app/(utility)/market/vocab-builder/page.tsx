"use client";

import Link from "next/link";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, BookA, Loader2 } from "lucide-react";
import { apiUrl } from "@/lib/api";

type Stage = "config" | "loading" | "result" | "error";
interface Word { word: string; definition: string; example: string; synonym: string; mnemonic: string; }
interface Result { topic: string; words: Word[]; }

export default function VocabBuilderPage() {
  const { t, i18n } = useTranslation();
  const [stage, setStage] = useState<Stage>("config");
  const [topic, setTopic] = useState("");
  const [num, setNum] = useState(10);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!topic.trim()) return;
    setError(""); setStage("loading");
    try {
      const res = await fetch(apiUrl("/api/v1/market-tools/vocab-builder"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, num_words: num, language: i18n.language }),
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
        <span>/</span><span className="text-[var(--foreground)]">{t("Vocabulary Builder")}</span>
      </div>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-lime-500/10"><BookA size={20} className="text-lime-500" /></div>
        <div><h1 className="text-xl font-semibold text-[var(--foreground)]">{t("Vocabulary Builder")}</h1><p className="text-xs text-[var(--muted-foreground)]">{t("Build word lists with examples and memory aids")}</p></div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Topic or word set")}</label>
            <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder={t("e.g. Academic verbs for essays")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Number of words")}</label>
            <input type="number" min={5} max={30} value={num} onChange={(e) => setNum(Math.max(5, Math.min(30, Number(e.target.value))))}
              className="w-32 rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <button onClick={submit} className="flex w-full items-center justify-center gap-2 rounded-lg bg-lime-500 px-4 py-2.5 text-sm font-medium text-white hover:opacity-90">{t("Build List")}</button>
        </div>
      )}
      {stage === "loading" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><Loader2 size={36} className="animate-spin text-lime-500" /><p className="text-sm text-[var(--muted-foreground)]">{t("Building your word list...")}</p></div>)}
      {stage === "error" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><p className="text-sm text-red-400">{error}</p><button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">{t("Back")}</button></div>)}
      {stage === "result" && result && (
        <div className="max-w-2xl space-y-3">
          {(result.words || []).map((w, i) => (
            <div key={i} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
              <div className="flex items-baseline gap-2">
                <p className="text-sm font-semibold text-lime-400">{w.word}</p>
                {w.synonym && <span className="text-[11px] text-[var(--muted-foreground)]/60">≈ {w.synonym}</span>}
              </div>
              <p className="mt-1 text-sm text-[var(--foreground)]">{w.definition}</p>
              {w.example && <p className="mt-1 text-xs italic text-[var(--muted-foreground)]">“{w.example}”</p>}
              {w.mnemonic && <p className="mt-1 text-xs text-indigo-400">💡 {w.mnemonic}</p>}
            </div>
          ))}
          <button onClick={() => { setStage("config"); setResult(null); }} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">{t("New List")}</button>
        </div>
      )}
    </div>
  );
}
