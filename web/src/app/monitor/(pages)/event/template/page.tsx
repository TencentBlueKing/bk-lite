'use client';
import './register-template-pilot';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Checkbox, Dropdown, Form, Input, message, Modal, Spin, Tag, Tooltip, Upload } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import {
  CaretRightOutlined,
  DeleteOutlined,
  DownloadOutlined,
  DownOutlined,
  SearchOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import useEventApi from '@/app/monitor/api/event';
import templateStyle from './index.module.scss';
import { TreeItem, TableDataItem, ObjectItem } from '@/app/monitor/types';
import { findLabelById, getIconByObjectName } from '@/app/monitor/utils/common';
import { OBJECT_DEFAULT_ICON } from '@/app/monitor/constants';
import { useSearchParams, useRouter } from 'next/navigation';
import TreeSelector from '@/app/monitor/components/treeSelector';
import { useMonitorObjectQuery } from '@/app/monitor/hooks/useMonitorObjectQuery';
import {
  resolveMonitorObjectQueryId,
  resolveMonitorObjectTreeKey
} from '@/app/monitor/utils/monitorObjectQuery';
import ResizableSidebar from '@/app/monitor/components/resizableSidebar';
import { cloneDeep } from 'lodash';
import BulkApplyModal from './bulkApplyModal';
import { buildMonitorStrategyDetailUrl } from '@/app/monitor/utils/policyRouteUtils';
import {
  clearTemplateSelection,
  containsBuiltinTemplate,
  formatTemplateListName,
  getTemplateKey,
  getTemplateMetricName,
  groupPolicyTemplates,
  PolicyTemplateItem,
  resolveTemplateDuration,
  selectTemplateGroup,
  toggleTemplateSelection
} from './templateBulkUtils';
import { resolveTemplateQueryCondition } from '../strategy/detail/formulaExpressionUtils';

const MAX_VISIBLE_SELECTED_TEMPLATE_TAGS = 4;

const Template: React.FC = () => {
  const { isLoading } = useApiClient();
  const { getMonitorObject } = useMonitorApi();
  const {
    getPolicyTemplate,
    getTemplateObjects,
    importPolicyTemplates,
    exportPolicyTemplates,
    bulkDeletePolicyTemplates,
    savePolicyTemplate,
  } = useEventApi();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { syncObjectId } = useMonitorObjectQuery();
  const templateAbortControllerRef = useRef<AbortController | null>(null);
  const templateRequestIdRef = useRef<number>(0);
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [treeLoading, setTreeLoading] = useState<boolean>(false);
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [defaultSelectObj, setDefaultSelectObj] = useState<React.Key>('');
  const [objectId, setObjectId] = useState<React.Key>('');
  const [objects, setObjects] = useState<ObjectItem[]>([]);
  const [selectedTemplateKeys, setSelectedTemplateKeys] = useState<string[]>([]);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [searchKeyword, setSearchKeyword] = useState('');
  const [bulkModalVisible, setBulkModalVisible] = useState(false);
  const [importing, setImporting] = useState(false);
  const [batchOperating, setBatchOperating] = useState(false);
  const [cloneTarget, setCloneTarget] = useState<PolicyTemplateItem | null>(null);
  const [cloneSaving, setCloneSaving] = useState(false);
  const [cloneForm] = Form.useForm<{ name: string; description?: string }>();

  const filteredTableData = useMemo(() => {
    const keyword = searchKeyword.trim().toLowerCase();
    if (!keyword) return tableData;
    return tableData.filter((item) => {
      const content = [
        item.name,
        item.description,
        item.metric_name,
        item.template_group,
        item.plugin_display_name,
        item.plugin_name
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return content.includes(keyword);
    });
  }, [tableData, searchKeyword]);

  const templateGroups = useMemo(
    () => groupPolicyTemplates(filteredTableData, selectedTemplateKeys),
    [filteredTableData, selectedTemplateKeys]
  );

  const selectedTemplates = useMemo(
    () =>
      tableData.filter((item) =>
        selectedTemplateKeys.includes(getTemplateKey(item))
      ),
    [tableData, selectedTemplateKeys]
  );

  const selectedTemplateTags = useMemo(() => {
    return selectedTemplates.map((item) => ({
      key: getTemplateKey(item),
      label: formatTemplateListName(item, selectedTemplates)
    }));
  }, [selectedTemplates]);

  const visibleSelectedTemplateTags = selectedTemplateTags.slice(
    0,
    MAX_VISIBLE_SELECTED_TEMPLATE_TAGS
  );
  const hiddenSelectedTemplateTags = selectedTemplateTags.slice(
    MAX_VISIBLE_SELECTED_TEMPLATE_TAGS
  );

  useEffect(() => {
    if (isLoading) return;
    getObjects();
  }, [isLoading]);

  useEffect(() => {
    if (objectId) {
      getAssetInsts(objectId);
    }
  }, [objectId]);

  useEffect(() => {
    return () => {
      cancelAllRequests();
    };
  }, []);

  const cancelAllRequests = () => {
    templateAbortControllerRef.current?.abort();
  };

  const handleObjectChange = async (id: string) => {
    cancelAllRequests();
    setObjectId(id);
    syncObjectId(id);
    setSelectedTemplateKeys(clearTemplateSelection());
    setCollapsedGroups(new Set());
    setSearchKeyword('');
  };

  const toggleGroupCollapsed = (groupName: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupName)) {
        next.delete(groupName);
      } else {
        next.add(groupName);
      }
      return next;
    });
  };

  const getAssetInsts = async (objectId: React.Key) => {
    templateAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    templateAbortControllerRef.current = abortController;
    const currentRequestId = ++templateRequestIdRef.current;
    try {
      setTableLoading(true);
      const monitorName = findLabelById(treeData, objectId as string);
      const params = {
        monitor_object_name: monitorName
      };
      const data = await getPolicyTemplate(params, {
        signal: abortController.signal
      });
      if (currentRequestId !== templateRequestIdRef.current) return;
      const list = data.map((item: TableDataItem, index: number) => ({
        ...item,
        id: item.id ?? `${item.plugin_id || item.collect_type || monitorName}:${item.name || item.metric_name || index}:${index}`,
        template_key: item.template_key || `${item.plugin_id || item.collect_type || monitorName}:${item.name || item.metric_name || index}:${index}`,
        description: item.description || '--',
        icon: getIconByObjectName(monitorName as string, objects)
      }));
      setTableData(list);
      setSelectedTemplateKeys(clearTemplateSelection());
      setCollapsedGroups(new Set());
    } finally {
      if (currentRequestId === templateRequestIdRef.current) {
        setTableLoading(false);
      }
    }
  };

  const getObjects = async () => {
    setTreeLoading(true);
    Promise.all([getMonitorObject(), getTemplateObjects()])
      .then((res) => {
        const monitorObjects = (res[0] || []).filter((item: ObjectItem) =>
          (res[1] || []).includes(item.id)
        );
        setObjects(monitorObjects);
        const _treeData = getTreeData(cloneDeep(monitorObjects));
        const defaulltId = (_treeData[0]?.children || [])[0]?.key;
        setDefaultSelectObj(
          resolveMonitorObjectTreeKey(
            monitorObjects,
            resolveMonitorObjectQueryId({
              searchParams,
              objects: monitorObjects,
              fallback: defaulltId
            }),
            defaulltId
          )
        );
        setTreeData(_treeData);
      })
      .finally(() => {
        setTreeLoading(false);
      });
  };

  const getTreeData = (data: ObjectItem[]): TreeItem[] => {
    const groupedData = data.reduce(
      (acc, item) => {
        if (!acc[item.type]) {
          acc[item.type] = {
            title: item.display_type || '--',
            key: item.type,
            children: []
          };
        }
        acc[item.type].children.push({
          title: item.display_name || '--',
          label: item.name || '--',
          key: item.id,
          icon: item.icon,
          children: []
        });
        return acc;
      },
      {} as Record<string, TreeItem>
    );
    return Object.values(groupedData);
  };

  const handleApply = () => {
    if (!selectedTemplates.length) {
      message.warning('请先选择策略模版');
      return;
    }
    setBulkModalVisible(true);
  };

  const refreshTemplates = () => {
    if (objectId) void getAssetInsts(objectId);
  };

  const handleImport = async (file: File, overwrite = false) => {
    try {
      setImporting(true);
      const result = await importPolicyTemplates(file, overwrite);
      if (result.requires_overwrite) {
        Modal.confirm({
          title: '覆盖重复模版？',
          content: `检测到 ${result.conflicts.length} 个重复的自定义模版，继续导入将覆盖当前项目中的配置，内置模版不会受影响。覆盖后将同步已从这些模板下发的策略。`,
          okText: '覆盖导入',
          cancelText: '取消',
          onOk: () => handleImport(file, true),
        });
        return;
      }
      message.success(`成功导入 ${result.imported_count} 个模版`);
      setSelectedTemplateKeys(clearTemplateSelection());
      refreshTemplates();
    } finally {
      setImporting(false);
    }
  };

  const handleExport = async () => {
    if (!selectedTemplateKeys.length) return;
    try {
      setBatchOperating(true);
      const blob = await exportPolicyTemplates(selectedTemplateKeys);
      const url = URL.createObjectURL(blob as Blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'monitor-policy-templates.zip';
      link.click();
      URL.revokeObjectURL(url);
    } finally {
      setBatchOperating(false);
    }
  };

  const containsBuiltin = containsBuiltinTemplate(selectedTemplates);

  const handleEditTemplate = (
    item: PolicyTemplateItem,
    event: React.MouseEvent
  ) => {
    event.stopPropagation();
    event.preventDefault();
    if (item.template_type !== 'custom') {
      message.warning('内置模版不可编辑');
      return;
    }
    const monitorName = findLabelById(treeData, objectId as string);
    router.push(
      buildMonitorStrategyDetailUrl('editTemplate', {
        monitorObjId: objectId as string | number,
        monitorName: String(monitorName || ''),
        id: getTemplateKey(item),
        name: String(item.name || ''),
        templateKey: getTemplateKey(item),
      })
    );
  };

  const handleOpenClone = (
    item: PolicyTemplateItem,
    event: React.MouseEvent
  ) => {
    event.stopPropagation();
    event.preventDefault();
    const sourceName = String(item.name || '').trim() || '模版';
    cloneForm.setFieldsValue({
      name: `${sourceName}-副本`,
      description: item.description === '--' ? '' : String(item.description || ''),
    });
    setCloneTarget(item);
  };

  const handleCloneTemplate = async () => {
    if (!cloneTarget) return;
    const values = await cloneForm.validateFields();
    const name = String(values.name || '').trim();
    if (!name) return;
    try {
      setCloneSaving(true);
      await savePolicyTemplate({
        monitor_object: cloneTarget.monitor_object_id || objectId,
        plugin: cloneTarget.plugin_id,
        name,
        description: String(values.description || ''),
        config: {
          ...cloneTarget,
          schedule: resolveTemplateDuration(cloneTarget.schedule),
          period: resolveTemplateDuration(cloneTarget.period),
          query_condition: resolveTemplateQueryCondition(cloneTarget),
        },
      });
      message.success('模版克隆成功');
      setCloneTarget(null);
      cloneForm.resetFields();
      refreshTemplates();
    } finally {
      setCloneSaving(false);
    }
  };

  const handleDelete = () => {
    if (!selectedTemplateKeys.length || containsBuiltin) return;
    Modal.confirm({
      title: `删除选中的 ${selectedTemplateKeys.length} 个模版？`,
      content: '删除后无法恢复。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          setBatchOperating(true);
          await bulkDeletePolicyTemplates(selectedTemplateKeys);
          message.success('模版删除成功');
          setSelectedTemplateKeys(clearTemplateSelection());
          refreshTemplates();
        } finally {
          setBatchOperating(false);
        }
      },
    });
  };

  const renderTemplateCard = (item: PolicyTemplateItem) => {
    const key = getTemplateKey(item);
    const selected = selectedTemplateKeys.includes(key);
    const icon = item.icon || OBJECT_DEFAULT_ICON;
    const metricName = getTemplateMetricName(item);
    const isCustom = item.template_type === 'custom';
    return (
      <div
        key={key}
        role="button"
        tabIndex={0}
        className={`${templateStyle.templateCard} ${selected ? templateStyle.templateCardSelected : ''}`}
        aria-pressed={selected}
        onClick={() => {
          setSelectedTemplateKeys((prev) => toggleTemplateSelection(prev, item));
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            setSelectedTemplateKeys((prev) => toggleTemplateSelection(prev, item));
          }
        }}
      >
        <Checkbox checked={selected} className={templateStyle.cardCheckbox} />
        <div className={templateStyle.cardIcon}>
          <img
            src={`/assets/icons/${icon}.svg`}
            alt={String(icon)}
            onError={(e) => {
              (e.target as HTMLImageElement).src =
                `/assets/icons/${OBJECT_DEFAULT_ICON}.svg`;
            }}
          />
        </div>
        <div className={templateStyle.cardBody}>
          <div className={templateStyle.cardTitle}>
            <Tooltip title={item.name || '--'} mouseEnterDelay={0.3}>
              <span className={templateStyle.cardTitleInner}>
                <span className={templateStyle.cardTitleText}>{item.name || '--'}</span>
                <span
                  className={`${templateStyle.cardTypeBadge} ${
                    isCustom
                      ? templateStyle.cardCustomBadge
                      : templateStyle.cardBuiltinBadge
                  }`}
                >
                  {isCustom ? '自定义' : '内置'}
                </span>
              </span>
            </Tooltip>
          </div>
          {metricName ? (
            <div className={templateStyle.cardMetric} title={metricName}>
              {metricName}
            </div>
          ) : null}
          <div className={templateStyle.cardDescription} title={item.description || '--'}>
            {item.description || '--'}
          </div>
          <div className="mt-2 flex items-center gap-1">
            {isCustom ? (
              <Button
                type="link"
                size="small"
                className="h-auto p-0 text-xs leading-[18px]"
                onClick={(event) => handleEditTemplate(item, event)}
              >
                编辑
              </Button>
            ) : null}
            <Button
              type="link"
              size="small"
              className="h-auto p-0 text-xs leading-[18px]"
              onClick={(event) => handleOpenClone(item, event)}
            >
              克隆
            </Button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className={templateStyle.container}>
      <ResizableSidebar collapseStorageKey="monitor.event.template.sidebarCollapsed">
        <div className={templateStyle.containerTree}>
          <TreeSelector
            data={treeData}
            defaultSelectedKey={defaultSelectObj as string}
            loading={treeLoading}
            onNodeSelect={handleObjectChange}
          />
        </div>
      </ResizableSidebar>

      <div className={templateStyle.table}>
        <div className={`${templateStyle.toolbar} gap-4`}>
          <Input
            allowClear
            suffix={<SearchOutlined />}
            placeholder="搜索模版名称、指标或描述"
            value={searchKeyword}
            onChange={(event) => setSearchKeyword(event.target.value)}
          />
          <div className="flex items-center gap-2">
            <Upload
              accept=".zip,application/zip"
              showUploadList={false}
              beforeUpload={(file) => {
                void handleImport(file as File);
                return Upload.LIST_IGNORE;
              }}
            >
              <Button icon={<UploadOutlined />} loading={importing}>导入</Button>
            </Upload>
            <Dropdown
              menu={{
                items: [
                  {
                    key: 'export',
                    label: '批量导出',
                    icon: <DownloadOutlined />,
                    disabled: !selectedTemplateKeys.length,
                    onClick: () => void handleExport(),
                  },
                  {
                    key: 'delete',
                    label: containsBuiltin ? '批量删除（内置模版不可删除）' : '批量删除',
                    icon: <DeleteOutlined />,
                    danger: true,
                    disabled: !selectedTemplateKeys.length || containsBuiltin,
                    onClick: handleDelete,
                  },
                ],
              }}
            >
              <Button loading={batchOperating}>批量操作 <DownOutlined /></Button>
            </Dropdown>
          </div>
        </div>

        <Spin spinning={tableLoading}>
          {templateGroups.length ? (
            <div className={templateStyle.groupList}>
              {templateGroups.map((group) => {
                const allChecked =
                  group.templates.length > 0 &&
                  group.selectedCount === group.templates.length;
                const indeterminate =
                  group.selectedCount > 0 &&
                  group.selectedCount < group.templates.length;
                const collapsed = collapsedGroups.has(group.name);
                return (
                  <section key={group.name} className={templateStyle.templateGroup}>
                    <div className={templateStyle.groupHeader}>
                      <div className="flex min-w-0 items-center gap-2">
                        <Tooltip title={collapsed ? '展开分组' : '收起分组'} mouseEnterDelay={0.3}>
                          <button
                            type="button"
                            className={templateStyle.groupCollapseBtn}
                            aria-expanded={!collapsed}
                            aria-label={collapsed ? '展开分组' : '收起分组'}
                            onClick={() => toggleGroupCollapsed(group.name)}
                          >
                            <CaretRightOutlined
                              className={`${templateStyle.groupCollapseIcon} ${
                                collapsed ? '' : templateStyle.groupCollapseIconExpanded
                              }`}
                            />
                          </button>
                        </Tooltip>
                        <span className={templateStyle.groupName}>{group.name}</span>
                        <span className={templateStyle.groupCount}>
                          {group.templates.length} 个模版
                        </span>
                      </div>
                      <div className={templateStyle.groupActions}>
                        <span className={templateStyle.groupSelected}>
                          已选 {group.selectedCount} / {group.templates.length}
                        </span>
                        <Checkbox
                          checked={allChecked}
                          indeterminate={indeterminate}
                          onChange={(event) => {
                            setSelectedTemplateKeys((prev) =>
                              selectTemplateGroup(
                                prev,
                                group.templates,
                                event.target.checked
                              )
                            );
                          }}
                        >
                          全选本组
                        </Checkbox>
                      </div>
                    </div>
                    {!collapsed && (
                      <div className={templateStyle.cardGrid}>
                        {group.templates.map(renderTemplateCard)}
                      </div>
                    )}
                  </section>
                );
              })}
            </div>
          ) : (
            <CompactEmptyState description={tableLoading ? '加载中' : '暂无策略模版'} />
          )}
        </Spin>

        {selectedTemplates.length > 0 && (
          <div className={templateStyle.bulkBar}>
            <div className={templateStyle.bulkSummary}>
              <span className={templateStyle.bulkCount}>
                已选 {selectedTemplates.length} 个策略模版
              </span>
              <div className={templateStyle.bulkTags}>
                {visibleSelectedTemplateTags.map((tag) => (
                  <Tag
                    key={tag.key}
                    className={templateStyle.bulkTemplateTag}
                    title={tag.label}
                  >
                    {tag.label}
                  </Tag>
                ))}
                {hiddenSelectedTemplateTags.length > 0 && (
                  <Tag
                    className={templateStyle.bulkMoreTag}
                    title={hiddenSelectedTemplateTags
                      .map((tag) => tag.label)
                      .join('、')}
                  >
                    +{hiddenSelectedTemplateTags.length}
                  </Tag>
                )}
              </div>
            </div>
            <div className={templateStyle.bulkActions}>
              <Button onClick={() => setSelectedTemplateKeys(clearTemplateSelection())}>
                清空
              </Button>
              <Button type="primary" onClick={handleApply}>
                应用
              </Button>
            </div>
          </div>
        )}
      </div>

      <BulkApplyModal
        visible={bulkModalVisible}
        monitorObjectId={objectId as string | number}
        monitorName={
          objects.find((item) => String(item.id) === String(objectId))?.name
        }
        selectedTemplates={selectedTemplates}
        onClose={() => setBulkModalVisible(false)}
        onSuccess={() => setSelectedTemplateKeys(clearTemplateSelection())}
      />
      <Modal
        title="克隆策略模版"
        open={Boolean(cloneTarget)}
        onCancel={() => {
          if (cloneSaving) return;
          setCloneTarget(null);
          cloneForm.resetFields();
        }}
        onOk={() => void handleCloneTemplate()}
        confirmLoading={cloneSaving}
        okText="克隆"
        cancelText="取消"
        destroyOnHidden
      >
        <Form form={cloneForm} layout="vertical">
          <Form.Item
            name="name"
            label="模版名称"
            rules={[{ required: true, message: '请输入模版名称' }]}
          >
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} maxLength={500} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default Template;
