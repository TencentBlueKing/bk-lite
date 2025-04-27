'use client';
import React, {
  useEffect,
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { useSearchParams } from 'next/navigation';
import {
  CrentialsAssoInstItem,
  CrentialsAssoDetailItem,
  ModelItem,
  AssoTypeItem,
  AssoListRef,
  RelationListInstItem,
  RelationInstanceRef,
} from '@/app/cmdb/types/assetManage';
import { getAssetColumns } from '@/app/cmdb/utils/common';
import { Spin, Collapse, Button, Modal, message, Empty } from 'antd';
import { CaretRightOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { AssoListProps } from '@/app/cmdb/types/assetData';
import CustomTable from '@/components/custom-table';
import useApiClient from '@/utils/request';
import assoListStyle from './index.module.scss';
import SelectInstance from './selectInstance';
import PermissionWrapper from '@/components/permission';
import { useRelationships } from '@/app/cmdb/context/relationships';

const { confirm } = Modal;

const AssoList = forwardRef<AssoListRef, AssoListProps>(
  ({ modelList, userList, organizationList, assoTypeList }, ref) => {
    const { t } = useTranslation();
    const [activeKey, setActiveKey] = useState<string[]>([]);
    const [allActiveKeys, setAllActiveKeys] = useState<string[]>([]);
    const [instIds, setInstIds] = useState<RelationListInstItem[]>([]);
    const [assoCredentials, setAssoCredentials] = useState<
      CrentialsAssoInstItem[]
    >([]);
    const [pageLoading, setPageLoading] = useState<boolean>(false);
    const searchParams = useSearchParams();
    const { get, del } = useApiClient();
    const modelId: string = searchParams.get('model_id') || '';
    const instId: string = searchParams.get('inst_id') || '';
    const instanceRef = useRef<RelationInstanceRef>(null);
    const prevModelLenRef = useRef(0);
    const { assoInstances, loading, selectedAssoId, fetchAssoInstances, setSelectedAssoId } = useRelationships();

    useEffect(() => {
      const prevLength = prevModelLenRef.current;
      const currentLength = modelList.length;
      if (prevLength === 0 && currentLength > 0) {
        getInitData(assoInstances);
      }
      prevModelLenRef.current = currentLength;
    }, [modelList, assoInstances]);

    const getInitData = async (data: CrentialsAssoInstItem[]) => {
      setPageLoading(true);
      try {
        processedData(data);
        await updateInstAttrList(data);
        if (!data?.length) {
          setInstIds([]);
          setAssoCredentials([]);
        }
        if (selectedAssoId) {
          scrollToElement(`collapse-${selectedAssoId}`);
        }
      } finally {
        setPageLoading(false);
      }
    };

    const processedData = (assoInstancesList: any) => {
      if (loading || !assoInstancesList?.length) return [];
      const newInstIds = assoInstancesList.reduce(
        (pre: RelationListInstItem[], cur: CrentialsAssoInstItem) => {
          if (!cur.inst_list) return pre;
          const allInstIds = cur.inst_list.map((item) => ({
            id: item._id,
            inst_asst_id: item.inst_asst_id,
          }));
          return [...pre, ...allInstIds];
        },
        []
      );
      setInstIds(newInstIds);
    };

    const updateInstAttrList = async (
      assoInstancesList: any,
      targetId?: string
    ) => {
      if (targetId) {
        const targetItem = assoInstancesList.find(
          (item: any) => item.model_asst_id === targetId
        );
        if (targetItem) {
          const updatedItem = await getModelAttrList(targetItem, {
            assoList: assoInstancesList,
            userData: userList,
            organizationData: organizationList,
            models: modelList,
            assoTypeList,
          });
          setAssoCredentials((prev: any) => {
            const newCredentials = prev.map((item: any) =>
              item.model_asst_id === targetId ? updatedItem : item
            );
            const keys = newCredentials.map((item: any) => item.model_asst_id);
            setActiveKey(keys);
            setAllActiveKeys(keys);
            return newCredentials;
          });
          return;
        }
      }

      const updatedItems = await Promise.all(
        assoInstancesList.map((item: any) =>
          getModelAttrList(item, {
            assoList: assoInstancesList,
            userData: userList,
            organizationData: organizationList,
            models: modelList,
            assoTypeList,
          })
        )
      );
      const keys = updatedItems.map((item) => item.model_asst_id);
      setActiveKey(keys);
      setAllActiveKeys(keys);
      setAssoCredentials(updatedItems);
    };

    const scrollToElement = (elementId: string) => {
      setTimeout(() => {
        const element = document.getElementById(elementId);
        if (element) {
          element.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
        setSelectedAssoId('');
      }, 100);
    };

    useEffect(() => {
      if (selectedAssoId && assoCredentials.length) {
        setActiveKey([...activeKey, selectedAssoId]);
        scrollToElement(`collapse-${selectedAssoId}`);
      }
    }, [selectedAssoId]);

    useImperativeHandle(ref, () => ({
      expandAll: (type: boolean) => {
        setActiveKey(type ? allActiveKeys : []);
      },
      showRelateModal: () => {
        instanceRef.current?.showModal({
          title: t('Model.association'),
          model_id: modelId,
          list: instIds,
          instId,
        });
      },
    }));

    const linkToDetail = (row: any, item: any) => {
      const linkModelId =
        item.src_model_id === modelId ? item.dst_model_id : item.src_model_id;
      const params: any = {
        icn: '',
        model_name: showModelName(linkModelId, modelList),
        model_id: linkModelId,
        classification_id: '',
        inst_id: row._id,
        inst_name: row.inst_name,
      };
      const queryString = new URLSearchParams(params).toString();
      const url = `/cmdb/assetData/detail/baseInfo?${queryString}`;
      window.open(url, '_blank', 'noopener,noreferrer');
    };

    const getModelAttrList = async (item: any, config: any) => {
      const responseData = await get(
        `/cmdb/api/model/${getAttrId(item)}/attr_list/`
      );
      const columns = [
        ...getAssetColumns({
          attrList: responseData,
          userList: config.userData,
          groupList: config.organizationData,
          t,
        }),
        {
          title: t('action'),
          dataIndex: 'action',
          key: 'action',
          fixed: 'right',
          width: 120,
          render: (_: unknown, record: any) => (
            <PermissionWrapper requiredPermissions={['Add']}>
              <Button
                type="link"
                onClick={() =>
                  cancelRelate(record.inst_asst_id, item.model_asst_id)
                }
              >
                {t('Model.disassociation')}
              </Button>
            </PermissionWrapper>
          ),
        },
      ];

      if (columns[0]) {
        columns[0].fixed = 'left';
        columns[0].render = (_: unknown, record: any) => (
          <a
            className="text-[var(--color-primary)]"
            onClick={() => linkToDetail(record, item)}
          >
            {record[columns[0].dataIndex]}
          </a>
        );
      }

      const updatedItem = {
        key: item.model_asst_id,
        label: showConnectName(item, config),
        model_asst_id: item.model_asst_id,
        children: (
          <CustomTable
            size="middle"
            pagination={false}
            dataSource={item.inst_list}
            columns={columns}
            scroll={{ x: 'calc(100vw - 306px)', y: 300 }}
            rowKey="_id"
          />
        ),
      };

      return updatedItem;
    };

    const cancelRelate = async (id: unknown, targetAssoId: string) => {
      confirm({
        title: t('disassociationTitle'),
        content: t('deleteContent'),
        centered: true,
        onOk() {
          return new Promise(async (resolve) => {
            try {
              await del(`/cmdb/api/instance/association/${id}/`);
              message.success(t('successfullyDisassociated'));
              const data = await fetchAssoInstances(modelId, instId);
              processedData(data);
              await updateInstAttrList(data, targetAssoId);
            } finally {
              resolve(true);
            }
          });
        },
      });
    };

    const showConnectName = (row: any, config: any) => {
      const sourceName = showModelName(row.src_model_id, config.models);
      const targetName = showModelName(row.dst_model_id, config.models);
      const relation = showConnectType(row.asst_id, config.assoTypeList);
      return `${sourceName} ${relation} ${targetName}`;
    };

    const showModelName = (id: string, list: ModelItem[]) => {
      return list.find((item) => item.model_id === id)?.model_name || '--';
    };
    const showConnectType = (id: string, assoTypeList: AssoTypeItem[]) => {
      return (
        assoTypeList.find((item) => item.asst_id === id)?.asst_name || '--'
      );
    };

    const getAttrId = (item: CrentialsAssoDetailItem) => {
      const { dst_model_id: dstModelId, src_model_id: srcModelId } = item;
      if (modelId === dstModelId) {
        return srcModelId;
      }
      return dstModelId;
    };

    const handleCollapseChange = (keys: any) => {
      setActiveKey(keys);
    };

    const confirmRelate = async () => {
      const data = await fetchAssoInstances(modelId, instId);
      getInitData(data);
    };

    return (
      <Spin spinning={!loading && pageLoading}>
        <div className={assoListStyle.relationships}>
          {assoCredentials.length ? (
            <Collapse
              bordered={false}
              activeKey={activeKey}
              expandIcon={({ isActive }) => (
                <CaretRightOutlined rotate={isActive ? 90 : 0} />
              )}
              items={assoCredentials.map((item) => ({
                ...item,
                id: `collapse-${item.key}`,
              }))}
              onChange={handleCollapseChange}
            />
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
        </div>
        <SelectInstance
          ref={instanceRef}
          userList={userList}
          models={modelList}
          assoTypes={assoTypeList}
          organizationList={organizationList}
          onSuccess={confirmRelate}
        />
      </Spin>
    );
  }
);
AssoList.displayName = 'assoList';
export default AssoList;
