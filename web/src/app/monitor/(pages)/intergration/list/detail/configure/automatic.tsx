import React, { useState, useRef, useEffect } from 'react';
import { Form, Input, Select, Button, message, InputNumber } from 'antd';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
import { v4 as uuidv4 } from 'uuid';
import { deepClone } from '@/app/monitor/utils/common';
import {
  COLLECT_TYPE_MAP,
  INSTANCE_TYPE_MAP,
  CONFIG_TYPE_MAP,
  useMiddleWareFields,
  TIMEOUT_UNITS,
} from '@/app/monitor/constants/monitor';
import { useSearchParams, useRouter } from 'next/navigation';
import useApiClient from '@/utils/request';
import { useCommon } from '@/app/monitor/context/common';
import { Organization, ListItem, TableDataItem } from '@/app/monitor/types';
import { IntergrationMonitoredObject } from '@/app/monitor/types/monitor';
import { useUserInfoContext } from '@/context/userInfo';
import { useColumnsAndFormItems } from '@/app/monitor/hooks/intergration';
import Permission from '@/components/permission';

const { Option } = Select;

const AutomaticConfiguration: React.FC = () => {
  const [form] = Form.useForm();
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { post, isLoading } = useApiClient();
  const commonContext = useCommon();
  const router = useRouter();
  const userContext = useUserInfoContext();
  const currentGroup = useRef(userContext?.selectedGroup);
  const groupId = [currentGroup?.current?.id || ''];
  const authList = useRef(commonContext?.authOrganizations || []);
  const organizationList: Organization[] = authList.current;
  const pluginName = searchParams.get('collect_type') || '';
  const collectType = COLLECT_TYPE_MAP[pluginName];
  const instType = INSTANCE_TYPE_MAP[pluginName];
  const configTypes = CONFIG_TYPE_MAP[pluginName];
  const objectName = searchParams.get('name') || '';
  const objectId = searchParams.get('id') || '';
  const getInitMonitoredObjectItem = () => {
    const initItem = {
      key: uuidv4(),
      node_ids: null,
      instance_name: null,
      group_ids: groupId,
    };
    if (['web', 'ping', 'middleware'].includes(collectType)) {
      return { ...initItem, url: null };
    }
    if (['snmp', 'ipmi'].includes(collectType)) {
      return { ...initItem, ip: null };
    }
    if (collectType === 'docker') {
      return { ...initItem, endpoint: null };
    }
    if (collectType === 'database') {
      return pluginName === 'ElasticSearch'
        ? { ...initItem, server: null }
        : { ...initItem, host: null, port: null };
    }
    if (collectType === 'vmware') {
      return { ...initItem, host: null };
    }
    return initItem as IntergrationMonitoredObject;
  };
  const authPasswordRef = useRef<any>(null);
  const privPasswordRef = useRef<any>(null);
  const passwordRef = useRef<any>(null);
  const [dataSource, setDataSource] = useState<IntergrationMonitoredObject[]>([
    getInitMonitoredObjectItem(),
  ]);
  const [authPasswordDisabled, setAuthPasswordDisabled] =
    useState<boolean>(true);
  const [privPasswordDisabled, setPrivPasswordDisabled] =
    useState<boolean>(true);
  const [passwordDisabled, setPasswordDisabled] = useState<boolean>(true);
  const [nodeList, setNodeList] = useState<ListItem[]>([]);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [nodesLoading, setNodesLoading] = useState<boolean>(false);
  const middleWareFieldsMap = useMiddleWareFields();

  const columns: any[] = [
    {
      title: t('monitor.intergrations.node'),
      dataIndex: 'node_ids',
      key: 'node_ids',
      width: 200,
      render: (_: unknown, record: TableDataItem, index: number) => (
        <Select
          loading={nodesLoading}
          value={record.node_ids}
          onChange={(val) => handleFilterNodeChange(val, index)}
        >
          {getFilterNodes(record.node_ids).map((item) => (
            <Option key={item.id} value={item.id}>
              {item.name}
            </Option>
          ))}
        </Select>
      ),
    },
    {
      title: t('monitor.intergrations.node'),
      dataIndex: 'node_ids',
      key: 'node_ids',
      width: 200,
      render: (_: unknown, record: TableDataItem, index: number) => (
        <Select
          mode="tags"
          maxTagCount="responsive"
          loading={nodesLoading}
          value={record.node_ids}
          onChange={(val) => handleNodeChange(val, index)}
        >
          {nodeList.map((item) => (
            <Option key={item.id} value={item.id}>
              {item.name}
            </Option>
          ))}
        </Select>
      ),
    },
    {
      title: 'IP',
      dataIndex: 'ip',
      key: 'ip',
      width: 200,
      render: (_: unknown, record: TableDataItem, index: number) => (
        <Input
          value={record.ip}
          onChange={(e) =>
            handleFieldAndInstNameChange(e, {
              index,
              field: 'ip',
            })
          }
        />
      ),
    },
    {
      title: middleWareFieldsMap[pluginName] || middleWareFieldsMap.default,
      dataIndex: 'url',
      key: 'url',
      width: 200,
      render: (_: unknown, record: TableDataItem, index: number) => (
        <Input
          value={record.url}
          onChange={(e) =>
            handleFieldAndInstNameChange(e, {
              index,
              field: 'url',
            })
          }
        />
      ),
    },
    {
      title: t('monitor.intergrations.instanceName'),
      dataIndex: 'instance_name',
      key: 'instance_name',
      width: 200,
      render: (_: unknown, record: TableDataItem, index: number) => (
        <Input
          value={record.instance_name}
          onChange={(e) => handleInstNameChange(e, index)}
        />
      ),
    },
    {
      title: t('common.group'),
      dataIndex: 'group_ids',
      key: 'group_ids',
      width: 200,
      render: (_: unknown, record: TableDataItem, index: number) => (
        <Select
          mode="tags"
          maxTagCount="responsive"
          value={record.group_ids}
          onChange={(val) => handleGroupChange(val, index)}
        >
          {organizationList.map((item) => (
            <Option key={item.value} value={item.value}>
              {item.label}
            </Option>
          ))}
        </Select>
      ),
    },
    {
      title: t('common.action'),
      key: 'action',
      dataIndex: 'action',
      width: 160,
      fixed: 'right',
      render: (_: unknown, record: TableDataItem, index: number) => (
        <>
          <Button
            type="link"
            className="mr-[10px]"
            onClick={() => handleAdd(record.key)}
          >
            {t('common.add')}
          </Button>
          {!['host', 'trap'].includes(collectType) && (
            <Button
              type="link"
              className="mr-[10px]"
              onClick={() => handleCopy(record as IntergrationMonitoredObject)}
            >
              {t('common.copy')}
            </Button>
          )}
          {!!index && (
            <Button type="link" onClick={() => handleDelete(record.key)}>
              {t('common.delete')}
            </Button>
          )}
        </>
      ),
    },
    {
      title: t('monitor.intergrations.endpoint'),
      dataIndex: 'endpoint',
      key: 'endpoint',
      width: 200,
      render: (_: unknown, record: TableDataItem, index: number) => (
        <Input
          value={record.endpoint}
          onChange={(e) =>
            handleFieldAndInstNameChange(e, {
              index,
              field: 'endpoint',
            })
          }
        />
      ),
    },
    {
      title: t('monitor.intergrations.servers'),
      dataIndex: 'server',
      key: 'server',
      width: 200,
      render: (_: unknown, record: TableDataItem, index: number) => (
        <Input
          value={record.server}
          onChange={(e) =>
            handleFieldAndInstNameChange(e, {
              index,
              field: 'server',
            })
          }
        />
      ),
    },
    {
      title: t('monitor.intergrations.host'),
      dataIndex: 'host',
      key: 'host',
      width: 200,
      render: (_: unknown, record: TableDataItem, index: number) => (
        <Input
          value={record.host}
          onChange={(e) =>
            handleFieldAndInstNameChange(e, {
              index,
              field: 'host',
              dataIndex: 'host',
            })
          }
        />
      ),
    },
    {
      title: t('monitor.intergrations.port'),
      dataIndex: 'port',
      key: 'port',
      width: 200,
      render: (_: unknown, record: TableDataItem, index: number) => (
        <InputNumber
          value={record.port}
          className="w-full"
          min={1}
          precision={0}
          onChange={(val) =>
            handlePortAndInstNameChange(val, {
              index,
              field: 'port',
            })
          }
        />
      ),
    },
    {
      title: t('monitor.intergrations.host'),
      dataIndex: 'host',
      key: 'host',
      width: 200,
      render: (_: unknown, record: TableDataItem, index: number) => (
        <Input
          value={record.host}
          onChange={(e) =>
            handleFieldAndInstNameChange(e, {
              index,
              field: 'host',
            })
          }
        />
      ),
    },
  ];

  const handleEditAuthPassword = () => {
    if (authPasswordDisabled) {
      form.setFieldsValue({
        authPassword: '',
      });
    }
    setAuthPasswordDisabled(false);
  };

  const handleEditPrivPassword = () => {
    if (privPasswordDisabled) {
      form.setFieldsValue({
        privPassword: '',
      });
    }
    setPrivPasswordDisabled(false);
  };

  const handleEditPassword = () => {
    if (passwordDisabled) {
      form.setFieldsValue({
        password: '',
      });
    }
    setPasswordDisabled(false);
  };

  // 使用自定义 Hook
  const { displaycolumns, formItems } = useColumnsAndFormItems({
    collectType,
    columns,
    authPasswordRef,
    privPasswordRef,
    passwordRef,
    authPasswordDisabled,
    privPasswordDisabled,
    passwordDisabled,
    handleEditAuthPassword,
    handleEditPrivPassword,
    handleEditPassword,
    pluginName,
  });

  useEffect(() => {
    if (!authPasswordDisabled && authPasswordRef?.current) {
      authPasswordRef.current.focus();
    }
  }, [authPasswordDisabled]);

  useEffect(() => {
    if (!privPasswordDisabled && privPasswordRef?.current) {
      privPasswordRef.current.focus();
    }
  }, [privPasswordDisabled]);

  useEffect(() => {
    if (!passwordDisabled && passwordRef?.current) {
      passwordRef.current.focus();
    }
  }, [passwordDisabled]);

  useEffect(() => {
    if (isLoading) return;
    getNodeList();
    initData();
  }, [isLoading]);

  const initData = () => {
    form.setFieldsValue({
      interval: 10,
    });
    switch (collectType) {
      case 'host':
        form.setFieldsValue({
          metric_type: configTypes,
        });
        break;
      case 'ipmi':
        form.setFieldsValue({
          protocol: 'lanplus',
        });
        break;
      case 'snmp':
        form.setFieldsValue({
          port: 161,
          version: 2,
          timeout: 10,
        });
      case 'middleware':
        form.setFieldsValue({
          timeout: 10,
        });
    }
  };

  const getNodeList = async () => {
    setNodesLoading(true);
    try {
      const data = await post('/monitor/api/node_mgmt/nodes/', {
        cloud_region_id: 0,
        page: 1,
        page_size: -1,
      });
      setNodeList(data.nodes || []);
    } finally {
      setNodesLoading(false);
    }
  };

  const getFilterNodes = (id: string) => {
    if (['ipmi', 'snmp'].includes(collectType)) {
      return nodeList;
    }
    const nodeIds = dataSource
      .map((item) => item.node_ids)
      .filter((item) => item !== id);
    const _nodeList = nodeList.filter(
      (item) => !nodeIds.includes(item.id as string)
    );
    return _nodeList;
  };

  const handleAdd = (key: string) => {
    const index = dataSource.findIndex((item) => item.key === key);
    const newData: IntergrationMonitoredObject = getInitMonitoredObjectItem();
    const updatedData = [...dataSource];
    updatedData.splice(index + 1, 0, newData); // 在当前行下方插入新数据
    setDataSource(updatedData);
  };

  const handleCopy = (row: IntergrationMonitoredObject) => {
    const index = dataSource.findIndex((item) => item.key === row.key);
    const newData: IntergrationMonitoredObject = { ...row, key: uuidv4() };
    const updatedData = [...dataSource];
    updatedData.splice(index + 1, 0, newData);
    setDataSource(updatedData);
  };

  const handleDelete = (key: string) => {
    setDataSource(dataSource.filter((item) => item.key !== key));
  };

  const handleSave = () => {
    form.validateFields().then((values) => {
      // 处理表单提交逻辑
      const _values = deepClone(values);
      delete _values.metric_type;
      delete _values.nodes;
      const params = {
        configs: getConfigs(_values),
        collect_type: collectType,
        monitor_object_id: +objectId,
        instances: dataSource.map((item) => {
          const { key, ...rest } = item;
          values.key = key;
          return {
            ...rest,
            node_ids: [item.node_ids].flat(),
            instance_type: instType,
            instance_id: getInstId(item),
          };
        }),
      };
      addNodesConfig(params);
    });
  };

  const getConfigs = (row: TableDataItem) => {
    switch (collectType) {
      case 'host':
        return form.getFieldValue('metric_type').map((item: string) => ({
          type: item,
          ...row,
        }));
      default:
        if (row.timeout) {
          row.timeout = row.timeout + 's';
        }
        return [{ type: configTypes[0], ...row }];
    }
  };

  const getInstId = (row: IntergrationMonitoredObject) => {
    switch (collectType) {
      case 'host':
        const hostTarget: any = nodeList.find(
          (item) => row.node_ids === item.id
        );
        return hostTarget?.ip + '-' + hostTarget?.cloud_region;
      case 'trap':
        const target: any = nodeList.find((item) => row.node_ids === item.id);
        return 'trap' + target?.ip + '-' + target?.cloud_region;
      case 'web':
        return row.url;
      case 'ping':
        return row.url;
      case 'middleware':
        return row.url;
      case 'docker':
        return row.endpoint;
      case 'database':
        return row.server || `${row.host}:${row.port}`;
      case 'vmware':
        return `vc-${row.host}`;
      default:
        return objectName + '-' + (row.ip || '');
    }
  };

  const addNodesConfig = async (params = {}) => {
    try {
      setConfirmLoading(true);
      await post(
        '/monitor/api/node_mgmt/batch_setting_node_child_config/',
        params
      );
      message.success(t('common.addSuccess'));
      const searchParams = new URLSearchParams({
        objId: objectId,
      });
      const targetUrl = `/monitor/intergration/list?${searchParams.toString()}`;
      router.push(targetUrl);
    } finally {
      setConfirmLoading(false);
    }
  };

  const handleFilterNodeChange = (val: string, index: number) => {
    const _dataSource = deepClone(dataSource);
    _dataSource[index].node_ids = val;
    if (['host', 'trap'].includes(collectType)) {
      _dataSource[index].instance_name =
        nodeList.find((item) => item.id === val)?.name || '';
    }
    setDataSource(_dataSource);
  };

  const handleNodeChange = (val: string[], index: number) => {
    const _dataSource = deepClone(dataSource);
    _dataSource[index].node_ids = val;
    setDataSource(_dataSource);
  };

  const handleGroupChange = (val: string[], index: number) => {
    const _dataSource = deepClone(dataSource);
    _dataSource[index].group_ids = val;
    setDataSource(_dataSource);
  };

  const handleInstNameChange = (
    e: React.ChangeEvent<HTMLInputElement>,
    index: number
  ) => {
    const _dataSource = deepClone(dataSource);
    _dataSource[index].instance_name = e.target.value;
    setDataSource(_dataSource);
  };

  const handlePortAndInstNameChange = (
    val: number,
    config: {
      index: number;
      field: string;
    }
  ) => {
    const _dataSource = deepClone(dataSource);
    const host = _dataSource[config.index].host || '';
    _dataSource[config.index][config.field] = val;
    _dataSource[config.index].instance_name = `${host}:${val || ''}`;
    setDataSource(_dataSource);
  };

  const handleFieldAndInstNameChange = (
    e: React.ChangeEvent<HTMLInputElement>,
    config: {
      index: number;
      field: string;
      dataIndex?: string;
    }
  ) => {
    const _dataSource = deepClone(dataSource);
    if (config.dataIndex === 'host') {
      const port = _dataSource[config.index].port || '';
      _dataSource[config.index][config.field] = e.target.value;
      _dataSource[config.index].instance_name = `${e.target.value}:${port}`;
      setDataSource(_dataSource);
      return;
    }
    _dataSource[config.index][config.field] = _dataSource[
      config.index
    ].instance_name = e.target.value;
    setDataSource(_dataSource);
  };

  return (
    <div className="px-[10px]">
      <Form form={form} name="basic" layout="vertical">
        <b className="text-[14px] flex mb-[10px] ml-[-10px]">
          {t('monitor.intergrations.configuration')}
        </b>
        {formItems}
        <Form.Item required label={t('monitor.intergrations.interval')}>
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
            {t('monitor.intergrations.intervalDes')}
          </span>
        </Form.Item>
        <b className="text-[14px] flex mb-[10px] ml-[-10px]">
          {t('monitor.intergrations.basicInformation')}
        </b>
        <Form.Item
          label={t('monitor.intergrations.MonitoredObject')}
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
            columns={displaycolumns}
            rowKey="key"
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
