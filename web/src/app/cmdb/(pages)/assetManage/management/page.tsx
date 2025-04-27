'use client';

import React, { useState, useEffect, useRef } from 'react';
import Introduction from '@/app/cmdb/components/introduction';
import { Input, Button, Modal, message, Spin, Empty } from 'antd';
import { deepClone } from '@/app/cmdb/utils/common';
import { GroupItem, ModelItem } from '@/app/cmdb/types/assetManage';
import {
  EditTwoTone,
  DeleteTwoTone,
  SwitcherOutlined,
  HolderOutlined,
} from '@ant-design/icons';
import Image from 'next/image';
import assetManageStyle from './index.module.scss';
import { getIconUrl } from '@/app/cmdb/utils/common';
import GroupModal from './list/groupModal';
import ModelModal from './list/modelModal';
import { useRouter } from 'next/navigation';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import { useCommon } from '@/app/cmdb/context/common';
import PermissionWrapper from '@/components/permission';

const AssetManage = () => {
  const { get, del, isLoading } = useApiClient();
  const { confirm } = Modal;
  const { t } = useTranslation();
  const commonContext = useCommon();
  const router = useRouter();
  const groupRef = useRef<any>(null);
  const modelRef = useRef<any>(null);
  const permissionGroupsInfo = useRef(
    commonContext?.permissionGroupsInfo || null
  );
  const isAdmin = permissionGroupsInfo.current?.is_all;
  const [modelGroup, setModelGroup] = useState<GroupItem[]>([]);
  const [groupList, setGroupList] = useState<GroupItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [searchText, setSearchText] = useState<string>('');
  const [dragItem, setDragItem] = useState<any>({});
  const [dragOverItem, setDragOverItem] = useState<any>({});

  useEffect(() => {
    if (isLoading) return;
    getModelGroup();
  }, [get, isLoading]);

  const showDeleteConfirm = (row: GroupItem) => {
    confirm({
      title: t('deleteTitle'),
      content: t('deleteContent'),
      centered: true,
      onOk() {
        return new Promise(async (resolve) => {
          try {
            await del(`/cmdb/api/classification/${row.classification_id}/`);
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

  const updateGroupList = () => {
    getModelGroup();
  };

  const updateModelList = () => {
    getModelGroup();
  };

  const onSearchTxtChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchText(e.target.value);
  };

  const onTxtPressEnter = () => {
    getModelGroup();
  };

  const onTxtClear = () => {
    getModelGroup();
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

  const handleDragStart = (item: any) => {
    if (item) return;
    setDragItem(item);
  };

  const handleDragEnter = (item: any) => {
    if (item) return;
    setDragOverItem(item);
  };

  const handleDragEnd = (groupIndex: number) => {
    if (groupIndex) return;
    if (dragItem === null || dragOverItem === null) {
      return;
    }
    const newModelGroup = Array.from(modelGroup);
    const newItems = newModelGroup[groupIndex].list;
    const [draggedItem] = newItems.splice(dragItem.index, 1);
    newItems.splice(dragOverItem.index, 0, draggedItem);
    setDragItem(null);
    setDragOverItem(null);
    setModelGroup(newModelGroup);
  };

  const getModelGroup = async () => {
    setLoading(true);
    try {
      const [modeldata, groupData, instCount] = await Promise.all([
        get('/cmdb/api/model/'),
        get('/cmdb/api/classification/'),
        get('/cmdb/api/instance/model_inst_count/')
      ]);
      const groups = deepClone(groupData).map((item: GroupItem) => ({
        ...item,
        list: [],
        count: 0,
      }));
      modeldata.forEach((modelItem: ModelItem) => {
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
      setGroupList(groupData);
      setModelGroup(groups);
    } catch (error) {
      console.error(error);
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

  return (
    <div className={assetManageStyle.container}>
      <Introduction title={t('Model.title')} message={t('Model.message')} />
      <div className={assetManageStyle.modelSetting}>
        <div className="nav-box flex justify-between mb-[10px]">
          <div className="left-side w-[240px]">
            <Input
              placeholder={t('search')}
              value={searchText}
              allowClear
              onChange={onSearchTxtChange}
              onPressEnter={onTxtPressEnter}
              onClear={onTxtClear}
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
          </div>
        </div>
        <Spin spinning={loading}>
          {modelGroup.length ? (
            modelGroup.map((item, groupIndex) => {
              return (
                <div className="model-group" key={item.classification_id}>
                  <div
                    className={`${assetManageStyle.groupTitle} flex items-center mt-[20px] text-[14px]`}
                  >
                    <span className="border-l-[4px] border-[var(--color-primary)] px-[4px] py-[1px] font-[600]">
                      {item.classification_name}（{item.count}）
                    </span>
                    {isAdmin ||
                      (!item.is_pre && (
                        <div className={assetManageStyle.groupOperate}>
                          <PermissionWrapper
                            requiredPermissions={['Edit Group']}
                          >
                            <EditTwoTone
                              className="edit mr-[6px] cursor-pointer"
                              onClick={() => showGroupModal('edit', item)}
                            />
                          </PermissionWrapper>

                          {!item.list.length && (
                            <PermissionWrapper
                              requiredPermissions={['Delete Group']}
                            >
                              <DeleteTwoTone
                                className="delete cursor-pointer"
                                onClick={() => showDeleteConfirm(item)}
                              />
                            </PermissionWrapper>
                          )}
                        </div>
                      ))}
                  </div>
                  <ul className={assetManageStyle.modelList}>
                    {item.list.map((model, index) => (
                      <li
                        className={`bg-[var(--color-bg)] flex justify-between items-center ${
                          assetManageStyle.modelListItem
                        } ${
                          dragOverItem?.model_id === model.model_id &&
                          dragOverItem?.model_id !== dragItem?.model_id &&
                          modelGroup[groupIndex].list.find(
                            (group) => group.model_id === dragItem.model_id
                          )
                            ? assetManageStyle.dragActive
                            : ''
                        }`}
                        key={index}
                        draggable
                        onDragStart={() =>
                          handleDragStart({
                            ...model,
                            index,
                          })
                        }
                        onDragEnter={() =>
                          handleDragEnter({
                            ...model,
                            index,
                          })
                        }
                        onDragEnd={() => handleDragEnd(groupIndex)}
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
                          <HolderOutlined
                            className={`${assetManageStyle.dragHander} cursor-move`}
                          />
                          <div style={{width: 40}}>
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
        groupList={groupList}
        onSuccess={updateModelList}
      />
    </div>
  );
};

export default AssetManage;
