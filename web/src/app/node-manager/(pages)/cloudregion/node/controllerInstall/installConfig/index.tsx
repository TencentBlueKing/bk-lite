'use client';
import React, {
  useEffect,
  useState,
  useRef,
  useCallback,
  useMemo,
} from 'react';
import { Button, Form, Select, Segmented } from 'antd';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import { TableDataItem } from '@/app/node-manager/types';
import { ControllerInstallFields } from '@/app/node-manager/types/cloudregion';
import { ManualInstallController } from '@/app/node-manager/types/controller';
import { useSearchParams } from 'next/navigation';
import { OPERATE_SYSTEMS } from '@/app/node-manager/constants/cloudregion';
import CustomTable from '@/components/custom-table';
import BatchEditModal from './batchEditModal';
import ExcelImportModal from './excelImportModal';
import { useTableConfig } from './tableConfig';
import { useTableRenderer } from './tableRenderer';
import { DownOutlined, UploadOutlined } from '@ant-design/icons';
import { Dropdown, Modal } from 'antd';
import type { MenuProps } from 'antd';
import { v4 as uuidv4 } from 'uuid';
import { cloneDeep } from 'lodash';
import useNodeManagerApi from '@/app/node-manager/api';
import useControllerApi from '@/app/node-manager/api/useControllerApi';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';
import { useInstallWays } from '@/app/node-manager/hooks/node';
import { useUserInfoContext } from '@/context/userInfo';
import { message } from 'antd';

interface InstallConfigProps {
  onNext: (data: any) => void;
  cancel: () => void;
}

