"use client";

import Link from "next/link";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Network, Loader2 } from "lucide-react";
import { apiUrl } from "@/lib/api";

type Stage = "config" | "loading" | "result" | "error";
interface Node { id: string; label: string; description: string; }
interface Edge { from: string; to: string; relation: string; }
interface Result { root: string; nodes: Node[]; edges: Edge[]; grounded?: boolean; }

export default function ConceptMapPage() {
  const { t, i18n } = useTranslation();
  const [stage, setStage] = useState<Stage>("config");
  const [topic, setTopic] = useState("");
  const [kb, setKb] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!topic.trim()) return;
    setError(""); setStage("loading");
    try {
      const res = await fetch(apiUrl("/api/v1/market-tools/concept-map"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, kb_name: kb || undefined, language: i18n.language }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setResult(data); setStage("result");
    } catch (e: unknown) { setError(e instanceof Error ? e.message : t("Generation failed")); setStage("error"); }
  };

  const labelOf = (id: string) => result?.nodes.find((n) => n.id === id)?.label || id;

  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market" className="flex items-center gap-1.5 hover:text-[var(--foreground)]"><ArrowLeft size={14} /> {t("Market")}</Link>
        <span>/</span><span className="text-[var(--foreground)]">{t("Concept Map")}</span>
      </div>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sky-500/10"><Network size={20} className="text-sky-500" /></div>
        <div><h1 className="text-xl font-semibold text-[var(--foreground)]">{t("Concept Map")}</h1><p className="text-xs text-[var(--muted-foreground)]">{t("Visualize how ideas connect")}</p></div>
      </div>

      {stage === "config" && (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Topic")}</label>
            <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder={t("e.g. The water cycle")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("Knowledge Base (optional)")}</label>
            <input value={kb} onChange={(e) => setKb(e.target.value)} placeholder={t("e.g. hkdse-math")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <button onClick={submit} className="flex w-full items-center justify-center gap-2 rounded-lg bg-sky-500 px-4 py-2.5 text-sm font-medium text-white hover:opacity-90">{t("Build Map")}</button>
        </div>
      )}
      {stage === "loading" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><Loader2 size={36} className="animate-spin text-sky-500" /><p className="text-sm text-[var(--muted-foreground)]">{t("Mapping the concepts...")}</p></div>)}
      {stage === "error" && (<div className="flex flex-1 flex-col items-center justify-center gap-4"><p className="text-sm text-red-400">{error}</p><button onClick={() => setStage("config")} className="text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">{t("Back")}</button></div>)}
      {stage === "result" && result && (
        <div className="max-w-3xl space-y-5">
          <div className="rounded-xl border border-sky-500/30 bg-sky-500/5 p-4 text-center">
            <p className="text-sm font-semibold text-sky-400">{result.root}</p>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {(result.nodes || []).map((n) => (
              <div key={n.id} className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
                <p className="text-sm font-semibold text-[var(--foreground)]">{n.label}</p>
                <p className="mt-1 text-xs text-[var(--muted-foreground)]">{n.description}</p>
              </div>
            ))}
          </div>
          {result.edges?.length > 0 && (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--secondary)] p-4">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">{t("Connections")}</p>
              <ul className="space-y-1.5 text-xs text-[var(--muted-foreground)]">
                {result.edges.map((e, i) => (
                  <li key={i}><span className="text-[var(--foreground)]">{labelOf(e.from)}</span> <span className="text-sky-400">→ {e.relation} →</span> <span className="text-[var(--foreground)]">{labelOf(e.to)}</span></li>
                ))}
              </ul>
            </div>
          )}
          <button onClick={() => { setStage("config"); setResult(null); }} className="rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-5 py-2.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]">{t("New Map")}</button>
        </div>
      )}
    </div>
  );
}
