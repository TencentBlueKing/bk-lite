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
import {
  IP_RANGE_CYCLE_HINT_THRESHOLD,
  ipRangeSize,
  isIpRangeOrderValid,
  isIpRangeWithinLimit,
} from '@/app/cmdb/components/ipInput/ipRangeLimits';
import { useCmdbUserList } from '@/app/cmdb/context/common';
import { FieldModalRef } from '@/app/cmdb/types/assetManage';
import { useTranslation } from '@/utils/i18n';
import useUnsavedConfirm from '@/hooks/useUnsavedConfirm';
import { ModelItem } from '@/app/cmdb/types/autoDiscovery';
import GroupTreeSelector from '@/components/group-tree-select';
import { useAssetManageStore } from '@/app/cmdb/store';
import { useUserInfoContext } from '@/context/userInfo';
import {
  CmdbInstanceOption,
  toCmdbInstanceOptions,
} from '@/app/cmdb/utils/instanceOption';
import { buildHostCloudQueryList } from '@/app/cmdb/utils/cloudRegion';
import {
  DEFAULT_INST_PAGE_SIZE,
  mergeInstSelection,
  resolveInstFetchModelId,
  resolveInstPaginationChange,
  restoreInstDrawerSelection,
} from './instAssetPicker';

import {
  CYCLE_OPTIONS,
  getNetworkDeviceOptions,
  createTaskValidationRules,
  isSupportedNetworkConfigBrand,
} from '@/app/cmdb/constants/professCollection';
import {
  NETWORK_COLLECTION_ASSET_MODELS,
  findDuplicateNetworkAssetIp,
  mergeNetworkAssetSearchPages,
  mergeVisibleNetworkAssetSelection,
} from '../utils/networkAssetSelection';

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
  'ip', // IP 发现：由接入点直连目标网段执行探测（规格 §13.1）
];
const LONG_TOOLTIP_OVERLAY_STYLE = {
  maxWidth: 'min(520px, calc(100vw - 48px))',
};

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
  Alert,
  Switch,
  message,
} from 'antd';

export type CollectionTargetSource = 'ip' | 'asset' | 'host';
const MAX_HOST_DISCOVERY_TARGETS = 2048;

interface TableItem {
  inst_uuid?: string;
  model_id?: string;
  model_name?: string;
  ip_addr?: string;
  cloud?: number | string;
}

interface BaseTaskFormProps {
  children?: React.ReactNode;
  nodeId?: string;
  showAdvanced?: boolean;
  showTimeout?: boolean;
  showIpPrecheck?: boolean;
  modelItem: ModelItem;
  submitLoading?: boolean;
  instPlaceholder?: string;
  assetOptionLabel?: string;
  timeoutProps?: {
    min?: number;
    max?: number;
    addonAfter?: string;
    tooltip?: React.ReactNode;
  };
  onClose: () => void;
  onTest?: () => void;
  submitText?: string;
  singleInstanceOnly?: boolean;
}

export interface BaseTaskRef {
  instOptions: CmdbInstanceOption[];
  accessPoints: { label: string; value: string;[key: string]: any }[];
  selectedData: TableItem[];
  ipRange: string[];
  collectionType: CollectionTargetSource;
  organization: number[];
  initCollectionType: (value: any, type: string) => void;
}

