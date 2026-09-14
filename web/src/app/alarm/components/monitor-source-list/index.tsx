'use client';

import React, { useState } from 'react';
import { Button, Tag } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import { useCopy } from '@/hooks/useCopy';
import { useTranslation } from '@/utils/i18n';

interface MonitorSourceListProps {
  sources?: string[];
  showCopy?: boolean;
}

const VISIBLE_COUNT = 3;

const MonitorSourceList: React.FC<MonitorSourceListProps> = ({ sources = [], showCopy = true }) => {
  const { t } = useTranslation();
  const { copy } = useCopy();
  const [expanded, setExpanded] = useState(false);
  if (!sources.length) return <>--</>;
  const visibleSources = expanded ? sources : sources.slice(0, VISIBLE_COUNT);

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1">
      {visibleSources.map((source) => (
        <Tag key={source} className="m-0 max-w-full whitespace-normal break-all">
          {source}
        </Tag>
      ))}
      {sources.length > VISIBLE_COUNT && (
        <Button
          type="link"
          size="small"
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? t('alarmCommon.collapseSources') : `${t('alarmCommon.expandSources')} (${sources.length})`}
        </Button>
      )}
      {showCopy && <Button
        type="text"
        size="small"
        icon={<CopyOutlined />}
        aria-label={t('alarmCommon.copySources')}
        title={t('alarmCommon.copySources')}
        onClick={() => copy(sources.join('\n'))}
      />}
    </div>
  );
};

export default MonitorSourceList;
