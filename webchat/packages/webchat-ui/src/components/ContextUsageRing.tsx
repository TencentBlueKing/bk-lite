'use client';

import React, { useEffect, useRef, useState } from 'react';
import {
  contextUsagePercent,
  formatContextTokens,
  type ContextUsageSegmentId,
  type LlmContextUsage,
} from '@webchat/core';
import { WC } from '../chrome';

const SEGMENT_COLOR: Record<ContextUsageSegmentId, string> = {
  system: WC.dim,
  tools: WC.indigo,
  skills: WC.warning,
  wiki: WC.success,
  summary: WC.fail,
  conversation: 'color-mix(in srgb, var(--color-primary, #155AEF) 45%, var(--theme-color-status-warning, #FAAD14))',
};

const SEGMENT_LABEL: Record<ContextUsageSegmentId, string> = {
  system: '系统提示',
  tools: '工具定义',
  skills: '技能包',
  wiki: 'Wiki 注入',
  summary: '已压缩摘要',
  conversation: '对话',
};

function ringStroke(percent: number): string {
  if (percent >= 90) {
    return WC.fail;
  }
  if (percent >= 75) {
    return WC.warning;
  }
  return WC.indigo;
}

function UsageRingGlyph({ percent }: { percent: number }) {
  const radius = 7;
  const circumference = 2 * Math.PI * radius;
  const filled = (Math.min(100, Math.max(0, percent)) / 100) * circumference;
  return (
    <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true">
      <circle cx="10" cy="10" r={radius} fill="none" stroke={WC.dockEdge} strokeWidth="2.4" />
      <circle
        cx="10"
        cy="10"
        r={radius}
        fill="none"
        strokeWidth="2.4"
        strokeLinecap="round"
        stroke={ringStroke(percent)}
        style={{ strokeDasharray: `${filled} ${circumference}` }}
        transform="rotate(-90 10 10)"
      />
    </svg>
  );
}

function UsagePopoverBody({ usage }: { usage: LlmContextUsage | null }) {
  if (!usage) {
    return (
      <div className="flex w-72 flex-col gap-2">
        <div className="text-sm font-medium" style={{ color: WC.headerInk }}>
          上下文用量
        </div>
        <p className="m-0 text-xs leading-5" style={{ color: WC.muted }}>
          发一条消息后，这里会显示下一次发给模型的包占了多少输入工作预算。
        </p>
      </div>
    );
  }
  const percent = contextUsagePercent(usage);
  const nearCap = percent >= 90;
  const pastCompact =
    usage.compactionThresholdTokens > 0 && usage.packetTokens >= usage.compactionThresholdTokens;
  return (
    <div className="flex w-80 flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium" style={{ color: WC.headerInk }}>
            上下文用量
          </div>
          <div className="text-xs" style={{ color: WC.muted }}>
            下一次发给模型的包
          </div>
        </div>
        <div className="text-right text-xs" style={{ color: WC.inkSoft }}>
          {percent}% 已用
          <div>
            约 {formatContextTokens(usage.packetTokens)} / {formatContextTokens(usage.inputWorkingTokens)}
          </div>
        </div>
      </div>
      <div className="flex h-2 w-full overflow-hidden rounded-sm" style={{ background: WC.botBubble }}>
        {usage.segments.map((segment) => (
          <div
            key={segment.id}
            className="h-full min-w-0"
            style={{ flexGrow: segment.tokens, flexBasis: 0, background: SEGMENT_COLOR[segment.id] }}
          />
        ))}
      </div>
      <div className="flex flex-col gap-1.5">
        {usage.segments.map((segment) => (
          <div key={segment.id} className="flex items-center gap-2 text-xs" style={{ color: WC.inkSoft }}>
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-sm"
              style={{ background: SEGMENT_COLOR[segment.id] }}
            />
            <span className="flex-1">{SEGMENT_LABEL[segment.id]}</span>
            <span style={{ color: WC.muted }}>{formatContextTokens(segment.tokens)}</span>
          </div>
        ))}
      </div>
      <p className="m-0 text-xs leading-5" style={{ color: WC.muted }}>
        分母是输入工作预算（模型窗口 {formatContextTokens(usage.windowTokens || usage.inputWorkingTokens)}
        ）。压缩线约 {formatContextTokens(usage.compactionThresholdTokens)}。
      </p>
      {usage.compacted || pastCompact ? (
        <p className="m-0 text-xs leading-5" style={{ color: WC.inkSoft }}>
          界面上的历史还在；发给模型的包里，更早的轮次已收成摘要。
        </p>
      ) : null}
      {nearCap ? (
        <p className="m-0 text-xs leading-5" style={{ color: WC.warning }}>
          接近输入工作预算。再变长会继续压缩；系统提示和本轮问题放不下时才会失败。
        </p>
      ) : null}
    </div>
  );
}

export default function ContextUsageRing({ usage }: { usage: LlmContextUsage | null }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const percent = usage ? contextUsagePercent(usage) : 0;

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const onPointerDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        className="inline-flex h-8 items-center gap-1.5 rounded px-1.5 text-xs"
        style={{ color: WC.inkSoft }}
        title="上下文用量"
        aria-label={`${percent}% 上下文用量`}
        onClick={() => setOpen((value) => !value)}
      >
        <UsageRingGlyph percent={percent} />
        <span>{percent}%</span>
      </button>
      {open ? (
        <div
          className="absolute bottom-full right-0 z-20 mb-2 rounded-lg p-3"
          style={{
            background: WC.white,
            border: `1px solid ${WC.botBorder}`,
            boxShadow: WC.shadow,
          }}
        >
          <UsagePopoverBody usage={usage} />
        </div>
      ) : null}
    </div>
  );
}
