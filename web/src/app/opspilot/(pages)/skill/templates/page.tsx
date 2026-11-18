'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Alert, Button, Input, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import GridEntityCard from '@/components/grid-entity-card';
import ListPageHeader from '@/components/list-page-header';
import CardGridSkeleton from '@/components/card-grid-skeleton';
import CompactEmptyState from '@/components/compact-empty-state';
import PermissionWrapper from '@/components/permission';
import Icon from '@/components/icon';
import SkillViewSwitcher from '@/app/opspilot/components/skill/SkillViewSwitcher';
import usePermissions from '@/hooks/usePermissions';
import { useTranslation } from '@/utils/i18n';
import { useSkillApi } from '@/app/opspilot/api/skill';
import type { SkillTemplate } from '@/app/opspilot/types/skill';
import { buildTemplateSkillPayload, collectSkillNames } from '@/app/opspilot/utils/templateSkill';
import { pickStableIcon } from '@/app/opspilot/utils/pickStableIcon';

type CatalogState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; templates: SkillTemplate[] };

const GRID_CLASS = 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4';
const ICONS = ['jiqirenjiaohukapian', 'jiqiren', 'jiqiren1', 'jiqiren2'];

export default function SkillTemplatesPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const api = useSkillApi();
  const apiRef = useRef(api);
  apiRef.current = api;
  const { hasPermission } = usePermissions('/opspilot/skill');
  const canCreate = hasPermission(['Add']);
  const [catalog, setCatalog] = useState<CatalogState>({ status: 'loading' });
  const [refreshKey, setRefreshKey] = useState(0);
  const [search, setSearch] = useState('');
  const [submittingId, setSubmittingId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setCatalog({ status: 'loading' });
    apiRef.current.fetchSkillTemplates().then(
      (templates) => { if (!cancelled) setCatalog({ status: 'ready', templates }); },
      () => { if (!cancelled) setCatalog({ status: 'error' }); },
    );
    return () => { cancelled = true; };
  }, [refreshKey]);

  const templates = useMemo(() => {
    if (catalog.status !== 'ready') return [];
    const query = search.trim().toLocaleLowerCase();
    return catalog.templates.filter((template) => `${template.name} ${template.introduction}`.toLocaleLowerCase().includes(query));
  }, [catalog, search]);

  const handleUseTemplate = async (template: SkillTemplate) => {
    if (!canCreate || submittingId !== null) return;
    setSubmittingId(template.id);
    try {
      const [names, tools] = await Promise.all([
        collectSkillNames((page, pageSize) => api.fetchSkill({ page, page_size: pageSize, is_template: 0 })),
        api.fetchSkillTools(),
      ]);
      const created = await api.createSkill(buildTemplateSkillPayload(template, names, tools));
      const query = new URLSearchParams({ id: String(created.id), name: created.name, desc: created.introduction });
      router.push(`/opspilot/skill/detail/settings?${query.toString()}`);
    } catch {
      message.error(t('skill.templateCreateFailed'));
    } finally {
      setSubmittingId(null);
    }
  };

  return (
    <div className="flex min-h-0 w-full flex-col">
      <ListPageHeader
        title={t('skill.templatesTitle')}
        description={t('skill.templatesDescription')}
        actions={
          <>
            <Input.Search
              className="w-full sm:w-72"
              aria-label={t('skill.searchTemplates')}
              placeholder={t('skill.searchTemplates')}
              allowClear
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <Button
              icon={<ReloadOutlined />}
              aria-label={t('common.refresh')}
              loading={catalog.status === 'loading'}
              onClick={() => setRefreshKey((value) => value + 1)}
            />
          </>
        }
      />
      <SkillViewSwitcher value="templates" />
      {catalog.status === 'loading' ? <CardGridSkeleton count={4} className={GRID_CLASS} /> : catalog.status === 'error' ? (
        <Alert
          type="error"
          showIcon
          message={t('skill.templatesLoadFailed')}
          action={<Button onClick={() => setRefreshKey((value) => value + 1)}>{t('common.retry')}</Button>}
        />
      ) : templates.length === 0 ? (
        <CompactEmptyState description={search.trim() ? t('skill.noMatchingTemplates') : t('skill.noTemplates')} />
      ) : (
        <div className={`grid auto-rows-max gap-4 ${GRID_CLASS}`}>
          {templates.map((template) => (
            <GridEntityCard
              key={template.id}
              name={template.name}
              description={template.introduction}
              icon={<Icon type={pickStableIcon(String(template.id), ICONS, template.name) || 'jiqiren'} className="text-2xl" />}
              origin="builtin"
              footer={
                <PermissionWrapper requiredPermissions={['Add']} permissionPath="/opspilot/skill" className="w-full">
                  <Button
                    type="primary"
                    className="w-full"
                    loading={submittingId === template.id}
                    disabled={!canCreate || submittingId !== null}
                    onClick={() => handleUseTemplate(template)}
                  >
                    {t('skill.useTemp')}
                  </Button>
                </PermissionWrapper>
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}
