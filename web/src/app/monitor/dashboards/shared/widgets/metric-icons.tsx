import React from 'react';

/**
 * Bespoke duotone metric icons for KPI cards.
 *
 * Each icon is a self-contained 34×34 squircle that draws its own gradient fill
 * + inset ring + duotone glyph. All color comes from `currentColor` (set by the
 * card's icon color via the wrapper's inline `color`), so a single color drives
 * the gradient, ring, and glyph. Drawn on a shared 24-unit visual grid with a
 * consistent 1.8px round stroke for a cohesive, modern (non-Splunk-palette) set.
 */

interface IconProps {
  gradId: string;
}

const Squircle = ({ gradId }: IconProps) => (
  <>
    <defs>
      <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="currentColor" stopOpacity="0.16" />
        <stop offset="1" stopColor="currentColor" stopOpacity="0.05" />
      </linearGradient>
    </defs>
    <rect
      x="0.5"
      y="0.5"
      width="33"
      height="33"
      rx="10.5"
      fill={`url(#${gradId})`}
      stroke="currentColor"
      strokeOpacity="0.22"
    />
  </>
);

const svgProps = {
  viewBox: '0 0 34 34',
  fill: 'none',
  xmlns: 'http://www.w3.org/2000/svg',
  width: 34,
  height: 34
} as const;

const stroke = {
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const
};

/** 节点健康 — heartbeat over a soft monitor surface */
export const HealthIcon = () => (
  <svg {...svgProps}>
    <Squircle gradId="miHealthGrad" />
    <rect x="9" y="9.5" width="16" height="15" rx="4" fill="currentColor" fillOpacity="0.16" />
    <path d="M9.5 17.5h3l1.6-3.6 2.6 6.4 1.8-4h3.5" {...stroke} />
  </svg>
);

/** 内存使用率 — RAM chip with pins */
export const MemoryIcon = () => (
  <svg {...svgProps}>
    <Squircle gradId="miMemGrad" />
    <rect x="9.5" y="11.5" width="15" height="11" rx="2" fill="currentColor" fillOpacity="0.16" />
    <rect x="9.5" y="11.5" width="15" height="11" rx="2" {...stroke} />
    <path d="M13 22.5v2M17 22.5v2M21 22.5v2M13 9.5v2M17 9.5v2M21 9.5v2" {...stroke} />
    <path d="M14.5 15.5v3M19.5 15.5v3" {...stroke} />
  </svg>
);

/** 未确认占比 — envelope with a pending dot */
export const UnackedIcon = () => (
  <svg {...svgProps}>
    <Squircle gradId="miUnackedGrad" />
    <rect x="8.5" y="10.5" width="17" height="12" rx="2.5" fill="currentColor" fillOpacity="0.14" />
    <rect x="8.5" y="10.5" width="17" height="12" rx="2.5" {...stroke} />
    <path d="M9 12l8 5.5L25 12" {...stroke} />
    <circle cx="23.5" cy="10.5" r="3" fill="currentColor" />
  </svg>
);

/** 消息积压 — stacked message layers */
export const BacklogIcon = () => (
  <svg {...svgProps}>
    <Squircle gradId="miBacklogGrad" />
    <rect x="9" y="9.5" width="16" height="4.5" rx="1.5" fill="currentColor" fillOpacity="0.18" />
    <rect x="9" y="15" width="16" height="4.5" rx="1.5" {...stroke} />
    <rect x="9" y="20.5" width="16" height="4.5" rx="1.5" {...stroke} />
  </svg>
);

/** 发布速率 — paper plane / send throughput */
export const PublishIcon = () => (
  <svg {...svgProps}>
    <Squircle gradId="miPublishGrad" />
    <path d="M24.5 9.5l-15 6 5.5 2.2" fill="currentColor" fillOpacity="0.18" />
    <path d="M24.5 9.5l-15 6 5.5 2.2 1.8 5.3L24.5 9.5z" {...stroke} />
    <path d="M15 17.7l3.3-2.6" {...stroke} />
  </svg>
);
