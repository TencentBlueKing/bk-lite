'use client';
import React, { useEffect, useRef, useState } from 'react';
import { FormInstance, Input, message } from 'antd';
import OperateModal from '@/components/operate-modal';
import useApiClient from '@/utils/request';
import { Form, Menu } from 'antd';
import cloudregionstyle from './index.module.scss';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import useApiCloudRegion from '@/app/node-manager/api/cloudregion';
import EntityList from '@/components/entity-list/index';
import PermissionWrapper from '@/components/permission';
import type {
  cloudRegionItem,
  CloudregioncardProps,
} from '@/app/node-manager/types/cloudregion';

const Cloudregion = () => {
  const cloudregionformRef = useRef<FormInstance>(null);
  const divref = useRef(null);
  const { t } = useTranslation();
  const router = useRouter();
  const { isLoading } = useApiClient();
  const { getcloudlist, updatecloudintro } = useApiCloudRegion();
  const [selectedRegion, setSelectedRegion] =
    useState<CloudregioncardProps | null>(null);
  const [openeditcloudregion, setOpeneditcloudregion] = useState(false);
  const [clouditem, setClouditem] = useState<cloudRegionItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);

  // 获取相关的接口
  const fetchCloudRegions = async () => {
    setLoading(true);
    try {
      const data = await getcloudlist();
      if (data.length) {
        setSelectedRegion(data[0]);
        setClouditem([
          {
            id: data[0].id,
            name: data[0].name,
            description: data[0].introduction as string,
            icon: 'yunquyu',
          },
        ]);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isLoading) {
      fetchCloudRegions();
    }
  }, [isLoading]);

  useEffect(() => {
    cloudregionformRef.current?.resetFields();
    cloudregionformRef.current?.setFieldsValue({
      cloudregion: {
        id: selectedRegion?.id,
        title: selectedRegion?.name,
        introduction: selectedRegion?.introduction,
      },
    });
  }, [openeditcloudregion]);

  const handleFormOkClick = () => {
    const { cloudregion } = cloudregionformRef.current?.getFieldsValue();
    updatecloudintro(cloudregion.id, {
      introduction: cloudregion.introduction,
    }).then(() => {
      fetchCloudRegions();
      message.success(t('common.updateSuccess'));
    });
    setOpeneditcloudregion(false);
  };

  const handleEdit = () => {
    setOpeneditcloudregion(true);
  };

  const navigateToNode = (item: cloudRegionItem) => {
    router.push(
      `/node-manager/cloudregion/node?cloud_region_id=1&name=${item.name}`
    );
  };
  return (
    <div
      ref={divref}
      className={`${cloudregionstyle.cloudregion} w-full h-full`}
    >
      <EntityList
        data={clouditem}
        loading={loading}
        menuActions={() => {
          return (
            <Menu>
              <PermissionWrapper requiredPermissions={['Edit']}>
                <Menu.Item key="edit" onClick={() => handleEdit()}>
                  {t('common.edit')}
                </Menu.Item>
              </PermissionWrapper>
            </Menu>
          );
        }}
        openModal={() => {}}
        onCardClick={(item: cloudRegionItem) => {
          navigateToNode(item);
        }}
      ></EntityList>
      {/* 编辑默认云区域弹窗 */}
      <OperateModal
        title={t('node-manager.cloudregion.editform.title')}
        open={openeditcloudregion}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        onCancel={() => {
          setOpeneditcloudregion(false);
        }}
        onOk={() => {
          handleFormOkClick();
        }}
      >
        <Form layout="vertical" ref={cloudregionformRef} name="nest-messages">
          <Form.Item name={['cloudregion', 'id']} hidden>
            <Input />
          </Form.Item>
          <Form.Item name={['cloudregion', 'title']} label={t('common.name')}>
            <Input placeholder={selectedRegion?.name} disabled />
          </Form.Item>
          <Form.Item
            name={['cloudregion', 'introduction']}
            label={t('node-manager.cloudregion.editform.Introduction')}
          >
            <Input.TextArea rows={5} />
          </Form.Item>
        </Form>
      </OperateModal>
    </div>
  );
};

export default Cloudregion;
