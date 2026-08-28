'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Button,
  Input,
  Modal,
  Popconfirm,
  Spin,
  message,
} from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import { useCommon } from '@/app/cmdb/context/common';
import { useModelApi, useSceneViewApi, useInstanceApi } from '@/app/cmdb/api';
import type { AttrFieldType, ColumnItem, ModelItem, UserItem } from '@/app/cmdb/types/assetManage';
import { getAssetColumns } from '@/app/cmdb/utils/common';
import { resolveCmdbInstUuid } from '@/app/cmdb/utils/instUuid';
import { buildBaseInfoPath } from '@/app/cmdb/(pages)/views/viewUrls';
import SceneEditorDrawer from './SceneEditorDrawer';
import ViewSummary from './viewSummary';
import ModelResultSection from './modelResultSection';
import {
  groupSceneViews,
  type SceneViewRecord,
} from './groupScenes';
import {
  browserStorage,
  readModelSearches,
  toSearchPayload,
  writeModelSearch,
  type ModelSearchPreference,
} from './tagViewSearchPreference';
import type {
  SceneExecuteResult,
  SceneViewPayload,
} from '@/app/cmdb/api/sceneView';

const DEFAULT_PAGE_SIZE = 20;
const GROUP_LABEL: Record<SceneViewRecord['visibility'], string> = {
  personal: 'SceneView.groupMine',
  organization: 'SceneView.groupOrg',
  global: 'SceneView.groupGlobal',
};

interface ModelPager {
  page: number;
  pageSize: number;
}

const toPaginationPayload = (pagers: Record<string, ModelPager>) =>
  Object.fromEntries(
    Object.entries(pagers).map(([modelId, pager]) => [
      modelId,
      { page: pager.page, page_size: pager.pageSize },
    ])
  );

