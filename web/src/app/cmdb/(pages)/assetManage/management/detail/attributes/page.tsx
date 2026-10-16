'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Button, Modal, message, Space, Form, Input, Tag } from 'antd';
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  EditOutlined,
  FolderOutlined,
} from '@ant-design/icons';
import Icon from '@/components/icon';
import AttributesModal from './attributesModal';
import PublicEnumLibraryModal, { PublicEnumLibraryModalRef } from '../../list/publicEnumLibraryModal';
import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import SearchActionBar from '@/components/search-action-bar';
import type { ColumnItem } from '@/types';
import { ATTR_TYPE_LIST } from '@/app/cmdb/constants/asset';
import { useTranslation } from '@/utils/i18n';
import PermissionWrapper from '@/components/permission';
import { useModelApi } from '@/app/cmdb/api';
import { useModelDetail } from '../context';
import { loadAttributeEnterpriseExtension } from '@/app/cmdb/hooks/useAttributeEnterpriseExtension';
import type {
  AttrGroup,
  AttrItem,
  FullInfoUniqueRuleItem,
  UniqueDisplayType,
} from '@/app/cmdb/types/assetManage';
import { StatusToneBadge, YesNoBadge } from '@/app/cmdb/utils/statusTone';

const useAttributeEnterpriseExtension = loadAttributeEnterpriseExtension();

const getUniqueTagMeta = (uniqueType?: string, isOnly?: boolean) => {
  if (uniqueType === 'joint') {
    return { tone: 'primary' as const, textKey: 'Model.jointUnique' };
  }
  if (uniqueType === 'single' || isOnly) {
    return { tone: 'success' as const, textKey: 'Model.singleUnique' };
  }
  return { tone: 'neutral' as const, textKey: 'no' };
};

const getAttrUniqueDisplayType = (
  attr: AttrItem,
  uniqueRules: FullInfoUniqueRuleItem[] = []
): UniqueDisplayType => {
  const attrId = attr.attr_id
  const jointFieldIds = new Set(
    uniqueRules
      .filter((rule) => rule.field_ids.length > 1)
      .flatMap((rule) => rule.field_ids)
  )
  const singleFieldIds = new Set(
    uniqueRules
      .filter((rule) => rule.field_ids.length === 1)
      .flatMap((rule) => rule.field_ids)
  )

  if (jointFieldIds.has(attrId)) {
    return 'joint'
  }
  if (attr.is_only || singleFieldIds.has(attrId)) {
    return 'single'
  }
  return 'none'
}

