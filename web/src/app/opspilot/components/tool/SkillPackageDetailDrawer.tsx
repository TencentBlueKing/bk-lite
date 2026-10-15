'use client';

import React from 'react';
import { Descriptions, Divider, Drawer, Tag } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import MarkdownRenderer from '@/components/markdown';
import Icon from '@/components/icon';
import type { SkillPackage } from '@/app/opspilot/types/skill';
import { useTranslation } from '@/utils/i18n';

interface SkillPackageDetailDrawerProps {
  asset: SkillPackage | null;
  open: boolean;
  onClose: () => void;
}

type Translate = (
  key: string,
  defaultMessage?: string,
  values?: Record<string, string | number>,
) => string;

const getSkillAssetSourceLabel = (sourceType: string | undefined, t: Translate) => {
  if (sourceType === 'builtin') return t('tool.sourceBuiltin', '内置');
  if (sourceType === 'zip') return t('tool.sourceImported', '导入');
  return sourceType || t('common.noData');
};

const renderTagList = (items: string[] | undefined, t: Translate) => {
  if (!items?.length) {
    return <CompactEmptyState description={t('common.noData')} />;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => (
        <Tag key={item} className="m-0">{item}</Tag>
      ))}
    </div>
  );
};

const SkillPackageDetailDrawer: React.FC<SkillPackageDetailDrawerProps> = ({
  asset,
  open,
  onClose,
}) => {
  const { t } = useTranslation();
  const displayName = asset?.display_name || asset?.name || t('tool.detailTitle', '技能包详情');
  const displayDescription =
    asset?.description_tr || asset?.description || t('skill.settings.noDescription');

  return (
    <Drawer
      title={displayName}
      placement="right"
      onClose={onClose}
      open={open}
      width={680}
    >
      {asset && (
        <div className="space-y-5">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
            <div className="flex items-start gap-3">
              <Icon type="jinengpeixun" className="shrink-0 text-4xl" />
              <div className="min-w-0 flex-1">
                <h2 className="truncate text-base font-semibold text-[var(--color-text-1)]">{displayName}</h2>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-[var(--color-text-3)]">
                  {displayDescription}
                </p>
              </div>
            </div>
          </div>

          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label={t('common.name')}>
              {displayName || t('common.noData')}
            </Descriptions.Item>
            <Descriptions.Item label={t('tool.packageId', '包 ID')}>
              {asset.package_id || t('common.noData')}
            </Descriptions.Item>
            <Descriptions.Item label={t('common.version')}>
              {asset.version || t('common.noData')}
            </Descriptions.Item>
            <Descriptions.Item label={t('common.category')}>
              {asset.category || t('common.noData')}
            </Descriptions.Item>
            <Descriptions.Item label={t('common.source')}>
              {getSkillAssetSourceLabel(asset.is_build_in ? 'builtin' : asset.source_type, t)}
            </Descriptions.Item>
            <Descriptions.Item label={t('common.enabledStatus', '启用状态')}>
              <Tag color={asset.is_enabled === false ? 'default' : 'success'}>
                {asset.is_enabled === false ? t('common.disabled', '禁用') : t('common.enabled', '启用')}
              </Tag>
            </Descriptions.Item>
          </Descriptions>

          <div>
            <Divider orientation="left">{t('tool.dependentTools', '依赖工具')}</Divider>
            {renderTagList(asset.required_tools, t)}
          </div>

          <div>
            <Divider orientation="left">{t('tool.triggers', '触发词')}</Divider>
            {renderTagList(asset.triggers, t)}
          </div>

          <div>
            <Divider orientation="left">{t('tool.fullDescription', '完整说明')}</Divider>
            {asset.skill_markdown ? (
              <div className="max-h-[520px] overflow-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                <MarkdownRenderer content={asset.skill_markdown} />
              </div>
            ) : (
              <CompactEmptyState description={t('common.noData')} />
            )}
          </div>
        </div>
      )}
    </Drawer>
  );
};

export default SkillPackageDetailDrawer;