const InstallConfig: React.FC<InstallConfigProps> = ({ onNext, cancel }) => {
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { installController } = useNodeManagerApi();
  const { manualInstallController } = useControllerApi();
  const commonContext = useUserInfoContext();
  const INFO_ITEM = useMemo(
    () => ({
      key: uuidv4(),
      ip: null,
      organizations: [commonContext.selectedGroup?.id],
      port: 22,
      username: 'root',
      auth_type: 'password',
      password: null,
      node_name: null,
    }),
    [commonContext.selectedGroup?.id]
  );
  const { getPackages } = useNodeManagerApi();
  const cloudId = useCloudId();
  const searchParams = useSearchParams();
  const [form] = Form.useForm();
  const installWays = useInstallWays();
  const name = searchParams.get('name') || '';
  const groupList = (commonContext?.groups || []).map((item) => ({
    label: item.name,
    value: item.id,
  }));
  const batchEditModalRef = useRef<any>(null);
  const excelImportModalRef = useRef<any>(null);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [versionLoading, setVersionLoading] = useState<boolean>(false);
  const [installMethod, setInstallMethod] = useState<string>('remoteInstall');
  const [os, setOs] = useState<string>('linux');
  const [sidecarVersionList, setSidecarVersionList] = useState<TableDataItem[]>(
    []
  );
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const { confirm } = Modal;
  const { renderTableColumn, renderActionColumn } = useTableRenderer();

  useEffect(() => {
    if (tableData.length === 0) {
      setTableData([{ ...INFO_ITEM, key: uuidv4() }]);
    }
  }, [INFO_ITEM]);

  // 获取表格配置
  const tableConfig = useTableConfig(installMethod);

  // 添加行
  const addInfoItem = useCallback(
    (row: TableDataItem) => {
      setTableData((prev) => {
        const data = cloneDeep(prev);
        const index = data.findIndex((item) => item.key === row.key);
        data.splice(index + 1, 0, {
          ...cloneDeep(INFO_ITEM),
          key: uuidv4(),
        });
        return data;
      });
    },
    [INFO_ITEM]
  );

  // 删除行
  const deleteInfoItem = useCallback((row: TableDataItem) => {
    setTableData((prev) => {
      const data = cloneDeep(prev);
      const index = data.findIndex((item) => item.key === row.key);
      if (index !== -1) {
        data.splice(index, 1);
      }
      return data;
    });
  }, []);

  const tableColumns = useMemo(() => {
    const columns = tableConfig.map((columnConfig: any) =>
      renderTableColumn(columnConfig, tableData, setTableData)
    );
    // 添加操作列
    columns.push(renderActionColumn(tableData, addInfoItem, deleteInfoItem));
    return columns;
  }, [
    tableConfig,
    tableData,
    groupList,
    cloudId,
    addInfoItem,
    deleteInfoItem,
    renderTableColumn,
    renderActionColumn,
  ]);

  const isRemote = useMemo(() => {
    return installMethod === 'remoteInstall';
  }, [installMethod]);

  // Windows 系统只支持手动安装
  const availableInstallWays = useMemo(() => {
    if (os === 'windows') {
      return installWays.filter((way) => way.value === 'manualInstall');
    }
    return installWays;
  }, [os, installWays]);

  // 根据选中的操作系统过滤版本列表
  const filteredSidecarVersionList = useMemo(() => {
    if (!os) return sidecarVersionList;
    return sidecarVersionList.filter((item) => item.os === os);
  }, [os, sidecarVersionList]);

  useEffect(() => {
    if (!isLoading) {
      getSidecarList();
    }
  }, [isLoading]);

  useEffect(() => {
    if (os) {
      form.setFieldsValue({
        sidecar_package: null,
      });
      // Windows 系统自动切换到手动安装
      if (os === 'windows') {
        setInstallMethod('manualInstall');
        form.setFieldsValue({
          install: 'manualInstall',
        });
      }
      // 恢复表格到初始状态
      setTableData([{ ...INFO_ITEM, key: uuidv4() }]);
      setSelectedRowKeys([]);
    }
  }, [os, INFO_ITEM]);

  useEffect(() => {
    form.resetFields();
  }, [name]);

  const handleBatchEdit = () => {
    const selectedRows = tableData.filter((item) =>
      selectedRowKeys.includes(item.key as string)
    );
    batchEditModalRef.current?.showModal({
      columns: tableConfig,
      selectedRows,
      groupList,
    });
  };

  const handleBatchEditSuccess = (editedFields: any) => {
    const updatedData = tableData.map((item) => {
      if (selectedRowKeys.includes(item.key as string)) {
        return {
          ...item,
          ...editedFields,
        };
      }
      return item;
    });
    setTableData(updatedData);
  };

  const handleBatchDelete = () => {
    confirm({
      title: t('common.prompt'),
      content: t('node-manager.cloudregion.integrations.batchDeleteConfirm'),
      centered: true,
      onOk() {
        const updatedData = tableData.filter(
          (item) => !selectedRowKeys.includes(item.key as string)
        );
        // 如果删除后为空，保留一条空行
        if (updatedData.length === 0) {
          setTableData([{ ...INFO_ITEM, key: uuidv4() }]);
        } else {
          setTableData(updatedData);
        }
        setSelectedRowKeys([]);
      },
    });
  };

  const handleImport = () => {
    excelImportModalRef.current?.showModal({
      title: t('node-manager.cloudregion.integrations.importData'),
      columns: tableConfig,
      groupList,
    });
  };

  const handleImportSuccess = (importedData: any[]) => {
    const newRows = importedData.map((row) => ({
      ...row,
      key: uuidv4(),
    }));
    setTableData([...tableData, ...newRows]);
  };

  const batchMenuItems: MenuProps['items'] = [
    {
      key: 'batchEdit',
      label: t('common.batchEdit'),
    },
    {
      key: 'batchDelete',
      label: t('common.batchDelete'),
      disabled: selectedRowKeys.length === 1 && tableData.length === 1,
    },
  ];

  const handleBatchMenuClick: MenuProps['onClick'] = (e) => {
    if (e.key === 'batchEdit') {
      handleBatchEdit();
    } else if (e.key === 'batchDelete') {
      handleBatchDelete();
    }
  };

  const validateTableData = (): boolean => {
    if (!tableConfig) return true;
    let hasError = false;
    const newData = [...tableData];
    // 先清除所有字段的错误状态
    newData.forEach((row, index) => {
      tableConfig.forEach((column: any) => {
        const { name } = column;
        newData[index] = {
          ...newData[index],
          [`${name}_error`]: null,
        };
      });
    });
    // 验证所有字段
    tableConfig.forEach((column: any) => {
      const { name, rules = [], required = false } = column;
      tableData.forEach((row, index) => {
        let value = row[name];
        let errorMsg: string | null = null;
        // 特殊处理：如果是password字段且auth_type为private_key，则验证private_key字段
        if (name === 'password' && row['auth_type'] === 'private_key') {
          value = row['private_key'];
        }

        // 如果字段标记为required，进行必填验证
        if (required) {
          if (
            value === undefined ||
            value === null ||
            value === '' ||
            (Array.isArray(value) && value.length === 0)
          ) {
            errorMsg = t('common.required');
          }
        }
        // 如果有rules配置，按照rules验证（只支持pattern类型）
        if (rules.length > 0 && !errorMsg) {
          for (const rule of rules) {
            // 正则验证（只在有值时验证）
            if (rule.type === 'pattern') {
              if (value !== undefined && value !== null && value !== '') {
                const regex = new RegExp(rule.pattern);
                if (!regex.test(String(value))) {
                  errorMsg = rule.message || t('common.required');
                  break;
                }
              }
            }
          }
        }
        if (errorMsg) {
          hasError = true;
          newData[index] = {
            ...newData[index],
            [`${name}_error`]: errorMsg,
          };
        }
      });
    });
    // 更新数据源以显示错误状态
    setTableData(newData);
    if (hasError) {
      return false;
    }
    return true;
  };

  const rowSelection = {
    selectedRowKeys,
    onChange: (newSelectedRowKeys: React.Key[]) => {
      setSelectedRowKeys(newSelectedRowKeys);
    },
  };

  const changeCollectType = (id: string) => {
    setInstallMethod(id);
    setTableData([{ ...INFO_ITEM, key: uuidv4() }]);
    setSelectedRowKeys([]);
  };

  const getSidecarList = async () => {
    setVersionLoading(true);
    try {
      const data = await getPackages({ os: '', object: 'Controller' });
      setSidecarVersionList(data);
    } finally {
      setVersionLoading(false);
    }
  };

  const handleCreate = async () => {
    setConfirmLoading(true);
    try {
      const values = await form.validateFields();
      if (!validateTableData()) {
        setConfirmLoading(false);
        return;
      }
      // 根据安装方式准备不同的节点数据
      const nodes: any[] = [];
      const params: any = {
        cloud_region_id: cloudId,
        work_node: name,
        package_id: values.sidecar_package || '',
      };
      if (isRemote) {
        params.nodes = tableData.map((item) => ({
          ip: item.ip,
          os: os,
          organizations: item.organizations,
          port: item.port,
          username: item.username,
          password: item.private_key ? '' : item.password,
          private_key: item.private_key || '',
          node_name: item.node_name,
        }));
      } else {
        params.nodes = tableData.map((item) => ({
          ip: item.ip,
          organizations: item.organizations,
          node_name: item.node_name,
          node_id: item.key,
        }));
        params.os = os;
      }
      let result;
      let manualTaskList: TableDataItem[] = [];
      if (isRemote) {
        result = (await installController(params)) || {};
      } else {
        const manualParams: ManualInstallController = {
          cloud_region_id: cloudId,
          os: os,
          package_id: values.sidecar_package || '',
          nodes: tableData.map((item) => ({
            ip: item.ip,
            node_name: item.node_name,
            organizations: item.organizations,
            node_id: item.key as string,
          })),
        };
        result = await manualInstallController(manualParams);
        manualTaskList = (result || []).map((item: any) => ({
          ...item,
          os,
        }));
      }
      message.success(t('common.operationSuccessful'));
      onNext({
        taskIds: isRemote
          ? result?.task_id
          : manualTaskList.map((item: TableDataItem) => item.node_id),
        installMethod,
        os,
        nodes,
        manualTaskList, // 手动安装时传递任务列表
        packageId: values.sidecar_package || '',
      });
    } finally {
      setConfirmLoading(false);
    }
  };

  return (
    <div className="w-full min-w-[600px]">
      <Form form={form} name="basic" layout="vertical">
        <Form.Item
          name="os"
          required
          label={t('node-manager.cloudregion.Configuration.system')}
        >
          <Segmented options={OPERATE_SYSTEMS} value={os} onChange={setOs} />
        </Form.Item>
        <Form.Item<ControllerInstallFields>
          required
          label={t('node-manager.cloudregion.node.installationMethod')}
        >
          <Form.Item name="install" noStyle>
            <Segmented
              options={availableInstallWays}
              value={installMethod}
              onChange={changeCollectType}
            />
          </Form.Item>
          <div className="mt-[8px] text-[12px] text-[var(--color-text-3)]">
            {isRemote
              ? t('node-manager.cloudregion.node.installWayDes')
              : t('node-manager.cloudregion.node.autoInstallDes')}
          </div>
        </Form.Item>
        <Form.Item<ControllerInstallFields>
          required
          label={t('node-manager.cloudregion.node.sidecarVersion')}
        >
          <Form.Item
            name="sidecar_package"
            noStyle
            rules={[{ required: true, message: t('common.required') }]}
          >
            <Select
              style={{
                width: 300,
              }}
              showSearch
              allowClear
              placeholder={t('common.pleaseSelect')}
              loading={versionLoading}
              filterOption={(input, option) =>
                (option?.label || '')
                  .toLowerCase()
                  .includes(input.toLowerCase())
              }
              options={filteredSidecarVersionList.map((item) => ({
                value: item.id,
                label: item.version,
              }))}
            />
          </Form.Item>
          <div className="mt-[8px] text-[12px] text-[var(--color-text-3)]">
            {t('node-manager.cloudregion.node.sidecarVersionDes')}
          </div>
        </Form.Item>
        <div className="flex items-center justify-between mb-[10px]">
          <span className="text-[14px]">
            {t('node-manager.cloudregion.node.installInfo')}
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
                onClick: handleBatchMenuClick,
              }}
              disabled={!selectedRowKeys.length}
            >
              <Button>
                {t('node-manager.cloudregion.integrations.batchOperation')}
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
                if (!tableData.length) {
                  return Promise.reject(new Error(t('common.required')));
                }
                return Promise.resolve();
              },
            },
          ]}
        >
          <CustomTable
            rowKey="key"
            scroll={{ x: 'calc(100vw - 320px)' }}
            columns={tableColumns}
            dataSource={tableData}
            rowSelection={rowSelection}
          />
        </Form.Item>
      </Form>
      <div className="mt-[10px] pl-[20px]">
        <Button
          type="primary"
          className="mr-[10px]"
          loading={confirmLoading}
          onClick={handleCreate}
        >
          {`${t('node-manager.cloudregion.node.toInstall')} (${
            tableData.length
          })`}
        </Button>
        <Button onClick={cancel}>{t('common.cancel')}</Button>
      </div>
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

export default InstallConfig;
