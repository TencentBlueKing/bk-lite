import React from 'react';
import { Tooltip } from 'antd';
import {
  resolveCardListAccentPresentation,
  type CardListAccentStyle,
} from '@/app/ops-analysis/utils/cardList';

interface CardListAccentProps {
  text: string;
  style?: CardListAccentStyle;
  kind: 'leading' | 'badge';
}

export const CardListAccent: React.FC<CardListAccentProps> = ({
  text,
  style,
  kind,
}) => {
  const presentation = resolveCardListAccentPresentation(text, style);

  if (presentation.mode === 'colorDot') {
    return (
      <Tooltip placement="top" title={presentation.tooltipText}>
        <span
          role="img"
          aria-label={presentation.tooltipText}
          data-accent-mode="colorDot"
          className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
          style={{ background: presentation.color }}
        >
          <span className="sr-only">{presentation.tooltipText}</span>
        </span>
      </Tooltip>
    );
  }

  if (presentation.mode === 'textWithBackground') {
    return (
      <span
        data-accent-mode="textWithBackground"
        className="inline-flex max-w-full truncate rounded-full px-2 py-0.5 text-xs font-medium"
        style={{
          color: presentation.color,
          backgroundColor: presentation.backgroundColor,
        }}
      >
        {presentation.displayText}
      </span>
    );
  }

  const color =
    presentation.mode === 'text' ? presentation.color : undefined;
  const displayText = presentation.displayText;

  if (kind === 'badge') {
    return (
      <span
        data-accent-mode={color ? 'text' : 'plain'}
        className="inline-flex max-w-full truncate rounded-sm bg-(--color-primary-bg-active) px-1.5 py-0.5 text-xs font-medium text-(--color-text-1)"
        style={color ? { color, fontWeight: 600 } : undefined}
      >
        {displayText}
      </span>
    );
  }

  return (
    <span
      data-accent-mode={color ? 'text' : 'plain'}
      className="shrink-0 text-xs font-medium tabular-nums text-(--color-text-3)"
      style={color ? { color, fontWeight: 600 } : undefined}
    >
      {displayText}
    </span>
  );
};
