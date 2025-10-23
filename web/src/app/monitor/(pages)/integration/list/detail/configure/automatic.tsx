import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Form, Select, Button, message, InputNumber } from 'antd';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
import { v4 as uuidv4 } from 'uuid';
import { TIMEOUT_UNITS } from '@/app/monitor/constants/integration';
import { useSearchParams, useRouter } from 'next/navigation';
import useApiClient from '@/utils/request';
import useIntegrationApi from '@/app/monitor/api/integration';
import { TableDataItem } from '@/app/monitor/types';
import {
  IntegrationAccessProps,
  IntegrationMonitoredObject,
} from '@/app/monitor/types/integration';
import { useUserInfoContext } from '@/context/userInfo';
import Permission from '@/components/permission';
import { useMonitorConfig } from '@/app/monitor/hooks/integration/index';
import { useCommonColumns } from '@/app/monitor/hooks/integration/common/commonColumns';
import { cloneDeep } from 'lodash';

const { Option } = Select;

const AutomaticConfiguration: React.FC<IntegrationAccessProps> = ({
  showInterval = true,
}) => {
  const [form] = Form.useForm();
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { isLoading } = useApiClient();
  const { getMonitorNodeList, updateNodeChildConfig } = useIntegrationApi();
  const router = useRouter();
  const configs = useMonitorConfig();
  const columnsConfig = useCommonColumns();
  const userContext = useUserInfoContext();
  const currentGroup = useRef(userContext?.selectedGroup);
  const groupId = [currentGroup?.current?.id || ''];
  const pluginName = searchParams.get('plugin_name') || '';
  const objectName = searchParams.get('name') || '';
  const objectId = searchParams.get('id') || '';
  const [dataSource, setDataSource] = useState<IntegrationMonitoredObject[]>(
    []
  );
  const [nodeList, setNodeList] = useState<TableDataItem[]>([]);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [nodesLoading, setNodesLoading] = useState<boolean>(false);
  const [initTableItems, setInitTableItems] =
    useState<IntegrationMonitoredObject>({});

  const onTableDataChange = (data: IntegrationMonitoredObject[]) => {
    setDataSource(data);
  };

  const configsInfo = useMemo(() => {
    return configs.getPlugin({
      objectName,
      mode: 'auto',
      pluginName,
      dataSource,
      onTableDataChange,
    });
  }, [pluginName, objectName, dataSource]);

  const collectType = useMemo(() => {
    return configsInfo.collect_type || '';
  }, [configsInfo]);

  const columns = useMemo(() => {
    const commonColumns = columnsConfig.getCommonColumns({
      nodesLoading,
      nodeList,
      dataSource,
      collectType,
      initTableItems,
      onTableDataChange,
    });
    const displaycolumns = configsInfo.columns;
    return [commonColumns[0], ...displaycolumns, ...commonColumns.slice(1, 5)];
  }, [
    columnsConfig,
    nodesLoading,
    nodeList,
    dataSource,
    configsInfo,
    collectType,
  ]);

  const formItems = useMemo(() => {
    return configsInfo.formItems;
  }, [configsInfo]);

  useEffect(() => {
    if (isLoading) return;
    getNodeList();
    initData();
  }, [isLoading]);

  useEffect(() => {
    if (configsInfo.initTableItems) {
      const initItems = {
        ...configsInfo.initTableItems,
        node_ids: null,
        instance_name: null,
        group_ids: groupId,
        key: uuidv4(),
      };
      setInitTableItems(initItems);
      setDataSource([initItems]);
    }
  }, [nodeList]);

  const initData = () => {
    form.setFieldsValue({
      interval: collectType === 'http' ? 60 : 10,
      ...configsInfo.defaultForm,
    });
  };

  const getNodeList = async () => {
    setNodesLoading(true);
    try {
      const data = await getMonitorNodeList({
        cloud_region_id: 0,
        page: 1,
        page_size: -1,
        is_active: true,
      });
      setNodeList(data.nodes || []);
    } finally {
      setNodesLoading(false);
    }
  };

  const handleSave = () => {
    form.validateFields().then((values) => {
      const row = cloneDeep(values);
      delete row.nodes;
      const params = configsInfo.getParams(row, { dataSource, nodeList });
      params.monitor_object_id = +objectId;
      addNodesConfig(params);
    });
  };

  const addNodesConfig = async (params = {}) => {
    try {
      setConfirmLoading(true);
      await updateNodeChildConfig(params);
      message.success(t('common.addSuccess'));
      const searchParams = new URLSearchParams({
        objId: objectId,
      });
      const targetUrl = `/monitor/integration/list?${searchParams.toString()}`;
      router.push(targetUrl);
    } finally {
      setConfirmLoading(false);
    }
  };

  return (
    <div className="px-[10px]">
      <Form form={form} name="basic" layout="vertical">
        <b className="text-[14px] flex mb-[10px] ml-[-10px]">
          {t('monitor.integrations.configuration')}
        </b>
        {formItems}
        {showInterval && (
          <Form.Item required label={t('monitor.integrations.interval')}>
            <Form.Item
              noStyle
              name="interval"
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <InputNumber
                className="mr-[10px]"
                min={1}
                precision={0}
                addonAfter={
                  <Select style={{ width: 116 }} defaultValue="s">
                    {TIMEOUT_UNITS.map((item: string) => (
                      <Option key={item} value={item}>
                        {item}
                      </Option>
                    ))}
                  </Select>
                }
              />
            </Form.Item>
            <span className="text-[12px] text-[var(--color-text-3)]">
              {t('monitor.integrations.intervalDes')}
            </span>
          </Form.Item>
        )}
        <b className="text-[14px] flex mb-[10px] ml-[-10px]">
          {t('monitor.integrations.basicInformation')}
        </b>
        <Form.Item
          label={t('monitor.integrations.MonitoredObject')}
          name="nodes"
          rules={[
            {
              required: true,
              validator: async () => {
                if (!dataSource.length) {
                  return Promise.reject(new Error(t('common.required')));
                }
                if (
                  dataSource.some((item) =>
                    Object.values(item).some((value) => !value)
                  )
                ) {
                  return Promise.reject(new Error(t('common.required')));
                }
                return Promise.resolve();
              },
            },
          ]}
        >
          <CustomTable
            scroll={{ y: 'calc(100vh - 490px)', x: 'calc(100vw - 320px)' }}
            dataSource={dataSource}
            columns={columns}
            rowKey="key"
            loading={nodesLoading}
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
