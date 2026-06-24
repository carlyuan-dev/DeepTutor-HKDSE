"use client";

import Link from "next/link";
import { Fragment, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Brackets, Loader2 } from "lucide-react";
import { apiUrl } from "@/lib/api";

type Stage = "config" | "loading" | "quiz" | "error";
interface Blank { id: number; answer: string; hint: string; }
interface Result { title: string; text: string; blanks: Blank[]; }

export default function ClozePage() {
  const { t, i18n } = useTranslation();
  const [stage, setStage] = useState<Stage>("config");
  const [topic, setTopic] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [num, setNum] = useState(6);
  const [result, setResult] = useState<Result | null>(null);
  const [filled, setFilled] = useState<Record<number, string>>({});
  const [checked, setChecked] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!topic.trim() && !sourceText.trim()) return;
    setError(""); setStage("loading"); setChecked(false); setFilled({});
    try {
      const res = await fetch(apiUrl("/api/v1/market-tools/cloze"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, source_text: sourceText, num_blanks: num, language: i18n.language }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setResult(data); setStage("quiz");
    } catch (e: unknown) { setError(e instanceof Error ? e.message : t("Generation failed")); setStage("error"); }
  };

  const isCorrect = (b: Blank) => (filled[b.id] || "").trim().toLowerCase() === (b.answer || "").trim().toLowerCase();
  const correctCount = result ? result.blanks.filter(isCorrect).length : 0;

  const renderText = () => {
    if (!result) return null;
    const parts = result.text.split(/(\[\[\d+\]\])/g);
    return parts.map((part, idx) => {
      const m = part.match(/^\[\[(\d+)\]\]$/);
      if (!m) return <Fragment key={idx}>{part}</Fragment>;
      const id = Number(m[1]);
      const b = result.blanks.find((x) => x.id === id);
      const ok = b && isCorrect(b);
      return (
        <input key={idx} value={filled[id] || ""} onChange={(e) => setFilled({ ...filled, [id]: e.target.value })}
          disabled={checked}
          className={`mx-1 inline-block w-28 rounded border-b-2 bg-transparent px-1 text-center text-sm outline-none ${
            checked ? (ok ? "border-emerald-500 text-emerald-400" : "border-rose-500 text-rose-400") : "border-[var(--border)] text-[var(--foreground)]"
          }`} />
      );
    });
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market" className="flex items-center gap-1.5 hover:text-[var(--foreground)]"><ArrowLeft size={14} /> {t("Market")}</Link>
        <span>/</span><span className="text-[var(--foreground)]">{t("Cloze Practice")}</span>
      </div>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-500/10"><Brackets size={20} className="text-amber-500" /></div>
        <div><h1 className="text-xl font-semibold text-[var(--foreground)]">{t("Cloze Practice")}</h1><p className="text-xs text-[var(--muted-foreground)]">{t("Fill in the blanks to test active recall")}</p></div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Topic")}</label>
            <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder={t("e.g. Cell biology")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Or paste source text (optional)")}</label>
            <textarea value={sourceText} onChange={(e) => setSourceText(e.target.value)} rows={4} placeholder={t("Paste text to turn into a cloze...")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Number of blanks")}</label>
            <input type="number" min={3} max={12} value={num} onChange={(e) => setNum(Math.max(3, Math.min(12, Number(e.target.value))))}
              className="w-32 rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <button onClick={submit} className="flex w-full items-center justify-center gap-2 rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-medium text-white hover:opacity-90">{t("Generate Exercise")}</button>
        </div>
      )}
      {stage === "loading" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><Loader2 size={36} className="animate-spin text-amber-500" /><p className="text-sm text-[var(--muted-foreground)]">{t("Creating your exercise...")}</p></div>)}
      {stage === "error" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><p className="text-sm text-red-400">{error}</p><button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">{t("Back")}</button></div>)}
      {stage === "quiz" && result && (
        <div className="max-w-2xl space-y-5">
          {result.title && <p className="text-sm font-semibold text-[var(--foreground)]">{result.title}</p>}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5 text-sm leading-loose text-[var(--foreground)]">{renderText()}</div>
          {checked && (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
              <p className="mb-2 text-sm font-semibold text-[var(--foreground)]">{correctCount} / {result.blanks.length} {t("correct")}</p>
              <ul className="space-y-1 text-xs">
                {result.blanks.map((b) => (
                  <li key={b.id} className={isCorrect(b) ? "text-emerald-400" : "text-rose-400"}>#{b.id}: {b.answer}{b.hint ? ` — ${b.hint}` : ""}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="flex gap-3">
            {!checked ? (
              <button onClick={() => setChecked(true)} className="rounded-lg bg-amber-500 px-5 py-2.5 text-sm font-medium text-white hover:opacity-90">{t("Check Answers")}</button>
            ) : (
              <button onClick={() => { setChecked(false); setFilled({}); }} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">{t("Retry")}</button>
            )}
            <button onClick={() => { setStage("config"); setResult(null); }} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">{t("New Exercise")}</button>
          </div>
        </div>
      )}
    </div>
  );
}
