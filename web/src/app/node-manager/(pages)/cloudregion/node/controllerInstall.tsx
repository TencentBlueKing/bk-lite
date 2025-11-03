'use client';
import React, {
  useEffect,
  useState,
  useRef,
  useCallback,
  useMemo,
} from 'react';
import {
  Button,
  Form,
  Select,
  Input,
  Segmented,
  message,
  InputNumber,
} from 'antd';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import { ModalRef, TableDataItem } from '@/app/node-manager/types';
import {
  ControllerInstallFields,
  ControllerInstallProps,
} from '@/app/node-manager/types/cloudregion';
import controllerInstallSyle from './index.module.scss';
import { useSearchParams } from 'next/navigation';
import { OPERATE_SYSTEMS } from '@/app/node-manager/constants/cloudregion';
import CustomTable from '@/components/custom-table';
import BatchEditModal from './batchEditModal';
import {
  EditOutlined,
  PlusCircleOutlined,
  MinusCircleOutlined,
  ArrowLeftOutlined,
} from '@ant-design/icons';
import { cloneDeep, isNumber, uniqueId } from 'lodash';
import { useAuth } from '@/context/auth';
import axios from 'axios';
import useNodeManagerApi from '@/app/node-manager/api';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';
import { useInstallWays } from '@/app/node-manager/hooks/node';
import ControllerTable from './controllerTable';
import ManualInstallFormItems from './manualInstall';
import { useUserInfoContext } from '@/context/userInfo';

