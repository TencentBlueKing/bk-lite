'use client';

import React, {
  useState,
  useEffect,
  useRef,
  forwardRef,
  useImperativeHandle,
} from 'react';
import FieldModal from '@/app/cmdb/(pages)/assetData/list/fieldModal';
import { useInstanceApi, useCollectApi, useModelApi } from '@/app/cmdb/api';
import styles from '../index.module.scss';
import CustomTable from '@/components/custom-table';
import IpRangeInput from '@/app/cmdb/components/ipInput';
import { useCommon } from '@/app/cmdb/context/common';
import { FieldModalRef } from '@/app/cmdb/types/assetManage';
import { useTranslation } from '@/utils/i18n';
import { ModelItem } from '@/app/cmdb/types/autoDiscovery';
import GroupTreeSelector from '@/components/group-tree-select';

import {
  CYCLE_OPTIONS,
  NETWORK_DEVICE_OPTIONS,
  createTaskValidationRules,
} from '@/app/cmdb/constants/professCollection';
import {
  CaretRightOutlined,
  QuestionCircleOutlined,
  PlusOutlined,
  DownOutlined,
} from '@ant-design/icons';
import {
  Form,
  Radio,
  TimePicker,
  InputNumber,
  Space,
  Collapse,
  Tooltip,
  Input,
  Button,
  Select,
  Dropdown,
  Drawer,
} from 'antd';

interface TableItem {
  _id?: string;
  model_id?: string;
  model_name?: string;
}

interface BaseTaskFormProps {
  children?: React.ReactNode;
  nodeId?: string;
  showAdvanced?: boolean;
  modelItem: ModelItem;
  submitLoading?: boolean;
  instPlaceholder?: string;
  timeoutProps?: {
    min?: number;
    defaultValue?: number;
    addonAfter?: string;
  };
  onClose: () => void;
  onTest?: () => void;
}

export interface BaseTaskRef {
  instOptions: { label: string; value: string; [key: string]: any }[];
  accessPoints: { label: string; value: string; [key: string]: any }[];
  selectedData: TableItem[];
  ipRange: string[];
  collectionType: string;
  organization: number[];
  initCollectionType: (value: any, type: string) => void;
}

