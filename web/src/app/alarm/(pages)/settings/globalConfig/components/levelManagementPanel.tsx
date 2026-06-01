'use client';

import React from 'react';
import PermissionWrapper from '@/components/permission';
import LevelIcon from '@/app/alarm/components/levelIcon';
import { useTranslation } from '@/utils/i18n';
import { Grid, Typography, Row, Col, Table, Tag, Button, Space } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined } from '@ant-design/icons';
import { LevelItem, LevelMetaGroup } from '@/app/alarm/types/index';
import { BRAND, NEUTRAL } from '@/app/alarm/constants/colors';

const getLevelTagStyle = (color?: string, compact?: boolean) => ({
  backgroundColor: color || BRAND.LEVEL_FALLBACK_AMBER,
  color: NEUTRAL.ON_DARK_FG,
  border: 'none',
  borderRadius: compact ? 7 : 8,
  display: 'inline-flex',
  alignItems: 'center',
  gap: compact ? 2 : 4,
  paddingInline: compact ? 5 : 7,
  paddingBlock: compact ? 2 : 3,
  marginInlineEnd: 0,
  fontSize: compact ? 11 : 12,
  lineHeight: 1.4,
  maxWidth: '100%',
});

interface LevelManagementPanelProps {
  levelMeta: Record<string, LevelMetaGroup>;
  onOpenLevelModal: (
    levelType: 'event' | 'alert' | 'incident',
    row?: LevelItem,
  ) => void;
  onDeleteLevel: (row: LevelItem) => void;
}

export default function LevelManagementPanel({
  levelMeta,
  onOpenLevelModal,
  onDeleteLevel,
}: LevelManagementPanelProps) {
  const { t } = useTranslation();
  const screens = Grid.useBreakpoint();
  const isCompactLevelView = !screens.md || !!screens.xl;
  const levelNameTextMaxWidth = isCompactLevelView ? 78 : 126;

  const levelTypeTitles: Record<'event' | 'alert' | 'incident', string> = {
    event: t('settings.globalConfig.eventLevel'),
    alert: t('settings.globalConfig.alertLevel'),
    incident: t('settings.globalConfig.incidentLevel'),
  };

  const addLevelButtonText = t('settings.globalConfig.addLevel')
    .replace(/\s*等级$/u, '')
    .replace(/\s+levels?$/iu, '')
    .trim();

  const levelColumns: ColumnsType<LevelItem> = [
    {
      title: t('settings.globalConfig.levelId'),
      dataIndex: 'level_id',
      key: 'level_id',
      width: isCompactLevelView ? 64 : 84,
      align: 'center',
    },
    {
      title: t('settings.globalConfig.levelDisplayEffect'),
      dataIndex: 'level_display_name',
      key: 'level_display_name',
      width: isCompactLevelView ? 140 : 228,
      render: (_value, record) => (
        <Tag style={getLevelTagStyle(record.color, isCompactLevelView)}>
          <span
            className={
              isCompactLevelView
                ? 'flex h-3 w-3 shrink-0 items-center justify-center leading-none'
                : 'flex h-3.5 w-3.5 shrink-0 items-center justify-center leading-none'
            }
          >
            <LevelIcon
              icon={record.icon}
              className={isCompactLevelView ? 'h-3 w-3' : 'h-3.5 w-3.5'}
              style={{ color: NEUTRAL.ON_DARK_FG, lineHeight: 1 }}
            />
          </span>
          <span
            className="truncate"
            style={{ maxWidth: levelNameTextMaxWidth }}
            title={record.level_display_name}
          >
            {record.level_display_name}
          </span>
        </Tag>
      ),
    },
    {
      title: t('settings.globalConfig.levelActions'),
      key: 'actions',
      width: isCompactLevelView ? 98 : 124,
      render: (_value, record) => (
        <Space size={isCompactLevelView ? 8 : 10}>
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button
              type="link"
              size="small"
              className="px-0 text-[#2F6BFF]"
              onClick={() =>
                onOpenLevelModal(
                  record.level_type as 'event' | 'alert' | 'incident',
                  record,
                )
              }
            >
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button
              type="link"
              size="small"
              danger
              className="px-0"
              onClick={() => onDeleteLevel(record)}
            >
              {t('common.delete')}
            </Button>
          </PermissionWrapper>
        </Space>
      ),
    },
  ];

  return (
    <div className="mt-4 rounded-2xl border border-(--color-border-1) bg-(--color-bg-1) p-3 sm:p-3.5">
      <div className="mb-3">
        <div className="flex items-center gap-2">
          <span className="inline-block h-4 w-1 rounded-full bg-[#2F6BFF]" />
          <Typography.Title level={4} style={{ margin: 0, fontSize: '15px' }}>
            {t('settings.globalConfig.levelPanelTitle')}
          </Typography.Title>
        </div>
        <div className="mt-1 pl-3 text-[12px] leading-5 text-(--color-text-3)">
          {t('settings.globalConfig.levelPanelDescription')}
        </div>
      </div>
      <div className="overflow-hidden">
        <Row gutter={[24, 24]} align="stretch">
          {(['event', 'alert', 'incident'] as const).map((levelType) => {
            const group = levelMeta[levelType];

            return (
              <Col xs={24} lg={12} xl={8} key={levelType} className="flex">
                <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-(--color-border-1) bg-(--color-bg-1)">
                  <div
                    className="flex items-center justify-between border-b border-(--color-border-1) px-2.5 py-1.5 sm:px-3 sm:py-2"
                    style={{
                      background:
                        'color-mix(in srgb, var(--color-fill-1) 58%, white)',
                    }}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-[14px] font-medium text-(--color-text-1) sm:text-[15px]">
                        {levelTypeTitles[levelType]}
                      </span>
                    </div>
                    <PermissionWrapper requiredPermissions={['Edit']}>
                      <Button
                        type="link"
                        size="small"
                        className="px-0"
                        onClick={() => onOpenLevelModal(levelType)}
                      >
                        <span className="inline-flex items-center gap-0.5">
                          <PlusOutlined className="text-[10px]" />
                          <span>{addLevelButtonText}</span>
                        </span>
                      </Button>
                    </PermissionWrapper>
                  </div>
                  <div className="px-2.5 py-1.5 sm:px-3 sm:py-2">
                    <Table
                      className="level-table-clean"
                      rowKey="id"
                      size="small"
                      pagination={false}
                      tableLayout="fixed"
                      sticky
                      scroll={{ y: 280 }}
                      columns={levelColumns}
                      dataSource={group?.list || []}
                    />
                  </div>
                </div>
              </Col>
            );
          })}
        </Row>
      </div>
    </div>
  );
}
