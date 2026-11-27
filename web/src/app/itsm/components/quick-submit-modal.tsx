'use client';

import { SearchOutlined } from '@ant-design/icons';
import { Alert, App, Button, Empty, Input, Select, Tabs } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from '@/utils/i18n';
import { useItsmApi } from '../api/useItsmApi';
import { matchesServiceSearch, SERVICE_GRID_CLASS, ServiceCards } from '../portal/workbench-widgets';
import type { PortalData, PortalService } from '../types';
import { ItsmModal } from './interaction-surfaces';

type ServiceData =
  | { status: 'loading' }
  | { status: 'failed'; message: string }
  | { status: 'loaded'; portal: PortalData };

const personalTabs = [
  { key: 'favorites', empty: 'itsm.quickSubmit.emptyFavorites' },
  { key: 'recents', empty: 'itsm.quickSubmit.emptyRecents' },
] as const;
const COLLAPSED_COUNT = 6;
const pulseClass = 'animate-neutral-pulse rounded-md bg-[var(--color-fill-2)]';

function QuickSubmitSkeleton({ label }: { label: string }) {
  return <div role="status" aria-label={label} aria-busy="true" className="space-y-4">
    <div className={`h-9 w-full ${pulseClass}`} />
    <div className="flex gap-4 border-b border-[var(--color-border)] py-2">
      {Array.from({ length: 3 }, (_, index) => <div key={index} className={`h-4 w-20 ${pulseClass}`} />)}
    </div>
    <div className="flex gap-5">
      <div className={`hidden h-80 w-44 shrink-0 md:block ${pulseClass}`} />
      <div className={`min-w-0 flex-1 ${SERVICE_GRID_CLASS}`}>
        {Array.from({ length: 6 }, (_, index) => <div key={index} className={`h-24 ${pulseClass}`} />)}
      </div>
    </div>
  </div>;
}

function categoryIds(portal: PortalData, root: number) {
  const ids = new Set([root]);
  const pending = [root];
  while (pending.length) {
    const parent = pending.pop();
    for (const item of portal.catalogs) {
      if (item.parent_id !== parent || ids.has(item.id)) continue;
      ids.add(item.id);
      pending.push(item.id);
    }
  }
  return ids;
}

