import React from 'react';
import { Tag, Tooltip } from 'antd';
import styles from './index.module.scss';

export interface TagCapsuleGroupProps {
  value: unknown;
  maxVisible?: number;
  compact?: boolean;
  showTooltip?: boolean;
}

const TAG_COLOR_PRESETS = [
  'magenta',
  'red',
  'volcano',
  'orange',
  'gold',
  'lime',
  'green',
  'cyan',
  'blue',
  'geekblue',
  'purple',
] as const;

const normalizeTagText = (value: unknown): string => {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const candidate = record.value ?? record.label ?? record.name ?? record.key;
    if (candidate !== undefined && candidate !== null) {
      return String(candidate).trim();
    }
  }
  return String(value).trim();
};

const parseJsonArray = (value: string): unknown[] | null => {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
};

const normalizeTagValues = (value: unknown): string[] => {
  if (Array.isArray(value)) {
    return value.map((item) => normalizeTagText(item)).filter(Boolean);
  }

  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) return [];

    if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
      const parsed = parseJsonArray(trimmed);
      if (parsed) {
        return normalizeTagValues(parsed);
      }
    }

    return [trimmed];
  }

  const normalized = normalizeTagText(value);
  return normalized ? [normalized] : [];
};

const getTagColorByLabel = (label: string): string => {
  const normalized = label.trim().toLowerCase();
  if (!normalized) return TAG_COLOR_PRESETS[0];

  let hash = 2166136261;
  for (let i = 0; i < normalized.length; i++) {
    hash ^= normalized.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }

  return TAG_COLOR_PRESETS[(hash >>> 0) % TAG_COLOR_PRESETS.length];
};

const TagCapsuleGroup: React.FC<TagCapsuleGroupProps> = ({
  value,
  maxVisible = 2,
  compact = false,
  showTooltip = true,
}) => {
  const tags = normalizeTagValues(value);

  if (!tags.length) {
    return <>--</>;
  }

  const visibleCount = Math.min(maxVisible, tags.length);
  const visibleTags = tags.slice(0, visibleCount);
  const hiddenTags = tags.slice(visibleCount);
  const allTagsTitle = (
    <div className={styles.moreTooltip}>
      {tags.map((label, index) => (
        <div key={`${label}-${index}`} className={styles.moreTooltipItem}>
          {label}
        </div>
      ))}
    </div>
  );

  return (
    <span
      className={`${styles.tagCapsuleGroup} ${compact ? styles.compact : ''}`}
    >
      {visibleTags.map((label, index) => {
        const capsule = (
          <Tag
            className={styles.tagItem}
            color={getTagColorByLabel(label)}
            key={`${label}-${index}`}
          >
            <span className={styles.tagText}>{label}</span>
          </Tag>
        );

        if (!showTooltip || label.length <= 20) {
          return capsule;
        }

        return (
          <Tooltip key={`${label}-${index}-tooltip`} title={label}>
            {capsule}
          </Tooltip>
        );
      })}

      {hiddenTags.length > 0 && (
        <Tooltip title={allTagsTitle}>
          <Tag className={styles.moreTag}>+{hiddenTags.length}</Tag>
        </Tooltip>
      )}
    </span>
  );
};

export default TagCapsuleGroup;
