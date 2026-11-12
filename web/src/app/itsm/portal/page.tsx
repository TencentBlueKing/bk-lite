'use client';

import { Button, Card, Empty, Tag, message } from 'antd';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { useItsmApi } from '../api/useItsmApi';
import { useTranslation } from '@/utils/i18n';
import type { PortalData, PortalService } from '../types';

const emptyPortal: PortalData = { catalogs: [], services: [], favorites: [], recents: [], hots: [] };

function ServiceCards({
  items,
  emptyText,
  onFavorite,
  t,
}: {
  items: PortalService[];
  emptyText: string;
  onFavorite: (id: number) => void;
  t: (id: string, defaultMessage?: string, values?: Record<string, string>) => string;
}) {
  if (!items.length) {
    return (
      <div className="rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-fill-1)] py-6">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {items.map((item) => (
        <Card
          key={item.id}
          size="small"
          title={<span className="text-sm font-medium text-[var(--color-text-1)]">{item.name}</span>}
          extra={<Button size="small" onClick={() => onFavorite(item.id)}>{t('itsm.portal.favorite')}</Button>}
        >
          <div className="mb-3 text-xs text-[var(--color-text-3)]">
            {item.workflow_name ? t('itsm.portal.workflow', undefined, { name: item.workflow_name }) : item.description || t('itsm.portal.unbound')}
          </div>
          <div className="flex items-center justify-between border-t border-[var(--color-border)] pt-2.5">
            <Tag className="m-0" color={item.is_hot ? 'processing' : 'default'}>
              {item.is_hot ? t('itsm.portal.hot') : t('itsm.portal.normal')}
            </Tag>
            <Link href={`/itsm/portal/apply/${item.id}`}>
              <Button type="link" size="small" className="px-0">{t('itsm.portal.apply')}</Button>
            </Link>
          </div>
        </Card>
      ))}
    </div>
  );
}

export default function PortalPage() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [data, setData] = useState<PortalData>(emptyPortal);

  const load = useCallback(async () => {
    const portalData = await api.portal();
    setData(portalData as PortalData);
  }, [api.portal]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => {
      message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed'));
    });
  }, [api.ready, load]);

  const favorite = async (id: number) => {
    await api.toggleFavorite(id);
    await load();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <div className="text-base font-semibold leading-tight text-[var(--color-text-1)]">{t('itsm.portal.title')}</div>
        <Link href="/itsm/portal/services"><Button type="primary">{t('itsm.portal.manage')}</Button></Link>
      </div>

      <div className="flex flex-col gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-2">
          <span className="text-sm font-medium text-[var(--color-text-1)]">{t('itsm.portal.favorites')}</span>
          <span className="text-xs text-[var(--color-text-3)]">{t('itsm.portal.count', undefined, { count: String(data.favorites.length) })}</span>
        </div>
        <ServiceCards
          items={data.favorites}
          emptyText={t('itsm.portal.emptyFavorites')}
          onFavorite={(id) => { void favorite(id); }}
          t={t}
        />
      </div>

      <div className="flex flex-col gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-2">
          <span className="text-sm font-medium text-[var(--color-text-1)]">{t('itsm.portal.recents')}</span>
          <span className="text-xs text-[var(--color-text-3)]">{t('itsm.portal.count', undefined, { count: String(data.recents.length) })}</span>
        </div>
        <ServiceCards
          items={data.recents}
          emptyText={t('itsm.portal.emptyRecents')}
          onFavorite={(id) => { void favorite(id); }}
          t={t}
        />
      </div>

      <div className="flex flex-col gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-2">
          <span className="text-sm font-medium text-[var(--color-text-1)]">{t('itsm.portal.hots')}</span>
          <span className="text-xs text-[var(--color-text-3)]">{t('itsm.portal.count', undefined, { count: String(data.hots.length) })}</span>
        </div>
        <ServiceCards
          items={data.hots}
          emptyText={t('itsm.portal.emptyHots')}
          onFavorite={(id) => { void favorite(id); }}
          t={t}
        />
      </div>

      {data.catalogs.map((catalog) => {
        const catalogServices = data.services.filter((item) => item.catalog_id === catalog.id);
        return (
          <div key={catalog.id} className="flex flex-col gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
            <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-2">
              <span className="text-sm font-medium text-[var(--color-text-1)]">{catalog.name}</span>
              <span className="text-xs text-[var(--color-text-3)]">{t('itsm.portal.count', undefined, { count: String(catalogServices.length) })}</span>
            </div>
            <ServiceCards
              items={catalogServices}
              emptyText={t('itsm.portal.emptyCatalog')}
              onFavorite={(id) => { void favorite(id); }}
              t={t}
            />
          </div>
        );
      })}
    </div>
  );
}
