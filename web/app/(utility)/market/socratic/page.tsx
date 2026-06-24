"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, MessagesSquare, Loader2, Send } from "lucide-react";
import { apiUrl } from "@/lib/api";

interface Turn { role: "student" | "tutor"; content: string; }

export default function SocraticPage() {
  const { t, i18n } = useTranslation();
  const [topic, setTopic] = useState("");
  const [started, setStarted] = useState(false);
  const [history, setHistory] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const send = async (message: string) => {
    if (!message.trim()) return;
    const newHistory: Turn[] = [...history, { role: "student", content: message }];
    setHistory(newHistory); setInput(""); setLoading(true); setError("");
    try {
      const res = await fetch(apiUrl("/api/v1/market-tools/socratic"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, history, student_message: message, language: i18n.language }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setHistory([...newHistory, { role: "tutor", content: data.reply || "" }]);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : t("Generation failed")); }
    setLoading(false);
    setTimeout(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }), 50);
  };

  const begin = () => {
    if (!topic.trim()) return;
    setStarted(true);
    send(t("I want to understand this topic. Can you guide me?"));
  };

  return (
    <div className="flex h-full flex-col overflow-hidden p-8">
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link href="/market" className="flex items-center gap-1.5 hover:text-[var(--foreground)]"><ArrowLeft size={14} /> {t("Market")}</Link>
        <span>/</span><span className="text-[var(--foreground)]">{t("Socratic Tutor")}</span>
      </div>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-500/10"><MessagesSquare size={20} className="text-blue-500" /></div>
        <div><h1 className="text-xl font-semibold text-[var(--foreground)]">{t("Socratic Tutor")}</h1><p className="text-xs text-[var(--muted-foreground)]">{t("Learn by being guided with questions, not answers")}</p></div>
      </div>

      {!started ? (
        <div className="max-w-2xl space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-[var(--muted-foreground)]">{t("What do you want to understand?")}</label>
            <input value={topic} onChange={(e) => setTopic(e.target.value)} onKeyDown={(e) => e.key === "Enter" && begin()}
              placeholder={t("e.g. Why does ice float on water?")}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
          </div>
          <button onClick={begin} className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-500 px-4 py-2.5 text-sm font-medium text-white hover:opacity-90">{t("Start Session")}</button>
        </div>
      ) : (
        <div className="flex flex-1 flex-col overflow-hidden">
          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto pb-4">
            {history.map((turn, i) => (
              <div key={i} className={`flex ${turn.role === "student" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm ${turn.role === "student" ? "bg-blue-500 text-white" : "border border-[var(--border)] bg-[var(--secondary)] text-[var(--foreground)]"}`}>
                  {turn.content}
                </div>
              </div>
            ))}
            {loading && <div className="flex justify-start"><div className="rounded-2xl border border-[var(--border)] bg-[var(--secondary)] px-4 py-2.5"><Loader2 size={16} className="animate-spin text-blue-500" /></div></div>}
            {error && <p className="text-center text-xs text-red-400">{error}</p>}
          </div>
          <div className="flex gap-2 border-t border-[var(--border)] pt-4">
            <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && !loading && send(input)}
              placeholder={t("Type your thoughts or answer...")}
              className="flex-1 rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-3 py-2 text-sm text-[var(--foreground)] outline-none" />
            <button onClick={() => send(input)} disabled={loading || !input.trim()} className="flex items-center justify-center rounded-lg bg-blue-500 px-4 text-white hover:opacity-90 disabled:opacity-40"><Send size={16} /></button>
          </div>
        </div>
      )}
    </div>
  );
}
