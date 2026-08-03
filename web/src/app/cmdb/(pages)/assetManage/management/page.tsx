'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '@/context/auth';
import { useSession } from 'next-auth/react';
import Introduction from '@/components/introduction';
import { Input, Button, Modal, message, Spin, Empty, Tooltip, Dropdown, Space, Switch, Tag } from 'antd';
import { deepClone } from '@/app/cmdb/utils/common';
import { GroupItem, ModelItem } from '@/app/cmdb/types/assetManage';
import {
  EditTwoTone,
  DeleteTwoTone,
  SwitcherOutlined,
  CopyOutlined,
  PlusOutlined,
  SettingOutlined,
  DownloadOutlined,
  UploadOutlined,
  DownOutlined,
  RightOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  HolderOutlined,
} from '@ant-design/icons';
import {
  DndContext,
  closestCenter,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  arrayMove,
} from '@dnd-kit/sortable';
import SortableItem from '@/app/cmdb/components/sortable-item';
import assetManageStyle from './index.module.scss';
import ModelIcon from '@/app/cmdb/components/model-icon';
import GroupModal from './list/groupModal';
import ModelModal from './list/modelModal';
import CopyModelModal from './list/copyModelModal';
import PublicEnumLibraryModal, { PublicEnumLibraryModalRef } from './list/publicEnumLibraryModal';
import ImportModelConfigModal, { ImportModelConfigModalRef } from './list/importModelConfigModal';
import ExportModelConfigModal, { ExportModelConfigModalRef } from './list/exportModelConfigModal';
import ManageToolbar from './list/manageToolbar';
import CustomTable from '@/components/custom-table';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import PermissionWrapper from '@/components/permission';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useClassificationApi, useInstanceApi, useModelApi } from '@/app/cmdb/api';
import { useCommon } from '@/app/cmdb/context/common';
import { useUserInfoContext } from '@/context/userInfo';
import type { MenuProps } from 'antd';

interface DraftClassification {
  classification_id: string;
  classification_name: string;
  is_visible: boolean;
  order: number;
  models: Array<{
    model_id: string;
    model_name: string;
    icn?: string;
    is_pre?: boolean;
    is_custom_reporting?: boolean;
    is_visible: boolean;
    order_id: number;
  }>;
}