const BaseTaskForm = forwardRef<BaseTaskRef, BaseTaskFormProps>(
  (
    {
      children,
      showAdvanced = true,
      showTimeout = true,
      showIpPrecheck = true,
      nodeId,
      submitLoading,
      modelItem,
      timeoutProps = {
        max: 86400,
        addonAfter: '',
      },
      instPlaceholder,
      assetOptionLabel,
      onClose,
      onTest,
      submitText,
      singleInstanceOnly = false,
    },
    ref
  ) => {
    const editingId = useAssetManageStore((state) => state.editingId);
    const scan_cycle_type = useAssetManageStore((state) => state.scan_cycle_type);
    const { model_id: modelId, task_type: taskType, target_model_id: targetModelId } = modelItem;
    const isNetworkConfigFileTask = modelId === 'network_config_file';
    const instanceModelId = targetModelId || modelId;
    const previousInstanceModelIdRef = useRef(instanceModelId);
    const normalizedTaskType = taskType || nodeId || '';
    const isNetworkCollectionAssetTask =
      modelId === 'network' && normalizedTaskType === 'snmp';
    const timeoutMin = timeoutProps.min ?? (normalizedTaskType === 'snmp' ? 30 : 1);
    const { t } = useTranslation();
    const guardClose = useUnsavedConfirm();
    const instanceApi = useInstanceApi();
    const collectApi = useCollectApi();
    const modelApi = useModelApi();
    const form = Form.useFormInstance();
    const fieldRef = useRef<FieldModalRef>(null);
    const userList = useCmdbUserList();
    const { selectedGroup } = useUserInfoContext();
    const [instOptLoading, setOptLoading] = useState(false);
    const [instOptions, setOptions] = useState<CmdbInstanceOption[]>([]);
    const [ipRange, setIpRange] = useState<string[]>([]);
    const [collectionType, setCollectionType] = useState<CollectionTargetSource>('ip');
    const [selectedData, setSelectedData] = useState<TableItem[]>([]);
    const [accessPoints, setAccessPoints] = useState<
      { label: string; value: string; [key: string]: any }[]
    >([]);
    const [accessPointLoading, setAccessPointLoading] = useState(false);
    const [instVisible, setInstVisible] = useState(false);
    const [relateType, setRelateType] = useState('');
    const [assetModelIds, setAssetModelIds] = useState<string[]>([
      ...NETWORK_COLLECTION_ASSET_MODELS,
    ]);
    const [selectedRows, setSelectedRows] = useState<any[]>([]);
    const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([]);
    const [displaySelectedKeys, setDisplaySelectedKeys] = useState<React.Key[]>(
      []
    );
    const [instData, setInstData] = useState<any[]>([]);
    const [instLoading, setInstLoading] = useState(false);
    const [ipRangeOrg, setIpRangeOrg] = useState<number[]>([]);
    const [selectedInstUuids, setSelectedInstUuids] = useState<string[]>([]);
    const cleanupStrategyValue = Form.useWatch('cleanupStrategy', form);
    const accessPointId = Form.useWatch('accessPointId', form);
    const organizationValue = Form.useWatch('organization', form);
    const [instPagination, setInstPagination] = useState({
      current: 1,
      pageSize: DEFAULT_INST_PAGE_SIZE,
      total: 0,
    });
    const dropdownItems = {
      items: getNetworkDeviceOptions(t),
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

    const isSslCerTask = modelId === 'ssl_cer';
    const supportsIpSelection =
      !singleInstanceOnly &&
      !isSslCerTask &&
      IP_SELECTION_TASK_TYPES.includes(normalizedTaskType);
    const supportsAssetOnlySelection =
      ASSET_ONLY_SELECTION_TASK_TYPES.includes(normalizedTaskType) ||
      isSslCerTask;

    const requiresSingleInstanceSelect = singleInstanceOnly
      || SINGLE_INSTANCE_SELECT_TASK_TYPES.includes(normalizedTaskType);
    const requiresAccessPointSelect = ACCESS_POINT_TASK_TYPES.includes(
      normalizedTaskType
    );

    const isCommonSelectInstTask = COMMON_SELECT_INST_TASK_TYPES.includes(
      normalizedTaskType
    ) && !isNetworkConfigFileTask;
    const isHostTask = normalizedTaskType === 'host';
    const isHostDiscovery = collectionType === 'host';
    const isHostAssetMode = (isHostTask && collectionType === 'asset') || isHostDiscovery;
    const selectionModelId = isHostDiscovery ? 'host' : instanceModelId;
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
      (hasSelectedAccessPoint && hasSelectedAccessPointCloudRegion &&
        (!isHostDiscovery || normalizeOrganizationValue(organizationValue).length > 0));
    const hostAssetSelectTooltip = !isHostAssetMode
      ? undefined
      : !hasSelectedAccessPoint
        ? t(isHostDiscovery ? 'Collection.hostDiscoveryNeedsProxy' : 'Collection.hostAssetSelectionNeedsProxy')
        : !hasSelectedAccessPointCloudRegion
          ? t('Collection.proxyCloudUnavailable')
          : isHostDiscovery && !normalizeOrganizationValue(organizationValue).length
            ? t('Collection.hostDiscoveryNeedsOrganization')
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
      if ((!isHostTask && !isHostDiscovery) || !hasSelectedAccessPointCloudRegion) {
        return [];
      }
      return buildHostCloudQueryList(selectedAccessPointCloudRegion);
    };

    useEffect(() => {
      if (!supportsAssetOnlySelection) {
        return;
      }
      setCollectionType('asset');
    }, [supportsAssetOnlySelection]);

    const hostCloudColumn = {
      title: t('Collection.hostDiscoveryCloud'), dataIndex: 'cloud', key: 'cloud',
      render: (value: number | string) => String(value ?? '--'),
    };
    const instColumns = [
      ...(isHostDiscovery ? [hostCloudColumn] : []),
      {
        title: t('Collection.instanceName'),
        dataIndex: 'inst_name',
        key: 'inst_name',
        render: (text: any) => text || '--',
      },
      {
        title: t('Collection.manageIp'),
        dataIndex: 'ip_addr',
        key: 'ip_addr',
        render: (text: any) => text || '--',
      },
      ...(isNetworkCollectionAssetTask
        ? [
          {
            title: t('Collection.objectType'),
            dataIndex: 'model_id',
            key: 'model_id',
            render: (modelKey: string) =>
              dropdownItems.items.find((item) => item.key === modelKey)
                ?.label || modelKey || '--',
          },
        ]
        : []),
    ];

    useEffect(() => {
      if (cleanupStrategyValue === 'after_expiration') {
        const currentDays = form.getFieldValue('cleanupDays');
        if (!currentDays || currentDays === 0) {
          form.setFieldsValue({ cleanupDays: 3 });
        }
      }
    }, [cleanupStrategyValue, form]);

    const seedDrawerSelection = () => {
      const restored = restoreInstDrawerSelection(selectedData);
      setSelectedKeys(restored.selectedKeys);
      setSelectedRows(restored.selectedRows);
    };

    const fetchInstData = async (
      fetchModelId: string,
      page = 1,
      pageSize = instPagination.pageSize
    ) => {
      try {
        if ((isHostTask || isHostDiscovery) && !hasSelectedAccessPointCloudRegion) {
          setInstData([]);
          resetInstPagination();
          return;
        }

        setInstLoading(true);
        setInstPagination((prev) => ({
          ...prev,
          current: page,
          pageSize,
        }));
        const params: any = {
          model_id: fetchModelId,
          page,
          page_size: pageSize,
        };

        if (isHostTask || isHostDiscovery) {
          params.query_list = getHostCloudQueryList();
          if (isHostDiscovery) {
            params.query_list.push({ field: 'organization', type: 'list[]', value: normalizeOrganizationValue(organizationValue) });
          }
        }

        const res = await instanceApi.searchInstances(params);
        setInstData(res.insts || []);
        setInstPagination({
          current: page,
          pageSize,
          total: res.count || 0,
        });
      } catch (error) {
        console.error('Failed to fetch instances:', error);
      } finally {
        setInstLoading(false);
      }
    };

    const fetchNetworkInstData = async (
      modelIds: string[],
      page = 1,
      pageSize = 10
    ) => {
      if (!modelIds.length) {
        setInstData([]);
        setInstPagination((prev) => ({
          ...prev,
          current: 1,
          total: 0,
        }));
        return;
      }

      try {
        setInstLoading(true);
        const pages = await Promise.all(
          modelIds.map(async (searchModelId) => {
            const res = await instanceApi.searchInstances({
              model_id: searchModelId,
              page,
              page_size: pageSize,
            });
            return {
              insts: (res.insts || []).map((item: TableItem) => ({
                ...item,
                model_id: item.model_id || searchModelId,
              })),
              count: res.count || 0,
            };
          })
        );
        const merged = mergeNetworkAssetSearchPages(pages);
        setInstData(merged.insts);
        setInstPagination((prev) => ({
          ...prev,
          current: page,
          pageSize,
          total: merged.count,
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

      if (isHostDiscovery) {
        setSelectedRows(selectedData);
        setSelectedKeys(selectedData.map((row) => row.inst_uuid as string));
      } else {
        seedDrawerSelection();
      }
      setInstVisible(true);
      if (isNetworkCollectionAssetTask) {
        fetchNetworkInstData(assetModelIds);
        return;
      }
      if (isCommonSelectInstTask) {
        fetchInstData(selectionModelId, 1, instPagination.pageSize);
      }
    };

    const handleCollectionTypeChange = (nextType: CollectionTargetSource) => {
      if (nextType === collectionType) {
        return;
      }

      clearAssetSelection();
      clearIpRangeSelection();

      setCollectionType(nextType);
    };

    const handleAccessPointChange = (value: string) => {
      if (isHostAssetMode && accessPointId !== value) {
        clearAssetSelection();
        if (isHostDiscovery) message.info(t('Collection.hostDiscoverySelectionReset'));
      }
    };

    const handleMenuClick = ({ key }: { key: string }) => {
      setRelateType(key);
      seedDrawerSelection();
      setInstVisible(true);
      fetchInstData(key, 1, instPagination.pageSize);
    };

    const handleRowSelect = (
      selectedRowKeys: React.Key[],
      checkedRows: TableItem[]
    ) => {
      if (isHostDiscovery) {
        const merged = mergeVisibleNetworkAssetSelection({
          previouslySelected: selectedRows,
          visibleInstUuids: instData.map((row) => row.inst_uuid),
          checkedRows,
        });
        setSelectedKeys(merged.map((row) => row.inst_uuid));
        setSelectedRows(merged);
        return;
      }
      setSelectedKeys(selectedRowKeys);
      setSelectedRows((prev) =>
        mergeInstSelection({
          currentPageRows: instData,
          selectedRowKeys,
          previousSelectedRows: prev,
        })
      );
    };

    const getNetworkConfigDisabledReason = (record: any) => {
      if (isHostDiscovery && !record?.ip_addr) return t('Collection.hostDiscoveryMissingIp');
      if (!isNetworkConfigFileTask) {
        return '';
      }
      if (!record?.brand) {
        return '缺少厂商字段，无法选择';
      }
      if (!isSupportedNetworkConfigBrand(record.brand)) {
        return '暂不支持该厂商';
      }
      return '';
    };

    const handleDrawerClose = () => {
      setInstVisible(false);
      setSelectedKeys([]);
      setSelectedRows([]);
    };

    const handleDrawerConfirm = () => {
      const nextSelected = isNetworkCollectionAssetTask
        ? mergeVisibleNetworkAssetSelection({
          previouslySelected: selectedData,
          visibleInstUuids: instData.map((item) => item.inst_uuid),
          checkedRows: selectedRows,
        })
        : selectedRows.map((item) => item);
      if (isHostDiscovery && nextSelected.length > MAX_HOST_DISCOVERY_TARGETS) {
        message.error(t('Collection.hostDiscoveryLimit'));
        return;
      }
      const duplicateIp = (isNetworkCollectionAssetTask || isHostDiscovery)
        ? findDuplicateNetworkAssetIp(nextSelected)
        : null;
      if (duplicateIp) {
        message.error(
          t(
            'Collection.duplicateManageIp',
            '同一任务中管理 IP 不能重复：{ip}',
            { ip: duplicateIp }
          )
        );
        return;
      }
      setInstVisible(false);
      setSelectedData(nextSelected);
      form.setFieldValue('assetInst', nextSelected);
    };

    const handleDeleteRow = (record: TableItem) => {
      const newSelectedData = selectedData.filter(
        (item) => item.inst_uuid !== record.inst_uuid
      );
      setSelectedData(newSelectedData);
      form.setFieldValue('assetInst', newSelectedData);
    };

    const handleBatchDelete = () => {
      if (displaySelectedKeys.length === 0) {
        return;
      }
      const newSelectedData = selectedData.filter(
        (item) => !displaySelectedKeys.includes(item.inst_uuid)
      );
      setSelectedData(newSelectedData);
      form.setFieldValue('assetInst', newSelectedData);
      setDisplaySelectedKeys([]);
    };

    const assetColumns = [
      ...(isHostDiscovery ? [
        { title: t('Collection.manageIp'), dataIndex: 'ip_addr', key: 'ip_addr' }, hostCloudColumn,
      ] : []),
      {
        title: t('name'),
        dataIndex: 'inst_name',
        key: 'inst_name',
        render: (text: any, record: any) => record.inst_name || '--',
      },
      ...(isNetworkCollectionAssetTask
        ? [
          {
            title: t('Collection.objectType'),
            dataIndex: 'model_id',
            key: 'model_id',
            render: (modelKey: string) =>
              dropdownItems.items.find((item) => item.key === modelKey)
                ?.label || modelKey || '--',
          },
        ]
        : []),
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
      if (previousInstanceModelIdRef.current === instanceModelId) {
        return;
      }
      previousInstanceModelIdRef.current = instanceModelId;
      form.setFieldValue('instUuid', undefined);
      setOptions([]);
      setSelectedInstUuids([]);
    }, [form, instanceModelId]);

    useEffect(() => {
      const init = async () => {
        if (requiresSingleInstanceSelect) {
          const selectedIds = (await fetchSelectedInstances()) || [];
          setSelectedInstUuids(selectedIds);
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

    const fetchOptions = async (instUuids: string[] = []) => {
      try {
        setOptLoading(true);
        const data = await instanceApi.searchInstances({
          model_id: instanceModelId,
          page: 1,
          page_size: 10000,
        });
        const currentInstUuid = form.getFieldValue('instUuid');
        setOptions(
          toCmdbInstanceOptions(data.insts || []).map((option) => ({
            ...option,
            disabled: (instUuids.length ? instUuids : selectedInstUuids)
              .filter((instUuid) => instUuid !== currentInstUuid)
              .includes(option.value),
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
        const attrList = await modelApi.getModelAttrList(instanceModelId);
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
      setCollectionType(type as CollectionTargetSource);
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
                            min={1}
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
                  if (isHostDiscovery && !isSameOrganizationValue(ipRangeOrg, orgArray)) {
                    clearAssetSelection();
                    message.info(t('Collection.hostDiscoverySelectionReset'));
                  }
                  setIpRangeOrg(orgArray);
                  form.setFieldValue('organization', orgArray);
                }}
                multiple={true}
              />
            </Form.Item>

            {/* 接入点 */}
            {requiresAccessPointSelect && (
              <Form.Item
                label={
                  <span>
                    {t('Collection.accessPoint')}
                    <Tooltip
                      overlayStyle={LONG_TOOLTIP_OVERLAY_STYLE}
                      title={
                        <span>
                          {t('Collection.accessPointHelp')}
                          <a
                            className="ml-2 text-blue-500 hover:text-blue-600"
                            href="/node-manager/cloudregion"
                            target="_blank"
                            rel="noreferrer"
                          >
                            {t('Collection.accessPointLink')}
                          </a>
                        </span>
                      }
                    >
                      <QuestionCircleOutlined className="ml-1 cursor-help text-gray-400" />
                    </Tooltip>
                  </span>
                }
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
                  onChange={handleAccessPointChange}
                />
              </Form.Item>
            )}

            {/* 实例选择 */}
            {requiresSingleInstanceSelect && (
              <Form.Item label={instPlaceholder} required>
                <Space>
                  <Form.Item name="instUuid" rules={rules.instUuid} noStyle>
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
                    {modelItem.supports_host_discovery && <Radio value="host">{t('Collection.chooseHost')}</Radio>}
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

                            if (!isIpRangeOrderValid(value[0], value[1])) {
                              return Promise.reject(
                                new Error(t('Collection.ipRangeOrderInvalid')),
                              );
                            }

                            if (!isIpRangeWithinLimit(value[0], value[1])) {
                              return Promise.reject(
                                new Error(t('Collection.ipRangeTooLarge')),
                              );
                            }

                            return Promise.resolve();
                          },
                        },
                      ]}
                    >
                      <IpRangeInput value={ipRange} onChange={onIpChange} />
                    </Form.Item>
                    {ipRangeSize(ipRange?.[0], ipRange?.[1]) >
                      IP_RANGE_CYCLE_HINT_THRESHOLD && (
                      <Form.Item
                        labelCol={{ span: 0 }}
                        wrapperCol={{ span: 24 }}
                        className={styles.ipRangeCycleHintItem}
                      >
                        <Alert
                          type="warning"
                          showIcon
                          className={styles.formFieldHint}
                          message={t('Collection.ipRangeCycleHint')}
                        />
                      </Form.Item>
                    )}
                  </>
                ) : (
                  /* 选择资产 */
                  <Form.Item
                    name="assetInst"
                    label={isHostDiscovery ? t('Collection.chooseHost') : instPlaceholder}
                    extra={isHostDiscovery ? t('Collection.hostDiscoveryTip', '', { plugin: modelItem.name || modelId }) : undefined}
                    required
                    rules={rules.assetInst}
                    trigger="onChange"
                  >
                    <div>
                      <Space>
                        {isCommonSelectInstTask || isNetworkCollectionAssetTask ? (
                          <Tooltip
                            overlayStyle={LONG_TOOLTIP_OVERLAY_STYLE}
                            title={hostAssetSelectTooltip}
                          >
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
                        rowKey="inst_uuid"
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
                {showTimeout && (
                <Form.Item
                  label={
                    <span>
                      {t('Collection.timeout')}
                      <Tooltip title={timeoutProps.tooltip ?? t('Collection.timeoutTooltip')}>
                        <QuestionCircleOutlined className="ml-1 text-gray-400" />
                      </Tooltip>
                    </span>
                  }
                  name="timeout"
                  rules={rules.timeout}
                >
                  <InputNumber
                    className="w-40"
                    min={timeoutMin}
                    max={timeoutProps.max ?? 86400}
                    addonAfter={timeoutProps.addonAfter}
                  />
                </Form.Item>
                )}
                {showIpPrecheck && (
                <Form.Item
                  label={
                    <span>
                      {t('Collection.ipPrecheck')}
                      <Tooltip title={t('Collection.ipPrecheckTooltip')}>
                        <QuestionCircleOutlined className="ml-1 text-gray-400" />
                      </Tooltip>
                    </span>
                  }
                  name="ip_precheck"
                  valuePropName="checked"
                  initialValue={false}
                >
                  <Switch />
                </Form.Item>
                )}
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
          <Button
            onClick={() => guardClose(form.isFieldsTouched(), onClose)}
            disabled={submitLoading}
          >
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
            isHostDiscovery ? t('Collection.chooseHost') : isCommonSelectInstTask || isNetworkCollectionAssetTask
              ? t('Collection.chooseAsset')
              : `选择${dropdownItems.items.find((item) => item.key === relateType)?.label || '资产'}`
          }
          width={620}
          open={instVisible}
          maskClosable={false}
          styles={{
            body: {
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
            },
          }}
          onClose={() => guardClose(selectedRows.length > 0, handleDrawerClose)}
          footer={
            <div style={{ textAlign: 'left' }}>
              <Space>
                <Button type="primary" onClick={handleDrawerConfirm}>
                  {t('Collection.confirm')}
                </Button>
                <Button
                  onClick={() =>
                    guardClose(selectedRows.length > 0, handleDrawerClose)
                  }
                >
                  {t('Collection.cancel')}
                </Button>
              </Space>
            </div>
          }
        >
          {isNetworkCollectionAssetTask ? (
            <div className="mb-4 shrink-0">
              <div className="mb-2 text-sm">
                {t('Collection.selectDeviceModels')}
              </div>
              <Select
                mode="multiple"
                className="w-full"
                allowClear
                placeholder={t('Collection.selectDeviceModelsPlaceholder')}
                value={assetModelIds}
                options={dropdownItems.items.map((item) => ({
                  label: item.label,
                  value: item.key,
                }))}
                onChange={(ids: string[]) => {
                  setAssetModelIds(ids);
                  fetchNetworkInstData(ids, 1, instPagination.pageSize);
                }}
              />
            </div>
          ) : null}
          <div className="min-h-0 h-full flex-1 overflow-hidden">
            <CustomTable
              columns={instColumns}
              dataSource={instData}
              size="middle"
              loading={instLoading}
              rowKey="inst_uuid"
              scroll={{ y: 'calc(100vh - 280px)' }}
              pagination={{
                ...instPagination,
                onChange: (page, pageSize) => {
                  if (isNetworkCollectionAssetTask) {
                    fetchNetworkInstData(assetModelIds, page, pageSize);
                    return;
                  }
                  const next = resolveInstPaginationChange({
                    currentPageSize: instPagination.pageSize,
                    nextPage: page,
                    nextPageSize: pageSize,
                  });
                  fetchInstData(
                    isHostDiscovery
                      ? selectionModelId
                      : resolveInstFetchModelId({
                        isCommonSelectInstTask,
                        instanceModelId,
                        collectionModelId: modelId,
                        relateType,
                      }),
                    next.page,
                    next.pageSize,
                  );
                },
              }}
              rowSelection={{
                type: 'checkbox',
                selectedRowKeys: selectedKeys,
                preserveSelectedRowKeys: true,
                onChange: handleRowSelect,
                getCheckboxProps: (record: any) => ({
                  disabled: Boolean(getNetworkConfigDisabledReason(record)),
                  title: getNetworkConfigDisabledReason(record),
                }),
              }}
            />
          </div>
        </Drawer>
      </>
    );
  }
);

BaseTaskForm.displayName = 'BaseTaskForm';
export default BaseTaskForm;
