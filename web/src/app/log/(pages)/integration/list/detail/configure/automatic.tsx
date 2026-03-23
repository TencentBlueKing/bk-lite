import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Form, Button, message, Dropdown, Modal } from 'antd';
import type { MenuProps } from 'antd';
import { DownOutlined, UploadOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
import { v4 as uuidv4 } from 'uuid';
import { useSearchParams, useRouter } from 'next/navigation';
import useApiClient from '@/utils/request';
import useIntegrationApi from '@/app/log/api/integration';
import { TableDataItem } from '@/app/log/types';
import {
  IntegrationAccessProps,
  IntegrationLogInstance
} from '@/app/log/types/integration';
import { useUserInfoContext } from '@/context/userInfo';
import Permission from '@/components/permission';
import { useCollectTypeConfig } from '@/app/log/hooks/integration/index';
import { useCommonColumns } from '@/app/log/hooks/integration/common/commonColumns';
import { cloneDeep } from 'lodash';
import BatchEditModal from './batchEditModal';
import ExcelImportModal from './excelImportModal';
const { confirm } = Modal;

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
  const pluginDisplayName = searchParams.get('plugin_display_name') || type;
  const [dataSource, setDataSource] = useState<IntegrationLogInstance[]>([]);
  const [nodeList, setNodeList] = useState<TableDataItem[]>([]);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [initTableItems, setInitTableItems] = useState<IntegrationLogInstance>(
    {}
  );
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const batchEditModalRef = useRef<any>(null);
  const excelImportModalRef = useRef<any>(null);

  const onTableDataChange = (data: IntegrationLogInstance[]) => {
    setDataSource(data);
  };

  const configsInfo = useMemo(() => {
    return getCollectTypeConfig({
      mode: 'auto',
      type,
      collector,
      dataSource,
      onTableDataChange
    });
  }, [type, collector, dataSource]);

  const columns = useMemo(() => {
    const commonColumns = columnsConfig.getCommonColumns({
      nodeList,
      dataSource,
      initTableItems,
      onTableDataChange
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
        group_ids: groupId
      };
      setInitTableItems(initItems);
      setDataSource([initItems]);
    }
  }, [nodeList]);

  const initData = () => {
    form.setFieldsValue({
      ...configsInfo.defaultForm
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
        is_active: true
      });
      setNodeList(data.nodes || []);
    } finally {
      setLoading(false);
    }
  };

  // Build column config for import/batch edit modals
  const modalColumns = useMemo(() => {
    // Common columns config (hardcoded based on useCommonColumns)
    const commonColumnConfigs = [
      {
        name: 'node_ids',
        label: t('log.integration.node'),
        type: 'select' as const,
        required: true,
        enable_row_filter: true
      },
      {
        name: 'instance_name',
        label: t('log.integration.instanceName'),
        type: 'input' as const,
        required: true
      },
      {
        name: 'group_ids',
        label: t('common.belongingGroup'),
        type: 'group_select' as const,
        required: true,
        widget_props: {
          mode: 'multiple' as const
        }
      }
    ];
    // Dynamic columns from configsInfo (if any)
    const dynamicColumnConfigs = (configsInfo.columns || []).map(
      (col: any) => ({
        name: col.dataIndex || col.key,
        label: typeof col.title === 'string' ? col.title : col.dataIndex,
        type: col.type || 'input',
        required: col.required || false,
        widget_props: col.widget_props
      })
    );
    return [...commonColumnConfigs, ...dynamicColumnConfigs];
  }, [t, configsInfo.columns]);

  // Format nodeList for modal options
  const formattedNodeList = useMemo(() => {
    return nodeList.map((node: any) => ({
      label: `${node.name}（${node.ip}）`,
      value: node.id
    }));
  }, [nodeList]);

  const handleBatchDelete = () => {
    confirm({
      title: t('common.prompt'),
      content: t('monitor.integrations.batchDeleteConfirm'),
      centered: true,
      onOk() {
        const updatedData = dataSource.filter(
          (item) => !selectedRowKeys.includes(item.instance_id as string)
        );
        if (updatedData.length === 0) {
          const newData = {
            ...initTableItems,
            instance_id: uuidv4()
          };
          setDataSource([newData]);
        } else {
          setDataSource(updatedData);
        }
        setSelectedRowKeys([]);
      }
    });
  };

  const handleBatchEdit = () => {
    const selectedRows = dataSource.filter((item) =>
      selectedRowKeys.includes(item.instance_id as string)
    );
    batchEditModalRef.current?.showModal({
      columns: modalColumns,
      selectedRows,
      nodeList: formattedNodeList
    });
  };

  const handleBatchEditSuccess = (editedFields: any) => {
    const updatedData = dataSource.map((item) => {
      if (selectedRowKeys.includes(item.instance_id as string)) {
        return {
          ...item,
          ...editedFields
        };
      }
      return item;
    });
    setDataSource(updatedData);
  };

  const handleImport = () => {
    excelImportModalRef.current?.showModal({
      title: t('monitor.integrations.importData'),
      columns: modalColumns,
      nodeList: formattedNodeList,
      pluginName: pluginDisplayName
    });
  };

  const handleImportSuccess = (importedData: any[]) => {
    const newRows = importedData.map((row) => ({
      ...row,
      instance_id: uuidv4(),
      group_ids: row.group_ids || groupId
    }));
    setDataSource([...dataSource, ...newRows]);
  };

  const batchMenuItems: MenuProps['items'] = [
    {
      key: 'batchEdit',
      label: t('common.batchEdit')
    },
    {
      key: 'batchDelete',
      label: t('common.batchDelete'),
      disabled: dataSource.length === 1
    }
  ];

  const handleBatchMenuClick: MenuProps['onClick'] = (e) => {
    if (e.key === 'batchEdit') {
      handleBatchEdit();
    } else if (e.key === 'batchDelete') {
      handleBatchDelete();
    }
  };

  const rowSelection = {
    selectedRowKeys,
    onChange: (newSelectedRowKeys: React.Key[]) => {
      setSelectedRowKeys(newSelectedRowKeys);
    }
  };

  const validateTableData = (): boolean => {
    let hasError = false;
    const newData = [...dataSource];
    // Define required fields for validation
    const requiredFields = ['node_ids', 'instance_name', 'group_ids'];
    // Clear all field errors first
    newData.forEach((row, index) => {
      requiredFields.forEach((fieldName) => {
        newData[index] = {
          ...newData[index],
          [`${fieldName}_error`]: null
        };
      });
    });
    // Validate all required fields
    requiredFields.forEach((fieldName) => {
      dataSource.forEach((row, index) => {
        const value = row[fieldName];
        let errorMsg: string | null = null;
        // Check if value is empty
        if (
          value === undefined ||
          value === null ||
          value === '' ||
          (Array.isArray(value) && value.length === 0)
        ) {
          errorMsg = t('common.required');
        }
        if (errorMsg) {
          hasError = true;
          newData[index] = {
            ...newData[index],
            [`${fieldName}_error`]: errorMsg
          };
        }
      });
    });
    // Update dataSource to show error states
    setDataSource(newData);
    return !hasError;
  };

  const handleSave = () => {
    // Validate table data first
    if (!validateTableData()) {
      return;
    }
    form.validateFields().then((values) => {
      const row = cloneDeep(values);
      delete row.nodes;
      // Clean up _error fields from dataSource before sending to API
      const cleanedDataSource = dataSource.map((item) => {
        const cleanedItem = { ...item };
        Object.keys(cleanedItem).forEach((key) => {
          if (key.endsWith('_error')) {
            delete cleanedItem[key];
          }
        });
        return cleanedItem;
      });
      const params = configsInfo.getParams(row, {
        dataSource: cleanedDataSource,
        nodeList
      });
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
      <Form form={form} name="basic" layout="vertical">
        <b className="text-[14px] flex mb-[10px] ml-[-10px]">
          {t('log.integration.configuration')}
        </b>
        <div className="w-1/2 min-w-[500px]">{formItems}</div>
        <div className="w-[calc(100vw-306px)] min-w-[500px]">
          <div className="flex items-center justify-between mb-[10px]">
            <span className="text-[14px]">
              {t('log.integration.MonitoredObject')}
              <span
                className="text-[#ff4d4f] align-middle text-[14px] ml-[4px]"
                style={{ fontFamily: 'SimSun, sans-serif' }}
              >
                *
              </span>
            </span>
            <div className="flex gap-[8px]">
              <Button
                icon={<UploadOutlined />}
                type="primary"
                onClick={handleImport}
              >
                {t('common.import')}
              </Button>
              <Dropdown
                menu={{
                  items: batchMenuItems,
                  onClick: handleBatchMenuClick
                }}
                disabled={!selectedRowKeys.length}
              >
                <Button>
                  {t('monitor.integrations.batchOperation')}
                  <DownOutlined className="ml-[4px]" />
                </Button>
              </Dropdown>
            </div>
          </div>
          <Form.Item
            name="nodes"
            rules={[
              {
                required: true,
                validator: async () => {
                  if (!dataSource.length) {
                    return Promise.reject(new Error(t('common.required')));
                  }
                  // Only check required fields, not all fields
                  const requiredFields = [
                    'node_ids',
                    'instance_name',
                    'group_ids'
                  ];
                  const hasEmptyField = dataSource.some((item) => {
                    return requiredFields.some((field) => {
                      const value = item[field];
                      return (
                        value === undefined ||
                        value === null ||
                        value === '' ||
                        (Array.isArray(value) && value.length === 0)
                      );
                    });
                  });
                  if (hasEmptyField) {
                    return Promise.reject(new Error(t('common.required')));
                  }
                  return Promise.resolve();
                }
              }
            ]}
          >
            <CustomTable
              scroll={{ y: 'calc(100vh - 490px)' }}
              dataSource={dataSource}
              columns={columns}
              rowKey="instance_id"
              loading={loading}
              pagination={false}
              rowSelection={rowSelection}
            />
          </Form.Item>
        </div>
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
      <BatchEditModal
        ref={batchEditModalRef}
        onSuccess={handleBatchEditSuccess}
      />
      <ExcelImportModal
        ref={excelImportModalRef}
        onSuccess={handleImportSuccess}
      />
    </div>
  );
};

export default AutomaticConfiguration;
