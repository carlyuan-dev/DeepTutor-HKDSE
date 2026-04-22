"use client";

import Link from "next/link";
import { ArrowLeft, ArrowRight, Calculator, type LucideIcon } from "lucide-react";

interface Feature {
  id: string;
  icon: LucideIcon;
  name: string;
  nameZh: string;
  description: string;
  steps: string[];
  href?: string;
}

const FEATURES: Feature[] = [
  {
    id: "F1",
    icon: Calculator,
    name: "Maths Exam Paper Generator",
    nameZh: "數學試卷生成",
    description:
      "Generate a HKDSE Compulsory Part exam paper in Paper 1 (conventional Q&A) or Paper 2 (30 MC) format. Filter by topic strand or generate a full-syllabus paper. Full worked solutions included.",
    steps: [
      "Choose Paper 1, Paper 2, or both; select topic strands",
      "Set number of questions and difficulty level",
      "Generate paper and view worked solutions alongside each question",
    ],
  },
  {
    id: "F2",
    icon: Calculator,
    name: "Step-by-Step Solution Checker",
    nameZh: "解題步驟批改",
    description:
      "Students input their full working for a maths problem step by step. AI checks each step, identifies exactly where the error occurs, explains why it is wrong, and shows the correct continuation.",
    steps: [
      "Paste the question and enter your working line by line",
      "AI checks each step and marks it correct or incorrect",
      "View the corrected working from the first error onward",
    ],
    href: "/market/hkdse/maths/step-checker",
  },
  {
    id: "F3",
    icon: Calculator,
    name: "Topic Drill",
    nameZh: "專題練習",
    description:
      "Students pick a specific topic (e.g. Quadratic Equations, Trigonometry) and receive a set of 5–15 practice questions at three difficulty levels. Each question is graded instantly with a worked solution.",
    steps: [
      "Select a topic from the HKDSE syllabus checklist",
      "Choose difficulty (Basic / Applied / Challenge) and number of questions",
      "Answer each question and view instant feedback with full solution",
    ],
  },
];

export default function MathsPage() {
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
        <span className="text-[var(--foreground)]">Mathematics</span>
      </div>

      {/* Subject header */}
      <div className="mb-8 flex items-center gap-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-amber-500/10">
          <Calculator size={24} strokeWidth={1.5} className="text-amber-500" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-[var(--foreground)]">Mathematics</h1>
            <span className="rounded-md border border-[var(--border)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--muted-foreground)]/60">
              MATH
            </span>
          </div>
          <p className="text-sm text-amber-500">數學（必修部分）</p>
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
            <p className="mb-3 text-xs text-amber-500">{feat.nameZh}</p>
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
