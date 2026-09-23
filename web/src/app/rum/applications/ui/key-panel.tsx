'use client';

import { useState } from 'react';
import { Button, Popconfirm, Tag, Tooltip } from 'antd';
import { CheckOutlined, CopyOutlined, ReloadOutlined } from '@ant-design/icons';

import RumPermission from '@/app/rum/components/rum-permission';
import { useTranslation } from '@/utils/i18n';

const toolIconClass =
  'shrink-0 text-[var(--color-text-3)] hover:!text-[var(--color-primary)]';

export default function KeyPanel({
  browserKey,
  onReissue,
  reissuePending = false,
  autoIssued = false,
}: {
  browserKey: string;
  onReissue: () => void;
  reissuePending?: boolean;
  autoIssued?: boolean;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const copyLabel = copied ? t('rum.common.copied', '已复制') : t('rum.common.copy', '复制');
  const reissueLabel = t('rum.detail.reissue', '重新签发');

  async function copy() {
    if (!browserKey) return;
    await navigator.clipboard.writeText(browserKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{t('rum.detail.currentKey', '当前将使用')}</span>
        {autoIssued ? <Tag color="success">{t('rum.detail.issued', '已签发')}</Tag> : null}
      </div>
      <div className="flex max-w-xl items-center gap-1">
        <code className="min-w-0 flex-1 truncate rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-2)] px-3 py-2 font-mono text-xs">
          {browserKey || t('rum.detail.keyEmpty', '尚未签发 Browser Key')}
        </code>
        <Tooltip title={copyLabel}>
          <Button
            type="text"
            size="small"
            className={toolIconClass}
            icon={copied ? <CheckOutlined aria-hidden="true" /> : <CopyOutlined aria-hidden="true" />}
            disabled={!browserKey}
            aria-label={copyLabel}
            onClick={() => void copy()}
          />
        </Tooltip>
        {reissuePending ? (
          <Tooltip title={reissueLabel}>
            <Button
              type="text"
              size="small"
              className={toolIconClass}
              icon={<ReloadOutlined aria-hidden="true" />}
              disabled
              aria-label={reissueLabel}
            />
          </Tooltip>
        ) : (
          <RumPermission resource="applications" action="Operate">
            <Popconfirm
              title={reissueLabel}
              description={t(
                'rum.detail.reissueConfirm',
                '确认重新签发？旧 Key 立即失效，已部署页面需同步更新。',
              )}
              onConfirm={onReissue}
              okText={reissueLabel}
              cancelText={t('rum.common.cancel', '取消')}
            >
              <Tooltip title={reissueLabel}>
                <Button
                  type="text"
                  size="small"
                  className={toolIconClass}
                  icon={<ReloadOutlined aria-hidden="true" />}
                  aria-label={reissueLabel}
                />
              </Tooltip>
            </Popconfirm>
          </RumPermission>
        )}
      </div>
    </div>
  );
}
