'use client';

import { SearchOutlined } from '@ant-design/icons';
import { Alert, App, Button, Empty, Input, Tabs } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from '@/utils/i18n';
import { useItsmApi } from '../api/useItsmApi';
import { matchesServiceSearch, SERVICE_GRID_CLASS, ServiceBrowser, ServiceCards } from '../portal/workbench-widgets';
import type { PortalData } from '../types';
import { ItsmDrawer } from './interaction-surfaces';

type ServiceData =
  | { status: 'loading' }
  | { status: 'failed'; message: string }
  | { status: 'loaded'; portal: PortalData };

const personalTabs = [
  { key: 'favorites', empty: 'itsm.quickSubmit.emptyFavorites' },
  { key: 'recents', empty: 'itsm.quickSubmit.emptyRecents' },
] as const;

const pulseClass = 'animate-neutral-pulse rounded-md bg-[var(--color-fill-2)]';

function QuickSubmitSkeleton({ label }: { label: string }) {
  return <div role="status" aria-label={label} aria-busy="true">
    <div aria-hidden="true" className="space-y-4">
      <div className={`h-8 w-full ${pulseClass}`} />
      <div className="flex gap-4 border-b border-[var(--color-border)] py-2">
        {Array.from({ length: 3 }, (_, index) => <div key={index} className={`h-4 w-16 ${pulseClass}`} />)}
      </div>
      <div className="flex items-center justify-between gap-3">
        <div className={`h-3 w-24 ${pulseClass}`} />
        <div className={`h-8 w-48 ${pulseClass}`} />
      </div>
      <div className={`h-3 w-20 ${pulseClass}`} />
      <div className={SERVICE_GRID_CLASS}>
        {Array.from({ length: 4 }, (_, index) => <div key={index} className="flex gap-3 rounded-xl border border-[var(--color-border)] p-4">
          <div className={`size-10 shrink-0 ${pulseClass}`} />
          <div className="min-w-0 flex-1 space-y-2">
            <div className={`h-4 w-3/4 ${pulseClass}`} />
            <div className={`h-3 w-5/6 ${pulseClass}`} />
          </div>
          <div className={`size-6 ${pulseClass}`} />
        </div>)}
      </div>
    </div>
  </div>;
}

export function QuickSubmitDrawer({ onClose, onNavigate }: { onClose: () => void; onNavigate: () => void }) {
  const { t } = useTranslation();
  const fallback = t('itsm.quickSubmit.loadFailed');
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
      if (active) setData({ status: 'failed', message: reason instanceof Error ? reason.message : fallback });
    });
    return () => { active = false; };
  }, [ready, loadPortal, attempt, fallback]);

  const favorite = async (id: number) => {
    if (pending !== undefined || data.status !== 'loaded') return;
    setPending(id);
    try {
      const result = await toggleFavorite(id);
      setData(current => {
        if (current.status !== 'loaded') return current;
        const favorites = current.portal.favorites.filter(item => item.id !== id);
        const added = result.service || current.portal.services.find(item => item.id === id);
        if (result.favorite && added) favorites.push(added);
        return { status: 'loaded', portal: { ...current.portal, favorites } };
      });
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : t('itsm.quickSubmit.favoriteFailed'));
    } finally {
      setPending(undefined);
    }
  };

  const portal = data.status === 'loaded' ? data.portal : undefined;
  return <ItsmDrawer title={t('itsm.quickSubmit.title')} open onCancel={onClose} width="min(760px, 100vw)">
    {data.status === 'loading' && <QuickSubmitSkeleton label={t('itsm.quickSubmit.loading')} />}
    {data.status === 'failed' && <Alert type="error" showIcon message={data.message}
      action={<Button onClick={() => setAttempt(value => value + 1)}>{t('itsm.common.retry')}</Button>} />}
    {portal && !portal.can_apply && <Alert type="warning" showIcon message={t('itsm.quickSubmit.notAllowed')} />}
    {portal?.can_apply && <>
      <Input aria-label={t('itsm.portal.searchService')} allowClear prefix={<SearchOutlined />} placeholder={t('itsm.quickSubmit.searchPlaceholder')}
        value={search} onChange={event => setSearch(event.target.value)} />
      <Tabs className="mt-2" items={[
        { key: 'all', label: t('itsm.portal.allServices'), children: <ServiceBrowser portal={portal} search={search} onFavorite={favorite} pending={pending} fromTicketCenter onNavigate={onNavigate} /> },
        ...personalTabs.map(tab => {
          const items = portal[tab.key].filter(item => matchesServiceSearch(item, search));
          return {
            key: tab.key,
            label: t(`itsm.portal.${tab.key}`),
            children: items.length
              ? <ServiceCards items={items} portal={portal} onFavorite={favorite} pending={pending} fromTicketCenter onNavigate={onNavigate} paginate />
              : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={search.trim() ? t('itsm.quickSubmit.noMatch') : t(tab.empty)} />,
          };
        }),
      ]} />
    </>}
  </ItsmDrawer>;
}
