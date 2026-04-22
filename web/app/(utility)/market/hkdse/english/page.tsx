"use client";

import Link from "next/link";
import { ArrowLeft, ArrowRight, Globe, type LucideIcon } from "lucide-react";

interface Feature {
  id: string;
  icon: LucideIcon;
  name: string;
  nameSub: string;
  description: string;
  steps: string[];
  href?: string;
}

const FEATURES: Feature[] = [
  {
    id: "F1",
    icon: Globe,
    name: "English Exam Paper Generator",
    nameSub: "英文試卷生成",
    description:
      "Select a knowledge base and generate a HKDSE Paper 1 style English reading comprehension paper. Includes multiple question types (Multiple Choice, Short Answer, Summary Writing) with a full marking scheme.",
    steps: [
      "Select knowledge base and passage type (informational / argumentative)",
      "Set number of questions, difficulty, and question type mix",
      "Generate the paper and download the marking scheme",
    ],
  },
  {
    id: "F2",
    icon: Globe,
    name: "English Essay Coach",
    nameSub: "英文作文批改",
    description:
      "Students paste their English essay and receive AI feedback scored against HKDSE Paper 2 criteria — Content, Language, and Organisation — with inline annotations and a rewritten model paragraph.",
    steps: [
      "Paste essay text and select the essay genre (argument / letter / report)",
      "AI scores each criterion and highlights errors inline",
      "Read the overall feedback and compare with the model paragraph",
    ],
  },
  {
    id: "F3",
    icon: Globe,
    name: "Integrated Skills Simulator",
    nameSub: "綜合能力練習",
    description:
      "Simulates the HKDSE Paper 3 task. Students are given two input texts, then complete Note-making, Summary writing, and an Output text (letter / report). AI gives feedback at each stage.",
    steps: [
      "Read the two provided input texts",
      "Complete Note-making → Summary → Output text in sequence",
      "Receive AI feedback and a model answer for each stage",
    ],
    href: "/market/hkdse/english/integrated",
  },
];

export default function EnglishPage() {
  return (
    <div className="flex h-full flex-col overflow-y-auto p-8">
      {/* Breadcrumb */}
      <div className="mb-6 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
        <Link
          href="/market"
          className="flex items-center gap-1.5 transition-colors hover:text-[var(--foreground)]"
        >
          <ArrowLeft size={14} />
          Market
        </Link>
        <span>/</span>
        <span className="text-[var(--foreground)]">English Language</span>
      </div>

      {/* Subject header */}
      <div className="mb-8 flex items-center gap-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-sky-500/10">
          <Globe size={24} strokeWidth={1.5} className="text-sky-500" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-[var(--foreground)]">English Language</h1>
            <span className="rounded-md border border-[var(--border)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--muted-foreground)]/60">
              ENG
            </span>
          </div>
          <p className="text-sm text-sky-500">英國語文</p>
        </div>
      </div>

      {/* Feature cards */}
      <div className="max-w-2xl space-y-4">
        {FEATURES.map((feat) => (
          <div
            key={feat.id}
            className="rounded-2xl border border-[var(--border)] bg-[var(--secondary)] p-5"
          >
            <div className="mb-3 flex items-center gap-2">
              <span className="font-mono text-[11px] text-[var(--muted-foreground)]/50">
                {feat.id}
              </span>
              <span className="rounded-full border border-[var(--border)] px-2 py-0.5 text-[10px] text-[var(--muted-foreground)]/60">
                Pending
              </span>
            </div>

            <p className="text-sm font-semibold text-[var(--foreground)]">{feat.name}</p>
            <p className="mb-3 text-xs text-sky-500">{feat.nameSub}</p>
            <p className="mb-4 text-xs leading-relaxed text-[var(--muted-foreground)]">
              {feat.description}
            </p>

            <ol className="mb-4 space-y-1">
              {feat.steps.map((step, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-[var(--muted-foreground)]">
                  <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-[var(--background)] text-[10px] font-medium text-[var(--foreground)]">
                    {i + 1}
                  </span>
                  {step}
                </li>
              ))}
            </ol>

            {feat.href && (
              <Link
                href={feat.href}
                className="inline-flex items-center gap-1 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              >
                Open page <ArrowRight size={11} />
              </Link>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