const ControllerInstall: React.FC<ControllerInstallProps> = ({
  cancel,
  config,
}) => {
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const commonContext = useUserInfoContext();
  const authContext = useAuth();
  const token = authContext?.token || null;
  const INFO_ITEM = {
    ip: null,
    organizations: [commonContext.selectedGroup?.id],
    port: 22,
    username: 'root',
    password: null,
    node_name: null,
  };
  const { getPackages, installController, getInstallCommand } =
    useNodeManagerApi();
  const cloudId = useCloudId();
  const searchParams = useSearchParams();
  const [form] = Form.useForm();
  const installWays = useInstallWays();
  const name = searchParams.get('name') || '';
  const groupList = (commonContext?.groups || []).map((item) => ({
    label: item.name,
    value: item.id,
  }));
  const instRef = useRef<ModalRef>(null);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [versionLoading, setVersionLoading] = useState<boolean>(false);
  const [installMethod, setInstallMethod] = useState<string>('remoteInstall');
  const [os, setOs] = useState<string>('linux');
  const [showInstallTable, setShowInstallTable] = useState<boolean>(false);
  const [taskId, setTaskId] = useState<number | null>(null);
  const [sidecarVersionList, setSidecarVersionList] = useState<TableDataItem[]>(
    []
  );
  const [tableData, setTableData] = useState<TableDataItem[]>([
    {
      ...cloneDeep(INFO_ITEM),
      id: '0',
    },
  ]);
  const [sidecarPackageLoading, setSidecarPackageLoading] =
    useState<boolean>(false);
  const [loadingCommand, setLoadingCommand] = useState<boolean>(false);
  const [script, setScript] = useState<string>('');
  const formValues = Form.useWatch([], form);

  const manualFormReady = useMemo(() => {
    if (installMethod !== 'manualInstall') return false;
    return !!(
      formValues?.manual_node_name &&
      formValues?.manual_ip &&
      formValues?.manual_organizations?.length
    );
  }, [formValues, installMethod]);

  const tableColumns = useMemo(() => {
    const columns: any = [
      {
        title: t('node-manager.cloudregion.node.ipAdrress'),
        dataIndex: 'ip',
        width: 100,
        key: 'ip',
        render: (value: string, row: TableDataItem) => {
          return (
            <Input
              defaultValue={row.ip}
              value={row.ip}
              placeholder={t('common.inputMsg')}
              onChange={(e) => handleInputChange(e, row, 'ip')}
            />
          );
        },
      },
      {
        title: t('node-manager.cloudregion.node.nodeName'),
        dataIndex: 'node_name',
        width: 100,
        key: 'node_name',
        render: (value: string, row: TableDataItem) => {
          return (
            <Input
              defaultValue={row.node_name}
              value={row.node_name}
              placeholder={t('common.inputMsg')}
              onChange={(e) => handleInputChange(e, row, 'node_name')}
            />
          );
        },
      },
      {
        title: (
          <>
            {t('node-manager.cloudregion.node.organaziton')}
            <EditOutlined
              className="cursor-pointer ml-[10px] text-[var(--color-primary)]"
              onClick={() => batchEditModal('organizations')}
            />
          </>
        ),
        dataIndex: 'organizations',
        width: 100,
        key: 'organizations',
        render: (value: string, row: TableDataItem) => {
          return (
            <Select
              mode="multiple"
              maxTagCount="responsive"
              defaultValue={row.organizations}
              value={row.organizations}
              filterOption={(input, option) =>
                (option?.label || '')
                  .toLowerCase()
                  .includes(input.toLowerCase())
              }
              options={groupList}
              onChange={(group) =>
                handleSelectChange(group, row, 'organizations')
              }
            />
          );
        },
      },
      {
        title: (
          <>
            {t('node-manager.cloudregion.node.loginPort')}
            <EditOutlined
              className="cursor-pointer ml-[10px] text-[var(--color-primary)]"
              onClick={() => batchEditModal('port')}
            />
          </>
        ),
        dataIndex: 'port',
        width: 100,
        key: 'port',
        render: (value: string, row: TableDataItem) => {
          return (
            <InputNumber
              className="w-full"
              min={1}
              precision={0}
              value={row.port}
              defaultValue={row.port}
              onChange={(e) => handlePortChange(e, row, 'port')}
            />
          );
        },
      },
      {
        title: (
          <>
            {t('node-manager.cloudregion.node.loginAccount')}
            <EditOutlined
              className="cursor-pointer ml-[10px] text-[var(--color-primary)]"
              onClick={() => batchEditModal('username')}
            />
          </>
        ),
        dataIndex: 'username',
        width: 100,
        key: 'username',
        render: (value: string, row: TableDataItem) => {
          return (
            <Input
              defaultValue={row.username}
              value={row.username}
              onChange={(e) => handleInputChange(e, row, 'username')}
            />
          );
        },
      },
      {
        title: (
          <>
            {t('node-manager.cloudregion.node.loginPassword')}
            <EditOutlined
              className="cursor-pointer ml-[10px] text-[var(--color-primary)]"
              onClick={() => batchEditModal('password')}
            />
          </>
        ),
        dataIndex: 'password',
        width: 100,
        key: 'password',
        render: (value: string, row: TableDataItem) => {
          return (
            <Input.Password
              defaultValue={row.password}
              value={row.password}
              placeholder={t('common.inputMsg')}
              onChange={(e) => handleInputChange(e, row, 'password')}
            />
          );
        },
      },
      {
        title: t('common.actions'),
        dataIndex: 'action',
        width: 60,
        fixed: 'right',
        key: 'action',
        render: (value: string, row: TableDataItem, index: number) => {
          return (
            <>
              <Button
                type="link"
                icon={<PlusCircleOutlined />}
                onClick={() => addInfoItem(row)}
              ></Button>
              {!!index && (
                <Button
                  type="link"
                  icon={<MinusCircleOutlined />}
                  onClick={() => deleteInfoItem(row)}
                ></Button>
              )}
            </>
          );
        },
      },
    ];
    return installMethod === 'remoteInstall'
      ? columns
      : [...columns.slice(0, 3), columns[columns.length - 1]];
  }, [installMethod, tableData]);

  const isRemote = useMemo(() => {
    return installMethod === 'remoteInstall';
  }, [installMethod]);

  useEffect(() => {
    if (os && !isLoading) {
      form.setFieldsValue({
        sidecar_package: null,
        manual_sidecar: null,
      });
      setScript('');
      getSidecarList();
    }
  }, [os, isLoading]);

  useEffect(() => {
    form.resetFields();
    form.setFieldsValue({
      manual_organizations: [commonContext.selectedGroup?.id],
    });
  }, [name]);

  useEffect(() => {
    if (installMethod === 'manualInstall' && formValues) {
      if (
        formValues.manual_node_name &&
        formValues.manual_ip &&
        formValues.manual_organizations?.length &&
        formValues.manual_sidecar
      ) {
        setLoadingCommand(true);
        (async () => {
          try {
            const params = {
              os: os,
              package_name: sidecarVersionList.find(
                (item: TableDataItem) => item.id === formValues.manual_sidecar
              )?.name,
              cloud_region_id: cloudId,
              organizations: formValues.manual_organizations,
              node_name: formValues.manual_node_name,
              ip: formValues.manual_ip,
            };
            const data = await getInstallCommand(params);
            setScript(data);
          } catch (error) {
            console.error('Failed to get install command:', error);
          } finally {
            setLoadingCommand(false);
          }
        })();
      } else {
        setScript('');
      }
    }
  }, [formValues?.manual_sidecar]);

  const validateTableData = useCallback(() => {
    if (
      tableData.every((item) =>
        Object.values(item).every((tex) =>
          isNumber(tex) ? !!tex : !!tex?.length
        )
      )
    ) {
      return Promise.resolve();
    }
    return Promise.reject(new Error(t('common.valueValidate')));
  }, [tableData]);

  const handleBatchEdit = useCallback(
    (row: TableDataItem) => {
      const data = cloneDeep(tableData);
      data.forEach((item) => {
        item[row.field] = row.value;
      });
      setTableData(data);
    },
    [tableData]
  );

  const cancelInstall = useCallback(() => {
    goBack();
  }, []);

  const batchEditModal = (field: string) => {
    instRef.current?.showModal({
      title: t('common.bulkEdit'),
      type: field,
      form: {},
    });
  };

  const changeCollectType = (id: string) => {
    setInstallMethod(id);
    form.setFieldsValue({
      work_node: null,
      sidecar_package: null,
      executor_package: null,
      manual_node_name: null,
      manual_ip: null,
      manual_organizations: [commonContext.selectedGroup?.id],
      manual_sidecar: null,
    });
    setScript('');
    const data = [
      {
        ...cloneDeep(INFO_ITEM),
        id: '0',
      },
    ];
    setTableData(data);
  };

  const addInfoItem = (row: TableDataItem) => {
    const data = cloneDeep(tableData);
    const index = data.findIndex((item) => item.id === row.id);
    data.splice(index + 1, 0, {
      ...cloneDeep(INFO_ITEM),
      id: uniqueId(),
    });
    setTableData(data);
  };

  const deleteInfoItem = (row: TableDataItem) => {
    const data = cloneDeep(tableData);
    const index = data.findIndex((item) => item.id === row.id);
    if (index != -1) {
      data.splice(index, 1);
      setTableData(data);
    }
  };

  const handleInputChange = (
    e: React.ChangeEvent<HTMLInputElement>,
    row: TableDataItem,
    key: string
  ) => {
    const data = cloneDeep(tableData);
    const index = data.findIndex((item) => item.id === row.id);
    if (index !== -1) {
      data[index][key] = e.target.value;
      if (key === 'ip' && e.target.value) {
        data[index].node_name = e.target.value + '-' + cloudId;
      }
      setTableData(data);
    }
  };

  const handlePortChange = (value: number, row: TableDataItem, key: string) => {
    const data = cloneDeep(tableData);
    const index = data.findIndex((item) => item.id === row.id);
    if (index !== -1) {
      data[index][key] = value;
      setTableData(data);
    }
  };

  const handleSelectChange = (
    value: string,
    row: TableDataItem,
    key: string
  ) => {
    const data = cloneDeep(tableData);
    const index = data.findIndex((item) => item.id === row.id);
    if (index !== -1) {
      data[index][key] = value;
      setTableData(data);
    }
  };

  const getSidecarList = async () => {
    setVersionLoading(true);
    try {
      const data = await getPackages({ os: os, object: 'Controller' });
      setSidecarVersionList(data);
      const firstItem = data?.[0]?.id || null;
      form.setFieldsValue({
        manual_sidecar: firstItem,
        sidecar_package: firstItem,
      });
    } finally {
      setVersionLoading(false);
    }
  };

  const goBack = () => {
    cancel();
  };

  const handleCreate = () => {
    setConfirmLoading(false);
    form.validateFields().then((values) => {
      const nodes = tableData.map((item) => ({
        ip: item.ip,
        os: config.os,
        organizations: item.organizations,
        port: item.port,
        username: item.username,
        password: item.password,
        node_name: item.node_name,
      }));
      const params = {
        cloud_region_id: cloudId,
        nodes,
        work_node: name,
        package_id: values.sidecar_package || '',
      };
      create(params);
    });
  };

  const create = async (params: ControllerInstallFields) => {
    try {
      setConfirmLoading(true);
      const data = await installController(params);
      message.success(t('common.operationSuccessful'));
      setTaskId(data.task_id);
      setShowInstallTable(true);
    } catch {
      setTaskId(null);
    } finally {
      setConfirmLoading(false);
    }
  };

  const handleManualSidecarChange = (value: string) => {
    form.setFieldsValue({ manual_sidecar: value });
  };

  const handleManualDownload = async () => {
    const sidecarId = form.getFieldValue('manual_sidecar');
    if (!sidecarId) return;

    try {
      const name = sidecarVersionList.find(
        (item: TableDataItem) => item.id === sidecarId
      )?.name;
      setSidecarPackageLoading(true);
      const response = await axios({
        url: `/api/proxy/node_mgmt/api/package/download/${sidecarId}/`,
        method: 'GET',
        responseType: 'blob', // 确保返回的是二进制数据
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      const blob = response.data;
      const contentDisposition = response.headers['content-disposition'];
      let fileName = `${name}`; // 默认文件名
      if (contentDisposition) {
        const fileNameMatch = contentDisposition.match(/filename="?(.+)"?/);
        if (fileNameMatch && fileNameMatch[1]) {
          fileName = decodeURIComponent(fileNameMatch[1]); // 解码文件名，避免中文乱码
        }
      }
      const mimeType = blob.type || 'application/octet-stream';
      const url = URL.createObjectURL(new Blob([blob], { type: mimeType }));
      const link = document.createElement('a');
      link.href = url;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      message.success(t('common.successfulDownloaded'));
    } catch (error: any) {
      message.error(error + '');
    } finally {
      setSidecarPackageLoading(false);
    }
  };

  return (
    <div className="w-full">
      {showInstallTable ? (
        <ControllerTable
          config={{
            taskId,
            type: 'installController',
            groupList,
          }}
          cancel={cancelInstall}
        ></ControllerTable>
      ) : (
        <div className={controllerInstallSyle.controllerInstall}>
          <div className={controllerInstallSyle.title}>
            <ArrowLeftOutlined
              className="text-[var(--color-primary)] text-[20px] cursor-pointer mr-[10px]"
              onClick={goBack}
            />
            <span>{t('node-manager.cloudregion.node.installController')}</span>
          </div>
          <div className={controllerInstallSyle.form}>
            <Form form={form} name="basic" layout="vertical">
              <Form.Item
                name="os"
                required
                label={t('node-manager.cloudregion.Configuration.system')}
              >
                <Segmented
                  options={OPERATE_SYSTEMS}
                  value={os}
                  onChange={setOs}
                />
              </Form.Item>
              <Form.Item<ControllerInstallFields>
                required
                label={t('node-manager.cloudregion.node.installationMethod')}
              >
                <Form.Item name="install" noStyle>
                  <Segmented
                    options={installWays}
                    value={installMethod}
                    onChange={changeCollectType}
                  />
                </Form.Item>
                <div className={controllerInstallSyle.description}>
                  {t('node-manager.cloudregion.node.installWayDes')}
                </div>
              </Form.Item>
              {isRemote ? (
                <>
                  <Form.Item<ControllerInstallFields>
                    required
                    label={t('node-manager.cloudregion.node.sidecarVersion')}
                  >
                    <Form.Item
                      name="sidecar_package"
                      noStyle
                      rules={[
                        { required: true, message: t('common.required') },
                      ]}
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
                        options={sidecarVersionList.map((item) => ({
                          value: item.id,
                          label: item.version,
                        }))}
                      />
                    </Form.Item>
                    <div className={controllerInstallSyle.description}>
                      {t('node-manager.cloudregion.node.sidecarVersionDes')}
                    </div>
                  </Form.Item>
                  <Form.Item<ControllerInstallFields>
                    name="nodes"
                    label={t('node-manager.cloudregion.node.installInfo')}
                    rules={[{ required: true, validator: validateTableData }]}
                  >
                    <CustomTable
                      rowKey="id"
                      columns={tableColumns}
                      dataSource={tableData}
                    />
                  </Form.Item>
                </>
              ) : (
                <ManualInstallFormItems
                  sidecarVersionList={sidecarVersionList}
                  sidecarPackageLoading={sidecarPackageLoading}
                  loadingCommand={loadingCommand}
                  script={script}
                  groupList={groupList}
                  versionLoading={versionLoading}
                  selectedSidecar={formValues?.manual_sidecar}
                  onSidecarChange={handleManualSidecarChange}
                  onDownload={handleManualDownload}
                  disabled={!manualFormReady}
                />
              )}
            </Form>
          </div>
          <div className={controllerInstallSyle.footer}>
            {isRemote && (
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
            )}
            <Button onClick={goBack}>{t('common.cancel')}</Button>
          </div>
        </div>
      )}
      <BatchEditModal
        ref={instRef}
        config={{
          systemList: OPERATE_SYSTEMS,
          groupList,
        }}
        onSuccess={handleBatchEdit}
      />
    </div>
  );
};

export default ControllerInstall;
