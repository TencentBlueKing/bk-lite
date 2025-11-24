'use client';
import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useMemo,
  useEffect,
} from 'react';
import { Form, Select, message, Button, Popconfirm, Radio, Spin } from 'antd';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ModalSuccess, ModalRef } from '@/app/node-manager/types';
import useNodeManagerApi from '@/app/node-manager/api';
import type { TableDataItem } from '@/app/node-manager/types';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';
import { COLLECTOR_LABEL } from '@/app/node-manager/constants/collector';
const { Option } = Select;

interface Option {
  value: string;
  label: string;
  children?: Option[];
}

const CollectorModal = forwardRef<ModalRef, ModalSuccess>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const {
      getCollectorlist,
      getPackageList,
      installCollector,
      batchOperationCollector,
      getConfiglist,
      applyConfig,
      getNodeStateEnum,
    } = useNodeManagerApi();
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
    const [pageLoading, setPageLoading] = useState<boolean>(false);
    const [system, setSystem] = useState<string>('');
    const [options, setOptions] = useState<Option[]>([]);
    const [typeOptions, setTypeOptions] = useState<any[]>([]);
    const [selectedType, setSelectedType] = useState<string>('');

    useImperativeHandle(ref, () => ({
      showModal: ({ type, ids, selectedsystem }) => {
        setCollectorVisible(true);
        setType(type);
        setSystem(selectedsystem as string);
        setNodeIds(ids || []);
        initTypeOptions(selectedsystem || '');
        type === 'startCollector' && getConfigData();
      },
    }));

    useEffect(() => {
      collectorFormRef.current?.resetFields();
    }, [collectorFormRef]);

    const configs = useMemo(() => {
      return configList.filter((item) => item.collector_id === collector);
    }, [collector]);

    const initTypeOptions = async (selectedsystem: string) => {
      setPageLoading(true);
      try {
        const res = await getNodeStateEnum();
        if (res?.tag) {
          const tagData = res.tag;
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
          collectorFormRef.current?.setFieldsValue({
            type: defaultType,
          });
          if (defaultType) {
            getCollectors(selectedsystem, defaultType);
          }
        }
      } finally {
        setPageLoading(false);
      }
    };

    const getCollectors = async (selectedsystem: string, typeTag?: string) => {
      setCollectorLoading(true);
      const currentType = typeTag || selectedType;
      try {
        const params: any = {
          node_operating_system: selectedsystem,
        };
        if (currentType) {
          params.tags = currentType;
        }
        const data = await getCollectorlist(params);
        const natsexecutorId =
          selectedsystem === 'linux'
            ? 'natsexecutor_linux'
            : 'natsexecutor_windows';
        const options: any = [];
        data?.forEach((item: any) => {
          if (item.id === natsexecutorId) {
            options.push({
              label: 'Controller',
              title: 'Controller',
              options: [
                {
                  label: item.name,
                  value: item.id,
                },
              ],
            });
            return;
          }
          const tag = getCollectorLabelKey(item.name);
          const tagIndex = options.findIndex((item: any) => item.title === tag);
          if (tagIndex >= 0) {
            options[tagIndex].options.push({
              label: item.name,
              value: item.id,
            });
          } else {
            options.push({
              label: tag,
              title: tag,
              options: [
                {
                  label: item.name,
                  value: item.id,
                },
              ],
            });
          }
        });
        setOptions(options);
        setCollectorlist(data);
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
      collectorFormRef.current?.resetFields();
    };

    //点击确定按钮的相关逻辑处理
    const handleConfirm = () => {
      //表单验证
      collectorFormRef.current?.validateFields().then((values) => {
        let request: any = installCollector;
        let params: any = {
          nodes: nodeIds,
          collector_package: values.version,
        };
        switch (type) {
          case 'startCollector':
            params = {
              node_ids: nodeIds,
              collector_id: collector,
              configuration: values.configuration,
              operation: 'start',
            };
            request = batchOperationCollector;
            startCollector(request, params);
            return;
          case 'restartCollector':
            params = {
              node_ids: nodeIds,
              collector_id: collector,
              operation: 'restart',
            };
            request = batchOperationCollector;
            break;
          case 'stopCollector':
            params = {
              node_ids: nodeIds,
              collector_id: collector,
              operation: 'stop',
            };
            request = batchOperationCollector;
            break;
          default:
            break;
        }
        operate(request, params);
      });
    };

    const startCollector = (callback: any, params: any) => {
      const { configuration, ...rest } = params;
      Promise.all([
        operate(callback, rest, !!configuration),
        configuration && handleApply(configuration),
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
        collector_configuration_id: id,
      }));
      await applyConfig(params);
    };

    const operate = async (
      callback: any,
      params: any,
      keepLoading?: boolean
    ) => {
      try {
        setConfirmLoading(true);
        const data = await callback(params);
        const config = {
          taskId: data.task_id || '',
          type,
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

    const handleCollectorChange = async (option: string) => {
      const id = option;
      setCollector(id);
      setPackageList([]);
      collectorFormRef.current?.setFieldsValue({
        version: null,
        configuration: null,
      });
      const object = collectorlist.find(
        (item: TableDataItem) => item.id === id
      )?.name;
      if (type === 'installCollector' && id) {
        try {
          setVersionLoading(true);
          const data = await getPackageList({ object, os: system });
          setPackageList(data);
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
        configuration: null,
      });
      getCollectors(system, value);
    };

    return (
      <OperateModal
        title={t(`node-manager.cloudregion.node.${type}`)}
        open={collectorVisible}
        destroyOnClose
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
                onClick={handleConfirm}
              >
                {t('common.confirm')}
              </Button>
            )}
          </>
        }
      >
        <Spin spinning={pageLoading}>
          <Form ref={collectorFormRef} layout="vertical" colon={false}>
            <Form.Item
              name="type"
              label={t('common.type')}
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
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
            <Form.Item noStyle>
              <Form.Item
                name="collector"
                label={t('node-manager.cloudregion.node.collector')}
                rules={[
                  {
                    required: true,
                    message: t('common.required'),
                  },
                ]}
              >
                <Select
                  showSearch
                  allowClear
                  loading={collectorLoading}
                  options={options}
                  onChange={handleCollectorChange}
                ></Select>
              </Form.Item>
              {type === 'startCollector' && collector?.includes('telegraf') && (
                <div className="text-[12px] text-[var(--color-text-2)]">
                  {t('node-manager.cloudregion.node.telegrafConfigTips')}
                </div>
              )}
            </Form.Item>
            {type === 'startCollector' &&
              collector &&
              !collector.includes('telegraf') && (
              <Form.Item
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
                    label: item.name,
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
                    message: t('common.required'),
                  },
                ]}
              >
                <Select
                  showSearch
                  allowClear
                  loading={versionLoading}
                  placeholder={t('common.selectMsg')}
                  options={packageList.map((item) => ({
                    value: item.id,
                    label: item.version,
                  }))}
                  filterOption={(input, option) =>
                    (option?.label || '')
                      .toLowerCase()
                      .includes(input.toLowerCase())
                  }
                />
              </Form.Item>
            )}
          </Form>
        </Spin>
      </OperateModal>
    );
  }
);
CollectorModal.displayName = 'CollectorModal';
export default CollectorModal;
