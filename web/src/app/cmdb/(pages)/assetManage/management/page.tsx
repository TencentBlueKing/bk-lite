'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '@/context/auth';
import { useSession } from 'next-auth/react';
import Introduction from '@/app/cmdb/components/introduction';
import { Input, Button, Modal, message, Spin, Empty, Tooltip, Dropdown, Space, Switch } from 'antd';
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
import Image from 'next/image';
import assetManageStyle from './index.module.scss';
import { getIconUrl } from '@/app/cmdb/utils/common';
import GroupModal from './list/groupModal';
import ModelModal from './list/modelModal';
import CopyModelModal from './list/copyModelModal';
import PublicEnumLibraryModal, { PublicEnumLibraryModalRef } from './list/publicEnumLibraryModal';
import ImportModelConfigModal, { ImportModelConfigModalRef } from './list/importModelConfigModal';
import ManageToolbar from './list/manageToolbar';
import CustomTable from '@/components/custom-table';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import PermissionWrapper from '@/components/permission';
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
    is_visible: boolean;
    order_id: number;
  }>;
}

const AssetManage = () => {
  const { getClassificationList, deleteClassification } =
    useClassificationApi();
  const { getModelInstanceCount } = useInstanceApi();
  const { exportModelConfig, getModelList, saveModelLayout } = useModelApi();
  const { isSuperUser, selectedGroup } = useUserInfoContext();
  const authContext = useAuth();
  const { data: session } = useSession();
  const token = (session?.user as any)?.token || authContext?.token || null;
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
  const [modelGroup, setModelGroup] = useState<GroupItem[]>([]);
  const [groupList, setGroupList] = useState<GroupItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [searchText, setSearchText] = useState<string>('');
  const [rawModelGroup, setRawModelGroup] = useState<GroupItem[]>([]);
  const [hoveredModelId, setHoveredModelId] = useState<string | null>(null);
  const [exportLoading, setExportLoading] = useState<boolean>(false);
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

  const onSearchTxtChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchText(e.target.value);
  };
  const onSearchTxtEnter = (e: React.KeyboardEvent<HTMLInputElement>) => {
    setSearchText((e.target as HTMLInputElement).value);
  };

  // 导出模型配置
  const handleExportConfig = async () => {
    setExportLoading(true);
    try {
      await exportModelConfig(tokenRef.current);
    } catch (error: any) {
      message.error(error.message);
    } finally {
      setExportLoading(false);
    }
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

  const manageModelColumns = [
    {
      title: t('Model.modelName') || '模型',
      dataIndex: 'model_name',
      key: 'model_name',
      render: (_: unknown, record: DraftClassification['models'][number]) => (
        <div
          className="flex items-center"
          style={{ opacity: record.is_visible ? 1 : 0.5 }}
        >
          <div style={{ width: 28 }} className="flex-shrink-0">
            <Image
              src={getIconUrl(record as any)}
              className="block w-auto h-7"
              alt={t('picture')}
              width={28}
              height={28}
            />
          </div>
          <div className="flex flex-col pl-[10px] min-w-0">
            <span className="text-[14px] font-[600] truncate">{record.model_name}</span>
            <span className="text-[12px] text-[var(--color-text-3)] truncate">{record.model_id}</span>
          </div>
        </div>
      ),
    },
    {
      title: t('Model.visible') || '可见',
      key: 'is_visible',
      width: 90,
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
          <div className="left-side w-[240px]">
            <Input
              placeholder={t('common.search')}
              value={searchText}
              allowClear
              onChange={onSearchTxtChange}
              onPressEnter={onSearchTxtEnter}
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
                      disabled: exportLoading,
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
            <div className="flex" style={{ gap: 16 }}>
              {/* 左栏：分类（可拖拽 + 选中 + 可见性） */}
              <div style={{ width: 240, flexShrink: 0 }}>
                <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleGroupDragEnd}>
                  <SortableContext items={draftLayout.map(g => g.classification_id)} strategy={verticalListSortingStrategy}>
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                      {draftLayout.map((group, gi) => (
                        <SortableItem key={group.classification_id} id={group.classification_id} index={gi}>
                          <div
                            onClick={() => setSelectedClassificationId(group.classification_id)}
                            className="flex items-center justify-between px-[8px] py-[6px] rounded cursor-pointer"
                            style={{
                              width: '100%',
                              opacity: group.is_visible ? 1 : 0.5,
                              background:
                                group.classification_id === selectedClassificationId
                                  ? 'var(--color-fill-1)'
                                  : 'transparent',
                            }}
                          >
                            <span className="flex items-center min-w-0">
                              <HolderOutlined className="mr-[6px] cursor-move flex-shrink-0" />
                              <span className="truncate text-[14px]">
                                {group.classification_name}（{group.models.length}）
                              </span>
                            </span>
                            <Tooltip title={group.is_visible ? (t('common.hide') || '隐藏') : (t('common.show') || '显示')}>
                              <span
                                className="flex-shrink-0 ml-[6px]"
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
              {/* 右栏：选中分类下的模型（CustomTable + 行拖拽 + 可见性开关） */}
              <div style={{ flex: 1, minWidth: 0 }}>
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
          ) : modelGroup.length ? (
            modelGroup.map(item => {
              return (
                <div className="model-group" key={item.classification_id}>
                  <div
                    className={`${assetManageStyle.groupTitle} flex items-center mt-[20px] text-[14px]`}
                  >
                    <span className="border-l-[4px] border-[var(--color-primary)] px-[4px] py-[1px] font-[600]">
                      {item.classification_name}（{item.count}）
                    </span>
                    {!item.is_pre && (
                      <div className={assetManageStyle.groupOperate}>
                        <PermissionWrapper
                          requiredPermissions={['Edit Group']}
                          instPermissions={item.permission}
                        >
                          <EditTwoTone
                            className="edit mr-[6px] cursor-pointer"
                            onClick={() => showGroupModal('edit', item)}
                          />
                        </PermissionWrapper>

                        {!item.list.length && (
                          <PermissionWrapper
                            requiredPermissions={['Delete Group']}
                            instPermissions={item.permission}
                          >
                            <DeleteTwoTone
                              className="delete cursor-pointer"
                              onClick={() => showDeleteConfirm(item)}
                            />
                          </PermissionWrapper>
                        )}
                      </div>
                    )}
                  </div>
                  <ul className={assetManageStyle.modelList}>
                    {item.list.map((model, index) => (
                      <li
                        className={`bg-[var(--color-bg)] flex justify-between items-center ${assetManageStyle.modelListItem}`}
                        key={index}
                        onMouseEnter={() => setHoveredModelId(model.model_id)}
                        onMouseLeave={() => setHoveredModelId(null)}
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
                          <div style={{ width: 40 }}>
                            <Image
                              src={getIconUrl(model)}
                              className="block w-auto h-10"
                              alt={t('picture')}
                              width={40}
                              height={40}
                            />
                          </div>
                          <div className="flex flex-col pl-[10px]">
                            <span className="text-[14px] pb-[4px] font-[600]">
                              {model.model_name}
                            </span>
                            <span className="text-[12px] text-[var(--color-text-3)]">
                              {model.model_id}
                            </span>
                          </div>
                        </div>
                        {/* 复制按钮 */}
                        {hoveredModelId === model.model_id && (
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
                                  icon={<CopyOutlined />}
                                  onClick={(e) => handleCopyClick(e, model)}
                                />
                              </Tooltip>
                            </div>
                          </PermissionWrapper>
                        )}
                        <div
                          className={assetManageStyle.rightSide}
                          onClick={() => linkToInstList(model)}
                        >
                          <SwitcherOutlined />
                          <span className="text-[12px] pt-[4px]">
                            {model.count}
                          </span>
                        </div>
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
                </div>
              );
            })
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
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
    </div>
  );
};

export default AssetManage;
