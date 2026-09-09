'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Empty, message, Popconfirm, Space, Switch, Tabs, Tag } from 'antd';
import GroupTreeSelect from '@/components/group-tree-select';
import {
  AppstoreOutlined,
  CloudServerOutlined,
  ClusterOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  HddOutlined,
  PlusOutlined,
  ShareAltOutlined,
} from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import SearchActionBar from '@/components/search-action-bar';
import { useTranslation } from '@/utils/i18n';
import { CREDENTIAL_CATEGORIES } from '@/components/credential-picker/types';
import type { CredentialGroupOption, CredentialItem, CredentialTypeItem } from '@/components/credential-picker/types';
import { useCredentialApi } from '@/app/system-manager/api/credential';
import CredentialFormDrawer, { type CredentialDrawerMode } from './CredentialFormDrawer';
import type { ColumnItem } from '@/types';
import { HandledRequestError } from '@/utils/request';

interface CredentialListTabProps {
  onGoTypes: () => void;
  active?: boolean;
}

const ALL_TYPES = '__all__';

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  host: <DesktopOutlined />,
  network: <ShareAltOutlined />,
  storage: <HddOutlined />,
  database: <DatabaseOutlined />,
  middleware: <ClusterOutlined />,
  cloud: <CloudServerOutlined />,
  other: <AppstoreOutlined />,
};

