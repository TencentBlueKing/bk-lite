'use client';

import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
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
import { useAssetManageStore } from '@/app/cmdb/store';
import { useUserInfoContext } from '@/context/userInfo';

import {
  CYCLE_OPTIONS,
  NETWORK_DEVICE_OPTIONS,
  createTaskValidationRules,
} from '@/app/cmdb/constants/professCollection';

// 需要IP选择的任务类型
const IP_SELECTION_TASK_TYPES = [
  'snmp',
  'db',
  'host',
  'middleware',
  'protocol',
  'host',
];
const ASSET_ONLY_SELECTION_TASK_TYPES = ['config_file'];
// 需要通用实例选择的任务类型
const COMMON_SELECT_INST_TASK_TYPES = [
  'db',
  'cloud',
  'host',
  'protocol',
  'middleware',
  'config_file',
];
// 需要单实例选择的任务类型
const SINGLE_INSTANCE_SELECT_TASK_TYPES = ['vm', 'k8s', 'cloud'];
// 需要接入点选择的任务类型
const ACCESS_POINT_TASK_TYPES = [
  'snmp',
  'db',
  'host',
  'middleware',
  'protocol',
  'config_file',
  'cloud',
  'vm',
  'ipmi',
];

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
  assetOptionLabel?: string;
  timeoutProps?: {
    min?: number;
    defaultValue?: number;
    addonAfter?: string;
  };
  onClose: () => void;
  onTest?: () => void;
  submitText?: string;
}

