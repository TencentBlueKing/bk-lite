'use client';

import { SearchOutlined } from '@ant-design/icons';
import { Alert, App, Button, Empty, Input, Skeleton, Tabs } from 'antd';
import { useEffect, useState } from 'react';
import { useItsmApi } from '../api/useItsmApi';
import { matchesServiceSearch, ServiceBrowser, ServiceCards } from '../portal/workbench-widgets';
import type { PortalData } from '../types';
import { ItsmDrawer } from './interaction-surfaces';

type ServiceData =
  | { status: 'loading' }
  | { status: 'failed'; message: string }
  | { status: 'loaded'; portal: PortalData };

const personalTabs = [
  { key: 'favorites', label: '我的收藏', empty: '暂无收藏的服务' },
  { key: 'recents', label: '最近使用', empty: '暂无最近使用的服务' },
] as const;

export function QuickSubmitDrawer({ onClose }: { onClose: () => void }) {
  const { ready, portal: loadPortal, toggleFavorite } = useItsmApi();
  const { message } = App.useApp();
  const [data, setData] = useState<ServiceData>({ status: 'loading' });
  const [search, setSearch] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [pending, setPending] = useState<number>();

  useEffect(() => {
    if (!ready) return;
    let active = true;
    setData({ status: 'loading' });
    void loadPortal().then(portal => {
      if (active) setData({ status: 'loaded', portal });
    }).catch((reason: unknown) => {
      if (active) setData({ status: 'failed', message: reason instanceof Error ? reason.message : '服务加载失败' });
    });
    return () => { active = false; };
  }, [ready, loadPortal, attempt]);

  const favorite = async (id: number) => {
    if (pending !== undefined || data.status !== 'loaded') return;
    setPending(id);
    try {
      const result = await toggleFavorite(id);
      setData(current => {
        if (current.status !== 'loaded') return current;
        const ids = new Set(current.portal.favorites.map(item => item.id));
        if (result.favorite) ids.add(id);
        else ids.delete(id);
        const favorites = current.portal.services.filter(item => ids.has(item.id));
        return { status: 'loaded', portal: { ...current.portal, favorites } };
      });
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : '更新收藏失败');
    } finally {
      setPending(undefined);
    }
  };

  const portal = data.status === 'loaded' ? data.portal : undefined;
  return <ItsmDrawer title="快速提单" open onCancel={onClose} width="min(760px, 100vw)">
    {data.status === 'loading' && <Skeleton active paragraph={{ rows: 5 }} />}
    {data.status === 'failed' && <Alert type="error" showIcon message={data.message}
      action={<Button onClick={() => setAttempt(value => value + 1)}>重试</Button>} />}
    {portal && !portal.can_apply && <Alert type="warning" showIcon message="你没有提单权限" />}
    {portal?.can_apply && <>
      <Input aria-label="搜索服务" allowClear prefix={<SearchOutlined />} placeholder="搜索服务名称、描述或流程"
        value={search} onChange={event => setSearch(event.target.value)} />
      <Tabs className="mt-2" items={[
        { key: 'all', label: '全部服务', children: <ServiceBrowser portal={portal} search={search} onFavorite={favorite} pending={pending} fromTicketCenter /> },
        ...personalTabs.map(tab => {
          const items = portal[tab.key].filter(item => matchesServiceSearch(item, search));
          return {
            key: tab.key,
            label: tab.label,
            children: items.length
              ? <ServiceCards items={items} portal={portal} onFavorite={favorite} pending={pending} fromTicketCenter paginate />
              : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={search.trim() ? '未找到匹配的服务' : tab.empty} />,
          };
        }),
      ]} />
    </>}
  </ItsmDrawer>;
}
