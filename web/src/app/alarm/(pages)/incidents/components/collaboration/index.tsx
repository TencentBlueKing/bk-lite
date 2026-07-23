'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Spin, Empty, Tag, Button, Avatar, Tooltip, message, Modal, Drawer, Select, Input, Checkbox } from 'antd';
import {
  PlusOutlined,
  StarOutlined,
  StarFilled,
  DeleteOutlined,
  UserAddOutlined,
  PaperClipOutlined,
  SearchOutlined,
  MessageOutlined,
  DownOutlined,
  UpOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useIncidentsApi } from '@/app/alarm/api/incidents';
import { useCommon } from '@/app/alarm/context/common';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import PermissionWrapper from '@/components/permission';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import type { MoreActionsDropdownItem } from '@/components/more-actions-dropdown';
import type {
  IncidentTableDataItem,
  IncidentUpdateItem,
  IncidentUpdateReply,
} from '@/app/alarm/types/incidents';
import type { UserItem } from '@/app/alarm/types/types';

/** Avatar background colors, cycled by first char of username */
const AVATAR_COLORS = [
  '#1677ff', '#52c41a', '#faad14', '#eb2f96',
  '#722ed1', '#13c2c2', '#fa541c', '#2f54eb',
];
const getAvatarColor = (name: string) =>
  AVATAR_COLORS[(name || 'A').charCodeAt(0) % AVATAR_COLORS.length];

const UPDATE_TYPE_CONFIG: Record<string, { color: string }> = {
  observation: { color: 'blue' },
  progress: { color: 'cyan' },
  conclusion: { color: 'green' },
  next_step: { color: 'orange' },
};

interface CollaborationTabProps {
  incidentDetail?: IncidentTableDataItem;
  incidentPk: string;
  onRefresh: () => void;
}

