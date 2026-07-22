'use client';

import { useMemo, useRef } from 'react';
import { Flex, Select, Space, Spin } from 'antd';
import ContentFormDrawer from '@/components/content-form-drawer';
import StatusBadgeShell from '@/components/status-badge-shell';
import { useTranslation } from '@/utils/i18n';
import {
  buildInlineSegments,
  buildSideBySideDiffRows,
  getDiffAccentClassName,
} from './diffUtils';
import type {
  CmdbConfigFileCompareTargetLike as ConfigFileItem,
  CmdbConfigFileVersionLike as ConfigFileVersion,
} from './types';

const formatDateTime = (value: string) => {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);
};

export interface CmdbConfigFileCompareDrawerProps {
  open: boolean;
  loading: boolean;
  compareTarget: ConfigFileItem | null;
  versionList: ConfigFileVersion[];
  leftVersionId: number | undefined;
  rightVersionId: number | undefined;
  leftContent: string;
  rightContent: string;
  onClose: () => void;
  onLeftVersionChange: (id: number) => void;
  onRightVersionChange: (id: number | undefined) => void;
}

const CmdbConfigFileCompareDrawer = ({
  open,
  loading,
  compareTarget,
  versionList,
  leftVersionId,
  rightVersionId,
  leftContent,
  rightContent,
  onClose,
  onLeftVersionChange,
  onRightVersionChange,
}: CmdbConfigFileCompareDrawerProps) => {
  const { t } = useTranslation();
  const leftPaneRef = useRef<HTMLDivElement | null>(null);
  const rightPaneRef = useRef<HTMLDivElement | null>(null);
  const syncingScrollRef = useRef(false);

  const syncScroll = (source: 'left' | 'right') => {
    const sourcePane =
      source === 'left' ? leftPaneRef.current : rightPaneRef.current;
    const targetPane =
      source === 'left' ? rightPaneRef.current : leftPaneRef.current;
    if (!sourcePane || !targetPane || syncingScrollRef.current) return;

    syncingScrollRef.current = true;
    targetPane.scrollTop = sourcePane.scrollTop;
    targetPane.scrollLeft = sourcePane.scrollLeft;
    requestAnimationFrame(() => {
      syncingScrollRef.current = false;
    });
  };

  const versionOptions = useMemo(
    () =>
      versionList.map((item) => ({
        label: `${item.version} | ${formatDateTime(item.created_at)}`,
        value: item.id,
      })),
    [versionList],
  );

  const leftVersion = useMemo(
    () => versionList.find((item) => item.id === leftVersionId),
    [leftVersionId, versionList],
  );

  const rightVersion = useMemo(
    () => versionList.find((item) => item.id === rightVersionId),
    [rightVersionId, versionList],
  );

  const diffRows = useMemo(
    () => buildSideBySideDiffRows(leftContent, rightContent),
    [leftContent, rightContent],
  );

  const diffRowsWithSegments = useMemo(
    () =>
      diffRows.map((row) => ({
        ...row,
        segments: buildInlineSegments(row.leftText, row.rightText),
      })),
    [diffRows],
  );

  const diffSummary = useMemo(
    () =>
      diffRows.reduce(
        (acc, row) => {
          if (row.status === 'changed') acc.changed += 1;
          if (row.status === 'added') acc.added += 1;
          if (row.status === 'removed') acc.removed += 1;
          return acc;
        },
        { changed: 0, added: 0, removed: 0 },
      ),
    [diffRows],
  );

  return (
    <ContentFormDrawer
      title={
        compareTarget
          ? `${t('ConfigFile.versionCompare')} · ${compareTarget.file_name}`
          : t('ConfigFile.versionCompare')
      }
      width={1320}
      open={open}
      onClose={onClose}
      hideFooter
    >
      <div className="flex h-full flex-col gap-4">
        <div className="rounded-2xl border border-[var(--color-border)] bg-white p-4 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
          <Flex justify="space-between" align="start" gap={16} wrap="wrap">
            <Space wrap size={12}>
              <Select
                placeholder={t('ConfigFile.selectLeftVersion')}
                value={leftVersionId}
                options={versionOptions}
                style={{ width: 330 }}
                onChange={onLeftVersionChange}
              />
              <Select
                placeholder={t('ConfigFile.selectRightVersion')}
                value={rightVersionId}
                options={versionOptions.filter(
                  (option) => option.value !== leftVersionId,
                )}
                style={{ width: 330 }}
                onChange={onRightVersionChange}
                allowClear
              />
            </Space>
            <Space wrap size={8}>
              <StatusBadgeShell
                label={`${t('ConfigFile.modified')} ${diffSummary.changed}`}
                palette={{
                  textColor: 'var(--color-warning)',
                  backgroundColor:
                    'color-mix(in srgb, var(--color-warning) 12%, transparent)',
                }}
              />
              <StatusBadgeShell
                label={`${t('ConfigFile.added')} ${diffSummary.added}`}
                palette={{
                  textColor: 'var(--color-success)',
                  backgroundColor:
                    'color-mix(in srgb, var(--color-success) 12%, transparent)',
                }}
              />
              <StatusBadgeShell
                label={`${t('ConfigFile.removed')} ${diffSummary.removed}`}
                palette={{
                  textColor: 'var(--color-error)',
                  backgroundColor:
                    'color-mix(in srgb, var(--color-error) 12%, transparent)',
                }}
              />
            </Space>
          </Flex>
        </div>

        <Spin spinning={loading}>
          <div className="grid h-[calc(100vh-220px)] grid-cols-2 gap-4">
            <div className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--color-border)] bg-white shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
              <div className="border-b border-[var(--color-border)] bg-[var(--color-fill-1)] px-4 py-3">
                <div className="text-xs text-[var(--color-text-secondary)]">
                  {t('ConfigFile.leftVersion')}
                </div>
                <div className="mt-1 font-mono text-[13px] text-[var(--color-text-primary)]">
                  {leftVersion?.version || '--'}
                </div>
                <div className="text-xs text-[var(--color-text-secondary)]">
                  {leftVersion ? formatDateTime(leftVersion.created_at) : '--'}
                </div>
              </div>
              <div
                ref={leftPaneRef}
                onScroll={() => syncScroll('left')}
                className="min-h-0 flex-1 overflow-auto bg-[#0f172a] px-0 py-3"
              >
                {diffRowsWithSegments.length ? (
                  diffRowsWithSegments.map((row) => (
                    <div
                      key={`${row.key}-left`}
                      className="grid grid-cols-[56px_1fr] text-xs leading-6 text-[#e2e8f0]"
                    >
                      <div className="px-3 py-1 text-right font-mono text-[#64748b]">
                        {row.leftNumber ?? ''}
                      </div>
                      <pre
                        className={`overflow-x-auto px-3 py-1 whitespace-pre-wrap break-all ${getDiffAccentClassName(row.status, 'left')}`}
                      >
                        {row.segments.left.map((segment, index) => (
                          <span
                            key={`${row.key}-left-${index}`}
                            className={
                              segment.changed
                                ? 'rounded-sm bg-amber-300/20 px-0.5 text-amber-100'
                                : ''
                            }
                          >
                            {segment.text || (index === 0 ? ' ' : '')}
                          </span>
                        ))}
                      </pre>
                    </div>
                  ))
                ) : (
                  <div className="px-4 py-10 text-center text-sm text-[#94a3b8]">
                    {t('ConfigFile.selectVersionHint')}
                  </div>
                )}
              </div>
            </div>

            <div className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--color-border)] bg-white shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
              <div className="border-b border-[var(--color-border)] bg-[var(--color-fill-1)] px-4 py-3">
                <div className="text-xs text-[var(--color-text-secondary)]">
                  {t('ConfigFile.rightVersion')}
                </div>
                <div className="mt-1 font-mono text-[13px] text-[var(--color-text-primary)]">
                  {rightVersion?.version || '--'}
                </div>
                <div className="text-xs text-[var(--color-text-secondary)]">
                  {rightVersion ? formatDateTime(rightVersion.created_at) : '--'}
                </div>
              </div>
              <div
                ref={rightPaneRef}
                onScroll={() => syncScroll('right')}
                className="min-h-0 flex-1 overflow-auto bg-[#0f172a] px-0 py-3"
              >
                {diffRowsWithSegments.length ? (
                  diffRowsWithSegments.map((row) => (
                    <div
                      key={`${row.key}-right`}
                      className="grid grid-cols-[56px_1fr] text-xs leading-6 text-[#e2e8f0]"
                    >
                      <div className="px-3 py-1 text-right font-mono text-[#64748b]">
                        {row.rightNumber ?? ''}
                      </div>
                      <pre
                        className={`overflow-x-auto px-3 py-1 whitespace-pre-wrap break-all ${getDiffAccentClassName(row.status, 'right')}`}
                      >
                        {row.segments.right.map((segment, index) => (
                          <span
                            key={`${row.key}-right-${index}`}
                            className={
                              segment.changed
                                ? 'rounded-sm bg-amber-300/20 px-0.5 text-amber-100'
                                : ''
                            }
                          >
                            {segment.text || (index === 0 ? ' ' : '')}
                          </span>
                        ))}
                      </pre>
                    </div>
                  ))
                ) : (
                  <div className="px-4 py-10 text-center text-sm text-[#94a3b8]">
                    {t('ConfigFile.selectVersionHint')}
                  </div>
                )}
              </div>
            </div>
          </div>
        </Spin>
      </div>
    </ContentFormDrawer>
  );
};

export default CmdbConfigFileCompareDrawer;
