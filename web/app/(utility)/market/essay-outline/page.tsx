"use client";

import Link from "next/link";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, PenLine, Loader2 } from "lucide-react";
import { apiUrl } from "@/lib/api";

type Stage = "config" | "loading" | "result" | "error";
interface Section { section: string; points: string[]; }
interface Result { thesis: string; hook: string; sections: Section[]; conclusion_idea: string; tips: string[]; }

const TYPES = [
  { v: "argumentative", l: "Argumentative" },
  { v: "expository", l: "Expository" },
  { v: "narrative", l: "Narrative" },
  { v: "letter", l: "Letter" },
];

export default function EssayOutlinePage() {
  const { t, i18n } = useTranslation();
  const [stage, setStage] = useState<Stage>("config");
  const [prompt, setPrompt] = useState("");
  const [type, setType] = useState("argumentative");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!prompt.trim()) return;
    setError(""); setStage("loading");
    try {
      const res = await fetch(apiUrl("/api/v1/market-tools/essay-outline"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, essay_type: type, language: i18n.language }),
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
        <span>/</span><span className="text-[var(--foreground)]">{t("Essay Outline")}</span>
      </div>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-fuchsia-500/10"><PenLine size={20} className="text-fuchsia-500" /></div>
        <div><h1 className="text-xl font-semibold text-[var(--foreground)]">{t("Essay Outline")}</h1><p className="text-xs text-[var(--muted-foreground)]">{t("Turn a prompt into a clear thesis and structure")}</p></div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Essay Prompt")}</label>
            <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3} placeholder={t("e.g. Should social media be regulated?")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Essay Type")}</label>
            <div className="flex flex-wrap gap-2">
              {TYPES.map((x) => (
                <button key={x.v} onClick={() => setType(x.v)}
                  className={`rounded-lg border px-3 py-2 text-xs ${type === x.v ? "border-fuchsia-500/50 bg-fuchsia-500/10 text-fuchsia-400" : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"}`}>{t(x.l)}</button>
              ))}
            </div>
          </div>
          <button onClick={submit} className="flex w-full items-center justify-center gap-2 rounded-lg bg-fuchsia-500 px-4 py-2.5 text-sm font-medium text-white hover:opacity-90">{t("Build Outline")}</button>
        </div>
      )}
      {stage === "loading" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><Loader2 size={36} className="animate-spin text-fuchsia-500" /><p className="text-sm text-[var(--muted-foreground)]">{t("Structuring your essay...")}</p></div>)}
      {stage === "error" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><p className="text-sm text-red-400">{error}</p><button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">{t("Back")}</button></div>)}
      {stage === "result" && result && (
        <div className="max-w-2xl space-y-4">
          <div className="rounded-xl border border-fuchsia-500/30 bg-fuchsia-500/5 p-4"><p className="text-xs font-semibold text-fuchsia-400">{t("Thesis")}</p><p className="mt-1 text-sm text-[var(--foreground)]">{result.thesis}</p></div>
          {result.hook && <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4"><p className="text-xs font-semibold text-[var(--muted-foreground)]">{t("Hook")}</p><p className="mt-1 text-sm text-[var(--foreground)]">{result.hook}</p></div>}
          {(result.sections || []).map((s, i) => (
            <div key={i} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
              <p className="mb-2 text-sm font-semibold text-[var(--foreground)]">{s.section}</p>
              <ul className="list-disc space-y-1 pl-4 text-sm text-[var(--muted-foreground)]">{(s.points || []).map((p, j) => (<li key={j}>{p}</li>))}</ul>
            </div>
          ))}
          {result.conclusion_idea && <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4"><p className="text-xs font-semibold text-[var(--muted-foreground)]">{t("Conclusion")}</p><p className="mt-1 text-sm text-[var(--foreground)]">{result.conclusion_idea}</p></div>}
          {result.tips?.length > 0 && <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4"><p className="mb-1 text-xs font-semibold text-[var(--muted-foreground)]">{t("Tips")}</p><ul className="list-disc space-y-1 pl-4 text-xs text-[var(--muted-foreground)]">{result.tips.map((tip, i) => (<li key={i}>{tip}</li>))}</ul></div>}
          <button onClick={() => { setStage("config"); setResult(null); }} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">{t("New Outline")}</button>
        </div>
      )}
    </div>
  );
}
