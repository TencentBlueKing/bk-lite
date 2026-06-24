'use client';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Checkbox, Empty, Input, message, Spin, Tag } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import useEventApi from '@/app/monitor/api/event';
import templateStyle from './index.module.scss';
import { TreeItem, TableDataItem, ObjectItem } from '@/app/monitor/types';
import { findLabelById, getIconByObjectName } from '@/app/monitor/utils/common';
import { OBJECT_DEFAULT_ICON } from '@/app/monitor/constants';
import { useSearchParams } from 'next/navigation';
import TreeSelector from '@/app/monitor/components/treeSelector';
import ResizableSidebar from '@/app/monitor/components/resizableSidebar';
import { cloneDeep } from 'lodash';
import BulkApplyModal from './bulkApplyModal';
import {
  clearTemplateSelection,
  getTemplateKey,
  groupPolicyTemplates,
  PolicyTemplateItem,
  selectTemplateGroup,
  toggleTemplateSelection
} from './templateBulkUtils';

const Template: React.FC = () => {
  const { isLoading } = useApiClient();
  const { getMonitorObject } = useMonitorApi();
  const { getPolicyTemplate, getTemplateObjects } = useEventApi();
  const searchParams = useSearchParams();
  const objId = searchParams.get('objId');
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
  const [searchKeyword, setSearchKeyword] = useState('');
  const [bulkModalVisible, setBulkModalVisible] = useState(false);

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
    const groupSet = new Set<string>();
    selectedTemplates.forEach((item) => {
      groupSet.add(item.template_group || item.plugin_display_name || item.plugin_name || '--');
    });
    return Array.from(groupSet);
  }, [selectedTemplates]);

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
    setSelectedTemplateKeys(clearTemplateSelection());
    setSearchKeyword('');
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
        setDefaultSelectObj(objId ? +objId : defaulltId);
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

  const renderTemplateCard = (item: PolicyTemplateItem) => {
    const key = getTemplateKey(item);
    const selected = selectedTemplateKeys.includes(key);
    const icon = item.icon || OBJECT_DEFAULT_ICON;
    return (
      <button
        key={key}
        type="button"
        className={`${templateStyle.templateCard} ${selected ? templateStyle.templateCardSelected : ''}`}
        aria-pressed={selected}
        onClick={() => {
          setSelectedTemplateKeys((prev) => toggleTemplateSelection(prev, item));
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
          <div className={templateStyle.cardTitle} title={item.name || '--'}>
            {item.name || '--'}
          </div>
          <Tag className={templateStyle.cardTag}>
            {item.template_group || item.plugin_display_name || item.plugin_name || '--'}
          </Tag>
          <div className={templateStyle.cardDescription} title={item.description || '--'}>
            {item.description || '--'}
          </div>
        </div>
      </button>
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
        <div className={templateStyle.toolbar}>
          <Input
            allowClear
            suffix={<SearchOutlined />}
            placeholder="搜索模版名称、指标或描述"
            value={searchKeyword}
            onChange={(event) => setSearchKeyword(event.target.value)}
          />
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
                return (
                  <section key={group.name} className={templateStyle.templateGroup}>
                    <div className={templateStyle.groupHeader}>
                      <div>
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
                    <div className={templateStyle.cardGrid}>
                      {group.templates.map(renderTemplateCard)}
                    </div>
                  </section>
                );
              })}
            </div>
          ) : (
            <Empty description={tableLoading ? '加载中' : '暂无策略模版'} />
          )}
        </Spin>

        {selectedTemplates.length > 0 && (
          <div className={templateStyle.bulkBar}>
            <div className={templateStyle.bulkSummary}>
              <span className={templateStyle.bulkCount}>
                已选 {selectedTemplates.length} 个策略模版
              </span>
              <div className={templateStyle.bulkTags}>
                {selectedTemplateTags.map((tag) => (
                  <Tag key={tag}>{tag}</Tag>
                ))}
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
        selectedTemplates={selectedTemplates}
        onClose={() => setBulkModalVisible(false)}
        onSuccess={() => setSelectedTemplateKeys(clearTemplateSelection())}
      />
    </div>
  );
};

export default Template;