const Attributes: React.FC = () => {
  const { confirm } = Modal;
  const { t } = useTranslation();
  const modelDetail = useModelDetail();
  const attributeEnterpriseExtension = useAttributeEnterpriseExtension();

  const {
    deleteModelAttr,
    getModelAttrGroupsFullInfo,
    createModelAttrGroup,
    updateModelAttrGroup,
    deleteModelAttrGroup,
    moveModelAttrGroup,
    reorderGroupAttrs,
    moveAttrToGroup,
  } = useModelApi();

  const modelId = modelDetail?.model_id;
  const modelPermission = modelDetail?.permission || [];
const attrRef = useRef<any>(null);
  const publicEnumLibraryRef = useRef<PublicEnumLibraryModalRef>(null);
  const groupFormRef = useRef<any>(null);
  const [searchText, setSearchText] = useState<string>('');
  const [filterText, setFilterText] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [tableData, setTableData] = useState<AttrItem[]>([]);
  const [groups, setGroups] = useState<AttrGroup[]>([]);
  const [groupModalVisible, setGroupModalVisible] = useState<boolean>(false);
  const [editingGroup, setEditingGroup] = useState<AttrGroup | null>(null);
  const [groupName, setGroupName] = useState<string>('');
  const [draggingAttr, setDraggingAttr] = useState<{
    attr: AttrItem;
    sourceGroupId: string;
  } | null>(null);

  const baseColumns: ColumnItem[] = [
    {
      title: 'ID',
      dataIndex: 'attr_id',
      key: 'attr_id',
      width: 200,
    },
    {
      title: t('name'),
      dataIndex: 'attr_name',
      key: 'attr_name',
      width: 200,
    },
    {
      title: t('type'),
      dataIndex: 'attr_type',
      key: 'attr_type',
      width: 150,
      render: (attr_type: unknown) => {
        const typeName = ATTR_TYPE_LIST.find(
          (item) => item.id === attr_type
        )?.name;
        return <span>{typeName ? t(typeName) : '--'}</span>;
      },
    },
    {
      title: t('editable'),
      key: 'editable',
      dataIndex: 'editable',
      width: 100,
      render: (editable: unknown) => (
        <YesNoBadge value={Boolean(editable)} />
      ),
    },
    {
      title: t('unique'),
      key: 'is_only',
      dataIndex: 'unique_display_type',
      width: 100,
      render: (_: unknown, record: AttrItem) => {
        const meta = getUniqueTagMeta(record.unique_display_type, record.is_only);
        return (
          <StatusToneBadge
            tone={meta.tone}
            label={meta.textKey === 'no' ? t('no') : t(meta.textKey)}
          />
        );
      },
    },
    {
      title: t('required'),
      key: 'is_required',
      dataIndex: 'is_required',
      width: 100,
      render: (is_required: unknown) => (
        <YesNoBadge value={Boolean(is_required)} />
      ),
    },
    {
      title: t('common.action'),
      key: 'action',
      dataIndex: 'action',
      width: 150,
      render: (_: any, record: AttrItem) => (
        <Space>
          <PermissionWrapper
            requiredPermissions={['Edit Model']}
            instPermissions={modelPermission}
          >
            <Button
              type="link"
              size="small"
              onClick={() => showAttrModal('edit', record)}
            >
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper
            requiredPermissions={['Edit Model']}
            instPermissions={modelPermission}
          >
            <Button
              type="link"
              size="small"
              danger
              onClick={() => showDeleteConfirm({ attr_id: record.attr_id })}
            >
              {t('common.delete')}
            </Button>
          </PermissionWrapper>
        </Space>
      ),
    },
  ];
  const columns = attributeEnterpriseExtension.extendColumns(baseColumns, {
    ui: { Tag },
  });

  useEffect(() => {
    if (modelId) {
      fetchGroupsAndData();
    }
  }, [modelId]);

  const fetchGroupsAndData = async () => {
    setLoading(true);
    try {
      const data: any = await getModelAttrGroupsFullInfo(modelId!);
      const apiGroups = data.groups || [];
      const uniqueRules = data.unique_rules || [];

      setGroups(apiGroups);

      const allAttrs: AttrItem[] = [];
      apiGroups.forEach((group: any) => {
        const groupAttrs = (group.attrs || []).map((attr: any) => ({
          ...attr,
          group_id: String(group.id),
          unique_display_type: getAttrUniqueDisplayType(attr, uniqueRules),
        }));
        allAttrs.push(...groupAttrs);
      });

      setTableData(allAttrs);
    } catch (error) {
      console.log(error);
    } finally {
      setLoading(false);
    }
  };

  const fetchGroups = async () => {
    await fetchGroupsAndData();
  };

  const showAttrModal = (type: string, row = {}) => {
    const title = t(
      type === 'add' ? 'Model.addAttribute' : 'Model.editAttribute'
    );
    attrRef.current?.showModal({
      title,
      type,
      attrInfo: row,
      subTitle: '',
    });
  };

  const showDeleteConfirm = (row = { attr_id: '' }) => {
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
            await deleteModelAttr(modelId!, row.attr_id);
            message.success(t('successfullyDeleted'));
            fetchGroupsAndData();
          } finally {
            resolve(true);
          }
        });
      },
    });
  };

  const showGroupModal = (group?: AttrGroup) => {
    if (group) {
      setEditingGroup(group);
      setGroupName(group.group_name);
    } else {
      setEditingGroup(null);
      setGroupName('');
    }
    setGroupModalVisible(true);
    setTimeout(() => {
      groupFormRef.current?.setFieldsValue({
        group_name: group?.group_name || '',
      });
    }, 0);
  };

  const handleGroupSubmit = async (continueAdd: boolean = false) => {
    try {
      await groupFormRef.current?.validateFields();

      if (editingGroup) {
        await updateModelAttrGroup(editingGroup.id, {
          group_name: groupName,
        });
        message.success(t('common.saveSuccess'));
      } else {
        await createModelAttrGroup({
          model_id: modelId!,
          group_name: groupName,
        });
        message.success(t('common.addSuccess'));
      }

      if (!continueAdd || editingGroup) {
        setGroupModalVisible(false);
        setGroupName('');
        setEditingGroup(null);
        groupFormRef.current?.resetFields();
      } else {
        setGroupName('');
        groupFormRef.current?.resetFields();
      }

      fetchGroups();
    } catch (error: any) {
      if (error?.errorFields) {
        return;
      }
      message.error(t('common.saveFailed'));
    }
  };

  const moveGroupUp = async (group: AttrGroup, index: number) => {
    if (index === 0) return;
    try {
      await moveModelAttrGroup(group.id, 'up');
      await fetchGroupsAndData();
      message.success(t('common.updateSuccess'));
    } catch (error) {
      console.log(error);
      message.error(t('common.updateFailed'));
    }
  };

  const moveGroupDown = async (group: AttrGroup, index: number) => {
    if (index === groups.length - 1) return;
    try {
      await moveModelAttrGroup(group.id, 'down');
      await fetchGroupsAndData();
      message.success(t('common.updateSuccess'));
    } catch (error) {
      console.log(error);
      message.error(t('common.updateFailed'));
    }
  };

  const showDeleteGroupConfirm = (group: AttrGroup) => {
    const groupAttrs = tableData.filter(
      (attr) => attr.group_id === String(group.id)
    );

    const baseMessage = `${t('Model.deleteGroupConfirmPrefix')}"${
      modelDetail?.model_name
    }"${t('Model.deleteGroupConfirmMiddle')}"${group.display_name || group.group_name}"${t(
      'Model.deleteGroupConfirmSuffix'
    )}`;

    const deleteMessage =
      groupAttrs.length > 0
        ? `${baseMessage}\n${t('Model.deleteGroupConfirm')}`
        : baseMessage;

    confirm({
      title: t('Model.deleteAttrGroup'),
      content: deleteMessage,
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      okButtonProps: groupAttrs.length > 0 ? { danger: true } : undefined,
      onOk() {
        return new Promise(async (resolve) => {
          try {
            await deleteModelAttrGroup(group.id);
            message.success(t('successfullyDeleted'));
            fetchGroupsAndData();
          } finally {
            resolve(true);
          }
        });
      },
    });
  };

  const handleAttrDragStart = (attr: AttrItem, sourceGroupId: string) => {
    setDraggingAttr({ attr, sourceGroupId });
  };

  const handleAttrDragEnd = async (
    groupId: number | string,
    newData: AttrItem[] | undefined,
    targetIndex: number
  ) => {
    if (!newData) return;

    const targetGroup = groups.find((g) => g.id === groupId);
    if (!targetGroup) return;

    if (draggingAttr && draggingAttr.sourceGroupId !== String(groupId)) {
      const { attr } = draggingAttr;
      try {
        await moveAttrToGroup({
          model_id: modelId!,
          attr_id: attr.attr_id,
          group_name: targetGroup.group_name,
          order_id: targetIndex,
        });
        await fetchGroupsAndData();
        message.success(t('common.updateSuccess'));
      } catch (error) {
        console.log(error);
        message.error(t('common.updateFailed'));
      } finally {
        setDraggingAttr(null);
      }
      return;
    }

    const otherAttrs = tableData.filter(
      (attr) => attr.group_id !== String(groupId)
    );
    setTableData([...otherAttrs, ...newData]);

    try {
      await reorderGroupAttrs({
        model_id: modelId!,
        group_name: targetGroup.group_name,
        attr_orders: newData.map((attr) => attr.attr_id),
      });
      message.success(t('common.updateSuccess'));
    } catch (error) {
      console.log(error);
      message.error(t('common.updateFailed'));
      fetchGroupsAndData();
    } finally {
      setDraggingAttr(null);
    }
  };

  const handleGroupDrop = async (targetGroupId: number | string) => {
    if (!draggingAttr) return;

    const { attr, sourceGroupId } = draggingAttr;
    const targetGroup = groups.find((g) => g.id === targetGroupId);

    if (!targetGroup) return;

    if (sourceGroupId === String(targetGroupId)) {
      setDraggingAttr(null);
      return;
    }

    const targetGroupAttrs = groupedAttrs[String(targetGroupId)] || [];
    if (targetGroupAttrs.length > 0) {
      setDraggingAttr(null);
      return;
    }

    try {
      await moveAttrToGroup({
        model_id: modelId!,
        attr_id: attr.attr_id,
        group_name: targetGroup.group_name,
        order_id: 0,
      });

      await fetchGroupsAndData();
      message.success(t('common.updateSuccess'));
    } catch (error) {
      console.log(error);
      message.error(t('common.updateFailed'));
    } finally {
      setDraggingAttr(null);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const onSearchTxtChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchText(e.target.value);
  };

  const onSearch = (value: string) => {
    setFilterText(value);
  };

  const onTxtClear = () => {
    setSearchText('');
    setFilterText('');
  };

  const updateAttrList = () => {
    fetchGroupsAndData();
  };

  const showPublicEnumLibraryModal = (libraryId?: string) => {
    publicEnumLibraryRef.current?.showModal(libraryId);
  };

  const getGroupedAttrs = () => {
    const grouped: Record<string, AttrItem[]> = {};

    groups.forEach((group) => {
      grouped[String(group.id)] = [];
    });

    const filteredData = filterText
      ? tableData.filter(
        (attr) =>
          attr.attr_id?.toLowerCase().includes(filterText.toLowerCase()) ||
          attr.attr_name?.toLowerCase().includes(filterText.toLowerCase())
      )
      : tableData;

    filteredData.forEach((attr) => {
      if (attr.group_id && grouped[attr.group_id]) {
        grouped[attr.group_id].push(attr);
      }
    });

    return grouped;
  };

  const groupedAttrs = getGroupedAttrs();
  const hasTagAttr = tableData.some((attr) => attr.attr_type === 'tag');

  return (
    <div className="flex h-full min-h-0 min-w-0 w-full flex-col">
      <SearchActionBar
        className="mb-4"
        spacing="flush"
        searchClassName="!w-[240px]"
        searchProps={{
          placeholder: t('common.search'),
          value: searchText,
          allowClear: true,
          onChange: onSearchTxtChange,
          onSearch,
          onClear: onTxtClear,
        }}
        actions={(
          <PermissionWrapper
            requiredPermissions={['Edit Model']}
            instPermissions={modelPermission}
          >
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={() => showGroupModal()}>
                {t('Model.addAttrGroup')}
              </Button>
              <Button type="primary" onClick={() => showAttrModal('add')}>
                {t('Model.addAttribute')}
              </Button>
            </div>
          </PermissionWrapper>
        )}
      />

      <div className="flex-1 overflow-y-auto">
        {loading && groups.length === 0 ? (
          <div className="space-y-4" aria-busy="true" aria-label="loading">
            {[0, 1].map((index) => (
              <section
                key={index}
                className="overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]"
              >
                <div className="h-10 border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35" />
                <div className="space-y-2 p-3">
                  <div className="h-8 animate-neutral-pulse rounded-md bg-[var(--color-fill-1)]" />
                  <div className="h-8 animate-neutral-pulse rounded-md bg-[var(--color-fill-1)]" />
                  <div className="h-8 w-3/4 animate-neutral-pulse rounded-md bg-[var(--color-fill-1)]" />
                </div>
              </section>
            ))}
          </div>
        ) : (
          groups.map((group, groupIndex) => {
            const groupAttrCount = (groupedAttrs[String(group.id)] || []).length;
            return (
            <section
              key={group.id}
              className="mb-4 overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]"
              onDragOver={handleDragOver}
              onDrop={(e) => {
                e.preventDefault();
                if (
                  draggingAttr &&
                  draggingAttr.sourceGroupId !== String(group.id)
                ) {
                  handleGroupDrop(group.id);
                }
              }}
            >
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
                <div className="flex items-center gap-2">
                  <FolderOutlined className="text-sm text-[var(--color-primary)]" />
                  <h2 className="m-0 text-[13px] font-semibold text-[var(--color-text-1)]">
                    {group.display_name || group.group_name}
                  </h2>
                  {groupAttrCount > 0 && (
                    <span className="inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--color-primary)_12%,var(--color-bg))] px-1.5 text-xs font-semibold tabular-nums text-[var(--color-primary)]">
                      {groupAttrCount}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1">
                    <PermissionWrapper
                      requiredPermissions={['Edit Model']}
                      instPermissions={modelPermission}
                    >
                      <Button
                        type="text"
                        size="small"
                        aria-label={t('common.edit')}
                        icon={<EditOutlined aria-hidden="true" style={{ fontSize: '14px' }} />}
                        onClick={() => showGroupModal(group)}
                      />
                    </PermissionWrapper>
                    <PermissionWrapper
                      requiredPermissions={['Edit Model']}
                      instPermissions={modelPermission}
                    >
                      <Button
                        type="text"
                        size="small"
                        danger
                        aria-label={t('common.delete')}
                        icon={
                          <Icon
                            type="shanchu"
                            aria-hidden="true"
                            style={{ fontSize: '18px', marginTop: '3px' }}
                          />
                        }
                        onClick={() => showDeleteGroupConfirm(group)}
                      />
                    </PermissionWrapper>
                    <PermissionWrapper
                      requiredPermissions={['Edit Model']}
                      instPermissions={modelPermission}
                    >
                      <Button
                        type="text"
                        size="small"
                        className="!px-1"
                        aria-label="Move up"
                        icon={
                          <ArrowUpOutlined
                            aria-hidden="true"
                            style={{ fontSize: '14px', fontWeight: 'bold' }}
                          />
                        }
                        disabled={groupIndex === 0}
                        onClick={() => moveGroupUp(group, groupIndex)}
                      />
                    </PermissionWrapper>
                    <PermissionWrapper
                      requiredPermissions={['Edit Model']}
                      instPermissions={modelPermission}
                    >
                      <Button
                        type="text"
                        size="small"
                        className="!px-1"
                        aria-label="Move down"
                        icon={
                          <ArrowDownOutlined
                            aria-hidden="true"
                            style={{ fontSize: '14px', fontWeight: 'bold' }}
                          />
                        }
                        disabled={groupIndex === groups.length - 1}
                        onClick={() => moveGroupDown(group, groupIndex)}
                      />
                    </PermissionWrapper>
                </div>
              </div>

              <CustomTable
                size="small"
                columns={columns}
                dataSource={groupedAttrs[String(group.id)] || []}
                loading={loading}
                rowKey="attr_id"
                pagination={false}
                rowDraggable={true}
                onRowDragStart={(index) => {
                  const attrs = groupedAttrs[String(group.id)] || [];
                  if (attrs[index]) {
                    handleAttrDragStart(attrs[index], String(group.id));
                  }
                }}
                onRowDragEnd={(newData, sourceIndex, targetIndex) =>
                  handleAttrDragEnd(
                    group.id,
                    newData as AttrItem[],
                    targetIndex
                  )
                }
              />
            </section>
            );
          })
        )}
      </div>

      <AttributesModal
        ref={attrRef}
        attrTypeList={ATTR_TYPE_LIST}
        groups={groups}
        hasTagAttr={hasTagAttr}
        onSuccess={updateAttrList}
        onManagePublicLibrary={showPublicEnumLibraryModal}
      />

      <PublicEnumLibraryModal
        ref={publicEnumLibraryRef}
        onSuccess={() => attrRef.current?.refreshPublicLibraries()}
      />

      <OperateModal
        width={500}
        title={
          editingGroup ? t('Model.editAttrGroup') : t('Model.addAttrGroup')
        }
        visible={groupModalVisible}
        onCancel={() => {
          setGroupModalVisible(false);
          setGroupName('');
          setEditingGroup(null);
          groupFormRef.current?.resetFields();
        }}
        footer={
          <div>
            <Button
              onClick={() => {
                setGroupModalVisible(false);
                setGroupName('');
                setEditingGroup(null);
                groupFormRef.current?.resetFields();
              }}
            >
              {t('common.cancel')}
            </Button>
            {!editingGroup && (
              <Button
                type="primary"
                className="ml-2"
                onClick={() => handleGroupSubmit(true)}
              >
                {t('Model.continueAdd')}
              </Button>
            )}
            <Button
              type="primary"
              className="ml-2"
              onClick={() => handleGroupSubmit(false)}
            >
              {t('common.confirm')}
            </Button>
          </div>
        }
      >
        <Form ref={groupFormRef} layout="vertical" name="groupForm">
          <Form.Item
            label={t('Model.attrGroupName')}
            name="group_name"
            rules={[
              { required: true, message: t('Model.enterAttrGroupName') },
              { whitespace: true, message: t('Model.enterAttrGroupName') },
            ]}
          >
            <Input
              placeholder={t('Model.enterAttrGroupName')}
              value={groupName}
              onChange={(e) => setGroupName(e.target.value)}
            />
          </Form.Item>
        </Form>
      </OperateModal>
    </div>
  );
};

export default Attributes;