function QuickServiceCatalog({ portal, search, onSearchClear, onFavorite, pending, onNavigate }: {
  portal: PortalData;
  search: string;
  onSearchClear: () => void;
  onFavorite: (id: number) => void;
  pending?: number;
  onNavigate: () => void;
}) {
  const { t } = useTranslation();
  const [catalog, setCatalog] = useState<number | null>(null);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const knownCatalogs = new Set(portal.catalogs.map(item => item.id));
  const uncategorized = (item: PortalService) => !item.catalog_id || !knownCatalogs.has(item.catalog_id);
  const branches = new Map(portal.catalogs.map(item => [item.id, categoryIds(portal, item.id)]));
  const countFor = (id: number) => id === 0 ? portal.services.filter(uncategorized).length
    : portal.services.filter(item => branches.get(id)?.has(item.catalog_id || 0)).length;
  const categories = portal.catalogs.filter(item => countFor(item.id));
  const all = portal.services.filter(item => matchesServiceSearch(item, search));
  const activeCatalog = search.trim() ? null : catalog;
  const selected = activeCatalog === null ? all : activeCatalog === 0 ? all.filter(uncategorized)
    : all.filter(item => branches.get(activeCatalog)?.has(item.catalog_id || 0));
  const groups = [
    ...portal.catalogs.map(item => ({ id: item.id, name: item.name, services: selected.filter(service => service.catalog_id === item.id) })),
    { id: 0, name: t('itsm.serviceBrowser.uncategorized'), services: selected.filter(uncategorized) },
  ].filter(group => group.services.length);
  const options = [
    { value: -1, label: `${t('itsm.serviceBrowser.allCatalogs')} · ${portal.services.length}` },
    ...categories.map(item => ({ value: item.id, label: `${item.name} · ${countFor(item.id)}` })),
    ...(countFor(0) ? [{ value: 0, label: `${t('itsm.serviceBrowser.uncategorized')} · ${countFor(0)}` }] : []),
  ];

  function catalogButton(id: number | null, name: string, count: number) {
    return <button key={id ?? 'all'} type="button" aria-current={activeCatalog === id ? 'page' : undefined}
      className={`mb-1 flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm ${activeCatalog === id ? 'bg-[var(--color-fill-2)] font-medium text-[var(--color-primary)]' : 'text-[var(--color-text-2)] hover:bg-[var(--color-fill-2)]'}`}
      onClick={() => { setCatalog(id); onSearchClear(); }}><span className="truncate">{name}</span><span className="shrink-0 text-xs text-[var(--color-text-3)]">{count}</span></button>;
  }

  return <div className="flex h-[min(54vh,520px)] min-h-[280px] min-w-0 flex-col gap-3 md:flex-row md:gap-5">
    <Select aria-label={t('itsm.serviceBrowser.filter')} className="w-full md:hidden" value={activeCatalog ?? -1}
      options={options} onChange={value => { setCatalog(value === -1 ? null : value); onSearchClear(); }} />
    <nav aria-label={t('itsm.quickSubmit.categories')} className="hidden w-48 shrink-0 overflow-y-auto border-r border-[var(--color-border)] pr-3 md:block">
      {catalogButton(null, t('itsm.serviceBrowser.allCatalogs'), portal.services.length)}
      {categories.map(item => catalogButton(item.id, item.name, countFor(item.id)))}
      {countFor(0) > 0 && catalogButton(0, t('itsm.serviceBrowser.uncategorized'), countFor(0))}
    </nav>
    <div className="min-h-0 min-w-0 flex-1 overflow-y-auto pr-1" aria-live="polite">
      <div className="mb-3 text-xs text-[var(--color-text-3)]">{t('itsm.quickSubmit.results', undefined, { count: selected.length })}</div>
      {groups.length ? groups.map(group => {
        const showAll = Boolean(search.trim()) || expanded[group.id];
        const shown = showAll ? group.services : group.services.slice(0, COLLAPSED_COUNT);
        return <section key={group.id} className="mb-6 last:mb-0">
          <div className="mb-3 flex items-center justify-between gap-2 border-b border-[var(--color-border)] pb-2">
            <h3 className="m-0 text-sm font-medium text-[var(--color-text-1)]">{group.name} <span className="text-xs font-normal text-[var(--color-text-3)]">({group.services.length})</span></h3>
            {!search.trim() && group.services.length > COLLAPSED_COUNT && <Button type="link" size="small" aria-expanded={Boolean(showAll)}
              onClick={() => setExpanded(current => ({ ...current, [group.id]: !showAll }))}>
              {showAll ? t('itsm.quickSubmit.collapse') : t('itsm.quickSubmit.expandAll', undefined, { count: group.services.length })}
            </Button>}
          </div>
          <ServiceCards items={shown} portal={portal} onFavorite={onFavorite} pending={pending} fromTicketCenter onNavigate={onNavigate} />
        </section>;
      }) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={search.trim() ? t('itsm.serviceBrowser.noMatch') : t('itsm.serviceBrowser.empty')} />}
    </div>
  </div>;
}

export function QuickSubmitModal({ onClose, onNavigate }: { onClose: () => void; onNavigate: () => void }) {
  const { t } = useTranslation();
  const fallback = t('itsm.quickSubmit.loadFailed');
  const { ready, portalAll: loadPortal, toggleFavorite } = useItsmApi();
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
  return <ItsmModal title={t('itsm.quickSubmit.title')} open onCancel={onClose} footer={null} width="min(1120px, calc(100vw - 32px))" destroyOnHidden>
    {data.status === 'loading' && <QuickSubmitSkeleton label={t('itsm.quickSubmit.loading')} />}
    {data.status === 'failed' && <Alert type="error" showIcon message={data.message}
      action={<Button onClick={() => setAttempt(value => value + 1)}>{t('itsm.common.retry')}</Button>} />}
    {portal && !portal.can_apply && <Alert type="warning" showIcon message={t('itsm.quickSubmit.notAllowed')} />}
    {portal?.can_apply && <>
      <Input aria-label={t('itsm.portal.searchService')} allowClear prefix={<SearchOutlined />} placeholder={t('itsm.quickSubmit.searchPlaceholder')}
        value={search} onChange={event => setSearch(event.target.value)} />
      <Tabs className="mt-2" items={[
        { key: 'all', label: t('itsm.portal.allServices'), children: <QuickServiceCatalog portal={portal} search={search} onSearchClear={() => setSearch('')} onFavorite={favorite} pending={pending} onNavigate={onNavigate} /> },
        ...personalTabs.map(tab => {
          const items = portal[tab.key].filter(item => matchesServiceSearch(item, search));
          return {
            key: tab.key,
            label: t(`itsm.portal.${tab.key}`),
            children: <div className="h-[min(54vh,520px)] min-h-[280px] overflow-y-auto pr-1">{items.length
              ? <ServiceCards items={items} portal={portal} onFavorite={favorite} pending={pending} fromTicketCenter onNavigate={onNavigate} />
              : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={search.trim() ? t('itsm.quickSubmit.noMatch') : t(tab.empty)} />}</div>,
          };
        }),
      ]} />
    </>}
  </ItsmModal>;
}
