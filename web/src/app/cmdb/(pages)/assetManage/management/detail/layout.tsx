'use client';

import React, { useRef, useState, useEffect } from 'react';
import Image from 'next/image';
import WithSideMenuLayout from '@/components/sub-layout';
import ModelModal from '../list/modelModal';
import attrLayoutStyle from './layout.module.scss';
import useApiClient from '@/utils/request';
import PermissionWrapper from '@/components/permission';
import { Card, Modal, message } from 'antd';
import { useRouter } from 'next/navigation';
import { getIconUrl } from '@/app/cmdb/utils/common';
import { EditTwoTone, DeleteTwoTone } from '@ant-design/icons';
import { useSearchParams } from 'next/navigation';
import { ClassificationItem } from '@/app/cmdb/types/assetManage';
import { useTranslation } from '@/utils/i18n';
import { useClassificationApi, useModelApi } from '@/app/cmdb/api';
import { ModelDetailContext } from './context';
import { useCommon } from '@/app/cmdb/context/common';
import { OrganizationField } from '@/app/cmdb/utils/common';

const AboutLayout = ({ children }: { children: React.ReactNode }) => {
  const { isLoading } = useApiClient();
  const { t } = useTranslation();
  const { confirm } = Modal;
  const router = useRouter();
  const commonContext = useCommon();

  const { getClassificationList } = useClassificationApi();
  const { deleteModel, getModelDetail } = useModelApi();

  const searchParams = useSearchParams();
  const modelId: string = searchParams.get('model_id') || '';
  const isPre = searchParams.get('is_pre') === 'true';
  const modelRef = useRef<any>(null);
  const [groupList, setGroupList] = useState<ClassificationItem[]>([]);
  const [modelDetail, setModelDetail] = useState<any>({});

  useEffect(() => {
    if (isLoading) return;
    getGroups();
    if (modelId) {
      fetchModelDetail();
    }
  }, [isLoading, modelId]);

  const fetchModelDetail = async () => {
    try {
      const data = await getModelDetail(modelId);
      setModelDetail(data);
    } catch (error) {
      console.log(error);
    }
  };

  const getGroups = async () => {
    try {
      const data = await getClassificationList();
      setGroupList(data);
    } catch (error) {
      console.log(error);
    }
  };

  const onSuccess = async (info: any) => {
    const params = new URLSearchParams({
      icn: info.icn || modelDetail.icn || '',
      model_name: info.model_name,
      model_id: info.model_id,
      classification_id: info.classification_id,
      is_pre: info.is_pre || searchParams.get('is_pre') || 'false',
    }).toString();
    router.replace(`/cmdb/assetManage/management/detail/attributes?${params}`);
    fetchModelDetail();

    if (commonContext?.refreshModelList) {
      await commonContext.refreshModelList();
    }
  };

  const handleBackButtonClick = () => {
    router.push(`/cmdb/assetManage`);
  };

  const showDeleteConfirm = (row = { model_id: '' }) => {
    confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk() {
        return new Promise(async (resolve) => {
          try {
            await deleteModel(row.model_id);
            message.success(t('successfullyDeleted'));
            if (commonContext?.refreshModelList) {
              await commonContext.refreshModelList();
            }
            router.push(`/cmdb/assetManage`);
          } finally {
            resolve(true);
          }
        });
      },
    });
  };

  const shoModelModal = (type: string, row = {}) => {
    const title = t(type === 'add' ? 'Model.addModel' : 'Model.editModel');
    modelRef.current?.showModal({
      title,
      type,
      modelForm: row,
      subTitle: '',
    });
  };

  return (
    <ModelDetailContext.Provider value={modelDetail}>
      <div className={`${attrLayoutStyle.attrLayout}`}>
        <Card style={{ width: '100%' }} className="mb-[20px]">
          <header className="flex items-center">
            <Image
              src={getIconUrl({
                icn: modelDetail.icn || '',
                model_id: modelId,
              })}
              className="block mr-[20px]"
              alt={t('picture')}
              width={30}
              height={30}
            />
            <div className="mr-[14px]">
              <div
                className={`text-[14px] font-[800] mb-[2px] ${attrLayoutStyle.ellipsisText} break-all`}
              >
                {modelDetail.model_name || ''}
              </div>
              <div className="text-[var(--color-text-2)] text-[12px] break-all">
                {modelId}
                <span className="ml-2">
                  【{t('associatedOrganization')}：
                  <OrganizationField value={modelDetail.group} />】
                </span>
              </div>
            </div>
            {!isPre && (
              <div className="self-start">
                <PermissionWrapper
                  requiredPermissions={['Edit Model']}
                  instPermissions={modelDetail.permission || []}
                >
                  <EditTwoTone
                    className="edit mr-[10px] text-[14px] cursor-pointer"
                    onClick={() =>
                      shoModelModal('edit', {
                        model_name: modelDetail.model_name || '',
                        model_id: modelId,
                        classification_id: modelDetail.classification_id || '',
                        icn: modelDetail.icn || '',
                        group: modelDetail.group,
                      })
                    }
                  />
                </PermissionWrapper>
                <PermissionWrapper
                  requiredPermissions={['Delete Model']}
                  instPermissions={modelDetail.permission || []}
                >
                  <DeleteTwoTone
                    className="delete text-[14px] cursor-pointer"
                    onClick={() =>
                      showDeleteConfirm({
                        model_id: modelId,
                      })
                    }
                  />
                </PermissionWrapper>
              </div>
            )}
          </header>
        </Card>
        <div
          style={{
            height: 'calc(100vh - 244px)',
            ['--custom-height' as string]: 'calc(100vh - 244px)',
          }}
          className={attrLayoutStyle.attrLayout}
        >
          <WithSideMenuLayout
            showBackButton={true}
            onBackButtonClick={handleBackButtonClick}
          >
            {children}
          </WithSideMenuLayout>
        </div>
        <ModelModal
          ref={modelRef}
          modelGroupList={groupList}
          onSuccess={onSuccess}
        />
      </div>
    </ModelDetailContext.Provider>
  );
};

export default AboutLayout;
