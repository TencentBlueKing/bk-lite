'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button, Drawer, Input, Select, Tooltip } from 'antd';
import { SyncOutlined } from '@ant-design/icons';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useSkillApi } from '@/app/opspilot/api/skill';
import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import ToolbarSplitShell from '@/components/toolbar-split-shell';
import CompactEmptyState from '@/components/compact-empty-state';
import CustomChatSSE from '@/app/opspilot/components/custom-chat-sse';
import { processHistoryMessageWithExtras } from '@/app/opspilot/components/custom-chat-sse/historyMessageProcessor';
import type { CustomChatMessage } from '@/app/opspilot/types/global';

interface SkillChannelOption {
  id: number;
  name: string;
  channel_type: string;
}

interface AdminConversationRow {
  session_id: string;
  title: string;
  channel_id: number;
  channel_type: string;
  channel_name: string;
  person_display: string;
  count?: number;
  created_at?: string | null;
  updated_at?: string | null;
}

const toChatMessages = (rows: any[]): CustomChatMessage[] =>
  (rows || []).map((row: any) => {
    const role = row.conversation_role === 'user' ? 'user' : 'bot';
    const processed = processHistoryMessageWithExtras(row.conversation_content, role);
    return {
      id: String(row.id),
      role,
      content: processed.content,
      createAt: row.conversation_time,
      thinking: processed.thinking,
      isThinking: false,
      browserStepsHistory: processed.browserStepsHistory ?? null,
      agentStepProgress: processed.agentStepProgress,
      plannedExecutionSteps: processed.plannedExecutionSteps,
      wikiCitations: processed.wikiCitations,
      toolCalls: processed.toolCalls,
      isStreamingTools: false,
      configDiffReports: processed.configDiffReports,
      configAnalysisReports: processed.configAnalysisReports,
      userChoiceRequests: processed.userChoiceRequests,
      approvalRequests: processed.approvalRequests,
      repairCommands: processed.repairCommands,
      reportFileDownloads: processed.reportFileDownloads,
    };
  });

