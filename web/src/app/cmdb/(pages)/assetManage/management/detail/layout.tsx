'use client';

import React, { useRef, useState, useEffect } from 'react';
import WithSideMenuLayout from '@/components/sub-layout';
import ModelModal from '../list/modelModal';
import CopyModelModal from '../list/copyModelModal';
import attrLayoutStyle from './layout.module.scss';
import useApiClient from '@/utils/request';
import PermissionWrapper from '@/components/permission';
import { Button, Modal, message, Tooltip } from 'antd';
import { useScreenAwareRouter } from '@/console-layout';
import TopSection from '@/components/top-section';
import ModelIcon from '@/app/cmdb/components/model-icon';
import SourceOriginBadge from '@/components/source-origin-badge';
import { CopyOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons';
import { useSearchParams } from 'next/navigation';
import { ClassificationItem } from '@/app/cmdb/types/assetManage';
import type { MenuItem } from '@/types';
import { useTranslation } from '@/utils/i18n';
import { useClassificationApi, useModelApi } from '@/app/cmdb/api';
import { ModelDetailContext } from './context';
import { useCommon } from '@/app/cmdb/context/common';
import { OrganizationField } from '@/app/cmdb/utils/common';

const AboutLayout = ({ children }: { children: React.ReactNode }) => {
  const { isLoading } = useApiClient();
  const { t } = useTranslation();
  const { confirm } = Modal;
  const router = useScreenAwareRouter();
  const commonContext = useCommon();

  const { getClassificationList } = useClassificationApi();
  const { deleteModel, getModelDetail, getModelAssociations } = useModelApi();

  const searchParams = useSearchParams();
  const modelId: string = searchParams.get('model_id') || '';
  const isPre = searchParams.get('is_pre') === 'true';
  const modelRef = useRef<any>(null);
  const copyModelRef = useRef<any>(null);
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
      model_name: info.model_name || modelDetail.model_name || '',
      model_id: info.model_id || modelId,
      classification_id:
        info.classification_id || modelDetail.classification_id || '',
      is_pre: String(
        info.is_pre ?? searchParams.get('is_pre') ?? modelDetail.is_pre ?? 'false'
      ),
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
      okButtonProps: { danger: true },
      centered: true,
      onOk() {
        return new Promise(async (resolve) => {
          try {
            const associations = await getModelAssociations(row.model_id);
            if (associations.length > 0) {
              Modal.confirm({
                title: t('common.prompt'),
                content: t('Model.deleteBlockedByAssociationsTip'),
                okText: t('Model.goToRelationshipsCleanup'),
                cancelText: t('common.cancel'),
                centered: true,
                onOk: () => {
                  const params = new URLSearchParams({
                    model_id: modelId,
                    model_name: modelDetail.model_name || '',
                    icn: modelDetail.icn || '',
                    classification_id: modelDetail.classification_id || '',
                    is_pre: searchParams.get('is_pre') || 'false',
                  }).toString();
                  router.push(`/cmdb/assetManage/management/detail/associations?${params}`);
                },
              });
              return;
            }
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

  const showCopyModelModal = () => {
    copyModelRef.current?.showModal({
      model_id: modelId,
      model_name: modelDetail.model_name || '',
      classification_id: modelDetail.classification_id || '',
      icn: modelDetail.icn || '',
      group: modelDetail.group,
    });
  };

  const detailMenuItems: MenuItem[] = [
    {
      name: 'attributes',
      title: t('Model.attributes'),
      url: '/cmdb/assetManage/management/detail/attributes',
      icon: '',
      operation: [],
    },
    {
      name: 'associations',
      title: t('Model.relationships'),
      url: '/cmdb/assetManage/management/detail/associations',
      icon: '',
      operation: [],
    },
    {
      name: 'uniqueRules',
      title: t('Model.uniqueRules'),
      url: '/cmdb/assetManage/management/detail/uniqueRules',
      icon: '',
      operation: [],
    },
    {
      name: 'autoAssociationRules',
      title: t('Model.autoAssociationRules'),
      url: '/cmdb/assetManage/management/detail/autoAssociationRules',
      icon: '',
      operation: [],
    },
  ];

  return (
    <ModelDetailContext.Provider value={modelDetail}>
      <div className={`${attrLayoutStyle.attrLayout} flex h-full min-h-0 min-w-0 w-full flex-col`}>
        <div className="mb-4 flex shrink-0 items-center rounded-md bg-[var(--color-bg)]">
          <TopSection
            className="min-w-0 flex-1"
            title={(
              <span className="inline-flex max-w-full items-center gap-2">
                <span className="min-w-0 truncate">{modelDetail.model_name || ''}</span>
                <SourceOriginBadge
                  kind={(modelDetail.is_pre ?? isPre) ? 'builtin' : 'custom'}
                />
              </span>
            )}
            content={(
              <span>
                {modelId}
                <span className="ml-2">
                  {t('associatedOrganization')}：
                  <OrganizationField value={modelDetail.group} />
                </span>
              </span>
            )}
            icon={(
              <ModelIcon
                icon={modelDetail.icn}
                modelId={modelId}
                className="block"
                alt={t('picture')}
                width={40}
                height={40}
              />
            )}
          />
          <div className="flex shrink-0 items-center gap-1 pr-4">
            <PermissionWrapper
              requiredPermissions={['Edit Model']}
              instPermissions={modelDetail.permission || []}
            >
              <Tooltip title={t('common.edit')}>
                <Button
                  type="text"
                  size="small"
                  aria-label={t('common.edit')}
                  icon={<EditOutlined />}
                  onClick={() =>
                    shoModelModal('edit', {
                      model_name: modelDetail.model_name || '',
                      model_id: modelId,
                      classification_id:
                        modelDetail.classification_id || '',
                      icn: modelDetail.icn || '',
                      group: modelDetail.group,
                      app_topo_layer: modelDetail.app_topo_layer,
                      is_pre: modelDetail.is_pre,
                    })
                  }
                />
              </Tooltip>
            </PermissionWrapper>
            {!isPre && (
              <PermissionWrapper
                requiredPermissions={['Delete Model']}
                instPermissions={modelDetail.permission || []}
              >
                <Tooltip title={t('common.delete')}>
                  <Button
                    type="text"
                    size="small"
                    danger
                    aria-label={t('common.delete')}
                    icon={<DeleteOutlined />}
                    onClick={() =>
                      showDeleteConfirm({
                        model_id: modelId,
                      })
                    }
                  />
                </Tooltip>
              </PermissionWrapper>
            )}
            <PermissionWrapper
              requiredPermissions={['Add Model']}
              instPermissions={modelDetail.permission || []}
            >
              <Tooltip title={t('Model.copyModel')}>
                <Button
                  type="text"
                  size="small"
                  aria-label={t('Model.copyModel')}
                  icon={<CopyOutlined />}
                  onClick={showCopyModelModal}
                />
              </Tooltip>
            </PermissionWrapper>
          </div>
        </div>
        <div
          className={`${attrLayoutStyle.attrLayout} min-h-0 min-w-0 flex-1`}
          style={{ ['--custom-height' as string]: '100%' }}
        >
          <WithSideMenuLayout
            showBackButton={true}
            onBackButtonClick={handleBackButtonClick}
            customMenuItems={detailMenuItems}
          >
            {children}
          </WithSideMenuLayout>
        </div>
        <ModelModal
          ref={modelRef}
          modelGroupList={groupList}
          onSuccess={onSuccess}
        />
        <CopyModelModal
          ref={copyModelRef}
          modelGroupList={groupList}
          onSuccess={onSuccess}
        />
      </div>
    </ModelDetailContext.Provider>
  );
};

export default AboutLayout;
