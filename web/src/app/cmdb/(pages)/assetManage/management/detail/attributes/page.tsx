'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Input, Button, Modal, message, Space, Form, Spin } from 'antd';
import {
  EditOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
} from '@ant-design/icons';
import Icon from '@/components/icon';
import AttributesModal from './attributesModal';
import { Tag } from 'antd';
import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import type { ColumnItem } from '@/types';
import { ATTR_TYPE_LIST } from '@/app/cmdb/constants/asset';
import { useTranslation } from '@/utils/i18n';
import PermissionWrapper from '@/components/permission';
import { useModelApi } from '@/app/cmdb/api';
import { useModelDetail } from '../context';
import type { AttrGroup, AttrItem } from '@/app/cmdb/types/assetManage';

const Attributes: React.FC = () => {
  const { confirm } = Modal;
  const { t } = useTranslation();
  const modelDetail = useModelDetail();

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

  const columns: ColumnItem[] = [
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
      render: (attr_type: unknown) => (
        <span>
          {ATTR_TYPE_LIST.find((item) => item.id === attr_type)?.name || '--'}
        </span>
      ),
    },
    {
      title: t('editable'),
      key: 'editable',
      dataIndex: 'editable',
      width: 100,
      render: (editable: unknown) => (
        <Tag color={editable ? 'green' : 'geekblue'}>
          {editable ? 'YES' : 'NO'}
        </Tag>
      ),
    },
    {
      title: t('unique'),
      key: 'is_only',
      dataIndex: 'is_only',
      width: 100,
      render: (is_only: unknown) => (
        <Tag color={is_only ? 'green' : 'geekblue'}>
          {is_only ? 'YES' : 'NO'}
        </Tag>
      ),
    },
    {
      title: t('required'),
      key: 'is_required',
      dataIndex: 'is_required',
      width: 100,
      render: (is_required: unknown) => (
        <Tag color={is_required ? 'green' : 'geekblue'}>
          {is_required ? 'YES' : 'NO'}
        </Tag>
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
              className="mr-[10px]"
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
              onClick={() => showDeleteConfirm({ attr_id: record.attr_id })}
            >
              {t('common.delete')}
            </Button>
          </PermissionWrapper>
        </Space>
      ),
    },
  ];

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

      setGroups(apiGroups);

      const allAttrs: AttrItem[] = [];
      apiGroups.forEach((group: any) => {
        const groupAttrs = (group.attrs || []).map((attr: any) => ({
          ...attr,
          group_id: String(group.id),
        }));
        allAttrs.push(...groupAttrs);
      });

      setTableData(allAttrs);
    } catch (error) {
      console.error(error);
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
      console.error(error);
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
      console.error(error);
      message.error(t('common.updateFailed'));
    }
  };

  const showDeleteGroupConfirm = (group: AttrGroup) => {
    const groupAttrs = tableData.filter(
      (attr) => attr.group_id === String(group.id)
    );

    const baseMessage = `${t('Model.deleteGroupConfirmPrefix')}"${
      modelDetail?.model_name
    }"${t('Model.deleteGroupConfirmMiddle')}"${group.group_name}"${t(
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
        console.error(error);
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
      console.error(error);
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
      console.error(error);
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

  return (
    <div className="h-full flex flex-col">
      <div className="nav-box flex justify-between mb-[16px]">
        <div className="flex gap-2">
          <Input.Search
            placeholder={t('common.search')}
            value={searchText}
            allowClear
            className="w-[240px]"
            onChange={onSearchTxtChange}
            onSearch={onSearch}
            onClear={onTxtClear}
          />
          <PermissionWrapper
            requiredPermissions={['Edit Model']}
            instPermissions={modelPermission}
          >
            <Button className="mr-2" onClick={() => showGroupModal()}>
              {t('Model.addAttrGroup')}
            </Button>
            <Button type="primary" onClick={() => showAttrModal('add')}>
              {t('Model.addAttribute')}
            </Button>
          </PermissionWrapper>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <Spin spinning={loading && groups.length === 0} className="mt-30">
          {groups.map((group, groupIndex) => (
            <div
              key={group.id}
              className="border border-gray-200 mb-4 border-b-0 bg-white"
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
              <div className="flex items-center justify-between px-4 py-3 bg-white border-b border-gray-100">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium text-gray-900">
                    {group.group_name}
                  </span>
                  <div className="flex items-center gap-2 ml-2">
                    <PermissionWrapper
                      requiredPermissions={['Edit Model']}
                      instPermissions={modelPermission}
                    >
                      <Button
                        type="text"
                        size="small"
                        icon={<EditOutlined style={{ fontSize: '14px' }} />}
                        onClick={() => showGroupModal(group)}
                        className="text-blue-500 hover:text-blue-600"
                      ></Button>
                    </PermissionWrapper>
                    <PermissionWrapper
                      requiredPermissions={['Edit Model']}
                      instPermissions={modelPermission}
                    >
                      <Button
                        type="text"
                        size="small"
                        icon={
                          <Icon
                            type="shanchu"
                            style={{ fontSize: '18px', marginTop: '3px' }}
                          />
                        }
                        onClick={() => showDeleteGroupConfirm(group)}
                        className="text-red-500 hover:text-red-600"
                      ></Button>
                    </PermissionWrapper>
                    <PermissionWrapper
                      requiredPermissions={['Edit Model']}
                      instPermissions={modelPermission}
                    >
                      <Button
                        type="text"
                        size="small"
                        className="!px-1"
                        icon={
                          <ArrowUpOutlined
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
                        icon={
                          <ArrowDownOutlined
                            style={{ fontSize: '14px', fontWeight: 'bold' }}
                          />
                        }
                        disabled={groupIndex === groups.length - 1}
                        onClick={() => moveGroupDown(group, groupIndex)}
                      />
                    </PermissionWrapper>
                  </div>
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
            </div>
          ))}
        </Spin>
      </div>

      <AttributesModal
        ref={attrRef}
        attrTypeList={ATTR_TYPE_LIST}
        groups={groups}
        onSuccess={updateAttrList}
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
