'use client';
import React, { useEffect, useRef, useState, useCallback } from 'react';
import useApiClient from '@/utils/request';
import { Menu, Button, Modal, message } from 'antd';
import cloudRegionStyle from './index.module.scss';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import useApiCloudRegion from '@/app/node-manager/api/cloudRegion';
import EntityList from '@/components/entity-list';
import PermissionWrapper from '@/components/permission';
import type {
  CloudRegionItem,
  CloudRegionCardProps,
} from '@/app/node-manager/types/cloudregion';
import CloudRegionModal from './cloudregionModal';
import { ModalRef } from '@/app/node-manager/types';
import { useMenuItem } from '@/app/node-manager/hooks/node';
const { confirm } = Modal;

const CloudRegion = () => {
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { getCloudList, deleteCloudRegion } = useApiCloudRegion();
  const router = useRouter();
  const modalRef = useRef<ModalRef>(null);
  const divRef = useRef(null);
  const [cloudItems, setCloudItems] = useState<CloudRegionItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const menuItem = useMenuItem();

  // 获取相关的接口
  const fetchCloudRegions = async () => {
    setLoading(true);
    try {
      const data = await getCloudList();
      const regionData = (data || []).map((item: CloudRegionCardProps) => {
        item.description = item.introduction;
        item.icon = 'yunquyu';
        return item;
      });
      setCloudItems(regionData.sort((a: any, b: any) => a.id - b.id));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isLoading) {
      fetchCloudRegions();
    }
  }, [isLoading]);

  const navigateToNode = (item: CloudRegionItem) => {
    router.push(
      `/node-manager/cloudregion/node?cloud_region_id=${item.id}&name=${item.name}`
    );
  };

  const openModal = (config: any) => {
    modalRef.current?.showModal({
      title: config?.title,
      type: config?.type,
      form: config?.form,
    });
  };

  const handleSubmit = () => {
    fetchCloudRegions();
  };

  const handleDelete = (id: string) => {
    confirm({
      title: t(`node-manager.cloudregion.deleteform.title`),
      content: t(`node-manager.cloudregion.deleteform.deleteInfo`),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk() {
        return new Promise(async (resolve) => {
          try {
            await deleteCloudRegion(id);
            message.success(t('common.successfullyDeleted'));
            fetchCloudRegions();
          } finally {
            return resolve(true);
          }
        });
      },
    });
  };

  const menuActions = useCallback(
    (data: any) => {
      return (
        <Menu onClick={(e) => e.domEvent.preventDefault()}>
          <Menu.Item
            className="!p-0"
            onClick={() =>
              openModal({ title: 'editform', type: 'edit', form: data })
            }
          >
            <PermissionWrapper
              requiredPermissions={['Edit']}
              className="!block"
            >
              <Button type="text" className="w-full">
                {t(`common.edit`)}
              </Button>
            </PermissionWrapper>
          </Menu.Item>
          {data?.name !== 'default' && (
            <Menu.Item className="!p-0" onClick={() => handleDelete(data.id)}>
              <PermissionWrapper
                requiredPermissions={['Delete']}
                className="!block"
              >
                <Button type="text" className="w-full">
                  {t(`common.delete`)}
                </Button>
              </PermissionWrapper>
            </Menu.Item>
          )}
        </Menu>
      );
    },
    [menuItem]
  );

  return (
    <div
      ref={divRef}
      className={`${cloudRegionStyle.cloudregion} w-full h-full`}
    >
      <EntityList
        data={cloudItems}
        loading={loading}
        menuActions={menuActions}
        openModal={() => openModal({ title: 'addform', type: 'add', form: {} })}
        onCardClick={(item: CloudRegionItem) => {
          navigateToNode(item);
        }}
      ></EntityList>
      {/* 编辑默认云区域弹窗 */}
      <CloudRegionModal ref={modalRef} onSuccess={handleSubmit} />
    </div>
  );
};

export default CloudRegion;
