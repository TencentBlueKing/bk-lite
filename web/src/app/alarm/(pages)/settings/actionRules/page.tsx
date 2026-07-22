'use client';

import React, { useMemo } from 'react';
import OperateModal from './components/operateModal';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import Introduction from '@/app/alarm/components/introduction';
import { ActionRuleListItem } from '@/app/alarm/types/settings';
import { useSettingApi } from '@/app/alarm/api/settings';
import { Button, Input, Switch, Tag, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ACTION_TRIGGER_EVENTS, ACTION_TYPES } from '@/app/alarm/constants/settings';
import { useSettingsTable } from '@/app/alarm/hooks/useSettingsTable';

const ActionRules: React.FC = () => {
  const { t } = useTranslation();
  const { getActionRuleList, deleteActionRule, patchActionRule } = useSettingApi();

  const {
    tableLoading,
    loadingIds,
    operateVisible,
    setOperateVisible,
    searchKey,
    setSearchKey,
    dataList,
    currentRow,
    pagination,
    handleEdit,
    handleDelete,
    handleFilterChange,
    handleFilterClear,
    handleTableChange,
    handleStatusToggle,
    refreshList,
  } = useSettingsTable<ActionRuleListItem>({
    fetchList: getActionRuleList,
    deleteItem: deleteActionRule,
    patchItem: patchActionRule,
  });

  const triggerEventLabelMap = useMemo(
    () => Object.fromEntries(ACTION_TRIGGER_EVENTS.map(({ value, label }) => [value, label])),
    []
  );

  const actionTypeLabelMap = useMemo(
    () => Object.fromEntries(ACTION_TYPES.map(({ value, label }) => [value, label])),
    []
  );

  const renderMatchRulesSummary = (matchRules: ActionRuleListItem['match_rules']): string => {
    if (!matchRules || matchRules.length === 0) return '--';
    const orParts = matchRules.map((orGroup) => {
      if (!orGroup || orGroup.length === 0) return '';
      return orGroup
        .map((cond) => `${cond.key} ${cond.operator} ${cond.value}`)
        .join(' AND ');
    });
    const summary = orParts.filter(Boolean).join(' OR ');
    return summary.length > 60 ? `${summary.slice(0, 60)}...` : summary;
  };

  const columns = useMemo(
    () => [
      {
        title: t('settings.actionRuleName'),
        dataIndex: 'name',
        key: 'name',
        width: 150,
      },
      {
        title: t('settings.actionTriggerEvent'),
        dataIndex: 'trigger_events',
        key: 'trigger_events',
        width: 220,
        render: (events: string[]) =>
          events && events.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {events.map((e) => (
                <Tag key={e}>{triggerEventLabelMap[e] || e}</Tag>
              ))}
            </div>
          ) : (
            '--'
          ),
      },
      {
        title: t('settings.assignStrategy.formMatchingRules'),
        dataIndex: 'match_rules',
        key: 'match_rules',
        width: 250,
        render: (matchRules: ActionRuleListItem['match_rules']) => (
          <Tooltip title={renderMatchRulesSummary(matchRules)}>
            <span className="truncate block max-w-[220px]">
              {renderMatchRulesSummary(matchRules)}
            </span>
          </Tooltip>
        ),
      },
      {
        title: t('settings.actionType'),
        dataIndex: 'action_type',
        key: 'action_type',
        width: 120,
        render: (type: ActionRuleListItem['action_type']) => (
          <Tag>{actionTypeLabelMap[type] || type}</Tag>
        ),
      },
      {
        title: t('settings.assignStartStop'),
        dataIndex: 'is_active',
        key: 'is_active',
        width: 110,
        render: (val: boolean, row: ActionRuleListItem) => (
          <Switch
            loading={!!loadingIds[row.id]}
            checked={val}
            onChange={(checked) => handleStatusToggle(row, checked)}
          />
        ),
      },
      {
        title: t('settings.assignActions'),
        key: 'operation',
        width: 130,
        render: (_: unknown, row: ActionRuleListItem) => (
          <div className="flex gap-4">
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button
                type="link"
                size="small"
                onClick={() => handleEdit('edit', row)}
              >
                {t('common.edit')}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['Delete']}>
              <Button
                type="link"
                size="small"
                danger
                onClick={() => handleDelete(row)}
              >
                {t('common.delete')}
              </Button>
            </PermissionWrapper>
          </div>
        ),
      },
    ],
    [t, loadingIds, handleStatusToggle, handleEdit, handleDelete, triggerEventLabelMap, actionTypeLabelMap]
  );

  return (
    <>
      <Introduction
        title={t('settings.actionRuleTitle')}
        message={t('settings.actionRuleMessage')}
      />
      <div className="oid-library-container p-4 bg-[var(--color-bg-1)] rounded-lg shadow">
        <div className="nav-box flex justify-between mb-[20px]">
          <div className="flex items-center">
            <Input
              allowClear
              value={searchKey}
              placeholder={t('common.search')}
              style={{ width: 250 }}
              onChange={(e) => setSearchKey(e.target.value)}
              onPressEnter={handleFilterChange}
              onClear={handleFilterClear}
            />
          </div>
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button type="primary" onClick={() => handleEdit('add')}>
              {t('common.addNew')}
            </Button>
          </PermissionWrapper>
        </div>
        <CustomTable
          size="middle"
          rowKey="id"
          loading={tableLoading}
          columns={columns}
          dataSource={dataList}
          pagination={pagination}
          onChange={handleTableChange}
          scroll={{ y: 'calc(100vh - 440px)' }}
        />
        <OperateModal
          open={operateVisible}
          onClose={() => setOperateVisible(false)}
          currentRow={currentRow}
          onSuccess={() => refreshList({ current: 1 })}
        />
      </div>
    </>
  );
};

export default ActionRules;
