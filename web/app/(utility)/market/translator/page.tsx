"use client";

import Link from "next/link";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Languages, Loader2 } from "lucide-react";
import { apiUrl } from "@/lib/api";

type Stage = "config" | "loading" | "result" | "error";
interface GlossaryItem { term: string; translation: string; note: string; }
interface Result { translation: string; glossary: GlossaryItem[]; }

const TARGETS = ["English", "繁體中文", "简体中文"];

export default function TranslatorPage() {
  const { t, i18n } = useTranslation();
  const [stage, setStage] = useState<Stage>("config");
  const [text, setText] = useState("");
  const [target, setTarget] = useState("English");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!text.trim()) return;
    setError(""); setStage("loading");
    try {
      const res = await fetch(apiUrl("/api/v1/market-tools/translator"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, target_lang: target, language: i18n.language }),
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
        <span>/</span><span className="text-[var(--foreground)]">{t("Translator & Glossary")}</span>
      </div>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-500/10"><Languages size={20} className="text-emerald-500" /></div>
        <div><h1 className="text-xl font-semibold text-[var(--foreground)]">{t("Translator & Glossary")}</h1><p className="text-xs text-[var(--muted-foreground)]">{t("Translate academic text and learn key terms")}</p></div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Text to translate")}</label>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={6} placeholder={t("Paste text in any language...")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Translate into")}</label>
            <div className="flex gap-2">
              {TARGETS.map((x) => (
                <button key={x} onClick={() => setTarget(x)}
                  className={`rounded-lg border px-3 py-2 text-xs ${target === x ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-400" : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"}`}>{x}</button>
              ))}
            </div>
          </div>
          <button onClick={submit} className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-500 px-4 py-2.5 text-sm font-medium text-white hover:opacity-90">{t("Translate")}</button>
        </div>
      )}
      {stage === "loading" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><Loader2 size={36} className="animate-spin text-emerald-500" /><p className="text-sm text-[var(--muted-foreground)]">{t("Translating...")}</p></div>)}
      {stage === "error" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><p className="text-sm text-red-400">{error}</p><button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">{t("Back")}</button></div>)}
      {stage === "result" && result && (
        <div className="max-w-2xl space-y-4">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">{t("Translation")}</p>
            <p className="text-sm leading-relaxed text-[var(--foreground)] whitespace-pre-wrap">{result.translation}</p>
          </div>
          {result.glossary?.length > 0 && (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
              <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">{t("Glossary")}</p>
              <div className="space-y-2">
                {result.glossary.map((g, i) => (
                  <div key={i} className="text-sm">
                    <span className="font-medium text-emerald-400">{g.term}</span>
                    <span className="text-[var(--muted-foreground)]"> — {g.translation}</span>
                    {g.note && <span className="text-xs text-[var(--muted-foreground)]/70"> ({g.note})</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
          <button onClick={() => { setStage("config"); setResult(null); }} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">{t("New Translation")}</button>
        </div>
      )}
    </div>
  );
}