export interface BaseTaskRef {
  instOptions: { label: string; value: string;[key: string]: any }[];
  accessPoints: { label: string; value: string;[key: string]: any }[];
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
      assetOptionLabel,
      onClose,
      onTest,
      submitText,
    },
    ref
  ) => {
    const editingId = useAssetManageStore((state) => state.editingId);
    const scan_cycle_type = useAssetManageStore((state) => state.scan_cycle_type);
    const { model_id: modelId, task_type: taskType, target_model_id: targetModelId } = modelItem;
    const instanceModelId = targetModelId || modelId;
    const normalizedTaskType = taskType || nodeId || '';
    const { t } = useTranslation();
    const instanceApi = useInstanceApi();
    const collectApi = useCollectApi();
    const modelApi = useModelApi();
    const form = Form.useFormInstance();
    const fieldRef = useRef<FieldModalRef>(null);
    const commonContext = useCommon();
    const { selectedGroup } = useUserInfoContext();
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
      { label: string; value: string; [key: string]: any }[]
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
    const cleanupStrategyValue = Form.useWatch('cleanupStrategy', form);
    const accessPointId = Form.useWatch('accessPointId', form);
    const organizationValue = Form.useWatch('organization', form);
    const [instPagination, setInstPagination] = useState({
      current: 1,
      pageSize: 10,
      total: 0,
    });
    const dropdownItems = {
      items: NETWORK_DEVICE_OPTIONS,
    };

    const normalizeOrganizationValue = useCallback((value: any): number[] => {
      const values = Array.isArray(value) ? value : value ? [value] : [];
      return values
        .map((item) => Number(item))
        .filter((item) => !Number.isNaN(item));
    }, []);

    const isSameOrganizationValue = (current: number[], next: number[]) => {
      if (current.length !== next.length) {
        return false;
      }
      return current.every((item, index) => item === next[index]);
    };

    const supportsIpSelection = IP_SELECTION_TASK_TYPES.includes(
      normalizedTaskType
    );
    const supportsAssetOnlySelection = ASSET_ONLY_SELECTION_TASK_TYPES.includes(
      normalizedTaskType
    );

    const requiresSingleInstanceSelect = SINGLE_INSTANCE_SELECT_TASK_TYPES.includes(
      normalizedTaskType
    );
    const requiresAccessPointSelect = ACCESS_POINT_TASK_TYPES.includes(
      normalizedTaskType
    );

    const isCommonSelectInstTask = COMMON_SELECT_INST_TASK_TYPES.includes(
      normalizedTaskType
    );
    const isHostTask = normalizedTaskType === 'host';
    const isHostAssetMode = isHostTask && collectionType === 'asset';
    const selectedAccessPoint = accessPoints.find(
      (item: any) => item.value === accessPointId,
    );
    const selectedAccessPointCloudRegion =
      selectedAccessPoint?.origin?.cloud_region;
    const hasSelectedAccessPoint = Boolean(accessPointId);
    const hasSelectedAccessPointCloudRegion = ![undefined, null, ''].includes(
      selectedAccessPointCloudRegion as never,
    );
    const canSelectHostAssets =
      !isHostAssetMode ||
      (hasSelectedAccessPoint && hasSelectedAccessPointCloudRegion);
    const hostAssetSelectTooltip = !isHostAssetMode
      ? undefined
      : !hasSelectedAccessPoint
        ? t('Collection.hostAssetSelectionNeedsProxy')
        : !hasSelectedAccessPointCloudRegion
          ? t('Collection.proxyCloudUnavailable')
          : undefined;

    useEffect(() => {
      const orgArray = normalizeOrganizationValue(organizationValue);
      if (!isSameOrganizationValue(ipRangeOrg, orgArray)) {
        setIpRangeOrg(orgArray);
      }
    }, [organizationValue, ipRangeOrg, normalizeOrganizationValue]);

    useEffect(() => {
      if (editingId || !selectedGroup?.id) {
        return;
      }

      const currentOrganization = normalizeOrganizationValue(
        form.getFieldValue('organization')
      );
      if (currentOrganization.length > 0) {
        return;
      }

      const defaultOrganization = normalizeOrganizationValue(selectedGroup.id);
      if (!defaultOrganization.length) {
        return;
      }

      setIpRangeOrg(defaultOrganization);
      form.setFieldValue('organization', defaultOrganization);
    }, [editingId, form, normalizeOrganizationValue, selectedGroup?.id]);

    const resetInstPagination = () => {
      setInstPagination((prev) => ({
        ...prev,
        current: 1,
        total: 0,
      }));
    };

    const clearAssetSelection = () => {
      setSelectedData([]);
      setDisplaySelectedKeys([]);
      setSelectedKeys([]);
      setSelectedRows([]);
      setInstData([]);
      setInstVisible(false);
      form.setFieldValue('assetInst', []);
      resetInstPagination();
    };

    const clearIpRangeSelection = () => {
      setIpRange([]);
      form.setFieldValue('ipRange', []);
    };

    const getHostCloudQueryList = () => {
      if (!isHostTask || !hasSelectedAccessPointCloudRegion) {
        return [];
      }

      const rawCloudRegion = selectedAccessPointCloudRegion;
      const cloudRegionString = String(rawCloudRegion).trim();

      return [
        {
          field: 'cloud',
          type: 'str=',
          value: cloudRegionString,
        },
      ];
    };

    useEffect(() => {
      if (!supportsAssetOnlySelection) {
        return;
      }
      setCollectionType('asset');
    }, [supportsAssetOnlySelection]);

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

    useEffect(() => {
      if (cleanupStrategyValue === 'after_expiration') {
        const currentDays = form.getFieldValue('cleanupDays');
        if (!currentDays || currentDays === 0) {
          form.setFieldsValue({ cleanupDays: 3 });
        }
      }
    }, [cleanupStrategyValue, form]);

    const fetchInstData = async (modelId: string, page = 1, pageSize = 10) => {
      try {
        if (isHostTask && !hasSelectedAccessPointCloudRegion) {
          setInstData([]);
          resetInstPagination();
          return;
        }

        setInstLoading(true);
        const params: any = {
          model_id: modelId,
          page,
          page_size: pageSize,
        };

        if (isHostTask) {
          params.query_list = getHostCloudQueryList();
        }

        const res = await instanceApi.searchInstances(params);
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
      if (isHostAssetMode && !canSelectHostAssets) {
        return;
      }

      setInstVisible(true);
      if (isCommonSelectInstTask) {
        fetchInstData(instanceModelId);
      }
    };

    const handleCollectionTypeChange = (nextType: 'ip' | 'asset') => {
      if (nextType === collectionType) {
        return;
      }

      if (nextType === 'ip') {
        clearAssetSelection();
      } else {
        clearIpRangeSelection();
      }

      setCollectionType(nextType);
    };

    const handleAccessPointChange = (value: string) => {
      if (isHostAssetMode && accessPointId !== value) {
        clearAssetSelection();
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
            danger
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
        if (requiresSingleInstanceSelect) {
          const selectedIds = (await fetchSelectedInstances()) || [];
          setSelectedInstIds(selectedIds);
          fetchOptions(selectedIds);
        }

        if (requiresAccessPointSelect) {
          fetchAccessPoints();
        }
      };
      init();
    }, [requiresSingleInstanceSelect, requiresAccessPointSelect]);

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
          model_id: instanceModelId,
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
          page_size: 10000,
          name: '',
        });
        setAccessPoints(
          res.nodes
            ?.filter((node: any) => node?.node_type === 'container')
            .map((node: any) => ({
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
        // API 返回扁平数组，需要转换为分组结构
        const groupMap = new Map<string, any[]>();
        (attrList || []).forEach((attr: any) => {
          const groupName = attr.attr_group;
          if (!groupMap.has(groupName)) {
            groupMap.set(groupName, []);
          }
          groupMap.get(groupName)!.push(attr);
        });

        // 转换为 FullInfoGroupItem[] 格式
        const groupedAttrList = Array.from(groupMap.entries()).map(
          ([groupName, attrs], index) => ({
            id: index,
            group_name: groupName,
            attrs,
            order: index,
            is_collapsed: false,
            description: '',
            attrs_count: attrs.length,
            can_move_up: false,
            can_move_down: false,
            can_delete: false,
          })
        );

        fieldRef.current?.showModal({
          type: 'add',
          attrList: groupedAttrList,
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
        setIpRange(value || []);
        form.setFieldValue('ipRange', value || []);
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
          <div>
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
                <div className="flex flex-col gap-3">
                  {/* 每天一次 */}
                  {editingId && scan_cycle_type !== 'cycle' ? (
                    <div
                      className="flex items-center"
                      title={t('Collection.cycleDeprecated')}
                    >
                      <Radio value={CYCLE_OPTIONS.DAILY} disabled={true}>
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
                  ) : null}
                  {/* 每隔几分钟执行一次 */}
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
                  {/* 执行一次 */}
                  {editingId && scan_cycle_type !== 'cycle' ? (
                    <Radio
                      value={CYCLE_OPTIONS.ONCE}
                      disabled={true}
                      title={t('Collection.cycleDeprecated')}
                    >
                      {t('Collection.executeOnce')}
                    </Radio>
                  ) : null}
                </div>
              </Radio.Group>
            </Form.Item>

            {/* 组织 */}
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
                  const orgArray = Array.isArray(value)
                    ? value
                    : value
                      ? [value]
                      : [];
                  setIpRangeOrg(orgArray);
                  form.setFieldValue('organization', orgArray);
                }}
                multiple={true}
              />
            </Form.Item>

            {/* 接入点 */}
            {requiresAccessPointSelect && (
              <Form.Item
                label={t('Collection.accessPoint')}
                name="accessPointId"
                required
                extra={
                  <div className="text-xs leading-5">
                    <span>{t('Collection.accessPointHelp')}</span>
                    <a
                      className="ml-2 text-blue-500 hover:text-blue-600"
                      href="/node-manager/cloudregion"
                      target="_blank"
                      rel="noreferrer"
                    >
                      {t('Collection.accessPointLink')}
                    </a>
                  </div>
                }
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
                  onChange={handleAccessPointChange}
                />
              </Form.Item>
            )}

            {/* 实例选择 */}
            {requiresSingleInstanceSelect && (
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
            {(supportsIpSelection || supportsAssetOnlySelection) && (
              <>
                {supportsIpSelection ? (
                  <Radio.Group
                    value={collectionType}
                    className="ml-8 mb-6"
                    onChange={(e) => handleCollectionTypeChange(e.target.value)}
                  >
                    <Radio value="ip">{t('Collection.chooseIp')}</Radio>
                    <Radio value="asset">
                      {assetOptionLabel || t('Collection.chooseAsset')}
                    </Radio>
                  </Radio.Group>
                ) : null}

                {supportsIpSelection && collectionType === 'ip' ? (
                  <>
                    {/* IP范围 */}
                    <Form.Item
                      label={t('Collection.ipRange')}
                      name="ipRange"
                      required
                      rules={[
                        {
                          required: true,
                          validator: (_, value: string[]) => {
                            const ipReg =
                              /^((2[0-4]\d|25[0-5]|[01]?\d\d?)\.){3}(2[0-4]\d|25[0-5]|[01]?\d\d?)$/;
                            if (
                              !value?.length ||
                              !ipReg.test(value[0]) ||
                              !ipReg.test(value[1])
                            ) {
                              return Promise.reject(
                                new Error(
                                  t('common.inputMsg') +
                                    t('Collection.ipRange'),
                                ),
                              );
                            }

                            const ipToNumber = (ip: string) =>
                              ip
                                .split('.')
                                .reduce(
                                  (acc, curr) => acc * 256 + Number(curr),
                                  0,
                                );

                            if (ipToNumber(value[0]) > ipToNumber(value[1])) {
                              return Promise.reject(
                                new Error(t('Collection.ipRangeOrderInvalid')),
                              );
                            }

                            return Promise.resolve();
                          },
                        },
                      ]}
                    >
                      <IpRangeInput value={ipRange} onChange={onIpChange} />
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
                        {isCommonSelectInstTask ? (
                          <Tooltip title={hostAssetSelectTooltip}>
                            <span>
                              <Button
                                type="primary"
                                onClick={handleOpenDrawer}
                                disabled={
                                  isHostAssetMode && !canSelectHostAssets
                                }
                              >
                                {t('common.select')}
                              </Button>
                            </span>
                          </Tooltip>
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
                forceRender
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
                <Form.Item
                  label={t('Collection.cleanupStrategy')}
                  name="cleanupStrategy"
                  initialValue="no_cleanup"
                >
                  <Radio.Group className="m-2">
                    <Space direction="vertical" className="w-full gap-3">
                      <div>
                        <Radio value="immediately">
                          {t('Collection.immediately')}
                        </Radio>
                        <div className="text-xs text-gray-400 ml-6 mt-1">
                          {t('Collection.immediatelyDesc')}
                        </div>
                        <div className="text-xs text-gray-400 ml-6">
                          {t('Collection.immediatelyTip')}
                        </div>
                      </div>
                      <div>
                        <Radio value="after_expiration">
                          {t('Collection.afterExpiration')}
                        </Radio>
                        {cleanupStrategyValue === 'after_expiration' && (
                          <div className="ml-6 mt-1 flex items-center gap-1">
                            <span className="text-sm text-gray-600 flex-shrink-0">
                              {t('Collection.afterExpirationPrefix')}
                            </span>
                            <Form.Item
                              name="cleanupDays"
                              noStyle
                              initialValue={3}
                              rules={[
                                {
                                  validator: (_rule, value) => {
                                    if (
                                      cleanupStrategyValue ===
                                        'after_expiration' &&
                                      !value
                                    ) {
                                      return Promise.reject(
                                        new Error(t('required')),
                                      );
                                    }
                                    return Promise.resolve();
                                  },
                                },
                              ]}
                            >
                              <InputNumber min={1} max={365} className="w-20" />
                            </Form.Item>
                            <span className="text-sm text-gray-600 flex-shrink-0">
                              {t('Collection.afterExpirationSuffix')}
                            </span>
                          </div>
                        )}
                        <div className="text-xs text-gray-400 ml-6 mt-1">
                          {t('Collection.afterExpirationTip')}
                        </div>
                      </div>
                      <div>
                        <Radio value="no_cleanup">
                          {t('Collection.doNotClean')}
                        </Radio>
                        <div className="text-xs text-gray-400 ml-6 mt-1">
                          {t('Collection.doNotCleanDesc')}
                        </div>
                        <div className="text-xs text-gray-400 ml-6">
                          {t('Collection.doNotCleanTip')}
                        </div>
                      </div>
                    </Space>
                  </Radio.Group>
                </Form.Item>
              </Collapse.Panel>
            </Collapse>
          )}
        </div>

        <div className={`${styles.taskFooter} space-x-4`}>
          {onTest && <Button onClick={onTest}>{t('Collection.test')}</Button>}
          <Button type="primary" htmlType="submit" loading={submitLoading}>
            {submitText || t('Collection.confirm')}
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
            isCommonSelectInstTask
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
                  isCommonSelectInstTask ? modelId : relateType,
                  page,
                  pageSize,
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