const SkillHistoryPage: React.FC = () => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const searchParams = useSearchParams();
  const skillId = searchParams?.get('id') || '';
  const { fetchSkillChannels, fetchAdminSkillConversations, fetchAdminSkillSessionMessages } = useSkillApi();

  const [channels, setChannels] = useState<SkillChannelOption[]>([]);
  const [channelId, setChannelId] = useState<number | undefined>();
  const [person, setPerson] = useState('');
  const [items, setItems] = useState<AdminConversationRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10 });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTitle, setDrawerTitle] = useState('');
  const [drawerMessages, setDrawerMessages] = useState<CustomChatMessage[]>([]);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const filtersRef = useRef({ channelId, person });
  filtersRef.current = { channelId, person };

  const apiRef = useRef({
    fetchSkillChannels,
    fetchAdminSkillConversations,
    fetchAdminSkillSessionMessages,
  });
  apiRef.current = {
    fetchSkillChannels,
    fetchAdminSkillConversations,
    fetchAdminSkillSessionMessages,
  };

  const channelLabel = useCallback(
    (type: string, name: string) => {
      const typeLabel = t(`skill.channel.types.${type}`, type);
      return name ? `${typeLabel} · ${name}` : typeLabel;
    },
    [t]
  );

  const formatTime = useCallback(
    (value?: string | null) => (value ? convertToLocalizedTime(value) : '--'),
    [convertToLocalizedTime]
  );

  const loadConversations = useCallback(
    async (page = pagination.current, pageSize = pagination.pageSize) => {
      if (!skillId) {
        setItems([]);
        setTotal(0);
        return;
      }
      const filters = filtersRef.current;
      setLoading(true);
      try {
        const params: Record<string, string | number | undefined> = {
          skill_id: skillId,
          page,
          page_size: pageSize,
        };
        if (filters.channelId) params.channel_id = filters.channelId;
        if (filters.person.trim()) params.person = filters.person.trim();
        const data = await apiRef.current.fetchAdminSkillConversations(params);
        setItems(data.items || []);
        setTotal(data.count || 0);
      } catch {
        setItems([]);
        setTotal(0);
      } finally {
        setLoading(false);
      }
    },
    [skillId, pagination.current, pagination.pageSize]
  );

  useEffect(() => {
    if (!skillId) {
      return;
    }
    apiRef.current.fetchSkillChannels(skillId).then((rows) => {
      setChannels(Array.isArray(rows) ? rows : []);
    }).catch(() => setChannels([]));
  }, [skillId]);

  useEffect(() => {
    loadConversations(pagination.current, pagination.pageSize);
  }, [loadConversations, pagination.current, pagination.pageSize, channelId]);

  const openConversation = useCallback(async (record: AdminConversationRow) => {
    setDrawerTitle(record.title || t('skill.history.drawerTitle', '会话详情'));
    setDrawerOpen(true);
    setDrawerLoading(true);
    setDrawerMessages([]);
    try {
      const messages = await apiRef.current.fetchAdminSkillSessionMessages(record.session_id);
      setDrawerMessages(toChatMessages(messages));
    } catch {
      setDrawerMessages([]);
    } finally {
      setDrawerLoading(false);
    }
  }, [t]);

  const columns = useMemo(
    () => [
      {
        title: t('skill.history.channel', '渠道'),
        dataIndex: 'channel_name',
        key: 'channel',
        render: (_: string, row: AdminConversationRow) => {
          const label = channelLabel(row.channel_type, row.channel_name);
          return <EllipsisWithTooltip text={label} className="truncate block" />;
        },
      },
      {
        title: t('skill.history.user', '用户'),
        dataIndex: 'person_display',
        key: 'user',
        render: (value: string) => (
          <EllipsisWithTooltip text={value} className="truncate block" />
        ),
      },
      {
        title: t('skill.history.title', '标题'),
        dataIndex: 'title',
        key: 'title',
        render: (text: string) => (
          <EllipsisWithTooltip text={text} className="truncate block w-full" />
        ),
      },
      {
        title: t('skill.history.createdAt', '创建时间'),
        dataIndex: 'created_at',
        key: 'created_at',
        width: 180,
        render: (value: string) => formatTime(value),
      },
      {
        title: t('skill.history.updatedAt', '更新时间'),
        dataIndex: 'updated_at',
        key: 'updated_at',
        width: 180,
        render: (value: string) => formatTime(value),
      },
      {
        title: t('skill.history.count', '数量'),
        dataIndex: 'count',
        key: 'count',
        width: 80,
        render: (value: number) => value ?? 0,
      },
      {
        title: t('common.actions', '操作'),
        key: 'actions',
        width: 80,
        render: (_: unknown, row: AdminConversationRow) => (
          <Button
            type="link"
            className="px-0"
            onClick={(event) => {
              event.stopPropagation();
              openConversation(row);
            }}
          >
            {t('skill.history.detail', '详情')}
          </Button>
        ),
      },
    ],
    [channelLabel, formatTime, openConversation, t]
  );

  return (
    <div className="flex h-full flex-col">
      <ToolbarSplitShell
        trailing={
          <>
            <Select
              allowClear
              className="w-[220px]"
              placeholder={t('skill.history.filterChannel', '全部渠道')}
              value={channelId}
              options={channels.map((item) => ({
                value: item.id,
                label: channelLabel(item.channel_type, item.name),
              }))}
              onChange={(value) => {
                setChannelId(value);
                setPagination((prev) => ({ ...prev, current: 1 }));
              }}
            />
            <Input.Search
              allowClear
              enterButton
              className="w-60"
              placeholder={t('skill.history.filterUser', '请输入用户名进行搜索...')}
              value={person}
              onChange={(event) => setPerson(event.target.value)}
              onSearch={() => {
                setPagination((prev) => ({ ...prev, current: 1 }));
                loadConversations(1, pagination.pageSize);
              }}
            />
            <Tooltip title={t('common.refresh', '刷新')}>
              <Button icon={<SyncOutlined />} onClick={() => loadConversations(pagination.current, pagination.pageSize)} />
            </Tooltip>
          </>
        }
      />
      <div className="min-w-0">
        {!loading && items.length === 0 ? (
          <CompactEmptyState description={t('skill.history.empty', '暂无会话记录')} />
        ) : (
          <CustomTable<AdminConversationRow>
            size="middle"
            rowKey="session_id"
            loading={loading}
            dataSource={items}
            columns={columns}
            autoScrollX={false}
            scroll={{ y: 'auto' }}
            pagination={{
              current: pagination.current,
              pageSize: pagination.pageSize,
              total,
              showSizeChanger: true,
              onChange: (page, pageSize) => setPagination({ current: page, pageSize: pageSize || 10 }),
            }}
          />
        )}
      </div>
      <Drawer
        title={drawerTitle || t('skill.history.drawerTitle', '会话详情')}
        open={drawerOpen}
        width={1000}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
        styles={{ body: { padding: 0, overflow: 'hidden' } }}
      >
        {drawerLoading ? (
          <div className="py-10 text-center text-[var(--color-text-3)]">{t('common.loading', '加载中')}</div>
        ) : (
          <div className="h-full">
            <CustomChatSSE
              initialMessages={drawerMessages}
              mode="display"
              showHeader={false}
              requirePermission={false}
            />
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default SkillHistoryPage;
