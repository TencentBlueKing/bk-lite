'use client';
import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useMemo
} from 'react';
import {
  Form,
  Select,
  message,
  Button,
  Popconfirm,
  Radio,
  Tag,
  Alert
} from 'antd';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ModalSuccess, ModalRef } from '@/app/node-manager/types';
import useNodeManagerApi from '@/app/node-manager/api';
import type { TableDataItem } from '@/app/node-manager/types';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';
import { COLLECTOR_LABEL } from '@/app/node-manager/constants/collector';
import { useCommon } from '@/app/node-manager/context/common';
import { buildCollectorOperationListParams } from '@/app/node-manager/utils/nodeOperation';
import {
  asCollectorPackageList,
  buildCollectorPackageListParams,
  describeCollectorInstallTarget,
  selectCollectorPackageVersions,
  type CollectorPackageVersionOption
} from '@/app/node-manager/utils/collectorPackageSelection';
import {
  EXECUTOR_TYPE_TAG,
  asCollectorCatalogList,
  filterCollectorsForOperationType,
  groupCollectorsForOperationSelect,
  listCollectorUpdateHints,
  mergeCatalogCollectorUpdateHints,
  promotePendingCollectorOptions,
  type CollectorOperationSelectGroup,
  type CollectorUpdateHint
} from '@/app/node-manager/utils/collectorConfig';

const getOptionUpdateTag = (data: unknown) => {
  if (!data || typeof data !== 'object' || !('updateTag' in data)) {
    return undefined;
  }
  const updateTag = (data as { updateTag?: unknown }).updateTag;
  return typeof updateTag === 'string' && updateTag ? updateTag : undefined;
};

const UpdateOptionLabel = ({
  name,
  updateTag
}: {
  name: string;
  updateTag?: string;
}) => (
  <span className="inline-flex max-w-full items-center gap-1">
    <span className="min-w-0 truncate">{name}</span>
    {updateTag ? (
      <Tag className="m-0" color="warning">
        {updateTag}
      </Tag>
    ) : null}
  </span>
);