const BaseTaskForm = forwardRef<BaseTaskRef, BaseTaskFormProps>(
  (
    {
      children,
      showAdvanced = true,
      nodeId,
      submitLoading,
      modelItem,
      timeoutProps = {
        min: 0,
        defaultValue: 600,
        addonAfter: '',
      },
      instPlaceholder,
      onClose,
      onTest,
    },
    ref
  ) => {
    const { model_id: modelId } = modelItem;
    const { t } = useTranslation();
    const instanceApi = useInstanceApi();
    const collectApi = useCollectApi();
    const modelApi = useModelApi();
    const form = Form.useFormInstance();
    const fieldRef = useRef<FieldModalRef>(null);
    const commonContext = useCommon();
    const users = useRef(commonContext?.userList || []);
    const userList = users.current;
    const [instOptLoading, setOptLoading] = useState(false);
    const [instOptions, setOptions] = useState<
      { label: string; value: string }[]
    >([]);
    const [ipRange, setIpRange] = useState<string[]>([]);
    const [collectionType, setCollectionType] = useState('ip');
    const [selectedData, setSelectedData] = useState<TableItem[]>([]);
    const [accessPoints, setAccessPoints] = useState<
      { label: string; value: string }[]
    >([]);
    const [accessPointLoading, setAccessPointLoading] = useState(false);
    const [instVisible, setInstVisible] = useState(false);
    const [relateType, setRelateType] = useState('');
    const [selectedRows, setSelectedRows] = useState<any[]>([]);
    const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([]);
    const [displaySelectedKeys, setDisplaySelectedKeys] = useState<React.Key[]>(
      []
    );
    const [instData, setInstData] = useState<any[]>([]);
    const [instLoading, setInstLoading] = useState(false);
    const [ipRangeOrg, setIpRangeOrg] = useState<number[]>([]);
    const [selectedInstIds, setSelectedInstIds] = useState<number[]>([]);
    const [instPagination, setInstPagination] = useState({
      current: 1,
      pageSize: 10,
      total: 0,
    });
    const dropdownItems = {
      items: NETWORK_DEVICE_OPTIONS,
    };

    const isCommonSelectInstNode = [
      'databases',
      'cloud',
      'host_manage',
    ].includes(nodeId as string);

    const instColumns = [
      {
        title: '实例名',
        dataIndex: 'inst_name',
        key: 'inst_name',
        render: (text: any) => text || '--',
      },
      {
        title: '管理IP',
        dataIndex: 'ip_addr',
        key: 'ip_addr',
        render: (text: any) => text || '--',
      },
    ];

    useEffect(() => {
      if (selectedData.length && instData.length) {
        const selectedInsts = instData.filter((item) =>
          selectedData.some((d) => d._id === item._id)
        );
        setSelectedRows(selectedInsts);
        setSelectedKeys(selectedInsts.map((item) => item._id));
      }
    }, [selectedData, instData]);

    const fetchInstData = async (modelId: string, page = 1, pageSize = 10) => {
      try {
        setInstLoading(true);
        const res = await instanceApi.searchInstances({
          model_id: modelId,
          page,
          page_size: pageSize,
        });
        setInstData(res.insts || []);
        setInstPagination((prev) => ({
          ...prev,
          current: page,
          total: res.count || 0,
        }));
      } catch (error) {
        console.error('Failed to fetch instances:', error);
      } finally {
        setInstLoading(false);
      }
    };

    const handleOpenDrawer = () => {
      setInstVisible(true);
      if (isCommonSelectInstNode) {
        fetchInstData(modelId);
      }
    };

    const handleMenuClick = ({ key }: { key: string }) => {
      setRelateType(key);
      setInstVisible(true);
      fetchInstData(key);
    };

    const handleRowSelect = (
      selectedRowKeys: React.Key[],
      selectedRows: any[]
    ) => {
      setSelectedKeys(selectedRowKeys);
      setSelectedRows(selectedRows);
    };

    const handleDrawerClose = () => {
      setInstVisible(false);
      setSelectedKeys([]);
      setSelectedRows([]);
    };

    const handleDrawerConfirm = () => {
      setInstVisible(false);
      setSelectedData(selectedRows.map((item) => item));
      form.setFieldValue('assetInst', selectedRows);
    };

    const handleDeleteRow = (record: TableItem) => {
      const newSelectedData = selectedData.filter(
        (item: any) => item._id !== record._id
      );
      setSelectedData(newSelectedData);
      form.setFieldValue('assetInst', newSelectedData);
    };

    const handleBatchDelete = () => {
      if (displaySelectedKeys.length === 0) {
        return;
      }
      const newSelectedData = selectedData.filter(
        (item: any) => !displaySelectedKeys.includes(item._id)
      );
      setSelectedData(newSelectedData);
      form.setFieldValue('assetInst', newSelectedData);
      setDisplaySelectedKeys([]);
    };

    const assetColumns = [
      {
        title: t('name'),
        dataIndex: 'inst_name',
        key: 'inst_name',
        render: (text: any, record: any) => record.inst_name || '--',
      },
      {
        title: t('common.actions'),
        key: 'action',
        width: 120,
        render: (_: any, record: TableItem) => (
          <Button
            type="link"
            size="small"
            onClick={() => handleDeleteRow(record)}
          >
            {t('common.delete')}
          </Button>
        ),
      },
    ];

    const rules: any = React.useMemo(
      () => createTaskValidationRules({ t, form }),
      [t, form]
    );

    useEffect(() => {
      const init = async () => {
        const selectedInstIds = await fetchSelectedInstances();
        setSelectedInstIds(selectedInstIds);
        fetchOptions(selectedInstIds);
        fetchAccessPoints();
      };
      init();
    }, []);

    const onIpChange = (value: string[]) => {
      setIpRange(value);
      form.setFieldValue('ipRange', value);
    };

    const fetchSelectedInstances = async () => {
      try {
        const res = await collectApi.getCollectModelInstances({
          task_type: modelItem.task_type,
        });
        return res.map((item: any) => item.id);
      } catch (error) {
        console.error('获取已选择实例失败:', error);
      }
    };

    const fetchOptions = async (instIds: number[] = []) => {
      try {
        setOptLoading(true);
        const data = await instanceApi.searchInstances({
          model_id: modelId,
          page: 1,
          page_size: 10000,
        });
        const currentInstId = form.getFieldValue('instId');
        setOptions(
          data.insts.map((item: any) => ({
            label: item.inst_name,
            value: item._id,
            origin: item,
            disabled: (instIds.length ? instIds : selectedInstIds)
              .filter((id) => id !== currentInstId)
              .includes(item._id),
          }))
        );
      } catch (error) {
        console.error('Failed to fetch inst:', error);
      } finally {
        setOptLoading(false);
      }
    };

    const fetchAccessPoints = async () => {
      try {
        setAccessPointLoading(true);
        const res = await collectApi.getCollectNodes({
          page: 1,
          page_size: 10,
          name: '',
        });
        setAccessPoints(
          res.nodes?.map((node: any) => ({
            label: node.name,
            value: node.id,
            origin: node,
          })) || []
        );
      } catch (error) {
        console.error('获取接入点失败:', error);
      } finally {
        setAccessPointLoading(false);
      }
    };

    const showFieldModal = async () => {
      try {
        const attrList = await modelApi.getModelAttrList(modelId);
        fieldRef.current?.showModal({
          type: 'add',
          attrList,
          formInfo: {},
          subTitle: '',
          title: t('common.addNew'),
          model_id: modelId,
          list: [],
        });
      } catch (error) {
        console.error('Failed to get attr list:', error);
      }
    };

    const initCollectionType = (value: any, type: string) => {
      if (type === 'ip') {
        setIpRange(ipRange);
      } else {
        setSelectedData(value || []);
        form.setFieldValue('assetInst', value || []);
      }
      setCollectionType(type);
    };

    useImperativeHandle(ref, () => ({
      instOptions,
      accessPoints,
      selectedData,
      collectionType,
      ipRange: ipRange,
      organization: ipRangeOrg,
      initCollectionType: (value: any, type: string) =>
        initCollectionType(value, type),
    }));

    return (
      <>
        <div className={styles.mainContent}>
          <div className={styles.sectionTitle}>
            {t('Collection.baseSetting')}
          </div>
          <div className="mr-4">
            <Form.Item
              name="taskName"
              label={t('Collection.taskNameLabel')}
              rules={rules.taskName}
            >
              <Input placeholder={t('common.inputTip')} />
            </Form.Item>

            {/* 扫描周期 */}
            <Form.Item
              label={t('Collection.cycle')}
              name="cycle"
              rules={rules.cycle}
            >
              <Radio.Group>
                <div className="space-y-3">
                  <div className="flex items-center">
                    <Radio value={CYCLE_OPTIONS.DAILY}>
                      {t('Collection.dailyAt')}
                      <Form.Item
                        name="dailyTime"
                        noStyle
                        dependencies={['cycle']}
                        rules={rules.dailyTime}
                      >
                        <TimePicker
                          className="w-40 ml-2"
                          format="HH:mm"
                          placeholder={t('common.selectTip')}
                        />
                      </Form.Item>
                    </Radio>
                  </div>
                  <div className="flex items-center">
                    <Radio value={CYCLE_OPTIONS.INTERVAL}>
                      <Space>
                        {t('Collection.everyMinute')}
                        <Form.Item
                          name="intervalValue"
                          noStyle
                          dependencies={['cycle']}
                          rules={rules.intervalValue}
                        >
                          <InputNumber
                            className="w-20"
                            min={5}
                            placeholder={t('common.inputTip')}
                          />
                        </Form.Item>
                        {t('Collection.executeInterval')}
                      </Space>
                    </Radio>
                  </div>
                  <Radio value={CYCLE_OPTIONS.ONCE}>
                    {t('Collection.executeOnce')}
                  </Radio>
                </div>
              </Radio.Group>
            </Form.Item>

            {/* 实例选择 */}
            {['vmware', 'k8s', 'cloud'].includes(nodeId as string) && (
              <Form.Item label={instPlaceholder} required>
                <Space>
                  <Form.Item name="instId" rules={rules.instId} noStyle>
                    <Select
                      style={{ width: '400px' }}
                      placeholder={t('common.selectTip')}
                      options={instOptions}
                      loading={instOptLoading}
                      showSearch
                      filterOption={(input, option) =>
                        (option?.label ?? '')
                          .toLowerCase()
                          .includes(input.toLowerCase())
                      }
                    />
                  </Form.Item>
                  <Button
                    type="default"
                    icon={<PlusOutlined />}
                    onClick={showFieldModal}
                  />
                </Space>
              </Form.Item>
            )}

            {/* ip选择 */}
            {nodeId &&
              ['network_topo', 'network', 'databases', 'host_manage'].includes(
                nodeId
              ) && (
              <>
                {(
                  <Radio.Group
                    value={collectionType}
                    className="ml-8 mb-6"
                    onChange={(e) => setCollectionType(e.target.value)}
                  >
                    <Radio value="ip">{t('Collection.chooseIp')}</Radio>
                    <Radio value="asset">{t('Collection.chooseAsset')}</Radio>
                  </Radio.Group>
                )}

                {collectionType === 'ip' ? (
                  <>
                    {/* IP范围 */}
                    <Form.Item
                      label={t('Collection.ipRange')}
                      name="ipRange"
                      required
                      rules={[
                        {
                          required: true,
                          message:
                              t('common.inputMsg') + t('Collection.ipRange'),
                        },
                      ]}
                    >
                      <IpRangeInput value={ipRange} onChange={onIpChange} />
                    </Form.Item>
                    <Form.Item
                      label={t('organization')}
                      name="organization"
                      rules={[
                        {
                          required: true,
                          message: t('common.inputMsg') + t('organization'),
                        },
                      ]}
                    >
                      <GroupTreeSelector
                        placeholder={t('common.selectTip')}
                        value={ipRangeOrg}
                        onChange={(value) => {
                          const orgArray = Array.isArray(value) ? value : (value ? [value] : []);
                          setIpRangeOrg(orgArray);
                        }}
                        multiple={false}
                      />
                    </Form.Item>
                  </>
                ) : (
                /* 选择资产 */
                  <Form.Item
                    name="assetInst"
                    label={instPlaceholder}
                    required
                    rules={rules.assetInst}
                    trigger="onChange"
                  >
                    <div>
                      <Space>
                        {isCommonSelectInstNode ? (
                          <Button type="primary" onClick={handleOpenDrawer}>
                            {t('common.select')}
                          </Button>
                        ) : (
                          <Dropdown
                            menu={{
                              ...dropdownItems,
                              onClick: handleMenuClick,
                            }}
                          >
                            <Button type="primary">
                              {t('common.select')} <DownOutlined />
                            </Button>
                          </Dropdown>
                        )}
                        <Button
                          onClick={handleBatchDelete}
                          disabled={displaySelectedKeys.length === 0}
                        >
                          {t('common.batchDelete')}
                        </Button>
                      </Space>
                      <CustomTable
                        columns={assetColumns}
                        dataSource={selectedData}
                        pagination={false}
                        className="mt-4"
                        size="middle"
                        rowKey="_id"
                        rowSelection={{
                          selectedRowKeys: displaySelectedKeys,
                          onChange: (selectedRowKeys) => {
                            setDisplaySelectedKeys(selectedRowKeys);
                          },
                        }}
                      />
                    </div>
                  </Form.Item>
                )}
              </>
            )}
            {/* 接入点 */}
            {nodeId !== 'k8s' && (
              <Form.Item
                label={t('Collection.accessPoint')}
                name="accessPointId"
                required
                rules={[
                  {
                    required: true,
                    message: t('required'),
                  },
                ]}
              >
                <Select
                  placeholder={t('common.selectTip')}
                  options={accessPoints}
                  loading={accessPointLoading}
                />
              </Form.Item>
            )}
          </div>
          {children}

          {showAdvanced && (
            <Collapse
              ghost
              expandIcon={({ isActive }) => (
                <CaretRightOutlined
                  rotate={isActive ? 90 : 0}
                  className="text-base"
                />
              )}
            >
              <Collapse.Panel
                header={
                  <div className={styles.panelHeader}>
                    {t('Collection.advanced')}
                  </div>
                }
                key="advanced"
              >
                <Form.Item
                  label={
                    <span>
                      {t('Collection.timeout')}
                      <Tooltip title={t('Collection.timeoutTooltip')}>
                        <QuestionCircleOutlined className="ml-1 text-gray-400" />
                      </Tooltip>
                    </span>
                  }
                  name="timeout"
                  rules={rules.timeout}
                >
                  <InputNumber
                    className="w-40"
                    min={timeoutProps.min}
                    addonAfter={timeoutProps.addonAfter}
                  />
                </Form.Item>
              </Collapse.Panel>
            </Collapse>
          )}
        </div>

        <div className={`${styles.taskFooter} space-x-4`}>
          {onTest && <Button onClick={onTest}>{t('Collection.test')}</Button>}
          <Button type="primary" htmlType="submit" loading={submitLoading}>
            {t('Collection.confirm')}
          </Button>
          <Button onClick={onClose} disabled={submitLoading}>
            {t('Collection.cancel')}
          </Button>
        </div>

        <FieldModal
          ref={fieldRef}
          userList={userList}
          onSuccess={() => fetchOptions()}
        />

        <Drawer
          title={
            isCommonSelectInstNode
              ? t('Collection.chooseAsset')
              : `选择${dropdownItems.items.find((item) => item.key === relateType)?.label || '资产'}`
          }
          width={620}
          open={instVisible}
          onClose={handleDrawerClose}
          footer={
            <div style={{ textAlign: 'left' }}>
              <Space>
                <Button type="primary" onClick={handleDrawerConfirm}>
                  {t('Collection.confirm')}
                </Button>
                <Button onClick={handleDrawerClose}>
                  {t('Collection.cancel')}
                </Button>
              </Space>
            </div>
          }
        >
          <CustomTable
            columns={instColumns}
            dataSource={instData}
            size="middle"
            loading={instLoading}
            rowKey="_id"
            scroll={{ y: 'calc(100vh - 280px)' }}
            pagination={{
              ...instPagination,
              onChange: (page, pageSize) =>
                fetchInstData(
                  isCommonSelectInstNode ? modelId : relateType,
                  page,
                  pageSize
                ),
            }}
            rowSelection={{
              type: 'checkbox',
              selectedRowKeys: selectedKeys,
              onChange: handleRowSelect,
              getCheckboxProps: () => ({
                disabled: false,
              }),
            }}
          />
        </Drawer>
      </>
    );
  }
);

BaseTaskForm.displayName = 'BaseTaskForm';
export default BaseTaskForm;
