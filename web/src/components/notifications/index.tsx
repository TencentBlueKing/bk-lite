'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { Badge, Popover, Tabs, Empty, Spin, Modal, Tooltip, Typography, message } from 'antd';
import { BellOutlined, DeleteOutlined, CheckCircleOutlined, DownOutlined, UpOutlined } from '@ant-design/icons';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import { usePolling } from '@/hooks/usePolling';
import { useClientData } from '@/context/client';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import Icon from '@/components/icon';

interface Notification {
  id: number;
  notification_time: string;
  app_module: string;
  content: string;
  is_read: boolean;
}

const Notifications = () => {
  const { t } = useTranslation();
  const { get, post, del } = useApiClient();
  const { clientData } = useClientData();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [unreadCount, setUnreadCount] = useState(0);
  const [open, setOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'unread' | 'all'>('unread');
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [page, setPage] = useState(1);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  const fetchUnreadCount = useCallback(async () => {
    try {
      const response = await get('/console_mgmt/notifications/unread_count/');
      setUnreadCount(response.count);
    } catch (error) {
      console.error('Failed to fetch unread count:', error);
    }
  }, [get]);

  useEffect(() => {
    fetchUnreadCount();
  }, [fetchUnreadCount]);

  usePolling(fetchUnreadCount, 30000, true);

  const appIconMap = new Map(
    clientData
      .filter(item => item.icon)
      .map((item) => [item.name, item.icon as string])
  );

  const fetchNotifications = useCallback(async (pageNum: number, isUnreadOnly: boolean) => {
    setLoading(true);
    try {
      const url = isUnreadOnly
        ? `/console_mgmt/notifications/?unread_only=true&page=${pageNum}&page_size=10`
        : `/console_mgmt/notifications/?page=${pageNum}&page_size=10`;

      const response = await get(url);
      setNotifications(prev => {
        const newNotifications = pageNum === 1 ? response.items : [...prev, ...response.items];
        setHasMore(response.count > newNotifications.length);
        return newNotifications;
      });
    } catch (error) {
      console.error('Failed to fetch notifications:', error);
    } finally {
      setLoading(false);
    }
  }, [get]);

  const handleOpenChange = (newOpen: boolean) => {
    setOpen(newOpen);
    if (newOpen) {
      setPage(1);
      setNotifications([]);
      fetchNotifications(1, activeTab === 'unread');
    }
  };

  const handleTabChange = (key: string) => {
    setActiveTab(key as 'unread' | 'all');
    setPage(1);
    setNotifications([]);
    fetchNotifications(1, key === 'unread');
  };

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;

    if (scrollHeight - scrollTop <= clientHeight + 50 && hasMore && !loading) {
      const nextPage = page + 1;
      setPage(nextPage);
      fetchNotifications(nextPage, activeTab === 'unread');
    }
  }, [hasMore, loading, page, activeTab, fetchNotifications]);

  const handleDelete = (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    const modalInstance: ReturnType<typeof Modal.confirm> = Modal.confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk: async () => {
        modalInstance.update({
          cancelButtonProps: { disabled: true }
        });
        try {
          await del(`/console_mgmt/notifications/${id}/`);
          fetchUnreadCount();
        } catch (error) {
          console.error('Failed to delete notification:', error);
        }
      }
    });
  };

  const handleMarkAllAsRead = () => {
    if (unreadCount === 0) {
      message.warning(t('common.noUnreadNotifications'));
      return;
    }
    const modalInstance: ReturnType<typeof Modal.confirm> = Modal.confirm({
      title: t('common.markAllAsReadConfirm'),
      content: t('common.markAllAsReadCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk: async () => {
        modalInstance.update({
          cancelButtonProps: { disabled: true }
        });
        try {
          await post('/console_mgmt/notifications/mark_all_as_read/');
          setUnreadCount(0);
          fetchUnreadCount();
        } catch (error) {
          console.error('Failed to mark all as read:', error);
        }
      }
    });
  };

  const handlenotificationClick = (notification: Notification) => async () => {
    if (!notification.is_read) {
      setNotifications(prev =>
        prev.map(n => n.id === notification.id ? { ...n, is_read: true } : n)
      );
      setUnreadCount(prev => Math.max(0, prev - 1));
      try {
        await post(`/console_mgmt/notifications/${notification.id}/mark_as_read/`);
      } catch (error) {
        console.error('Failed to mark as read:', error);
        setNotifications(prev =>
          prev.map(n => n.id === notification.id ? { ...n, is_read: false } : n)
        );
        setUnreadCount(prev => prev + 1);
      }
    }
  };

  const content = (
    <div className="w-[350px]">
      <div className="flex flex-col px-3">
        <div className="flex items-center justify-between">
          <span className="text-lg font-semibold">{t('common.notification')}</span>
          <div
            className="border p-1 rounded-sm text-xs text-[var(--color-text-2)] cursor-pointer hover:text-blue-500"
            onClick={handleMarkAllAsRead}
          >
            {t('common.markAllAsRead')}
          </div>
        </div>
        <Tabs
          activeKey={activeTab}
          onChange={handleTabChange}
          items={[
            {
              key: 'unread',
              label: (
                <Badge size="small" count={unreadCount}>
                  <span>
                    {t('common.unreadNotifications')}
                  </span>
                </Badge>

              )
            },
            {
              key: 'all',
              label: (
                <span>
                  {t('common.allNotifications')}
                </span>
              )
            }
          ]}
        />
      </div>

      <div
        ref={scrollContainerRef}
        className="max-h-[400px] overflow-y-auto"
        onScroll={handleScroll}
      >
        {loading && page === 1 ? (
          <div className="flex justify-center items-center py-8">
            <Spin />
          </div>
        ) : notifications?.length === 0 ? (
          <Empty
            description={t('common.noData')}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            className="py-8"
          />
        ) : (
          <>
            {notifications?.map((notification) => {
              return (
                <div
                  key={notification.id}
                  className={`group px-3 py-3 border-1 border-[var(--color-border)] border-b last:border-b-0 first:pt-0 cursor-pointer`}
                  onClick={handlenotificationClick(notification)}
                >
                  <div className='flex items-start justify-between'>
                    <div className="flex items-start gap-2 mb-2">
                      <Icon
                        type={appIconMap.get(notification.app_module) || notification.app_module}
                        className="text-2xl flex-shrink-0"
                      />
                      <div className={`text-base font-medium ${!notification.is_read ? '' : 'text-[var(--color-text-3)]'}`}>
                        {notification.app_module}
                      </div>
                    </div>
                    {!notification.is_read && (
                      <div className="w-1 h-1 rounded-full bg-red-500 flex-shrink-0"></div>
                    )}
                  </div>

                  <div className="mb-2">
                    <Typography.Paragraph
                      className={`${!notification.is_read ? '' : 'text-[var(--color-text-3)]'}`}
                      ellipsis={{
                        rows: 2,
                        expandable: 'collapsible',
                        symbol: (expanded: boolean) => expanded ? <UpOutlined className="text-blue-500" /> : <DownOutlined className="text-blue-500" />
                      }}
                    >
                      {notification.content}
                    </Typography.Paragraph>
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="text-xs text-[var(--color-text-4)]">
                      {convertToLocalizedTime(notification.notification_time, 'YYYY-MM-DD HH:mm:ss')}
                    </div>
                    <div className="flex gap-2 items-center opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                      {activeTab === 'unread' && !notification.is_read && (
                        <Tooltip title={t('common.setAsRead')}>
                          <CheckCircleOutlined
                            className='text-sm text-blue-500 cursor-pointer hover:text-blue-700'
                          />
                        </Tooltip>
                      )}
                      <Tooltip title={t('common.delete')}>
                        <DeleteOutlined
                          className='text-sm text-[var(--color-fail)] cursor-pointer hover:text-red-700'
                          onClick={(e) => handleDelete(notification.id, e)}
                          title={t('common.delete')}
                        />
                      </Tooltip>
                    </div>
                  </div>
                </div>
              );
            })}
            {loading && page > 1 && (
              <div className="flex justify-center py-3">
                <Spin size="small" />
              </div>
            )}
            {!loading && !hasMore && notifications?.length > 0 && (
              <div className="text-center py-3 text-xs text-gray-400">
                {t('common.noMore')}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );

  return (
    <Popover
      content={content}
      trigger="click"
      open={open}
      onOpenChange={handleOpenChange}
      placement="bottom"
      arrow={false}
    >
      <Tooltip title={t('common.notification')}>
        <div className="cursor-pointer flex items-center justify-center">
          <Badge size="small" count={unreadCount}>
            <BellOutlined className='text-[16px] text-[var(--color-text-3)] hover:text-[var(--color-primary)] transition-colors' />
          </Badge>
        </div>
      </Tooltip>
    </Popover>
  )
}

export default Notifications;