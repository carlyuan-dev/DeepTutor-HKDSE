"use client";

import Link from "next/link";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, NotebookPen, Loader2 } from "lucide-react";
import { apiUrl } from "@/lib/api";

type Stage = "config" | "generating" | "result" | "error";

interface NoteSection { heading: string; points: string[]; }
interface KeyTerm { term: string; definition: string; }
interface NoteResult {
  title: string;
  summary: string;
  sections: NoteSection[];
  key_terms: KeyTerm[];
  mnemonic: string;
}

const STYLES = [
  { value: "outline", label: "Outline" },
  { value: "cornell", label: "Cornell" },
  { value: "mindmap", label: "Mind Map" },
];

export default function NoteMakerPage() {
  const { t, i18n } = useTranslation();
  const [stage, setStage] = useState<Stage>("config");
  const [topic, setTopic] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [kb, setKb] = useState("");
  const [style, setStyle] = useState("outline");
  const [result, setResult] = useState<NoteResult | null>(null);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!topic.trim() && !sourceText.trim()) return;
    setError("");
    setStage("generating");
    try {
      const res = await fetch(apiUrl("/api/v1/market-tools/note-maker"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, source_text: sourceText, kb_name: kb || undefined, style, language: i18n.language }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setResult(data);
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
        <span className="text-[var(--foreground)]">{t("Smart Notes")}</span>
      </div>

      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-teal-500/10">
          <NotebookPen size={20} className="text-teal-500" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-[var(--foreground)]">{t("Smart Notes")}</h1>
          <p className="text-xs text-[var(--muted-foreground)]">{t("Turn a topic or pasted text into structured revision notes")}</p>
        </div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Topic")}</label>
            <input value={topic} onChange={(e) => setTopic(e.target.value)}
              placeholder={t("e.g. The French Revolution")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Or paste source text (optional)")}</label>
            <textarea value={sourceText} onChange={(e) => setSourceText(e.target.value)} rows={5}
              placeholder={t("Paste an article, chapter, or notes to condense...")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <div className="flex gap-4">
            <div className="flex-1 space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Knowledge Base (optional)")}</label>
              <input value={kb} onChange={(e) => setKb(e.target.value)}
                placeholder={t("e.g. hkdse-chinese")}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
            </div>
            <div className="flex-1 space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Style")}</label>
              <div className="flex gap-2">
                {STYLES.map((s) => (
                  <button key={s.value} onClick={() => setStyle(s.value)}
                    className={`rounded-lg border px-3 py-2 text-xs ${style === s.value ? "border-teal-500/50 bg-teal-500/10 text-teal-400" : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"}`}>
                    {t(s.label)}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <button onClick={submit} className="flex w-full items-center justify-center gap-2 rounded-lg bg-teal-500 px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90">
            {t("Generate Notes")}
          </button>
        </div>
      )}

      {stage === "generating" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <Loader2 size={36} className="animate-spin text-teal-500" />
          <p className="text-sm text-[var(--muted-foreground)]">{t("Writing your notes...")}</p>
        </div>
      )}

      {stage === "error" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <p className="text-sm text-red-400">{error}</p>
          <button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">{t("Back")}</button>
        </div>
      )}

      {stage === "result" && result && (
        <div className="max-w-3xl space-y-4">
          <div>
            <h2 className="text-lg font-semibold text-[var(--foreground)]">{result.title}</h2>
            {result.summary && <p className="mt-1 text-sm text-[var(--muted-foreground)]">{result.summary}</p>}
          </div>
          {(result.sections || []).map((sec, i) => (
            <div key={i} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
              <p className="mb-2 text-sm font-semibold text-[var(--foreground)]">{sec.heading}</p>
              <ul className="list-disc space-y-1 pl-4 text-sm text-[var(--muted-foreground)]">
                {(sec.points || []).map((p, j) => (<li key={j}>{p}</li>))}
              </ul>
            </div>
          ))}
          {result.key_terms?.length > 0 && (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-5">
              <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">{t("Key Terms")}</p>
              <dl className="space-y-2">
                {result.key_terms.map((kt, i) => (
                  <div key={i} className="flex gap-2 text-sm">
                    <dt className="font-medium text-teal-400">{kt.term}</dt>
                    <dd className="text-[var(--muted-foreground)]">— {kt.definition}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
          {result.mnemonic && (
            <div className="rounded-xl border border-teal-500/30 bg-teal-500/5 p-4">
              <p className="text-xs font-semibold text-teal-400">{t("Memory Aid")}</p>
              <p className="mt-1 text-sm text-[var(--foreground)]">{result.mnemonic}</p>
            </div>
          )}
          <button onClick={() => { setStage("config"); setResult(null); }} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">
            {t("New Notes")}
          </button>
        </div>
      )}
    </div>
  );
}