const AssetManage = () => {
  const { getClassificationList, deleteClassification } =
    useClassificationApi();
  const { getModelInstanceCount } = useInstanceApi();
  const { getModelList, saveModelLayout } = useModelApi();
  const { isSuperUser, selectedGroup } = useUserInfoContext();
  const authContext = useAuth();
  const { data: session } = useSession();
  const token = authContext?.token || (session?.user as any)?.token || null;
  const tokenRef = useRef(token);
  const commonContext = useCommon();
  const modelListFromContext = commonContext?.modelList || [];
  const { confirm } = Modal;
  const { t } = useTranslation();
  const router = useRouter();
  const groupRef = useRef<any>(null);
  const modelRef = useRef<any>(null);
  const copyModelRef = useRef<any>(null);
  const publicEnumLibraryRef = useRef<PublicEnumLibraryModalRef>(null);
  const importModelConfigRef = useRef<ImportModelConfigModalRef>(null);
  const exportModelConfigRef = useRef<ExportModelConfigModalRef>(null);
  const [modelGroup, setModelGroup] = useState<GroupItem[]>([]);
  const [groupList, setGroupList] = useState<GroupItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [searchText, setSearchText] = useState<string>('');
  const [rawModelGroup, setRawModelGroup] = useState<GroupItem[]>([]);
  const [collapsedGroupIds, setCollapsedGroupIds] = useState<Set<string>>(
    () => new Set()
  );
  const [manageMode, setManageMode] = useState<boolean>(false);
  const [savingLayout, setSavingLayout] = useState<boolean>(false);
  const [layoutDirty, setLayoutDirty] = useState<boolean>(false);
  const [draftLayout, setDraftLayout] = useState<DraftClassification[]>([]);
  const [selectedClassificationId, setSelectedClassificationId] = useState<string>('');
  const originalLayoutRef = useRef<DraftClassification[]>([]);

  const showConfigButtons = isSuperUser && selectedGroup?.name === 'Default';

  useEffect(() => {
    tokenRef.current = token;
  }, [token]);

  useEffect(() => {
    if (modelListFromContext.length > 0) {
      getModelGroup();
    }
  }, [modelListFromContext]);

  useEffect(() => {
    if (!searchText.trim()) {
      setModelGroup(rawModelGroup);
      return;
    }
    const lower = searchText.toLowerCase();
    const filtered = rawModelGroup.reduce((acc: GroupItem[], group) => {
      if (group.classification_name.toLowerCase().includes(lower)) {
        acc.push({ ...group, count: group.list.length });
      } else {
        const matched = group.list.filter((m) =>
          m.model_name.toLowerCase().includes(lower)
        );
        if (matched.length) {
          acc.push({ ...group, list: matched, count: matched.length });
        }
      }
      return acc;
    }, []);
    setModelGroup(filtered);
  }, [searchText, rawModelGroup]);

  useEffect(() => {
    if (!manageMode) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [groups, models] = await Promise.all([
          getClassificationList(true),
          getModelList(true),
        ]);
        if (cancelled) return;
        const grouped: DraftClassification[] = groups.map((g: any) => ({
          classification_id: g.classification_id,
          classification_name: g.classification_name,
          is_visible: g.is_visible ?? true,
          order: g.order ?? 999,
          models: models
            .filter((m: any) => m.classification_id === g.classification_id)
            .map((m: any) => ({
              model_id: m.model_id,
              model_name: m.model_name,
              icn: m.icn,
              is_pre: m.is_pre,
              is_custom_reporting: m.is_custom_reporting,
              is_visible: m.is_visible ?? true,
              order_id: m.order_id ?? 0,
            }))
            .sort((a: any, b: any) => a.order_id - b.order_id),
        }));
        grouped.sort((a, b) => a.order - b.order);
        setDraftLayout(grouped);
        setSelectedClassificationId(grouped[0]?.classification_id || '');
        originalLayoutRef.current = JSON.parse(JSON.stringify(grouped));
        setLayoutDirty(false);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [manageMode]);

  useEffect(() => {
    if (!manageMode) {
      setDraftLayout([]);
      setSelectedClassificationId('');
      originalLayoutRef.current = [];
      setLayoutDirty(false);
    }
  }, [manageMode]);

  useEffect(() => {
    if (!manageMode || !layoutDirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [manageMode, layoutDirty]);

  const showDeleteConfirm = (row: GroupItem) => {
    confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      centered: true,
      onOk() {
        return new Promise(async (resolve) => {
          try {
            await deleteClassification(row.classification_id);
            message.success(t('successfullyDeleted'));
            getModelGroup();
          } finally {
            resolve(true);
          }
        });
      },
    });
  };

  const showGroupModal = (type: string, row = {}) => {
    const title = t(type === 'add' ? 'Model.addGroup' : 'Model.editGroup');
    groupRef.current?.showModal({
      title,
      type,
      groupInfo: row,
      subTitle: '',
    });
  };

  const showModelModal = (type: string, row = {}) => {
    const title = t(type === 'add' ? 'Model.addModel' : 'Model.editModel');
    modelRef.current?.showModal({
      title,
      type,
      modelForm: row,
      subTitle: '',
    });
  };

  const showCopyModelModal = (model: ModelItem) => {
    copyModelRef.current?.showModal(model);
  };

  const showPublicEnumLibraryModal = () => {
    publicEnumLibraryRef.current?.showModal();
  };

  const showImportModelConfigModal = () => {
    importModelConfigRef.current?.showModal();
  };

  const updateGroupList = () => {
    getModelGroup();
  };

  const updateModelList = async () => {
    // 首先刷新 CommonProvider 中的 modelList
    if (commonContext?.refreshModelList) {
      await commonContext.refreshModelList();
    }
    getModelGroup();
  };

  const onSearch = (value: string) => {
    const keyword = value.trim();
    if (keyword) {
      setCollapsedGroupIds(new Set());
    }
    setSearchText(keyword);
  };

  // 导出模型配置：打开勾选弹窗
  const handleExportConfig = () => {
    exportModelConfigRef.current?.showModal();
  };

  const linkToDetail = (model: ModelItem) => {
    const params = new URLSearchParams({
      model_id: model.model_id,
      model_name: model.model_name,
      icn: model.icn,
      classification_id: model.classification_id,
      is_pre: model.is_pre,
    }).toString();
    router.push(`/cmdb/assetManage/management/detail/attributes?${params}`);
  };


  const getModelGroup = async () => {
    setLoading(true);
    try {
      const [groupData, instCount] = await Promise.all([
        getClassificationList(),
        getModelInstanceCount(),
      ]);
      const groups = deepClone(groupData).map((item: GroupItem) => ({
        ...item,
        list: [],
        count: 0,
      }));
      modelListFromContext.forEach((modelItem: ModelItem) => {
        const target = groups.find(
          (item: GroupItem) =>
            item.classification_id === modelItem.classification_id
        );
        if (target) {
          modelItem.count = instCount[modelItem.model_id] || 0;
          target.list.push(modelItem);
          target.count++;
        }
      });
      setRawModelGroup(groups);
      setModelGroup(groups);
      setGroupList(groupData);
    } finally {
      setLoading(false);
    }
  };

  const linkToInstList = (item: ModelItem) => {
    const params = new URLSearchParams({
      modelId: item.model_id,
      classificationId: item.classification_id,
    }).toString();
    router.push(`/cmdb/assetData?${params}`);
  };

  const handleCopyClick = (e: React.MouseEvent, model: ModelItem) => {
    e.stopPropagation();
    showCopyModelModal(model);
  };

  const toggleModelGroup = (classificationId: string) => {
    setCollapsedGroupIds((previous) => {
      const next = new Set(previous);
      if (next.has(classificationId)) {
        next.delete(classificationId);
      } else {
        next.add(classificationId);
      }
      return next;
    });
  };

  const markDirty = () => setLayoutDirty(true);

  const toggleGroupVisible = (gi: number) => {
    setDraftLayout(prev =>
      prev.map((g, i) => (i === gi ? { ...g, is_visible: !g.is_visible } : g))
    );
    markDirty();
  };

  const toggleModelVisible = (gi: number, mi: number) => {
    setDraftLayout(prev =>
      prev.map((g, i) => {
        if (i !== gi) return g;
        return {
          ...g,
          models: g.models.map((m, j) =>
            j === mi ? { ...m, is_visible: !m.is_visible } : m
          ),
        };
      })
    );
    markDirty();
  };

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleGroupDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    setDraftLayout(prev => {
      const oldIndex = prev.findIndex(g => g.classification_id === active.id);
      const newIndex = prev.findIndex(g => g.classification_id === over.id);
      if (oldIndex < 0 || newIndex < 0) return prev;
      return arrayMove(prev, oldIndex, newIndex);
    });
    markDirty();
  };

  const handleSaveLayout = async () => {
    setSavingLayout(true);
    try {
      const payload = {
        classifications: draftLayout.map((g, idx) => ({
          classification_id: g.classification_id,
          order: idx,
          is_visible: g.is_visible,
        })),
        models: draftLayout.flatMap(g =>
          g.models.map((m, idx) => ({
            model_id: m.model_id,
            order_id: idx,
            is_visible: m.is_visible,
          }))
        ),
      };
      await saveModelLayout(payload);
      message.success(t('common.updateSuccess'));
      if (commonContext?.refreshModelList) {
        await commonContext.refreshModelList();
      }
      setManageMode(false);
      getModelGroup();
    } catch (err: any) {
      message.error(err?.message || t('common.operationFailed'));
    } finally {
      setSavingLayout(false);
    }
  };

  const handleCancelLayout = () => {
    if (layoutDirty) {
      Modal.confirm({
        title: t('common.prompt') || '提示',
        content: t('Model.discardLayoutConfirm') || '当前改动未保存，确认放弃？',
        okText: t('common.confirm'),
        cancelText: t('common.cancel'),
        centered: true,
        onOk: () => setManageMode(false),
      });
      return;
    }
    setManageMode(false);
  };

  const selectedIndex = draftLayout.findIndex(
    (g) => g.classification_id === selectedClassificationId
  );
  const activeDraftGroup = selectedIndex >= 0 ? draftLayout[selectedIndex] : null;

  const handleModelRowDragEnd = (newList: DraftClassification['models']) => {
    if (selectedIndex < 0) return;
    setDraftLayout((prev) =>
      prev.map((g, i) => (i === selectedIndex ? { ...g, models: newList } : g))
    );
    markDirty();
  };

  const compactTableBodyCell = () => ({
    style: {
      height: 48,
      paddingBlock: 8,
      borderBottomColor: 'var(--color-border-1)',
      color: 'var(--color-text-2)',
      fontSize: 14,
    },
  });

  const manageModelColumns = [
    {
      title: (
        <span className="text-[13px] font-[500] leading-[20px] text-[var(--color-text-2)]">
          {t('Model.modelName') || '模型名称'}
        </span>
      ),
      dataIndex: 'model_name',
      key: 'model_name',
      ellipsis: true,
      onCell: compactTableBodyCell,
      render: (_: unknown, record: DraftClassification['models'][number]) => (
        <div
          className="flex items-center"
          style={{ opacity: record.is_visible ? 1 : 0.5 }}
        >
          <div
            className="flex flex-shrink-0 items-center justify-center rounded-[6px]"
            style={{ width: 30, height: 30, background: 'var(--color-fill-1)' }}
          >
            <ModelIcon
              icon={record.icn}
              modelId={record.model_id}
              className="block object-contain"
              style={{ width: 24, height: 24 }}
              alt={t('picture')}
              width={24}
              height={24}
            />
          </div>
          <span className="ml-[10px] min-w-0 truncate text-[14px] font-[500] leading-[22px] text-[var(--color-text-2)]">
            {record.model_name}
          </span>
          {record.is_custom_reporting ? (
            <Tag color="purple" className="ml-[8px] flex-shrink-0 rounded-[4px] px-[6px] text-[12px] font-[400] leading-[20px]">
              {t('CustomReporting.modeQuick')}
            </Tag>
          ) : null}
        </div>
      ),
    },
    {
      title: (
        <span className="text-[13px] font-[500] leading-[20px] text-[var(--color-text-2)]">
          {t('Model.modelId') || '模型ID'}
        </span>
      ),
      dataIndex: 'model_id',
      key: 'model_id',
      width: 220,
      ellipsis: true,
      onCell: compactTableBodyCell,
      render: (_: unknown, record: DraftClassification['models'][number]) => (
        <span
          style={{ opacity: record.is_visible ? 1 : 0.5 }}
          className="text-[13px] font-[400] leading-[20px] text-[var(--color-text-2)] [font-variant-numeric:tabular-nums]"
        >
          {record.model_id}
        </span>
      ),
    },
    {
      title: (
        <span className="text-[13px] font-[500] leading-[20px] text-[var(--color-text-2)]">
          {t('Model.source') || '来源'}
        </span>
      ),
      key: 'is_pre',
      width: 120,
      onCell: compactTableBodyCell,
      render: (_: unknown, record: DraftClassification['models'][number]) => (
        <Tag
          color={record.is_pre ? 'blue' : 'default'}
          className="m-0 rounded-[4px] px-[6px] text-[12px] font-[400] leading-[20px]"
          style={{ opacity: record.is_visible ? 1 : 0.5 }}
        >
          {record.is_pre ? (t('Model.builtin') || '内置') : (t('Model.custom') || '自定义')}
        </Tag>
      ),
    },
    {
      title: (
        <span className="text-[13px] font-[500] leading-[20px] text-[var(--color-text-2)]">
          {t('Model.visible') || '可见'}
        </span>
      ),
      key: 'is_visible',
      width: 90,
      onCell: compactTableBodyCell,
      render: (_: unknown, __: DraftClassification['models'][number], index: number) => (
        <Switch
          size="small"
          checked={draftLayout[selectedIndex]?.models[index]?.is_visible}
          onChange={() => toggleModelVisible(selectedIndex, index)}
        />
      ),
    },
  ];

  return (
    <div className={assetManageStyle.container}>
      <Introduction title={t('Model.title')} message={t('Model.message')} />
      <div className={assetManageStyle.modelSetting}>
        <div className="nav-box flex justify-between mb-[10px]">
          <div className="left-side w-[320px] max-w-full">
            <Input.Search
              placeholder={t('common.search')}
              allowClear
              onSearch={onSearch}
              onClear={() => setSearchText('')}
            />
          </div>
          <div className="right-side">
            <PermissionWrapper requiredPermissions={['Add Model']}>
              <Button
                type="primary"
                className="mr-[8px]"
                onClick={() => showModelModal('add')}
              >
                {t('Model.addModel')}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['Add Group']}>
              <Button onClick={() => showGroupModal('add')}>
                {t('Model.addGroup')}
              </Button>
            </PermissionWrapper>
            {showConfigButtons ? (
              <Dropdown
                menu={{
                  items: [
                    {
                      key: 'publicEnumLibrary',
                      icon: <SettingOutlined />,
                      label: t('PublicEnumLibrary.manage'),
                      onClick: showPublicEnumLibraryModal,
                    },
                    {
                      key: 'exportConfig',
                      icon: <DownloadOutlined />,
                      label: t('Model.exportModelConfig'),
                      onClick: handleExportConfig,
                    },
                    {
                      key: 'importConfig',
                      icon: <UploadOutlined />,
                      label: t('Model.importModelConfig'),
                      onClick: showImportModelConfigModal,
                    },
                  ] as MenuProps['items'],
                }}
                placement="bottomRight"
              >
                <Button className="ml-[8px]">
                  <Space>
                    {t('seeMore')}
                    <DownOutlined />
                  </Space>
                </Button>
              </Dropdown>
            ) : (
              <Button
                className="ml-[8px]"
                icon={<SettingOutlined />}
                onClick={showPublicEnumLibraryModal}
              >
                {t('PublicEnumLibrary.manage')}
              </Button>
            )}
            {showConfigButtons && (
              <ManageToolbar
                manageMode={manageMode}
                dirty={layoutDirty}
                saving={savingLayout}
                onEnter={() => setManageMode(true)}
                onCancel={handleCancelLayout}
                onSave={handleSaveLayout}
              />
            )}
          </div>
        </div>
        <Spin spinning={loading}>
          {manageMode ? (
            <div
              className={assetManageStyle.managementLayout}
              style={{ marginTop: 6 }}
            >
              {/* 左栏：分类（可拖拽 + 选中 + 可见性），独立滚动 */}
              <div className={assetManageStyle.managementSidebar}>
                <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleGroupDragEnd}>
                  <SortableContext items={draftLayout.map(g => g.classification_id)} strategy={verticalListSortingStrategy}>
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                      {draftLayout.map((group, gi) => (
                        <SortableItem key={group.classification_id} id={group.classification_id} index={gi}>
                          <div
                            onClick={() => setSelectedClassificationId(group.classification_id)}
                            className={`${assetManageStyle.managementGroupRow} text-[13px] font-[400] leading-[20px]`}
                            style={{
                              minHeight: 36,
                              padding: '5px 8px',
                              opacity: group.is_visible ? 1 : 0.5,
                              ...(group.classification_id === selectedClassificationId
                                ? {
                                  borderColor: 'transparent',
                                  background: 'var(--color-bg-active)',
                                  color: 'var(--color-primary)',
                                }
                                : {}),
                            }}
                          >
                            <span className="flex min-w-0 flex-1 items-center">
                              <HolderOutlined className="mr-[8px] flex-shrink-0 cursor-move text-[12px] text-current opacity-50" />
                              <span
                                className={`min-w-0 truncate text-current ${
                                  group.classification_id === selectedClassificationId
                                    ? 'font-[500]'
                                    : 'font-[400]'
                                }`}
                              >
                                {group.classification_name}
                              </span>
                              <span className="flex-shrink-0 text-[12px] leading-[18px] text-current opacity-70 [font-variant-numeric:tabular-nums]">
                                （{group.models.length}）
                              </span>
                            </span>
                            <Tooltip title={group.is_visible ? (t('common.hide') || '隐藏') : (t('common.show') || '显示')}>
                              <span
                                className="ml-[4px] inline-flex h-[24px] w-[24px] flex-shrink-0 items-center justify-center text-[13px] text-[var(--color-text-3)]"
                                onClick={(e) => { e.stopPropagation(); toggleGroupVisible(gi); }}
                              >
                                {group.is_visible ? <EyeOutlined /> : <EyeInvisibleOutlined />}
                              </span>
                            </Tooltip>
                          </div>
                        </SortableItem>
                      ))}
                    </ul>
                  </SortableContext>
                </DndContext>
              </div>
              {/* 右栏：选中分类下的模型，表格自身独立滚动 */}
              <div className="min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto rounded-[8px] border border-solid border-[var(--color-border-1)] bg-[var(--color-bg)] text-[var(--color-text-3)]">
                {activeDraftGroup ? (
                  <CustomTable
                    size="small"
                    rowKey="model_id"
                    pagination={false}
                    columns={manageModelColumns}
                    dataSource={activeDraftGroup.models}
                    rowDraggable={true}
                    onRowDragEnd={(newData) => handleModelRowDragEnd(newData as DraftClassification['models'])}
                  />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </div>
            </div>
          ) : (
            <div className={assetManageStyle.modelCardsScroll}>
              {modelGroup.length ? (
                modelGroup.map(item => {
                  const isCollapsed = collapsedGroupIds.has(
                    item.classification_id
                  );
                  const groupContentId = `model-group-${item.classification_id}`;
                  return (
                    <div
                      className={assetManageStyle.modelGroup}
                      key={item.classification_id}
                    >
                      <div className={assetManageStyle.groupTitle}>
                        <button
                          type="button"
                          className={assetManageStyle.groupToggle}
                          aria-expanded={!isCollapsed}
                          aria-controls={groupContentId}
                          onClick={() =>
                            toggleModelGroup(item.classification_id)
                          }
                        >
                          <RightOutlined
                            aria-hidden="true"
                            className={`${assetManageStyle.groupChevron} ${
                              isCollapsed
                                ? ''
                                : assetManageStyle.groupChevronExpanded
                            }`}
                          />
                          <span className={assetManageStyle.groupName}>
                            {item.classification_name}
                          </span>
                          <span className={assetManageStyle.groupCount}>
                            （{item.count}）
                          </span>
                        </button>
                        {!item.is_pre && (
                          <div className={assetManageStyle.groupOperate}>
                            <PermissionWrapper
                              requiredPermissions={['Edit Group']}
                              instPermissions={item.permission}
                            >
                              <Button
                                type="text"
                                size="small"
                                className={assetManageStyle.groupAction}
                                aria-label={t('common.edit')}
                                icon={<EditTwoTone aria-hidden="true" />}
                                onClick={() => showGroupModal('edit', item)}
                              />
                            </PermissionWrapper>

                            {!item.list.length && (
                              <PermissionWrapper
                                requiredPermissions={['Delete Group']}
                                instPermissions={item.permission}
                              >
                                <Button
                                  type="text"
                                  size="small"
                                  className={assetManageStyle.groupAction}
                                  aria-label={t('common.delete')}
                                  icon={<DeleteTwoTone aria-hidden="true" />}
                                  onClick={() => showDeleteConfirm(item)}
                                />
                              </PermissionWrapper>
                            )}
                          </div>
                        )}
                      </div>
                      {!isCollapsed && (
                        <ul
                          id={groupContentId}
                          className={assetManageStyle.modelList}
                        >
                          {item.list.map((model) => (
                            <li
                              className={assetManageStyle.modelListItem}
                              key={model.model_id}
                            >
                              <div
                                className={assetManageStyle.leftSide}
                                onClick={() =>
                                  linkToDetail({
                                    ...model,
                                    classification_id: item.classification_id,
                                  })
                                }
                              >
                                <div className={assetManageStyle.modelIcon}>
                                  <ModelIcon
                                    icon={model.icn}
                                    modelId={model.model_id}
                                    className={assetManageStyle.modelImage}
                                    alt={t('picture')}
                                    width={32}
                                    height={32}
                                  />
                                </div>
                                <div className={assetManageStyle.modelMeta}>
                                  <EllipsisWithTooltip
                                    text={model.model_name}
                                    className={assetManageStyle.modelName}
                                  />
                                  <span className={assetManageStyle.modelId}>
                                    {model.model_id}
                                  </span>
                                </div>
                              </div>
                              {/* 复制按钮 */}
                              <PermissionWrapper
                                requiredPermissions={['Add Model']}
                                instPermissions={model.permission}
                              >
                                <div className={assetManageStyle.copyButton}>
                                  <Tooltip title={t('Model.copyModel')}>
                                    <Button
                                      type="primary"
                                      shape="circle"
                                      size="small"
                                      aria-label={t('Model.copyModel')}
                                      icon={<CopyOutlined aria-hidden="true" />}
                                      onClick={(e) =>
                                        handleCopyClick(e, model)
                                      }
                                    />
                                  </Tooltip>
                                </div>
                              </PermissionWrapper>
                              <button
                                type="button"
                                className={assetManageStyle.rightSide}
                                onClick={() => linkToInstList(model)}
                              >
                                <SwitcherOutlined aria-hidden="true" />
                                <span>{model.count}</span>
                              </button>
                            </li>
                          ))}
                          <li
                            className={`${assetManageStyle.modelListItem} ${assetManageStyle.addModelCard}`}
                            key={`add-${item.classification_id}`}
                          >
                            <PermissionWrapper
                              requiredPermissions={['Add Model']}
                              instPermissions={item.permission}
                              className="block w-full h-full"
                            >
                              <Button
                                type="dashed"
                                block
                                icon={<PlusOutlined />}
                                className={assetManageStyle.addModelButton}
                                onClick={() =>
                                  showModelModal('add', {
                                    classification_id: item.classification_id,
                                  })
                                }
                              >
                                {t('Model.addModel')}
                              </Button>
                            </PermissionWrapper>
                          </li>
                        </ul>
                      )}
                    </div>
                  );
                })
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </div>
          )}
        </Spin>
      </div>
      <GroupModal ref={groupRef} onSuccess={updateGroupList} />
      <ModelModal
        ref={modelRef}
        modelGroupList={groupList}
        onSuccess={updateModelList}
      />
      <CopyModelModal
        ref={copyModelRef}
        modelGroupList={groupList}
        onSuccess={updateModelList}
      />
      <PublicEnumLibraryModal ref={publicEnumLibraryRef} />
      <ImportModelConfigModal ref={importModelConfigRef} onSuccess={updateModelList} />
      <ExportModelConfigModal ref={exportModelConfigRef} modelGroup={rawModelGroup} />
    </div>
  );
};

export default AssetManage;
