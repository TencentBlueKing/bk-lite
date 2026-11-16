'use client';

import { Alert, Button, Input, Popconfirm, Select, Switch, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { UserSelector } from '../../components/user-selector';
import OperateModal from '@/components/operate-modal';
import CustomTable from '@/app/itsm/components/itsm-list-table';
import { useItsmApi } from '../../api/useItsmApi';
import { useTranslation } from '@/utils/i18n';
import { FieldRow } from '../../components/field-row';
import type { WorkflowListItem } from '../../types';

interface CatalogItem {
  id: number;
  name: string;
  parent_id: number | null;
}

interface ServiceItem {
  id: number;
  name: string;
  catalog_id: number | null;
  workflow_id: number;
  workflow_name?: string;
  description: string;
  is_hot: boolean;
  is_enabled: boolean;
  visibility: string;
  visible_users: string[];
  visible_groups: number[];
}

export default function ServiceManagePage() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [catalogs, setCatalogs] = useState<CatalogItem[]>([]);
  const [services, setServices] = useState<ServiceItem[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowListItem[]>([]);
  const [catalogId, setCatalogId] = useState<number | null>(null);
  const [keyword, setKeyword] = useState('');
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [editingCatalog, setEditingCatalog] = useState<CatalogItem | null>(null);
  const [catalogName, setCatalogName] = useState('');
  const [parentId, setParentId] = useState<number | undefined>();
  const [serviceOpen, setServiceOpen] = useState(false);
  const [editingService, setEditingService] = useState<ServiceItem | null>(null);
  const [serviceName, setServiceName] = useState('');
  const [serviceCatalogId, setServiceCatalogId] = useState<number | undefined>();
  const [workflowId, setWorkflowId] = useState<number | undefined>();
  const [description, setDescription] = useState('');
  const [isHot, setIsHot] = useState(false);
  const [canManage, setCanManage] = useState<boolean>();
  const [visibility, setVisibility] = useState('all');
  const [visibleUsers, setVisibleUsers] = useState<string[]>([]);
  const [visibleGroups, setVisibleGroups] = useState<number[]>([]);
  const [groups, setGroups] = useState<{ id: number; name: string }[]>([]);

  const load = useCallback(async () => {
    const access = await api.portal() as { can_manage?: boolean };
    setCanManage(Boolean(access.can_manage));
    if (!access.can_manage) return;
    const [catalogData, serviceData, workflowData, groupData] = await Promise.all([
      api.listCatalogs() as Promise<{ items?: CatalogItem[] }>,
      api.listServices() as Promise<{ items?: ServiceItem[] }>,
      api.listWorkflows() as Promise<{ items?: WorkflowListItem[] }>,
      api.listHandlerGroups() as Promise<{ items?: { id: number; name: string }[] }>,
    ]);
    setGroups(groupData.items || []);
    setCatalogs(catalogData.items || []);
    setServices(serviceData.items || []);
    setWorkflows((workflowData.items || []).filter((item) => item.current_version_id));
  }, [api.listCatalogs, api.listServices, api.listWorkflows, api.listHandlerGroups, api.portal]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load]);

  const startCatalog = (item?: CatalogItem) => {
    setEditingCatalog(item || null);
    setCatalogName(item?.name || '');
    setParentId(item?.parent_id || undefined);
    setCatalogOpen(true);
  };

  const saveCatalog = async () => {
    if (!catalogName.trim()) {
      message.warning(t('itsm.portal.needCatalog'));
      return;
    }
    await api.createCatalog({ id: editingCatalog?.id, name: catalogName.trim(), parent_id: parentId || null });
    setCatalogOpen(false);
    await load();
  };

  const startService = (item?: ServiceItem) => {
    setEditingService(item || null);
    setServiceName(item?.name || '');
    setServiceCatalogId(item?.catalog_id || catalogId || undefined);
    setWorkflowId(item?.workflow_id);
    setDescription(item?.description || '');
    setIsHot(Boolean(item?.is_hot));
    setVisibility(item?.visibility || "all");
    setVisibleUsers(item?.visible_users || []);
    setVisibleGroups(item?.visible_groups || []);
    setServiceOpen(true);
  };

  const saveService = async () => {
    if (!serviceName.trim() || !workflowId) {
      message.warning(t('itsm.portal.needService'));
      return;
    }
    await api.createService({
      id: editingService?.id,
      name: serviceName.trim(),
      catalog_id: serviceCatalogId || null,
      workflow_id: workflowId,
      description,
      visibility,
      visible_users: visibleUsers,
      visible_groups: visibleGroups,
      is_hot: isHot,
      is_enabled: editingService ? editingService.is_enabled : true,
    });
    setServiceOpen(false);
    message.success(editingService ? t('itsm.portal.saved') : t('itsm.portal.created'));
    await load();
  };

  const shown = services.filter((item) => {
    if (catalogId && item.catalog_id !== catalogId) {
      return false;
    }
    return !keyword.trim() || item.name.includes(keyword.trim());
  });

  if (canManage === false) return <Alert type="warning" message="你没有服务目录管理权限" />;
  if (canManage === undefined) return null;

  return (
    <div className="flex min-h-0 gap-4">
      <div className="flex w-64 shrink-0 flex-col rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]">
        <div className="flex items-center justify-between border-b border-[var(--color-border)] px-3 py-2">
          <span className="text-sm font-medium text-[var(--color-text-1)]">{t('itsm.portal.catalog')}</span>
          <Button type="link" size="small" onClick={() => startCatalog()}>{t('itsm.common.create')}</Button>
        </div>
        <button
          type="button"
          className={`px-3 py-2 text-left text-sm ${catalogId === null ? 'bg-[var(--color-fill-1)] text-[var(--color-primary)]' : 'text-[var(--color-text-1)]'}`}
          onClick={() => setCatalogId(null)}
        >
          {t('itsm.portal.allServices')}
        </button>
        {catalogs.map((item) => (
          <div key={item.id} className={`flex items-center justify-between px-3 py-2 ${catalogId === item.id ? 'bg-[var(--color-fill-1)]' : ''}`}>
            <button type="button" className="min-w-0 flex-1 truncate text-left text-sm" onClick={() => setCatalogId(item.id)}>
              {item.parent_id ? '└ ' : ''}{item.name}
            </button>
            <Button type="link" size="small" onClick={() => startCatalog(item)}>{t('itsm.common.edit')}</Button>
            <Popconfirm title={t('itsm.portal.deleteCatalog')} onConfirm={() => { void api.deleteCatalog(item.id).then(load).catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.portal.deleteFailed'))); }}>
              <Button type="link" size="small" danger>{t('itsm.common.delete')}</Button>
            </Popconfirm>
          </div>
        ))}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3">
          <div className="text-sm font-medium text-[var(--color-text-1)]">{t('itsm.portal.services')}</div>
          <div className="flex gap-2">
            <Input className="w-48" placeholder={t('itsm.portal.searchService')} value={keyword} onChange={(event) => setKeyword(event.target.value)} allowClear />
            <Button type="primary" onClick={() => startService()}>{t('itsm.portal.newService')}</Button>
          </div>
        </div>
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
          <CustomTable
            rowKey="id"
            dataSource={shown}
            locale={{ emptyText: t('itsm.portal.emptyServices') }}
            columns={[
              { title: t('itsm.portal.name'), dataIndex: 'name', key: 'name' },
              { title: t('itsm.ticket.flow'), dataIndex: 'workflow_name', key: 'workflow_name', render: (value: string) => value || '—' },
              { title: t('itsm.portal.description'), dataIndex: 'description', key: 'description', render: (value: string) => value || '—' },
              {
                title: t('itsm.portal.hot'),
                dataIndex: 'is_hot',
                key: 'is_hot',
                render: (value: boolean, item: ServiceItem) => (
                  <Switch checked={value} onChange={(checked) => { void api.createService({ id: item.id, is_hot: checked }).then(load); }} />
                ),
              },
              {
                title: t('itsm.portal.enabled'),
                dataIndex: 'is_enabled',
                key: 'is_enabled',
                render: (value: boolean, item: ServiceItem) => (
                  <Switch checked={value} onChange={(checked) => { void api.createService({ id: item.id, is_enabled: checked }).then(load); }} />
                ),
              },
              {
                title: t('itsm.ticket.action'),
                key: 'actions',
                render: (_value: unknown, item: ServiceItem) => (
                  <span className="inline-flex gap-2">
                    <Button type="link" size="small" onClick={() => startService(item)}>{t('itsm.common.edit')}</Button>
                    <Popconfirm title={t('itsm.portal.deleteService')} onConfirm={() => { void api.deleteService(item.id).then(load); }}>
                      <Button type="link" size="small" danger>{t('itsm.common.delete')}</Button>
                    </Popconfirm>
                  </span>
                ),
              },
            ]}
          />
        </div>
      </div>
      <OperateModal title={editingCatalog ? t('itsm.portal.editCatalog') : t('itsm.portal.newCatalog')} open={catalogOpen} onCancel={() => setCatalogOpen(false)} onOk={() => { void saveCatalog(); }}>
        <div className="flex flex-col gap-3">
          <FieldRow label={t('itsm.portal.name')}>
            <Input placeholder={t('itsm.portal.catalogName')} value={catalogName} onChange={(event) => setCatalogName(event.target.value)} />
          </FieldRow>
          <FieldRow label={t('itsm.portal.parentCatalog')}>
            <Select
              className="w-full"
              allowClear
              placeholder={t('itsm.portal.parentCatalog')}
              value={parentId}
              options={catalogs.filter((item) => item.id !== editingCatalog?.id).map((item) => ({ value: item.id, label: item.name }))}
              onChange={setParentId}
            />
          </FieldRow>
        </div>
      </OperateModal>
      <OperateModal title={editingService ? t('itsm.common.edit') : t('itsm.portal.newService')} open={serviceOpen} onCancel={() => setServiceOpen(false)} onOk={() => { void saveService(); }}>
        <div className="flex flex-col gap-3">
          <FieldRow label={t('itsm.portal.name')}>
            <Input placeholder={t('itsm.portal.serviceName')} value={serviceName} onChange={(event) => setServiceName(event.target.value)} />
          </FieldRow>
          <FieldRow label={t('itsm.portal.ownerCatalog')}>
            <Select
              className="w-full"
              allowClear
              placeholder={t('itsm.portal.ownerCatalog')}
              value={serviceCatalogId}
              options={catalogs.map((item) => ({ value: item.id, label: item.name }))}
              onChange={setServiceCatalogId}
            />
          </FieldRow>
          <FieldRow label={t('itsm.ticket.flow')}>
            <Select
              className="w-full"
              placeholder={workflows.length ? t('itsm.portal.bindWorkflow') : t('itsm.portal.noWorkflow')}
              value={workflowId}
              options={workflows.map((item) => ({ value: item.id, label: item.name }))}
              onChange={setWorkflowId}
            />
          </FieldRow>
          <FieldRow label={t('itsm.portal.description')} align="start">
            <Input.TextArea rows={3} placeholder={t('itsm.portal.description')} value={description} onChange={(event) => setDescription(event.target.value)} />
          </FieldRow>
          <FieldRow label="可见范围">
            <Select className="w-full" aria-label="服务可见范围" value={visibility} onChange={setVisibility} options={[{ value: 'all', label: '全部用户' }, { value: 'restricted', label: '指定用户或组' }]} />
          </FieldRow>
          {visibility === 'restricted' && <>
            <FieldRow label="用户"><UserSelector ariaLabel="可见用户" value={visibleUsers} onChange={setVisibleUsers} allowClear /></FieldRow>
            <FieldRow label="用户组"><Select className="w-full" aria-label="可见用户组" mode="multiple" showSearch optionFilterProp="label" value={visibleGroups} onChange={setVisibleGroups} options={groups.map(item => ({ value: item.id, label: item.name }))} /></FieldRow>
            <p className="text-xs text-[var(--color-text-3)]">用户或组内成员、负责人满足任意一项即可访问。均未选择时，仅超管可见。</p>
          </>}
          <FieldRow label={t('itsm.portal.hot')}>
            <Switch checked={isHot} onChange={setIsHot} />
          </FieldRow>
        </div>
      </OperateModal>
    </div>
  );
}
