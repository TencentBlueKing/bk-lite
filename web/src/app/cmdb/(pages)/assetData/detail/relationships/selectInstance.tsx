'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useEffect,
} from 'react';
import {
  Select,
  Button,
  message,
  TablePaginationConfig,
  Spin,
  Modal,
} from 'antd';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import {
  AttrFieldType,
  ColumnItem,
  AssoFieldType,
  ListItem,
  RelationListInstItem,
  CrentialsAssoInstItem,
  RelationInstanceRef,
} from '@/app/cmdb/types/assetManage';
import { getAssetColumns } from '@/app/cmdb/utils/common';
import { useInstanceApi, useModelApi } from '@/app/cmdb/api';
import SearchFilter from '../../list/searchFilter';
import CustomTable from '@/components/custom-table';
import { SelectInstanceProps } from '@/app/cmdb/types/assetData';
import PermissionWrapper from '@/components/permission';

const { Option } = Select;
const { confirm } = Modal;

const SelectInstance = forwardRef<RelationInstanceRef, SelectInstanceProps>(
  ({ userList, models, assoTypes, needFetchAssoInstIds, onSuccess }, ref) => {
    const { t } = useTranslation();
    const instanceApi = useInstanceApi();
    const modelApi = useModelApi();
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [loading, setLoading] = useState<boolean>(false);
    const [title, setTitle] = useState<string>('');
    const [assoModelId, setAssoModelId] = useState<number>(0);
    const [instId, setInstId] = useState<string>('');
    const [modelId, setModelId] = useState<string>('');
    const [tableLoading, setTableLoading] = useState<boolean>(false);
    const [columns, setColumns] = useState<ColumnItem[]>([]);
    const [tableData, setTableData] = useState<any[]>([]);
    const [queryList, setQueryList] = useState<unknown>(null);
    const [relationList, setRelationList] = useState<ListItem[]>([]);
    const [assoInstIds, setAssoInstIds] = useState<RelationListInstItem[]>([]);
    const [proxyOptions, setProxyOptions] = useState<
      { proxy_id: string; proxy_name: string }[]
    >([]);
    const [intancePropertyList, setIntancePropertyList] = useState<
      AttrFieldType[]
    >([]);
    const [pagination, setPagination] = useState<TablePaginationConfig>({
      current: 1,
      total: 0,
      pageSize: 20,
    });

    useEffect(() => {
      if (modelId && assoModelId && pagination?.current) {
        fetchData();
      }
    }, [pagination?.current, pagination?.pageSize, queryList]);

    useEffect(() => {
      if (modelId === 'host') {
        instanceApi
          .getInstanceProxys()
          .then((data: any[]) => {
            setProxyOptions(data || []);
          })
          .catch(() => {
            setProxyOptions([]);
          });
      }
    }, [modelId]);

    useEffect(() => {
      if (relationList.length && assoModelId && intancePropertyList.length) {
        const columns = [
          ...getAssetColumns({
            attrList: intancePropertyList,
            userList,
            t,
          }),
          {
            title: t('common.actions'),
            dataIndex: 'action',
            key: 'action',
            fixed: 'right',
            width: 120,
            render: (_: unknown, record: any) => {
              const isRelated = !!assoInstIds.find(
                (item) => item.id === record._id
              );
              return (
                <PermissionWrapper
                  requiredPermissions={[
                    isRelated ? 'Add Associate' : 'Delete Associate',
                  ]}
                  instPermissions={record.permission}
                >
                  <Button
                    type="link"
                    onClick={() => handleRelate(record, isRelated)}
                  >
                    {t(
                      isRelated ? 'Model.disassociation' : 'Model.association'
                    )}
                  </Button>
                </PermissionWrapper>
              );
            },
          },
        ];
        columns[0].fixed = true;
        setColumns(columns);
      }
    }, [relationList, assoModelId, intancePropertyList, assoInstIds]);

    useImperativeHandle(ref, () => ({
      showModal: async ({ title, model_id, list, instId }) => {
        // 开启弹窗的交互
        setGroupVisible(true);
        setTitle(title);
        setModelId(model_id);
        setInstId(instId);
        setAssoInstIds(list);
        setLoading(true);
        try {
          const getAssoModelList = modelApi.getModelAssociations(model_id);
          Promise.all([
            getAssoModelList,
            needFetchAssoInstIds &&
              instanceApi.getAssociationInstanceList(
                model_id,
                instId.toString()
              ),
          ])
            .then((res) => {
              const relationData = res[0].map((item: AssoFieldType) => {
                return {
                  ...item,
                  name: `${showModelName(item.src_model_id)}-${showConnectType(
                    item.asst_id,
                    'asst_name'
                  )}-${showModelName(item.dst_model_id)}`,
                  id:
                    item.src_model_id === model_id
                      ? item.dst_model_id
                      : item.src_model_id,
                };
              });
              const currentAssoModelId = relationData[0]?._id || 0;
              const _modelId = relationData[0]?.id || '';
              setRelationList(relationData);
              setAssoModelId(currentAssoModelId);
              initPage(_modelId);
              if (needFetchAssoInstIds) {
                const assoIds = res[1].reduce(
                  (pre: RelationListInstItem[], cur: CrentialsAssoInstItem) => {
                    const allInstIds = cur.inst_list.map((item) => ({
                      id: item._id,
                      inst_asst_id: item.inst_asst_id,
                    }));
                    pre = [...pre, ...allInstIds];
                    return pre;
                  },
                  []
                );
                setAssoInstIds(assoIds);
              }
            })
            .catch(() => {
              setLoading(false);
            });
        } catch {
          setLoading(false);
        }
      },
    }));

    const initPage = async (modelId: string) => {
      setLoading(true);
      try {
        const params = getTableParams();
        params.model_id = modelId;
        params.page = 1;
        const attrList = modelApi.getModelAttrList(modelId);
        const getInstanseList = instanceApi.searchInstances(params);
        Promise.all([attrList, getInstanseList])
          .then((res) => {
            setIntancePropertyList(res[0]);
            setTableData(res[1].insts);
            setPagination((prev) => ({
              ...prev,
              total: res[1].count,
              current: 1,
            }));
            setLoading(false);
          })
          .catch(() => {
            setLoading(false);
          });
      } catch {
        setLoading(false);
      }
    };

    const getModelId = (id: number) => {
      const target = relationList.find((item) => item._id === id);
      return target?.id || '';
    };

    const showModelName = (id: string) => {
      return models.find((item) => item.model_id === id)?.model_name || '--';
    };
    const showConnectType = (id: string, key: string) => {
      return assoTypes.find((item) => item.asst_id === id)?.[key] || '--';
    };

    const handleRelate = async (row = { _id: '' }, isRelated: boolean) => {
      if (isRelated) {
        cancelRelate(row._id);
        return;
      }
      setTableLoading(true);
      try {
        const target = relationList.find((item) => item._id === assoModelId);
        const params = {
          model_asst_id: target?.model_asst_id,
          src_model_id: target?.src_model_id,
          dst_model_id: target?.dst_model_id,
          asst_id: target?.asst_id,
          src_inst_id: target?.src_model_id === modelId ? +instId : row._id,
          dst_inst_id: target?.dst_model_id === modelId ? +instId : row._id,
        };
        const res = await instanceApi.createInstanceAssociation(params);
        // 更新关联状态
        setAssoInstIds([
          ...assoInstIds,
          { id: row._id, inst_asst_id: res._id },
        ]);
        message.success(t('successfullyAssociated'));
        onSuccess && onSuccess();
      } finally {
        setTableLoading(false);
      }
    };

    const cancelRelate = async (id: unknown) => {
      confirm({
        title: t('disassociationTitle'),
        content: t('common.deleteContent'),
        centered: true,
        onOk() {
          return new Promise(async (resolve) => {
            try {
              const instAsstId = assoInstIds.find(
                (item) => item.id === id
              )?.inst_asst_id;

              if (!instAsstId) {
                message.error(t('common.operationFailed'));
                resolve(true);
                return;
              }

              await instanceApi.deleteInstanceAssociation(
                instAsstId.toString()
              );
              // 更新关联状态
              setAssoInstIds(assoInstIds.filter((item) => item.id !== id));
              message.success(t('successfullyDisassociated'));
              onSuccess && onSuccess();
            } finally {
              resolve(true);
            }
          });
        },
      });
    };

    const fetchData = async () => {
      setTableLoading(true);
      const params = getTableParams();
      try {
        const data = await instanceApi.searchInstances(params);
        setTableData(data.insts);
        setPagination((prev) => ({
          ...prev,
          total: data.count,
        }));
      } catch (error) {
        console.log(error);
      } finally {
        setTableLoading(false);
      }
    };

    const getTableParams = () => {
      return {
        query_list: queryList ? [queryList] : [],
        page: pagination.current,
        page_size: pagination.pageSize,
        order: '',
        model_id: getModelId(assoModelId),
        role: '',
      };
    };

    const handleCancel = () => {
      setGroupVisible(false);
    };

    const handleSearch = (condition: unknown) => {
      setQueryList(condition);
      setPagination((prev) => ({
        ...prev,
        current: 1,
      }));
    };

    const handleTableChange = (pagination = {}) => {
      setPagination(pagination);
    };

    const handleModelChange = (model: number) => {
      setAssoModelId(model);
      const id: any = getModelId(model);
      initPage(id);
    };

    return (
      <OperateModal
        title={title}
        styles={{ body: { display: 'flex', flexDirection: 'column' } }}
        open={groupVisible}
        width={900}
        onCancel={handleCancel}
        footer={
          <div>
            <Button onClick={handleCancel}>{t('common.cancel')}</Button>
          </div>
        }
      >
        <div className="flex flex-col">
          <div className="flex items-center justify-between mb-[16px]">
            <Select
              className="w-[300px]"
              value={assoModelId}
              onChange={handleModelChange}
            >
              {relationList.map((item, index) => {
                return (
                  <Option value={item._id} key={index}>
                    {item.name}
                  </Option>
                );
              })}
            </Select>
            <SearchFilter
              userList={userList}
              attrList={intancePropertyList}
              proxyOptions={proxyOptions}
              onSearch={handleSearch}
            />
          </div>
          <div className="flex-1 overflow-hidden">
            <Spin spinning={loading}>
              <CustomTable
                size="middle"
                dataSource={tableData}
                columns={columns}
                pagination={pagination}
                loading={tableLoading}
                rowKey="_id"
                scroll={{ x: 840, y: 'calc(100vh - 440px)' }}
                onChange={handleTableChange}
              />
            </Spin>
          </div>
        </div>
      </OperateModal>
    );
  }
);
SelectInstance.displayName = 'fieldMoadal';
export default SelectInstance;