const CollectorModal = forwardRef<ModalRef, ModalSuccess>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const {
      getCollectorlist,
      getPackageList,
      installCollector,
      batchOperationCollector,
      getConfiglist,
      applyConfig
    } = useNodeManagerApi();
    const commonContext = useCommon();
    const nodeStateEnum = commonContext?.nodeStateEnum || {};
    const cloudId = useCloudId();
    const collectorFormRef = useRef<FormInstance>(null);
    const popcConfirmArr = ['restartCollector'];
    const [type, setType] = useState<string>('installCollector');
    const [nodeIds, setNodeIds] = useState<string[]>(['']);
    const [collectorVisible, setCollectorVisible] = useState<boolean>(false);
    const [packageList, setPackageList] = useState<TableDataItem[]>([]);
    const [collectorlist, setCollectorlist] = useState<TableDataItem[]>([]);
    const [configList, setConfigList] = useState<TableDataItem[]>([]);
    const [versionLoading, setVersionLoading] = useState<boolean>(false);
    const [collectorLoading, setCollectorLoading] = useState<boolean>(false);
    const [configListLoading, setConfigListLoading] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [collector, setCollector] = useState<string | null>(null);
    const [options, setOptions] = useState<CollectorOperationSelectGroup[]>([]);
    const [packageVersionOptions, setPackageVersionOptions] = useState<
      CollectorPackageVersionOption[]
    >([]);
    const [installTargetError, setInstallTargetError] = useState('');
    const installTargetRef = useRef({
      os: '',
      cpuArchitecture: '',
      operationType: 'installCollector'
    });
    const [typeOptions, setTypeOptions] = useState<any[]>([]);
    const [selectedType, setSelectedType] = useState<string>('');
    const [updateHints, setUpdateHints] = useState<CollectorUpdateHint[]>([]);
    const [selectedNodes, setSelectedNodes] = useState<TableDataItem[]>([]);

    const installTargetErrorMessage = (reason: string) => {
      if (reason === 'mixed_operating_system') {
        return t(
          'node-manager.cloudregion.node.collectorOperationMixedOperatingSystem'
        );
      }
      if (reason === 'mixed_cpu_architecture') {
        return t(
          'node-manager.cloudregion.node.collectorOperationMixedCpuArchitecture'
        );
      }
      return t(
        'node-manager.cloudregion.node.collectorOperationUnknownArchitecture'
      );
    };

    useImperativeHandle(ref, () => ({
      showModal: ({
        type,
        ids,
        selectedsystem,
        selectedArchitecture,
        updateHints: nextHints,
        focusCollectorNames,
        selectedNodes: nextNodes
      }) => {
        const nodes = (nextNodes as TableDataItem[]) || [];
        const hints =
          nextHints ||
          listCollectorUpdateHints(nodes, focusCollectorNames || []);
        const target = describeCollectorInstallTarget(nodes, {
          os: selectedsystem,
          cpuArchitecture: selectedArchitecture
        });
        const os = target.ok ? target.os : '';
        const arch = target.ok ? target.cpuArchitecture : '';
        installTargetRef.current = {
          os,
          cpuArchitecture: arch,
          operationType: type
        };
        setCollectorVisible(true);
        setType(type);
        setInstallTargetError(
          target.ok ? '' : installTargetErrorMessage(target.reason)
        );
        setNodeIds(ids || []);
        setSelectedNodes(nodes);
        setUpdateHints(hints);
        setPackageList([]);
        setPackageVersionOptions([]);
        if (target.ok) {
          initTypeOptions(os, arch, type, hints, nodes);
        } else {
          setSelectedType('');
          setTypeOptions([]);
          setOptions([]);
          setCollectorlist([]);
        }
        type === 'startCollectorr' && getConfigData(); //先不调这个接口，因为配置文件已隐藏
      }
    }));

    const configs = useMemo(() => {
      return configList.filter((item) => item.collector_id === collector);
    }, [collector]);

    const selectedCollectorOption = useMemo(
      () =>
        options
          .flatMap((group) => group.options)
          .find((option) => String(option.value) === String(collector || '')),
      [collector, options]
    );

    const initTypeOptions = (
      selectedsystem: string,
      arch?: string,
      operationType?: string,
      hints?: CollectorUpdateHint[],
      nodes?: TableDataItem[]
    ) => {
      if (nodeStateEnum?.tag) {
        const tagData = nodeStateEnum.tag;
        const apps: any[] = [];
        Object.keys(tagData).forEach((key) => {
          const item = tagData[key];
          if (item.is_app) {
            apps.push({ label: item.name, value: key });
          }
        });
        setTypeOptions(apps);
        // 默认选中第一项
        const defaultType = apps.length > 0 ? apps[0].value : '';
        setSelectedType(defaultType);
        if (defaultType) {
          getCollectors(
            selectedsystem,
            defaultType,
            arch,
            operationType,
            hints,
            nodes
          );
        }
      }
    };

    const pendingSelectLabels = {
      updatable: (version: string) =>
        t('node-manager.cloudregion.node.collectorUpgradeable', '', {
          version
        }),
      imported: t('node-manager.cloudregion.node.justImportedCollector')
    };

    const getCollectors = async (
      selectedsystem: string,
      typeTag?: string,
      arch?: string,
      operationType?: string,
      hints?: CollectorUpdateHint[],
      nodes?: TableDataItem[]
    ) => {
      setCollectorLoading(true);
      const activeTarget = installTargetRef.current;
      const currentType = typeTag || selectedType;
      const currentArch =
        arch !== undefined ? arch : activeTarget.cpuArchitecture;
      const operatingSystem = selectedsystem || activeTarget.os;
      const currentHints = hints || updateHints;
      const currentNodes = nodes || selectedNodes;
      try {
        const params = buildCollectorOperationListParams({
          operatingSystem,
          cpuArchitecture: currentArch,
          typeTag: currentType
        });
        const data = await getCollectorlist(params);
        const catalog = asCollectorCatalogList(data);
        const visibleCollectors =
          currentType === EXECUTOR_TYPE_TAG
            ? filterCollectorsForOperationType(catalog, currentType)
            : catalog;
        const currentOperation = operationType || activeTarget.operationType;
        const nextHints = mergeCatalogCollectorUpdateHints(
          currentHints,
          visibleCollectors,
          currentNodes
        );
        setUpdateHints(nextHints);
        const grouped = groupCollectorsForOperationSelect(
          visibleCollectors,
          getCollectorLabelKey,
          currentOperation === 'installCollector'
            ? {
              requirePackage: true,
              missingPackageHint: t(
                'node-manager.cloudregion.node.missingCollectorPackage'
              )
            }
            : undefined
        );
        const nextOptions =
          currentOperation === 'installCollector'
            ? promotePendingCollectorOptions(
              grouped,
              nextHints,
              t('node-manager.cloudregion.node.pendingUpdateCollectors'),
              pendingSelectLabels
            )
            : grouped;
        setOptions(nextOptions);
        setCollectorlist(visibleCollectors);
        if (currentOperation === 'installCollector') {
          const pendingGroup = nextOptions.find(
            (group) =>
              group.title ===
              t('node-manager.cloudregion.node.pendingUpdateCollectors')
          );
          const nextCollector = pendingGroup?.options.find(
            (option) => !option.disabled
          )?.value;
          if (nextCollector) {
            collectorFormRef.current?.setFieldsValue({
              collector: nextCollector
            });
            void handleCollectorChange(
              String(nextCollector),
              visibleCollectors,
              {
                os: operatingSystem,
                cpuArchitecture: currentArch,
                operationType: currentOperation
              }
            );
          }
        }
      } finally {
        setCollectorLoading(false);
      }
    };

    const getConfigData = async () => {
      setConfigListLoading(true);
      try {
        const data = await getConfiglist({ cloud_region_id: cloudId });
        setConfigList(data);
      } finally {
        setConfigListLoading(false);
      }
    };

    //关闭用户的弹窗(取消和确定事件)
    const handleCancel = () => {
      setCollectorVisible(false);
      setVersionLoading(false);
      setCollectorLoading(false);
      setCollector(null);
      setSelectedType('');
      setTypeOptions([]);
      setOptions([]);
      setCollectorlist([]);
      setPackageVersionOptions([]);
      setInstallTargetError('');
      installTargetRef.current = {
        os: '',
        cpuArchitecture: '',
        operationType: 'installCollector'
      };
      setUpdateHints([]);
      setSelectedNodes([]);
      collectorFormRef.current?.resetFields();
    };

    //点击确定按钮的相关逻辑处理
    const handleConfirm = () => {
      //表单验证
      collectorFormRef.current?.validateFields().then((values) => {
        let request: any = installCollector;
        let params: any = {
          nodes: nodeIds,
          collector_package: values.version
        };
        let extraConfig: { collectorId?: string; collectorPackageId?: number } =
          {};

        switch (type) {
          case 'startCollector':
            params = {
              node_ids: nodeIds,
              collector_id: collector,
              configuration: values.configuration,
              operation: 'start'
            };
            extraConfig = { collectorId: collector || undefined };
            request = batchOperationCollector;
            startCollector(request, params, extraConfig);
            return;
          case 'restartCollector':
            params = {
              node_ids: nodeIds,
              collector_id: collector,
              operation: 'restart'
            };
            extraConfig = { collectorId: collector || undefined };
            request = batchOperationCollector;
            break;
          case 'stopCollector':
            params = {
              node_ids: nodeIds,
              collector_id: collector,
              operation: 'stop'
            };
            extraConfig = { collectorId: collector || undefined };
            request = batchOperationCollector;
            break;
          case 'installCollector':
          default:
            extraConfig = {
              collectorId: collector || undefined,
              collectorPackageId: values.version
            };
            break;
        }
        operate(request, params, false, extraConfig);
      });
    };

    const startCollector = (
      callback: any,
      params: any,
      extraConfig?: { collectorId?: string; collectorPackageId?: number }
    ) => {
      const { configuration, ...rest } = params;
      Promise.all([
        operate(callback, rest, !!configuration, extraConfig),
        configuration && handleApply(configuration)
      ])
        .then(() => {
          if (configuration) {
            message.success(t('common.operationSuccessful'));
            handleCancel();
          }
        })
        .finally(() => {
          setConfirmLoading(false);
        });
    };

    const handleApply = async (id: string) => {
      const params = nodeIds.map((item) => ({
        node_id: item,
        collector_configuration_id: id
      }));
      await applyConfig(params);
    };

    const operate = async (
      callback: any,
      params: any,
      keepLoading?: boolean,
      extraConfig?: { collectorId?: string; collectorPackageId?: number }
    ) => {
      try {
        setConfirmLoading(true);
        const data = await callback(params);
        const collectorName =
          collectorlist.find(
            (item: TableDataItem) =>
              item.id === (extraConfig?.collectorId || collector)
          )?.name || '';
        const config = {
          taskId: data.task_id || '',
          type,
          collectorId: extraConfig?.collectorId || collector || '',
          collectorPackageId: extraConfig?.collectorPackageId,
          collectorName
        };
        if (!keepLoading) {
          message.success(t('common.operationSuccessful'));
          handleCancel();
        }
        onSuccess(config);
      } finally {
        setConfirmLoading(!!keepLoading);
      }
    };

    const getCollectorLabelKey = (value: string = '') => {
      for (const key in COLLECTOR_LABEL) {
        if (COLLECTOR_LABEL[key].includes(value)) {
          return key;
        }
      }
    };

    const handleCollectorChange = async (
      option: string,
      collectors: TableDataItem[] = collectorlist,
      target?: {
        os: string;
        cpuArchitecture: string;
        operationType: string;
      }
    ) => {
      const id = option;
      const activeTarget = target || installTargetRef.current;
      setCollector(id);
      setPackageList([]);
      setPackageVersionOptions([]);
      collectorFormRef.current?.setFieldsValue({
        version: null,
        configuration: null
      });
      const object = collectors.find(
        (item: TableDataItem) => item.id === id
      )?.name;
      const packageParams = buildCollectorPackageListParams({
        objectName: object,
        os: activeTarget.os,
        cpuArchitecture: activeTarget.cpuArchitecture
      });
      if (activeTarget.operationType === 'installCollector' && id && packageParams) {
        try {
          setVersionLoading(true);
          const data = await getPackageList(packageParams);
          const selection = selectCollectorPackageVersions(
            asCollectorPackageList(data),
            packageParams.os,
            packageParams.cpu_architecture
          );
          setPackageList(selection.packages as TableDataItem[]);
          setPackageVersionOptions(selection.options);
          if (selection.defaultPackageId !== undefined) {
            collectorFormRef.current?.setFieldsValue({
              version: selection.defaultPackageId
            });
          }
        } finally {
          setVersionLoading(false);
        }
      }
    };

    // 处理类型改变
    const handleTypeChange = (value: string) => {
      setSelectedType(value);
      setCollector(null);
      setOptions([]);
      setCollectorlist([]);
      setPackageList([]);
      collectorFormRef.current?.setFieldsValue({
        collector: null,
        version: null,
        configuration: null
      });
      const target = installTargetRef.current;
      getCollectors(
        target.os,
        value,
        target.cpuArchitecture,
        target.operationType,
        updateHints,
        selectedNodes
      );
    };

    return (
      <OperateModal
        title={t(`node-manager.cloudregion.node.${type}`)}
        open={collectorVisible}
        destroyOnHidden
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        onCancel={handleCancel}
        footer={
          <>
            <Button key="back" onClick={handleCancel}>
              {t('common.cancel')}
            </Button>
            {popcConfirmArr.includes(type) ? (
              <Popconfirm
                title={t(`node-manager.cloudregion.node.${type}`)}
                description={t(`node-manager.cloudregion.node.${type}Info`)}
                okText={t('common.confirm')}
                cancelText={t('common.cancel')}
                onConfirm={handleConfirm}
              >
                <Button type="primary">{t('common.confirm')}</Button>
              </Popconfirm>
            ) : (
              <Button
                type="primary"
                loading={confirmLoading}
                disabled={!!installTargetError}
                onClick={handleConfirm}
              >
                {t('common.confirm')}
              </Button>
            )}
          </>
        }
      >
        {installTargetError ? (
          <Alert showIcon type="error" message={installTargetError} />
        ) : (
        <Form
          ref={collectorFormRef}
          layout="vertical"
          colon={false}
          initialValues={{ type: selectedType }}
        >
          <Form.Item
            name="type"
            label={t('common.type')}
            rules={[
              {
                required: true,
                message: t('common.required')
              }
            ]}
          >
            <Radio.Group onChange={(e) => handleTypeChange(e.target.value)}>
              {typeOptions.map((option) => (
                <Radio key={option.value} value={option.value}>
                  {option.label}
                </Radio>
              ))}
            </Radio.Group>
          </Form.Item>
          <Form.Item
            name="collector"
            label={t('node-manager.cloudregion.node.collector')}
            rules={[
              {
                required: true,
                message: t('common.required')
              }
            ]}
          >
            <Select
              showSearch
              allowClear
              loading={collectorLoading}
              options={options}
              optionFilterProp="label"
              optionRender={(option) => (
                <UpdateOptionLabel
                  name={String(option.data?.label ?? option.label ?? '')}
                  updateTag={getOptionUpdateTag(option.data)}
                />
              )}
              labelRender={(props) => (
                <UpdateOptionLabel
                  name={
                    selectedCollectorOption?.label ||
                    String(props.label ?? props.value ?? '')
                  }
                  updateTag={selectedCollectorOption?.updateTag}
                />
              )}
              onChange={(value) =>
                handleCollectorChange(value ? String(value) : '')
              }
            ></Select>
          </Form.Item>
          {type === 'startCollector' &&
            collector &&
            !collector.includes('telegraf') && (
              <Form.Item
                hidden
                name="configuration"
                label={t('node-manager.cloudregion.node.configuration')}
              >
                <Select
                  showSearch
                  allowClear
                  loading={configListLoading}
                  placeholder={t('common.selectMsg')}
                  filterOption={(input, option) =>
                    (option?.label || '')
                      .toLowerCase()
                      .includes(input.toLowerCase())
                  }
                  options={configs.map((item) => ({
                    value: item.id,
                    label: item.name
                  }))}
                />
              </Form.Item>
          )}
          {type === 'installCollector' && (
            <Form.Item
              name="version"
              label={t('node-manager.cloudregion.node.version')}
              rules={[
                {
                  required: true,
                  message: t('common.required')
                }
              ]}
            >
              <Select
                showSearch
                allowClear
                loading={versionLoading}
                disabled={!packageList.length}
                placeholder={
                  collector && !versionLoading && !packageList.length
                    ? t('node-manager.cloudregion.node.missingCollectorPackage')
                    : t('common.selectMsg')
                }
                options={packageVersionOptions}
                optionFilterProp="label"
              />
            </Form.Item>
          )}
        </Form>
        )}
      </OperateModal>
    );
  }
);
CollectorModal.displayName = 'CollectorModal';
export default CollectorModal;