const CollaborationTab: React.FC<CollaborationTabProps> = ({
  incidentDetail,
  incidentPk,
  onRefresh,
}) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { userList } = useCommon();
  const {
    getIncidentUpdates,
    createIncidentUpdate,
    deleteIncidentUpdate,
    toggleKeyInfo,
    modifyIncidentDetail,
  } = useIncidentsApi();

  const [updates, setUpdates] = useState<IncidentUpdateItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [inviteVisible, setInviteVisible] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);

  const [updateType, setUpdateType] = useState<string>('');
  const [updateContent, setUpdateContent] = useState('');
  const [isKeyInfo, setIsKeyInfo] = useState(false);

  const [inviteUsers, setInviteUsers] = useState<string[]>([]);
  const [inviteLoading, setInviteLoading] = useState(false);

  const [filterType, setFilterType] = useState<string | undefined>(undefined);
  const [searchKeyword, setSearchKeyword] = useState('');

  const [replyingTo, setReplyingTo] = useState<number | null>(null);
  const [replyContent, setReplyContent] = useState('');
  const [replyLoading, setReplyLoading] = useState(false);
  const [expandedReplies, setExpandedReplies] = useState<Set<number>>(new Set());

  const operators = incidentDetail?.operator || [];
  const collaborators = incidentDetail?.collaborators || [];

  const fetchUpdates = useCallback(async (silent = false) => {
    if (!incidentPk) return;
    if (!silent) setLoading(true);
    try {
      const res = await getIncidentUpdates(incidentPk, { page: 1, page_size: 100 });
      setUpdates(res.items || res || []);
    } finally {
      if (!silent) setLoading(false);
    }
  }, [incidentPk]);

  useEffect(() => {
    fetchUpdates();
  }, [fetchUpdates]);

  // Poll every 15s for new updates
  useEffect(() => {
    if (!incidentPk) return;
    const timer = setInterval(() => fetchUpdates(true), 15000);
    return () => clearInterval(timer);
  }, [incidentPk, fetchUpdates]);

  const filteredUpdates = useMemo(() => {
    let result = updates;
    if (filterType) {
      result = result.filter((item) => item.update_type === filterType);
    }
    if (searchKeyword.trim()) {
      const kw = searchKeyword.trim().toLowerCase();
      result = result.filter(
        (item) =>
          item.content.toLowerCase().includes(kw) ||
          (item.author_display_name || item.author).toLowerCase().includes(kw)
      );
    }
    return result;
  }, [updates, filterType, searchKeyword]);

  const handlePublishUpdate = async () => {
    if (!updateType || !updateContent.trim()) return;
    setSubmitLoading(true);
    try {
      await createIncidentUpdate(incidentPk, {
        update_type: updateType,
        content: updateContent.trim(),
        is_key_info: isKeyInfo,
        attachments: [],
      });
      message.success(t('common.saveSuccess'));
      setDrawerVisible(false);
      setUpdateType('');
      setUpdateContent('');
      setIsKeyInfo(false);
      fetchUpdates();
    } catch {
      message.error(t('common.saveFailed'));
    } finally {
      setSubmitLoading(false);
    }
  };

  const handleReply = async (parentId: number) => {
    if (!replyContent.trim()) return;
    setReplyLoading(true);
    try {
      await createIncidentUpdate(incidentPk, {
        parent: parentId,
        update_type: 'progress',
        content: replyContent.trim(),
        attachments: [],
      });
      message.success(t('common.saveSuccess'));
      setReplyingTo(null);
      setReplyContent('');
      setExpandedReplies((prev) => new Set(prev).add(parentId));
      fetchUpdates();
    } catch {
      message.error(t('common.saveFailed'));
    } finally {
      setReplyLoading(false);
    }
  };

  const handleToggleKeyInfo = async (updateId: number) => {
    try {
      await toggleKeyInfo(incidentPk, updateId);
      fetchUpdates();
    } catch {
      message.error(t('common.saveFailed'));
    }
  };

  const handleDeleteUpdate = (updateId: number) => {
    Modal.confirm({
      title: t('common.delete'),
      content: t('common.deleteConfirm'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk: async () => {
        try {
          await deleteIncidentUpdate(incidentPk, updateId);
          message.success(t('common.deleteSuccess'));
          fetchUpdates();
        } catch {
          message.error(t('common.saveFailed'));
        }
      },
    });
  };

  const handleInvite = async () => {
    if (!inviteUsers.length) return;
    setInviteLoading(true);
    try {
      const newCollaborators = Array.from(new Set([...collaborators, ...inviteUsers]));
      await modifyIncidentDetail(incidentPk, { collaborators: newCollaborators });
      message.success(t('common.saveSuccess'));
      setInviteVisible(false);
      setInviteUsers([]);
      onRefresh();
    } catch {
      message.error(t('common.saveFailed'));
    } finally {
      setInviteLoading(false);
    }
  };

  const handleRemoveCollaborator = async (username: string) => {
    try {
      const newCollaborators = collaborators.filter((u: string) => u !== username);
      await modifyIncidentDetail(incidentPk, { collaborators: newCollaborators });
      message.success(t('common.saveSuccess'));
      onRefresh();
    } catch {
      message.error(t('common.saveFailed'));
    }
  };

  const toggleRepliesExpanded = (updateId: number) => {
    setExpandedReplies((prev) => {
      const next = new Set(prev);
      if (next.has(updateId)) next.delete(updateId);
      else next.add(updateId);
      return next;
    });
  };

  const inviteUserOptions = userList
    .filter((u: UserItem) => !operators.includes(u.username) && !collaborators.includes(u.username))
    .map((u: UserItem) => ({
      label: `${u.display_name} (${u.username})`,
      value: u.username,
    }));

  const getTypeLabel = (type: string) => {
    const map: Record<string, string> = {
      observation: t('incidents.observation'),
      progress: t('incidents.progress'),
      conclusion: t('incidents.conclusion'),
      next_step: t('incidents.nextStep'),
    };
    return map[type] || type;
  };

  const getUserRole = (username: string): string | null => {
    if (operators.includes(username)) return t('incidents.owner');
    if (collaborators.includes(username)) return t('incidents.collaborator');
    return null;
  };

  const typeFilterOptions = [
    { label: t('alarmCommon.all'), value: '' },
    { label: t('incidents.observation'), value: 'observation' },
    { label: t('incidents.progress'), value: 'progress' },
    { label: t('incidents.conclusion'), value: 'conclusion' },
    { label: t('incidents.nextStep'), value: 'next_step' },
  ];

  /* ── Render helpers ─────────────────────────────── */

  const renderReply = (reply: IncidentUpdateReply) => {
    const displayName = reply.author_display_name || reply.author;
    const role = getUserRole(reply.author);
    return (
      <div key={reply.id} className="flex gap-3 py-2 first:pt-0">
        <Avatar
          size={28}
          style={{ backgroundColor: getAvatarColor(reply.author), fontSize: 13, flexShrink: 0 }}
        >
          {displayName[0]?.toUpperCase()}
        </Avatar>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-medium">{displayName}</span>
            {role && <span className="text-xs text-gray-400">{role}</span>}
            <span className="text-xs text-gray-400">{convertToLocalizedTime(reply.created_at)}</span>
          </div>
          <div className="text-[13px] text-gray-600 mt-0.5 whitespace-pre-wrap">{reply.content}</div>
          {reply.attachments?.length > 0 && (
            <div className="mt-1 flex gap-1 flex-wrap">
              {reply.attachments.map((att, i) => (
                <a key={i} href={att.url} target="_blank" rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-blue-500 hover:text-blue-600">
                  <PaperClipOutlined />{att.name}
                </a>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderUpdateRow = (item: IncidentUpdateItem) => {
    const displayName = item.author_display_name || item.author;
    const role = getUserRole(item.author);
    const hasReplies = item.replies?.length > 0;
    const isExpanded = expandedReplies.has(item.id);
    const isReplying = replyingTo === item.id;

    const moreMenuItems: MoreActionsDropdownItem[] = [
      {
        key: 'delete',
        label: t('common.delete'),
        danger: true,
        icon: <DeleteOutlined />,
        onClick: () => handleDeleteUpdate(item.id),
      },
    ];

    return (
      <div key={item.id} className="py-3 border-b border-gray-100 last:border-b-0">
        {/* Main row */}
        <div className="flex items-start gap-3">
          {/* Avatar */}
          <Avatar
            size={36}
            style={{ backgroundColor: getAvatarColor(item.author), fontSize: 15, flexShrink: 0 }}
          >
            {displayName[0]?.toUpperCase()}
          </Avatar>

          {/* Author + role */}
          <div className="w-[90px] shrink-0 pt-0.5">
            <div className="text-[13px] font-medium leading-tight truncate">{displayName}</div>
            {role && <div className="text-xs text-gray-400 leading-tight">{role}</div>}
          </div>

          {/* Time */}
          <div className="w-[70px] shrink-0 text-xs text-gray-400 pt-1 tabular-nums">
            {convertToLocalizedTime(item.created_at).split(' ')[1] || convertToLocalizedTime(item.created_at)}
          </div>

          {/* Type tag */}
          <div className="w-[56px] shrink-0 pt-0.5">
            <Tag color={UPDATE_TYPE_CONFIG[item.update_type]?.color} className="mr-0">
              {getTypeLabel(item.update_type)}
            </Tag>
          </div>

          {/* Content + attachments */}
          <div className="flex-1 min-w-0 pt-0.5">
            <div className="text-[13px] text-gray-700 whitespace-pre-wrap break-words">
              {item.content}
            </div>
            {item.attachments?.length > 0 && (
              <div className="mt-1 flex gap-2 flex-wrap">
                {item.attachments.map((att, i) => (
                  <a key={i} href={att.url} target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-blue-500 hover:text-blue-600">
                    <PaperClipOutlined />{att.name}
                  </a>
                ))}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-0 shrink-0 pt-0.5">
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button
                type="text"
                size="small"
                className="text-xs text-gray-500 hover:text-blue-500 px-1.5"
                icon={item.is_key_info
                  ? <StarFilled className="text-yellow-500" style={{ fontSize: 13 }} />
                  : <StarOutlined style={{ fontSize: 13 }} />}
                onClick={() => handleToggleKeyInfo(item.id)}
              >
                {t('incidents.markAsKeyInfo')}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button
                type="text"
                size="small"
                className="text-xs text-gray-500 hover:text-blue-500 px-1.5"
                icon={<MessageOutlined style={{ fontSize: 13 }} />}
                onClick={() => {
                  setReplyingTo(isReplying ? null : item.id);
                  setReplyContent('');
                }}
              >
                {t('incidents.reply')}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['Edit']}>
              <MoreActionsDropdown items={moreMenuItems} placement="bottomRight" />
            </PermissionWrapper>
          </div>
        </div>

        {/* Replies toggle */}
        {hasReplies && (
          <div className="ml-[52px] mt-2">
            <Button
              type="link"
              size="small"
              className="p-0 h-auto text-xs"
              icon={isExpanded ? <UpOutlined /> : <DownOutlined />}
              onClick={() => toggleRepliesExpanded(item.id)}
            >
              {isExpanded
                ? t('incidents.collapseReplies')
                : t('incidents.expandReplies', undefined, { count: String(item.replies.length) })
              }
            </Button>
          </div>
        )}

        {/* Replies list */}
        {hasReplies && isExpanded && (
          <div className="ml-[52px] mt-1 pl-3 border-l-2 border-gray-200">
            {item.replies.map(renderReply)}
          </div>
        )}

        {/* Reply input */}
        {isReplying && (
          <div className="ml-[52px] mt-2 flex gap-2 items-start">
            <Input.TextArea
              size="small"
              rows={2}
              maxLength={1000}
              autoFocus
              placeholder={t('incidents.replyPlaceholder')}
              value={replyContent}
              onChange={(e) => setReplyContent(e.target.value)}
              className="flex-1"
            />
            <div className="flex flex-col gap-1 shrink-0">
              <Button
                type="primary"
                size="small"
                loading={replyLoading}
                disabled={!replyContent.trim()}
                onClick={() => handleReply(item.id)}
              >
                {t('incidents.reply')}
              </Button>
              <Button size="small" onClick={() => { setReplyingTo(null); setReplyContent(''); }}>
                {t('common.cancel')}
              </Button>
            </div>
          </div>
        )}
      </div>
    );
  };

  /* ── Main render ────────────────────────────────── */

  return (
    <div className="flex gap-0 h-full">
      {/* Left: Updates list */}
      <div className="flex-1 min-w-0 overflow-auto pr-4">
        <Spin spinning={loading}>
          {/* Header */}
          <div className="flex justify-between items-center mb-3">
            <h4 className="text-sm font-semibold m-0">{t('incidents.structuredUpdates')}</h4>
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button
                type="primary"
                size="small"
                icon={<PlusOutlined />}
                onClick={() => setDrawerVisible(true)}
              >
                {t('incidents.addUpdate')}
              </Button>
            </PermissionWrapper>
          </div>

          {/* Filter bar */}
          <div className="flex items-center gap-3 mb-3">
            <Select
              size="small"
              allowClear
              placeholder={t('incidents.updateType')}
              className="w-[120px]"
              value={filterType}
              onChange={(val) => setFilterType(val || undefined)}
              options={typeFilterOptions}
            />
            <Input
              size="small"
              allowClear
              placeholder={t('incidents.searchContent')}
              prefix={<SearchOutlined className="text-gray-300" />}
              className="w-[220px]"
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
            />
            <span className="text-xs text-gray-400 ml-auto">
              {t('incidents.totalUpdates', undefined, { count: String(filteredUpdates.length) })}
            </span>
          </div>

          {/* Update list */}
          {filteredUpdates.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />
          ) : (
            <div>{filteredUpdates.map(renderUpdateRow)}</div>
          )}
        </Spin>
      </div>

      {/* Right: Collaborator panel */}
      <div className="w-[220px] shrink-0 border-l border-gray-200 pl-4">
        <div className="flex justify-between items-center mb-4">
          <h4 className="text-sm font-semibold m-0">{t('incidents.collaborators')}</h4>
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Tooltip title={t('incidents.inviteCollaborator')}>
              <Button
                type="text"
                size="small"
                icon={<UserAddOutlined />}
                onClick={() => setInviteVisible(true)}
              />
            </Tooltip>
          </PermissionWrapper>
        </div>

        {/* Owner */}
        <div className="mb-4">
          <div className="text-xs text-gray-400 mb-2 font-medium">{t('incidents.owner')}</div>
          {operators.map((username: string) => {
            const user = userList.find((u: UserItem) => u.username === username);
            const displayName = (user?.display_name as string) || username;
            return (
              <div key={username} className="flex items-center gap-2.5 mb-3">
                <Avatar size={32} style={{ backgroundColor: getAvatarColor(username), fontSize: 14 }}>
                  {displayName[0]?.toUpperCase()}
                </Avatar>
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] font-medium leading-tight truncate">{displayName}</div>
                </div>
                <Tag color="blue" className="text-xs m-0">{t('incidents.owner')}</Tag>
              </div>
            );
          })}
        </div>

        {/* Collaborators */}
        <div>
          <div className="text-xs text-gray-400 mb-2 font-medium">
            {t('incidents.collaborator')} ({collaborators.length})
          </div>
          {collaborators.length === 0 ? (
            <div className="text-xs text-gray-300 py-2">{t('incidents.noCollaborator')}</div>
          ) : (
            collaborators.map((username: string) => {
              const user = userList.find((u: UserItem) => u.username === username);
              const displayName = (user?.display_name as string) || username;
              return (
                <div key={username} className="flex items-center gap-2.5 mb-3 group">
                  <Avatar size={32} style={{ backgroundColor: getAvatarColor(username), fontSize: 14 }}>
                    {displayName[0]?.toUpperCase()}
                  </Avatar>
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] font-medium leading-tight truncate">{displayName}</div>
                  </div>
                  <PermissionWrapper requiredPermissions={['Edit']}>
                    <Button
                      type="text"
                      size="small"
                      danger
                      className="opacity-0 group-hover:opacity-100 transition-opacity"
                      icon={<DeleteOutlined style={{ fontSize: 12 }} />}
                      onClick={() => handleRemoveCollaborator(username)}
                    />
                  </PermissionWrapper>
                </div>
              );
            })
          )}

          {/* Invite button at bottom */}
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button
              type="dashed"
              size="small"
              block
              className="mt-2"
              icon={<UserAddOutlined />}
              onClick={() => setInviteVisible(true)}
            >
              {t('incidents.inviteCollaborator')}
            </Button>
          </PermissionWrapper>
        </div>
      </div>

      {/* Add Update Drawer */}
      <Drawer
        title={t('incidents.addUpdate')}
        open={drawerVisible}
        onClose={() => setDrawerVisible(false)}
        width={400}
        footer={
          <div className="flex justify-end gap-2">
            <Button onClick={() => setDrawerVisible(false)}>{t('common.cancel')}</Button>
            <Button
              type="primary"
              loading={submitLoading}
              disabled={!updateType || !updateContent.trim()}
              onClick={handlePublishUpdate}
            >
              {t('incidents.publishUpdate')}
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <div className="text-sm font-medium mb-1">{t('incidents.updateType')}</div>
            <Select
              className="w-full"
              placeholder={t('incidents.selectUpdateType')}
              value={updateType || undefined}
              onChange={setUpdateType}
              options={[
                { label: t('incidents.observation'), value: 'observation' },
                { label: t('incidents.progress'), value: 'progress' },
                { label: t('incidents.conclusion'), value: 'conclusion' },
                { label: t('incidents.nextStep'), value: 'next_step' },
              ]}
            />
          </div>
          <div>
            <div className="text-sm font-medium mb-1">{t('incidents.updateContent')}</div>
            <Input.TextArea
              rows={6}
              maxLength={1000}
              showCount
              placeholder={t('incidents.enterContent')}
              value={updateContent}
              onChange={(e) => setUpdateContent(e.target.value)}
            />
          </div>
          <Checkbox checked={isKeyInfo} onChange={(e) => setIsKeyInfo(e.target.checked)}>
            {t('incidents.markAsKeyInfo')}
          </Checkbox>
        </div>
      </Drawer>

      {/* Invite Collaborator Modal */}
      <Modal
        title={t('incidents.inviteCollaborator')}
        open={inviteVisible}
        onCancel={() => { setInviteVisible(false); setInviteUsers([]); }}
        onOk={handleInvite}
        confirmLoading={inviteLoading}
        okButtonProps={{ disabled: !inviteUsers.length }}
      >
        <Select
          mode="multiple"
          className="w-full"
          placeholder={t('incidents.searchUser')}
          options={inviteUserOptions}
          value={inviteUsers}
          onChange={setInviteUsers}
          showSearch
          filterOption={(input, option) =>
            (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
          }
        />
      </Modal>
    </div>
  );
};

export default CollaborationTab;
