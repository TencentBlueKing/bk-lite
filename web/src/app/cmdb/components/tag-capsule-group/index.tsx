import React from 'react';
import { Tag, Tooltip } from 'antd';
import styles from './index.module.scss';
import { getTagColorByLabel, normalizeTagValues } from '@/app/cmdb/utils/tag';

interface TagCapsuleGroupProps {
  value: unknown;
  maxVisible?: number;
  compact?: boolean;
  showTooltip?: boolean;
}

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
    <span className={`${styles.tagCapsuleGroup} ${compact ? styles.compact : ''}`}>
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
