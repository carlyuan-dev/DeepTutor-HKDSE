"use client";

import Link from "next/link";
import { ArrowLeft, ArrowRight, Languages, type LucideIcon } from "lucide-react";

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
    icon: Languages,
    name: "Chinese Exam Paper Generator",
    nameZh: "中文試卷生成",
    description:
      "老師或學生選擇知識庫（上載的教科書 / 歷屆試卷），設定題型和難度，系統自動生成一份符合 HKDSE 格式的中文閱讀理解試卷，附標準答案。",
    steps: [
      "選擇知識庫和篇章類型（文言文 / 白話文）",
      "設定題數、難度和題型比例",
      "點擊生成，取得完整試卷及答案",
    ],
    href: "/market/hkdse/chinese/paper-generator",
  },
  {
    id: "F2",
    icon: Languages,
    name: "Chinese Essay Marker",
    nameZh: "中文作文批改",
    description:
      "學生提交中文作文，AI 按 HKDSE 評分準則（內容、表達、組織）逐項給分，並提供具體的修改意見。",
    steps: [
      "貼上作文文本，輸入題目（可選）",
      "AI 按三個評分項目打分",
      "查看逐段批注和整體改進建議",
    ],
    href: "/market/hkdse/chinese/essay-grader",
  },
  {
    id: "F3",
    icon: Languages,
    name: "Classical Chinese Assistant",
    nameZh: "文言文精讀助手",
    description:
      "學生輸入文言文段落，系統提供逐句語譯、重點字詞注釋，並自動生成理解題讓學生練習。",
    steps: [
      "輸入或貼上文言文段落",
      "查看逐句白話語譯和字詞注釋",
      "完成系統生成的理解題並查看答案",
    ],
    href: "/market/hkdse/chinese/analyzer",
  },
];

export default function ChinesePage() {
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
        <span className="text-[var(--foreground)]">Chinese Language</span>
      </div>

      {/* Subject header */}
      <div className="mb-8 flex items-center gap-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-rose-500/10">
          <Languages size={24} strokeWidth={1.5} className="text-rose-500" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-[var(--foreground)]">Chinese Language</h1>
            <span className="rounded-md border border-[var(--border)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--muted-foreground)]/60">
              CHIN
            </span>
          </div>
          <p className="text-sm text-rose-500">中國語文</p>
        </div>
      </div>

      {/* Feature cards */}
      <div className="max-w-2xl space-y-4">
        {FEATURES.map((feat) => (
          <div
            key={feat.id}
            className="rounded-2xl border border-[var(--border)] bg-[var(--secondary)] p-5"
          >
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[11px] text-[var(--muted-foreground)]/50">
                  {feat.id}
                </span>
                <span className={`rounded-full border px-2 py-0.5 text-[10px] ${feat.href ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400" : "border-[var(--border)] text-[var(--muted-foreground)]/60"}`}>
                  {feat.href ? "Ready" : "Pending"}
                </span>
              </div>
            </div>

            <p className="text-sm font-semibold text-[var(--foreground)]">{feat.name}</p>
            <p className="mb-3 text-xs text-rose-500">{feat.nameZh}</p>
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
