import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Form, Button, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
import { v4 as uuidv4 } from 'uuid';
import { useSearchParams, useRouter } from 'next/navigation';
import useApiClient from '@/utils/request';
import useIntegrationApi from '@/app/log/api/integration';
import { TableDataItem } from '@/app/log/types';
import {
  IntegrationAccessProps,
  IntegrationLogInstance,
} from '@/app/log/types/integration';
import { useUserInfoContext } from '@/context/userInfo';
import Permission from '@/components/permission';
import { useCollectTypeConfig } from '@/app/log/hooks/integration/index';
import { useCommonColumns } from '@/app/log/hooks/integration/common/commonColumns';
import { cloneDeep } from 'lodash';

const AutomaticConfiguration: React.FC<IntegrationAccessProps> = () => {
  const [form] = Form.useForm();
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { isLoading } = useApiClient();
  const { getLogNodeList, batchCreateInstances } = useIntegrationApi();
  const router = useRouter();
  const { getCollectTypeConfig } = useCollectTypeConfig();
  const columnsConfig = useCommonColumns();
  const userContext = useUserInfoContext();
  const currentGroup = useRef(userContext?.selectedGroup);
  const groupId = [currentGroup?.current?.id || ''];
  const type = searchParams.get('name') || '';
  const collectTypeId = searchParams.get('id') || '';
  const collector = searchParams.get('collector') || '';
  const [dataSource, setDataSource] = useState<IntegrationLogInstance[]>([]);
  const [nodeList, setNodeList] = useState<TableDataItem[]>([]);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [initTableItems, setInitTableItems] = useState<IntegrationLogInstance>(
    {}
  );

  const onTableDataChange = (data: IntegrationLogInstance[]) => {
    setDataSource(data);
  };

  const configsInfo = useMemo(() => {
    return getCollectTypeConfig({
      mode: 'auto',
      type,
      collector,
      dataSource,
      onTableDataChange,
    });
  }, [type, collector, dataSource]);

  const columns = useMemo(() => {
    const commonColumns = columnsConfig.getCommonColumns({
      nodeList,
      dataSource,
      initTableItems,
      onTableDataChange,
    });
    const displaycolumns = configsInfo.columns;
    return [commonColumns[0], ...displaycolumns, ...commonColumns.slice(1, 5)];
  }, [columnsConfig, nodeList, dataSource, configsInfo, type]);

  const formItems = useMemo(() => {
    return configsInfo.formItems;
  }, [configsInfo]);

  useEffect(() => {
    if (isLoading) return;
    initData();
  }, [isLoading]);

  useEffect(() => {
    if (configsInfo.initTableItems) {
      const initItems = {
        instance_id: uuidv4(),
        ...configsInfo.initTableItems,
        node_ids: null,
        instance_name: null,
        group_ids: groupId,
      };
      setInitTableItems(initItems);
      setDataSource([initItems]);
    }
  }, [nodeList]);

  const initData = () => {
    form.setFieldsValue({
      ...configsInfo.defaultForm,
    });
    getNodeList();
  };

  const getNodeList = async () => {
    setLoading(true);
    try {
      const data = await getLogNodeList({
        cloud_region_id: 0,
        page: 1,
        page_size: -1,
        is_active: true,
      });
      setNodeList(data.nodes || []);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = () => {
    form.validateFields().then((values) => {
      const row = cloneDeep(values);
      delete row.nodes;
      const params = configsInfo.getParams(row, { dataSource, nodeList });
      params.collect_type_id = Number(collectTypeId);
      addNodesConfig(params);
    });
  };

  const addNodesConfig = async (params = {}) => {
    try {
      setConfirmLoading(true);
      await batchCreateInstances(params);
      message.success(t('common.addSuccess'));
      router.push('/log/integration/list');
    } finally {
      setConfirmLoading(false);
    }
  };

  return (
    <div className="px-[10px]">
      <Form form={form} name="basic" layout="vertical" className="w-[600px]">
        <b className="text-[14px] flex mb-[10px] ml-[-10px]">
          {t('log.integration.configuration')}
        </b>
        {formItems}
        <Form.Item
          className="w-[calc(100vw-306px)] min-w-[600px]"
          label={t('log.integration.MonitoredObject')}
          name="nodes"
          rules={[
            {
              required: true,
              validator: async () => {
                if (!dataSource.length) {
                  return Promise.reject(new Error(t('common.required')));
                }
                if (
                  dataSource.some((item) => {
                    return Object.values(item).some((value) => !value?.length);
                  })
                ) {
                  return Promise.reject(new Error(t('common.required')));
                }
                return Promise.resolve();
              },
            },
          ]}
        >
          <CustomTable
            scroll={{ y: 'calc(100vh - 490px)' }}
            dataSource={dataSource}
            columns={columns}
            rowKey="instance_id"
            loading={loading}
            pagination={false}
          />
        </Form.Item>
        <Form.Item>
          <Permission requiredPermissions={['Add']}>
            <Button
              type="primary"
              loading={confirmLoading}
              onClick={handleSave}
            >
              {t('common.confirm')}
            </Button>
          </Permission>
        </Form.Item>
      </Form>
    </div>
  );
};

export default AutomaticConfiguration;
