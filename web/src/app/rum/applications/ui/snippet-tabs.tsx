'use client';

import { useState } from 'react';
import { Button, Tabs, Tooltip } from 'antd';
import { CheckOutlined, CopyOutlined } from '@ant-design/icons';

import { RumCodeSkeleton } from '@/app/rum/components/rum-skeleton';
import { useTranslation } from '@/utils/i18n';

type TabKey = 'npm' | 'react' | 'cdn' | 'generic';

const TABS: TabKey[] = ['npm', 'react', 'cdn', 'generic'];

export default function SnippetTabs({
  codeByTab,
  labels,
}: {
  codeByTab: Record<TabKey, string>;
  labels: Record<TabKey, string>;
}) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<TabKey>('npm');
  const [copied, setCopied] = useState(false);
  const code = codeByTab[tab] || '';
  const copyLabel = copied ? t('rum.common.copied', '已复制') : t('rum.common.copy', '复制');

  async function copy() {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Tabs
          activeKey={tab}
          onChange={(key) => setTab(key as TabKey)}
          items={TABS.map((key) => ({ key, label: labels[key] }))}
          size="small"
          className="mb-0"
        />
        <Tooltip title={copyLabel}>
          <Button
            type="text"
            size="small"
            className="shrink-0 text-[var(--color-text-3)] hover:!text-[var(--color-primary)]"
            icon={copied ? <CheckOutlined aria-hidden="true" /> : <CopyOutlined aria-hidden="true" />}
            aria-label={copyLabel}
            onClick={() => void copy()}
          />
        </Tooltip>
      </div>
      {code ? (
        <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-2)] p-3 text-xs leading-relaxed">
          <code>{code}</code>
        </pre>
      ) : (
        <RumCodeSkeleton />
      )}
    </div>
  );
}