const SceneViewPage = () => {
  const { t } = useTranslation();
  const common = useCommon();
  const modelList: ModelItem[] = common?.modelList || [];
  const userList: UserItem[] = common?.userList || [];
  const { getModelAttrList } = useModelApi();
  const { getInstanceProxys } = useInstanceApi();
  const {
    listSceneViews,
    createSceneView,
    updateSceneView,
    deleteSceneView,
    executeSceneView,
    saveAsSceneView,
    exportSceneView,
  } = useSceneViewApi();

  const [scenes, setScenes] = useState<SceneViewRecord[]>([]);
  const [capabilities, setCapabilities] = useState({
    can_org_share: false,
    can_global: false,
  });
  const [listLoading, setListLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [result, setResult] = useState<SceneExecuteResult | null>(null);
  const [loadingScope, setLoadingScope] = useState<'all' | string | null>(null);
  const [modelPagers, setModelPagers] = useState<Record<string, ModelPager>>({});
  const [modelSearches, setModelSearches] = useState<Record<string, ModelSearchPreference>>({});
  const [attrByModel, setAttrByModel] = useState<Record<string, AttrFieldType[]>>({});
  const [proxyOptions, setProxyOptions] = useState<Array<{ proxy_id: string; proxy_name: string }>>([]);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<SceneViewRecord | null>(null);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [saveAsOpen, setSaveAsOpen] = useState(false);
  const [saveAsName, setSaveAsName] = useState('');

  const selected = useMemo(
    () => scenes.find((item) => item.id === selectedId) || null,
    [scenes, selectedId]
  );
  const groups = useMemo(() => groupSceneViews(scenes), [scenes]);
  const modelNameById = useMemo(() => {
    const map = new Map<string, ModelItem>();
    for (const item of modelList) map.set(item.model_id, item);
    return map;
  }, [modelList]);

  const refreshList = useCallback(async () => {
    setListLoading(true);
    try {
      const data = await listSceneViews();
      setScenes(data?.results || []);
      setCapabilities({
        can_org_share: Boolean(data?.capabilities?.can_org_share),
        can_global: Boolean(data?.capabilities?.can_global),
      });
    } finally {
      setListLoading(false);
    }
  }, [listSceneViews]);

  const runExecute = useCallback(
    async (
      id: number,
      pagers: Record<string, ModelPager>,
      searches: Record<string, ModelSearchPreference>,
      scope: 'all' | string
    ) => {
      setLoadingScope(scope);
      try {
        const data = await executeSceneView(id, {
          pagination: toPaginationPayload(pagers),
          searches: toSearchPayload(searches),
        });
        setResult(data);
        setModelPagers(() => {
          const next = { ...pagers };
          for (const item of data?.models || []) {
            if (!next[item.model_id]) {
              next[item.model_id] = { page: 1, pageSize: DEFAULT_PAGE_SIZE };
            }
          }
          return next;
        });
      } finally {
        setLoadingScope(null);
      }
    },
    [executeSceneView]
  );

  useEffect(() => {
    refreshList();
  }, [refreshList]);

  useEffect(() => {
    if (!selectedId) {
      setResult(null);
      setModelPagers({});
      setModelSearches({});
      setCollapsed({});
      return;
    }
    const searches = readModelSearches(browserStorage(), selectedId);
    setModelPagers({});
    setModelSearches(searches);
    setCollapsed({});
    runExecute(selectedId, {}, searches, 'all');
  }, [runExecute, selectedId]);

  const selectedModelKey = (selected?.model_ids || []).join(',');

  useEffect(() => {
    const modelIds = selectedModelKey ? selectedModelKey.split(',') : [];
    if (!modelIds.length) return;
    let cancelled = false;
    Promise.all(
      modelIds.map(async (modelId) => {
        try {
          const attrs = await getModelAttrList(modelId);
          return [modelId, Array.isArray(attrs) ? attrs : []] as const;
        } catch {
          return [modelId, []] as const;
        }
      })
    ).then((rows) => {
      if (!cancelled) setAttrByModel((prev) => ({ ...prev, ...Object.fromEntries(rows) }));
    });
    if (modelIds.some((modelId) => modelId === 'host' || modelId === 'subnet')) {
      getInstanceProxys()
        .then((data: Array<{ proxy_id: string; proxy_name: string }>) => {
          if (!cancelled) setProxyOptions(data || []);
        })
        .catch(() => {
          if (!cancelled) setProxyOptions([]);
        });
    }
    return () => {
      cancelled = true;
    };
  }, [selectedModelKey]);

  const handleSubmit = async (payload: SceneViewPayload) => {
    setSaving(true);
    try {
      const saved = editing
        ? await updateSceneView(editing.id, payload)
        : await createSceneView(payload);
      const wasEdit = Boolean(editing);
      setEditorOpen(false);
      setEditing(null);
      await refreshList();
      setSelectedId(saved.id);
      if (wasEdit) {
        const searches = readModelSearches(browserStorage(), saved.id);
        setModelSearches(searches);
        await runExecute(saved.id, {}, searches, 'all');
      }
      message.success(t(wasEdit ? 'successfullyModified' : 'successfullyAdded'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!selected) return;
    await deleteSceneView(selected.id);
    setSelectedId(null);
    await refreshList();
    message.success(t('successfullyDeleted'));
  };

  const handleSaveAs = async () => {
    if (!selected) return;
    const name = saveAsName.trim();
    if (!name) {
      message.error(t('SceneView.needName'));
      return;
    }
    const copy = await saveAsSceneView(selected.id, name);
    setSaveAsOpen(false);
    await refreshList();
    setSelectedId(copy.id);
    message.success(t('SceneView.savedAs'));
  };

  const handleExport = async () => {
    if (!selected || !result?.total) return;
    setExporting(true);
    try {
      const blob = await exportSceneView(selected.id);
      if (blob.type && blob.type.includes('application/json')) {
        const text = await blob.text();
        const payload = JSON.parse(text);
        message.error(payload.message || t('SceneView.noMatches'));
        return;
      }
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${selected.name}.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      message.success(t('SceneView.exported'));
    } finally {
      setExporting(false);
    }
  };

  const handleModelPageChange = (modelId: string, page: number, pageSize: number) => {
    if (!selectedId) return;
    const next = {
      ...modelPagers,
      [modelId]: { page, pageSize },
    };
    setModelPagers(next);
    runExecute(selectedId, next, modelSearches, modelId);
  };

  const handleModelSearch = (modelId: string, preference: ModelSearchPreference) => {
    if (!selectedId) return;
    const nextSearches = writeModelSearch(
      browserStorage(),
      selectedId,
      modelId,
      preference
    );
    const nextPagers = {
      ...modelPagers,
      [modelId]: {
        page: 1,
        pageSize: modelPagers[modelId]?.pageSize || DEFAULT_PAGE_SIZE,
      },
    };
    setModelSearches(nextSearches);
    setModelPagers(nextPagers);
    setCollapsed((prev) => ({ ...prev, [modelId]: false }));
    runExecute(selectedId, nextPagers, nextSearches, modelId);
  };

  const jumpToModel = (modelId: string) => {
    setCollapsed((prev) => ({ ...prev, [modelId]: false }));
    document
      .getElementById(`tag-view-model-${modelId}`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const linkFirstColumn = (columns: ColumnItem[], modelId: string): ColumnItem[] => {
    if (!columns.length) return columns;
    const [first, ...rest] = columns;
    const originalRender = first.render;
    return [
      {
        ...first,
        render: (value: unknown, record: Record<string, unknown>) => {
          const content = originalRender
            ? originalRender(value, record)
            : value == null || value === ''
              ? '--'
              : String(value);
          const instUuid = resolveCmdbInstUuid(record?.inst_uuid);
          if (!instUuid) return <>{content}</>;
          const model = modelNameById.get(modelId);
          return (
            <a
              href={buildBaseInfoPath({
                model_id: modelId,
                inst_uuid: instUuid,
                inst_name: String(record.inst_name || ''),
                model_name: model?.model_name,
                icn: model?.icn,
              })}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--color-primary)]"
            >
              {content}
            </a>
          );
        },
      },
      ...rest,
    ];
  };

  return (
    <div className="flex h-full min-h-0 bg-[var(--color-bg-1)]">
      <aside className="flex w-64 shrink-0 flex-col border-r border-[var(--color-border-1)]">
        <div className="flex items-center justify-between gap-2 px-3 py-3">
          <div className="text-sm font-medium text-[var(--color-text-1)]">
            {t('SceneView.title')}
          </div>
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditing(null);
              setEditorOpen(true);
            }}
          >
            {t('SceneView.create')}
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto px-2 pb-3">
          {listLoading ? (
            <div className="flex justify-center py-8">
              <Spin />
            </div>
          ) : groups.length === 0 ? (
            <CompactEmptyState description={t('SceneView.emptyList')} />
          ) : (
            groups.map((group) => (
              <div key={group.key} className="mb-3">
                <div className="px-2 py-1 text-xs text-[var(--color-text-3)]">
                  {t(GROUP_LABEL[group.key])}
                </div>
                {group.items.map((item) => {
                  const active = item.id === selectedId;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={`mb-1 w-full rounded px-2 py-1.5 text-left text-sm ${
                        active
                          ? 'bg-[var(--color-fill-2)] text-[var(--color-primary)]'
                          : 'text-[var(--color-text-1)] hover:bg-[var(--color-fill-1)]'
                      }`}
                      onClick={() => setSelectedId(item.id)}
                    >
                      {item.name}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        {!selected ? (
          <div className="flex h-full items-center justify-center">
            <CompactEmptyState description={t('SceneView.emptyPick')} />
          </div>
        ) : (
          <>
            <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-[var(--color-border-1)] px-4 py-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <div className="truncate text-base font-medium text-[var(--color-text-1)]">
                    {selected.name}
                  </div>
                  {!selected.can_edit && (
                    <span className="text-xs text-[var(--color-text-3)]">
                      {t('SceneView.readonly')}
                    </span>
                  )}
                </div>
                <div className="mt-1 text-xs text-[var(--color-text-3)]">
                  {selected.tags.join(selected.tag_match === 'or' ? ' | ' : ' + ')}
                </div>
              </div>
              {selected.can_edit && (
                <>
                  <Button
                    onClick={() => {
                      setEditing(selected);
                      setEditorOpen(true);
                    }}
                  >
                    {t('SceneView.edit')}
                  </Button>
                  <Popconfirm
                    title={t('deleteTitle')}
                    description={t('SceneView.deleteConfirm')}
                    onConfirm={handleDelete}
                  >
                    <Button danger>{t('common.delete')}</Button>
                  </Popconfirm>
                </>
              )}
              <Button
                onClick={() => {
                  setSaveAsName(`${selected.name}`);
                  setSaveAsOpen(true);
                }}
              >
                {t('SceneView.saveAs')}
              </Button>
              <Button
                type="primary"
                disabled={!result?.total}
                loading={exporting}
                onClick={handleExport}
              >
                {t('SceneView.export')}
              </Button>
            </div>

            <div className="min-h-0 flex-1 overflow-auto p-4">
              <Spin spinning={loadingScope === 'all'}>
                {result && (
                  <ViewSummary
                    total={result.total}
                    models={result.models || []}
                    modelNameById={modelNameById}
                    onJump={jumpToModel}
                  />
                )}

                {!(result?.models || []).length ? (
                  <CompactEmptyState description={t('SceneView.noMatches')} />
                ) : (
                  (result.models || []).map((item) => {
                    const attrs = (item.columns || []).map(
                      (col) =>
                        ({
                          attr_id: col.attr_id,
                          attr_name: col.attr_name,
                          attr_type: col.attr_type,
                          is_required: false,
                          editable: false,
                          option: [],
                        }) as AttrFieldType
                    );
                    const columns = linkFirstColumn(
                      attrs.length
                        ? getAssetColumns({ attrList: attrs, userList, t })
                        : [
                          {
                            title: t('name'),
                            dataIndex: 'inst_name',
                            key: 'inst_name',
                          },
                        ],
                      item.model_id
                    );
                    const pager = modelPagers[item.model_id] || {
                      page: 1,
                      pageSize: DEFAULT_PAGE_SIZE,
                    };
                    return (
                      <ModelResultSection
                        key={`${selectedId}-${item.model_id}`}
                        modelId={item.model_id}
                        title={modelNameById.get(item.model_id)?.model_name || item.model_id}
                        count={item.count}
                        columns={columns}
                        insts={item.insts}
                        page={pager.page}
                        pageSize={pager.pageSize}
                        attrList={attrByModel[item.model_id] || []}
                        userList={userList}
                        proxyOptions={proxyOptions}
                        searchPreference={modelSearches[item.model_id]}
                        collapsed={Boolean(collapsed[item.model_id])}
                        loading={loadingScope === item.model_id}
                        onToggle={() =>
                          setCollapsed((prev) => ({
                            ...prev,
                            [item.model_id]: !prev[item.model_id],
                          }))
                        }
                        onPageChange={(page, pageSize) =>
                          handleModelPageChange(item.model_id, page, pageSize)
                        }
                        onSearch={(preference) =>
                          handleModelSearch(item.model_id, preference)
                        }
                      />
                    );
                  })
                )}
              </Spin>
            </div>
          </>
        )}
      </section>

      <SceneEditorDrawer
        open={editorOpen}
        scene={editing}
        modelList={modelList}
        canOrgShare={capabilities.can_org_share}
        canGlobal={capabilities.can_global}
        saving={saving}
        onClose={() => {
          setEditorOpen(false);
          setEditing(null);
        }}
        onSubmit={handleSubmit}
      />

      <Modal
        title={t('SceneView.saveAs')}
        open={saveAsOpen}
        onCancel={() => setSaveAsOpen(false)}
        onOk={handleSaveAs}
      >
        <Input
          value={saveAsName}
          onChange={(event) => setSaveAsName(event.target.value)}
          placeholder={t('SceneView.saveAsName')}
          maxLength={128}
        />
      </Modal>
    </div>
  );
};

export default SceneViewPage;
