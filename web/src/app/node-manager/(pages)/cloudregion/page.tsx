'use client';
import React, { useEffect, useRef, useState } from 'react';
import useApiClient from '@/utils/request';
import { Button, message, Tag, Tooltip } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import cloudRegionStyle from './index.module.scss';
import { useScreenAwareRouter } from '@/console-layout';
import { useTranslation } from '@/utils/i18n';
import useNodeManagerApi from '@/app/node-manager/api';
import EntityList from '@/components/entity-list';
import GridEntityCard from '@/components/grid-entity-card';
import CardGridSkeleton from '@/components/card-grid-skeleton';
import SourceOriginBadge from '@/components/source-origin-badge';
import Icon from '@/components/icon';
import PermissionWrapper from '@/components/permission';
import type {
  CloudRegionItem,
  CloudRegionCardProps,
} from '@/app/node-manager/types/cloudregion';
import CloudRegionModal from './cloudregionModal';
import DeployModal from './deployModal';
import { ModalRef } from '@/app/node-manager/types';
import { cloneDeep } from 'lodash';
import type { MoreActionsDropdownItem } from '@/components/more-actions-dropdown';

const CloudRegion = () => {
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { getCloudList, deleteCloudRegion } = useNodeManagerApi();
  const router = useScreenAwareRouter();
  const modalRef = useRef<ModalRef>(null);
  const deployModalRef = useRef<ModalRef>(null);
  const divRef = useRef(null);
  const [cloudItems, setCloudItems] = useState<CloudRegionItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);

  // 获取相关的接口
  const fetchCloudRegions = async () => {
    setLoading(true);
    try {
      const data = await getCloudList();
      const regionData = (data || []).map((item: CloudRegionCardProps) => {
        const regionItem = cloneDeep(item);
        item.description = regionItem.display_introduction;
        item.name = regionItem.display_name;
        item.introduction = regionItem.display_introduction;
        item.originalName = regionItem.name;
        item.originalDescription = regionItem.introduction;
        item.icon = 'yunquyu';
        item.proxy_address = regionItem.proxy_address;
        // 处理 services 转换为 tagList
        if (item.services?.length) {
          item.tagList = item.services.map((service: any) => {
            let color = 'default';
            if (service.status === 'normal') {
              color = 'green';
            } else if (service.status === 'error') {
              color = 'red';
            } else if (service.status === 'not_deployed') {
              color = 'default';
            }
            return {
              name: service.name,
              color: color,
              tooltip: service.status === 'error' ? service.description : '',
            };
          });
        }
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
    const isNotDeployed = (item.services || []).find(
      (service) => service.status === 'not_deployed'
    );
    const notDeployed = isNotDeployed ? 1 : 0;
    const menu = isNotDeployed ? 'environment' : 'node';
    router.push(
      `/node-manager/cloudregion/${menu}?cloud_region_id=${item.id}&name=${item.originalName}&displayName=${item.name}&not_deployed=${notDeployed}&proxy_address=${item.proxy_address}`
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

  const buildCloudRegionMenuItems = (
    data: CloudRegionItem
  ): MoreActionsDropdownItem[] | undefined => {
    if (data?.is_default) return undefined;
    return [
      {
        key: 'edit',
        label: t('common.edit'),
        permission: 'Edit',
        onClick: () =>
          openModal({ title: 'editform', type: 'edit', form: data }),
      },
      {
        key: 'delete',
        label: t('common.delete'),
        permission: 'Delete',
        danger: true,
        confirm: {
          title: t('node-manager.cloudregion.deleteform.title'),
          content: t('node-manager.cloudregion.deleteform.deleteInfo'),
        },
        onClick: async () => {
          await deleteCloudRegion(data.id);
          message.success(t('common.successfullyDeleted'));
          fetchCloudRegions();
        },
      },
    ];
  };

  const renderCloudRegionMeta = (item: CloudRegionItem) => (
    <>
      <SourceOriginBadge
        kind={item.is_default ? 'builtin' : 'external'}
        className="h-5 px-1.5 text-[11px] leading-5"
      />
      {(item.tagList || []).map((tag, idx) => (
        <Tooltip key={`${tag.name}-${idx}`} title={tag.tooltip}>
          <Tag color={tag.color} className="mr-0">
            {tag.name}
          </Tag>
        </Tooltip>
      ))}
    </>
  );

  return (
    <div
      ref={divRef}
      className={`${cloudRegionStyle.cloudregion} w-full h-full`}
    >
      <EntityList
        data={cloudItems}
        loading={loading}
        loadingContent={<CardGridSkeleton count={8} />}
        renderCard={(item: CloudRegionItem) => (
          <GridEntityCard
            name={item.name}
            description={item.description}
            icon={<Icon type={item.icon} className="text-2xl" />}
            meta={renderCloudRegionMeta(item)}
            menuItems={buildCloudRegionMenuItems(item)}
            onClick={() => navigateToNode(item)}
          />
        )}
        operateSection={
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() =>
                openModal({ title: 'addform', type: 'add', form: {} })
              }
            >
              {t('common.new')}
            </Button>
          </PermissionWrapper>
        }
      />
      <CloudRegionModal ref={modalRef} onSuccess={handleSubmit} />
      <DeployModal ref={deployModalRef} onSuccess={handleSubmit} />
    </div>
  );
};

export default CloudRegion;