const CredentialListTab: React.FC<CredentialListTabProps> = ({ onGoTypes, active = true }) => {
  const { t } = useTranslation();
  const {
    getCredentialTypes,
    getCredentials,
    getCredential,
    createCredential,
    updateCredential,
    deleteCredential,
    setCredentialDisabled,
    getAssignableGroups,
    getUsableGroups,
  } = useCredentialApi();
  const [types, setTypes] = useState<CredentialTypeItem[]>([]);
  const [items, setItems] = useState<CredentialItem[]>([]);
  const [assignableGroups, setAssignableGroups] = useState<CredentialGroupOption[]>([]);
  const [usableGroups, setUsableGroups] = useState<CredentialGroupOption[]>([]);
  const [category, setCategory] = useState<string>(CREDENTIAL_CATEGORIES[0]);
  const [typeKey, setTypeKey] = useState<string>(ALL_TYPES);
  const [search, setSearch] = useState('');
  const [ownerId, setOwnerId] = useState<number | undefined>();
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerMode, setDrawerMode] = useState<CredentialDrawerMode>('create');
  const [current, setCurrent] = useState<CredentialItem | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const detailRequestSeq = useRef(0);

  const categoryLabel = (id: string) => t(`system.credential.categories.${id}`, id);
  const groupName = (id: number) => usableGroups.find((item) => item.id === id)?.name
    || assignableGroups.find((item) => item.id === id)?.name
    || String(id);
  const canManageOwner = (groupId: number) => assignableGroups.some((item) => item.id === groupId);

  const navCategories = useMemo(() => {
    const extra = types.flatMap((item) => item.categories).filter((id) => !CREDENTIAL_CATEGORIES.includes(id as typeof CREDENTIAL_CATEGORIES[number]));
    return [...CREDENTIAL_CATEGORIES, ...Array.from(new Set(extra))];
  }, [types]);

  const typesInCategory = useMemo(
    () => types.filter((item) => item.categories.includes(category)),
    [types, category],
  );

  const loadMeta = async () => {
    const [nextTypes, nextAssignable, nextUsable] = await Promise.all([
      getCredentialTypes({ page_size: 0 }),
      getAssignableGroups(),
      getUsableGroups(),
    ]);
    setTypes(nextTypes.items);
    setAssignableGroups(nextAssignable);
    setUsableGroups(nextUsable);
  };

  const loadList = async (opts: {
    page?: number;
    pageSize?: number;
    type?: string;
    owner?: number | null;
    keyword?: string;
  } = {}) => {
    const page = opts.page ?? pagination.current;
    const pageSize = opts.pageSize ?? pagination.pageSize;
    const nextType = opts.type ?? typeKey;
    const nextOwner = 'owner' in opts ? opts.owner : ownerId;
    const keyword = 'keyword' in opts ? opts.keyword ?? '' : search;
    setLoading(true);
    try {
      const data = await getCredentials({
        search: keyword || undefined,
        category,
        type: nextType === ALL_TYPES ? undefined : nextType,
        ...(nextOwner != null ? { group_id: nextOwner } : {}),
        page,
        page_size: pageSize,
      });
      setItems(data.items);
      setPagination({ current: page, pageSize, total: data.count });
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  const credentialActionError = (error: unknown) => {
    const code = error instanceof HandledRequestError ? error.message : '';
    if (code === 'in_use') {
      return t('system.credential.inUse');
    }
    return t('common.delFailed');
  };

  const confirmDelete = async (credentialId: string) => {
    try {
      await deleteCredential(credentialId);
      await Promise.all([loadMeta(), loadList()]);
    } catch (error) {
      message.error(credentialActionError(error));
    }
  };

  useEffect(() => {
    if (!active) {
      return;
    }
    void loadMeta();
  }, [active]);

  useEffect(() => {
    setTypeKey(ALL_TYPES);
    void loadList({ page: 1, type: ALL_TYPES, owner: ownerId, keyword: search });
  }, [category]);

  const openCreate = () => {
    if (!typesInCategory.length) {
      message.info(t('system.credential.noTypeHint'));
      return;
    }
    detailRequestSeq.current += 1;
    setDetailLoading(false);
    setCurrent(null);
    setDrawerMode('create');
    setDrawerOpen(true);
  };

  const closeDrawer = () => {
    detailRequestSeq.current += 1;
    setDetailLoading(false);
    setDrawerOpen(false);
  };

  const openRecord = (record: CredentialItem, mode: CredentialDrawerMode) => {
    const requestId = ++detailRequestSeq.current;
    setCurrent(record);
    setDrawerMode(mode);
    setDrawerOpen(true);
    setDetailLoading(true);
    void getCredential(record.credential_id)
      .then((detail) => {
        if (requestId !== detailRequestSeq.current) {
          return;
        }
        setCurrent(detail);
      })
      .catch(() => {
        if (requestId !== detailRequestSeq.current) {
          return;
        }
        message.error(t('common.fetchFailed'));
      })
      .finally(() => {
        if (requestId === detailRequestSeq.current) {
          setDetailLoading(false);
        }
      });
  };

  const lockedType = typeKey === ALL_TYPES ? undefined : typeKey;

  const columns: ColumnItem[] = [
    {
      title: t('system.credential.name'),
      dataIndex: 'name',
      key: 'name',
      width: 220,
      render: (_, record: CredentialItem) => (
        <Button
          type="link"
          className="!h-auto !p-0 font-medium text-[var(--color-text-1)] hover:!text-[var(--color-primary)]"
          onClick={() => openRecord(record, 'view')}
        >
          {record.name}
        </Button>
      ),
    },
    {
      title: t('system.credential.type'),
      dataIndex: 'type',
      key: 'type',
      width: 140,
      render: (key: string) => (
        <span className="text-sm text-[var(--color-text-2)]">
          {types.find((item) => item.key === key)?.name || key}
        </span>
      ),
    },
    {
      title: t('system.credential.organization'),
      dataIndex: 'group_id',
      key: 'group_id',
      width: 140,
      render: (id: number) => <span className="text-sm text-[var(--color-text-2)]">{groupName(id)}</span>,
    },
    {
      title: t('system.credential.refs'),
      dataIndex: 'refs',
      key: 'refs',
      width: 110,
      render: (refs: unknown) => {
        if (refs == null || (Array.isArray(refs) && refs.length === 0) || refs === '') {
          return <span className="text-[var(--color-text-4)]">—</span>;
        }
        if (Array.isArray(refs)) {
          const labelOf = (moduleName: string, count: number) => {
            if (moduleName === 'cmdb') {
              return t('system.credential.refCmdb', 'CMDB {count}', { count });
            }
            if (moduleName === 'monitor') {
              return t('system.credential.refMonitor', '监控 {count}', { count });
            }
            return `${moduleName} ${count}`;
          };
          return (
            <div className="flex flex-wrap gap-1">
              {refs.map((item) => {
                const moduleName =
                  item && typeof item === 'object'
                    ? String((item as { module?: string }).module || '')
                    : '';
                const count = item && typeof item === 'object' ? Number((item as { count?: number }).count) : 0;
                if (!moduleName || !count) {
                  return null;
                }
                return (
                  <Tag key={moduleName} bordered={false} color="blue" className="rounded">
                    {labelOf(moduleName, count)}
                  </Tag>
                );
              })}
            </div>
          );
        }
        return <span className="text-sm text-[var(--color-text-2)]">{String(refs)}</span>;
      },
    },
    {
      title: t('system.credential.enabled'),
      dataIndex: 'disabled',
      key: 'disabled',
      width: 90,
      align: 'center',
      render: (disabled: boolean, record: CredentialItem) => (
        canManageOwner(record.group_id) ? (
          <PermissionWrapper requiredPermissions={['Edit']}>
            {disabled ? (
              <Switch
                size="small"
                checked={false}
                onChange={(checked) => {
                  if (checked) {
                    void setCredentialDisabled(record.credential_id, false).then(() => loadList());
                  }
                }}
              />
            ) : (
              <Popconfirm
                title={t('system.credential.disableConfirm')}
                okText={t('common.confirm')}
                cancelText={t('common.cancel')}
                onConfirm={() => void setCredentialDisabled(record.credential_id, true).then(() => loadList())}
              >
                <span className="inline-flex">
                  <Switch size="small" checked />
                </span>
              </Popconfirm>
            )}
          </PermissionWrapper>
        ) : (
          <span className="text-sm text-[var(--color-text-3)]">
            {disabled ? t('common.disable') : t('system.credential.enabled')}
          </span>
        )
      ),
    },
    {
      title: t('common.actions'),
      key: 'actions',
      dataIndex: 'actions',
      width: 140,
      render: (_, record: CredentialItem) => (
        <Space>
          {canManageOwner(record.group_id) ? (
            <>
              <PermissionWrapper requiredPermissions={['Edit']}>
                <Button
                  type="link"
                  size="small"
                  onClick={() => openRecord(record, 'edit')}
                >
                  {t('common.edit')}
                </Button>
              </PermissionWrapper>
              <PermissionWrapper requiredPermissions={['Delete']}>
                <Popconfirm title={t('common.delConfirm')} onConfirm={() => confirmDelete(record.credential_id)}>
                  <Button
                    type="link"
                    size="small"
                    danger
                  >
                    {t('common.delete')}
                  </Button>
                </Popconfirm>
              </PermissionWrapper>
            </>
          ) : (
            <Button
              type="link"
              size="small"
              onClick={() => openRecord(record, 'view')}
            >
              {t('common.detail')}
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div className="flex h-full min-h-0 gap-4">
      {/* Left side: Category Navigation Bar (Primary Level) */}
      <div className="flex h-full w-[16%] min-w-[180px] max-w-[220px] shrink-0 flex-col overflow-hidden border-r border-[var(--color-border-2)] bg-[var(--color-bg)]">
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {navCategories.map((id) => {
            const active = category === id;
            return (
              <button
                key={id}
                type="button"
                className={`group mb-1.5 flex w-full cursor-pointer items-center rounded-md py-2.5 pl-3 pr-2.5 text-left text-sm transition-all duration-150 ${
                  active
                    ? 'bg-[var(--color-primary-bg-active)] font-medium text-[var(--color-primary)]'
                    : 'text-[var(--color-text-2)] hover:bg-[var(--color-fill-2)] hover:text-[var(--color-text-1)]'
                }`}
                onClick={() => setCategory(id)}
              >
                <div className="flex min-w-0 items-center gap-2.5">
                  <span
                    className={`text-base transition-colors ${
                      active
                        ? 'text-[var(--color-primary)]'
                        : 'text-[var(--color-text-3)] group-hover:text-[var(--color-text-2)]'
                    }`}
                  >
                    {CATEGORY_ICONS[id] || <AppstoreOutlined />}
                  </span>
                  <span className="truncate">{categoryLabel(id)}</span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="shrink-0">
          <Tabs
            activeKey={typeKey}
            onChange={(key) => {
              setTypeKey(key);
              void loadList({ page: 1, type: key });
            }}
            className="[&_.ant-tabs-nav]:!mb-0 [&_.ant-tabs-nav::before]:!border-[var(--color-border-2)] [&_.ant-tabs-content]:!hidden [&_.ant-tabs-content-holder]:!hidden"
            items={[
              {
                key: ALL_TYPES,
                label: t('system.credential.allTypes'),
              },
              ...typesInCategory.map((item) => ({
                key: item.key,
                label: (
                  <span className="inline-flex items-center">
                    <span>{item.name}</span>
                    <span className="ml-1 font-normal tabular-nums text-[var(--color-text-3)]">
                      ({item.credential_count ?? 0})
                    </span>
                  </span>
                ),
              })),
            ]}
          />
          <div className="py-3">
            <SearchActionBar
              spacing="flush"
              searchProps={{
                placeholder: t('system.credential.searchPlaceholder'),
                enterButton: false,
                onSearch: (value) => {
                  setSearch(value);
                  void loadList({ page: 1, keyword: value });
                },
              }}
              actions={(
                <>
                  <div className="w-48">
                    <GroupTreeSelect
                      multiple={false}
                      mode="ownership"
                      allowClear
                      showSearch
                      placeholder={t('system.credential.organization')}
                      value={ownerId}
                      onChange={(value) => {
                        const next = typeof value === 'number' ? value : undefined;
                        setOwnerId(next);
                        void loadList({ page: 1, owner: next ?? null });
                      }}
                    />
                  </div>
                  <PermissionWrapper requiredPermissions={['Add']}>
                    <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                      {t('system.credential.addCredential')}
                    </Button>
                  </PermissionWrapper>
                </>
              )}
            />
          </div>
        </div>

        {/* Content Table / Empty */}
        <div className="min-h-0 flex-1">
          {!typesInCategory.length && !loading ? (
            <div className="flex h-full min-h-[300px] flex-col items-center justify-center rounded-lg border border-dashed border-[var(--color-border-2)] bg-[var(--color-fill-1)]/20 p-8 text-center">
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={(
                  <div className="space-y-3">
                    <p className="text-sm text-[var(--color-text-3)]">
                      {t('system.credential.noTypeHint')}
                    </p>
                    <Button type="primary" ghost size="small" onClick={onGoTypes}>
                      {t('system.credential.goTypes')}
                    </Button>
                  </div>
                )}
              />
            </div>
          ) : (
            <CustomTable
              rowKey="credential_id"
              loading={loading}
              columns={columns}
              dataSource={items}
              pagination={{
                current: pagination.current,
                pageSize: pagination.pageSize,
                total: pagination.total,
                showSizeChanger: true,
                onChange: (page, pageSize) => void loadList({ page, pageSize }),
              }}
            />
          )}
        </div>
      </div>
      <CredentialFormDrawer
        open={drawerOpen}
        mode={drawerMode}
        types={typeKey === ALL_TYPES ? typesInCategory : typesInCategory.filter((item) => item.key === typeKey)}
        groups={assignableGroups}
        lockedType={lockedType}
        record={current}
        loading={detailLoading}
        onClose={closeDrawer}
        onSubmit={async (payload) => {
          if (drawerMode === 'create') {
            await createCredential(payload);
            await Promise.all([loadMeta(), loadList()]);
          } else if (current) {
            await updateCredential(current.credential_id, payload);
            await loadList();
          }
        }}
      />
    </div>
  );
};

export default CredentialListTab;
