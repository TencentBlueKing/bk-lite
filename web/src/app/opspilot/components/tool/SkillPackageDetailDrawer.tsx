'use client';

import React from 'react';
import { Descriptions, Divider, Drawer, Empty, Tag } from 'antd';
import MarkdownRenderer from '@/components/markdown';
import Icon from '@/components/icon';
import type { SkillPackage } from '@/app/opspilot/types/skill';

interface SkillPackageDetailDrawerProps {
  asset: SkillPackage | null;
  open: boolean;
  onClose: () => void;
}

const getSkillAssetSourceLabel = (sourceType?: string) => {
  if (sourceType === 'builtin') return '内置';
  if (sourceType === 'zip') return '导入';
  return sourceType || '暂无数据';
};

const renderTagList = (items?: string[]) => {
  if (!items?.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />;
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
  return (
    <Drawer
      title={asset?.name || '技能包详情'}
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
                <h2 className="truncate text-base font-semibold text-[var(--color-text-1)]">{asset.name}</h2>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-[var(--color-text-3)]">
                  {asset.description || '暂无描述'}
                </p>
              </div>
            </div>
          </div>

          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label="名称">{asset.name || '暂无数据'}</Descriptions.Item>
            <Descriptions.Item label="包 ID">{asset.package_id || '暂无数据'}</Descriptions.Item>
            <Descriptions.Item label="版本">{asset.version || '暂无数据'}</Descriptions.Item>
            <Descriptions.Item label="分类">{asset.category || '暂无数据'}</Descriptions.Item>
            <Descriptions.Item label="来源">{getSkillAssetSourceLabel(asset.source_type)}</Descriptions.Item>
            <Descriptions.Item label="启用状态">
              <Tag color={asset.is_enabled === false ? 'default' : 'success'}>
                {asset.is_enabled === false ? '禁用' : '启用'}
              </Tag>
            </Descriptions.Item>
          </Descriptions>

          <div>
            <Divider orientation="left">依赖工具</Divider>
            {renderTagList(asset.required_tools)}
          </div>

          <div>
            <Divider orientation="left">触发词</Divider>
            {renderTagList(asset.triggers)}
          </div>

          <div>
            <Divider orientation="left">完整说明</Divider>
            {asset.skill_markdown ? (
              <div className="max-h-[520px] overflow-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                <MarkdownRenderer content={asset.skill_markdown} />
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
            )}
          </div>
        </div>
      )}
    </Drawer>
  );
};

export default SkillPackageDetailDrawer;
