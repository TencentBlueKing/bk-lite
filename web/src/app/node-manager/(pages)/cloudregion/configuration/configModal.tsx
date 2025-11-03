'use client';
import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useEffect,
} from 'react';
import { Input, Form, Select, Button, message } from 'antd';
import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import {
  ModalSuccess,
  TableDataItem,
  ModalRef,
} from '@/app/node-manager/types';
import { useTranslation } from '@/utils/i18n';
import useNodeManagerApi from '@/app/node-manager/api';
import {
  VarSourceItem,
  VarResItem,
  ConfigParams,
} from '@/app/node-manager/types/cloudregion';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';
import CodeEditor from '@/app/node-manager/components/codeEditor';
import { useConfigModalColumns } from '@/app/node-manager/hooks/configuration';
import { cloneDeep } from 'lodash';
import { OPERATE_SYSTEMS } from '@/app/node-manager/constants/cloudregion';
const { Option } = Select;

const ConfigModal = forwardRef<ModalRef, ModalSuccess>(
  ({ onSuccess, config: { collectors = [] } }, ref) => {
    const {
      updateCollector,
      createConfig,
      updateChildConfig,
      getVariableList,
    } = useNodeManagerApi();
    const cloudId = useCloudId();
    const { t } = useTranslation();
    const columns = useConfigModalColumns();
    const configFormRef = useRef<FormInstance>(null);
    const [configVisible, setConfigVisible] = useState<boolean>(false);
    const [tableLoading, setTableLoading] = useState<boolean>(false);
    const [configForm, setConfigForm] = useState<TableDataItem>();
    const [editConfigId, setEditConfigId] = useState<string>('');
    const [type, setType] = useState<string>('add');
    const [varDataSource, setvarDataSource] = useState<VarSourceItem[]>([]);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);

    useImperativeHandle(ref, () => ({
      showModal: ({ type, form }) => {
        const _form = cloneDeep(form) as TableDataItem;
        setConfigVisible(true);
        setType(type);
        setEditConfigId(_form?.key);
        setConfigForm(_form);
        initializeVarForm();
      },
    }));

    //初始化表单的数据
    useEffect(() => {
      if (!configVisible) return;
      // 初始化变量列表
      configFormRef.current?.resetFields();
      if (['edit', 'edit_child'].includes(type)) {
        configFormRef.current?.setFieldsValue(configForm);
      }
    }, [configForm, configVisible]);

    const initializeVarForm = async () => {
      try {
        setTableLoading(true);
        const res = await getVariableList({
          cloud_region_id: cloudId,
        });
        const tempdata = res.map((item: VarResItem) => ({
          key: item.id,
          name: item.key,
          description: item.description || '--',
        }));
        setvarDataSource(tempdata);
      } finally {
        setTableLoading(false);
      }
    };

    const handleCancel = () => {
      setConfigVisible(false);
      setTableLoading(false);
    };

    const handleSuccess = () => {
      onSuccess(type);
      setConfirmLoading(false);
      setConfigVisible(false);
    };

    const handleCreateAndUpdate = async (params: ConfigParams) => {
      try {
        setConfirmLoading(true);
        const isAdd = type === 'add';
        await (isAdd
          ? createConfig(params)
          : updateCollector(editConfigId, params));
        handleSuccess();
        message.success(t(`common.${isAdd ? 'addSuccess' : 'updateSuccess'}`));
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleChildUpdate = async (configInfo: string) => {
      try {
        setConfirmLoading(true);
        const isAdd = type === 'add_child';
        const { id, collect_type, config_type, collector_config } =
          configForm as TableDataItem;
        await updateChildConfig(id as string, {
          collect_type,
          config_type,
          collector_config,
          content: configInfo,
        });
        handleSuccess();
        message.success(t(`common.${isAdd ? 'addSuccess' : 'updateSuccess'}`));
      } finally {
        setConfirmLoading(false);
      }
    };

    //处理配置编辑和子配置编辑的确定事件
    const handleConfirm = () => {
      configFormRef.current?.validateFields().then((values) => {
        const { name, collector_id: collector, configInfo } = values;
        if (['edit', 'add'].includes(type)) {
          const params: ConfigParams = {
            name,
            collector_id: collector,
            config_template: configInfo,
          };
          if (type === 'add') {
            params.cloud_region_id = cloudId;
          }
          handleCreateAndUpdate(params);
          return;
        }
        handleChildUpdate(configInfo);
      });
    };

    const ConfigEditorWithParams = ({
      value,
      varDataSource,
      columns,
      onChange,
    }: {
      value: string;
      varDataSource: VarSourceItem[];
      columns: any;
      onChange: any;
    }) => {
      const handleEditorChange = (newValue: string | undefined) => {
        if (newValue !== undefined) {
          onChange(newValue);
        }
      };
      return (
        <div className="flex">
          {/* 左侧输入区域 */}
          <CodeEditor
            value={value}
            onChange={handleEditorChange}
            className="mr-4"
            width="400px"
            height="250px"
            mode="python"
            theme="monokai"
            name="editor"
          />

          {/* 右侧参数说明和表格 */}
          <div className="flex flex-col w-full overflow-hidden">
            {/* 标题和描述 */}
            <h1 className="font-bold flex-shrink-0 text-sm">
              {t('node-manager.cloudregion.Configuration.parameterdes')}
            </h1>
            <p className="flex-shrink-0 text-xs mt-[4px] mb-[10px]">
              {t('node-manager.cloudregion.Configuration.varconfig')}
            </p>
            <CustomTable
              size="small"
              className="w-full"
              scroll={{ y: '160px' }}
              dataSource={varDataSource}
              loading={tableLoading}
              columns={columns}
            />
          </div>
        </div>
      );
    };

    const showConfigForm = () => {
      return (
        <Form ref={configFormRef} layout="vertical" colon={false}>
          {type === 'edit_child' ? (
            <>
              <Form.Item
                name="collect_type"
                label={t(
                  'node-manager.cloudregion.Configuration.collectionType'
                )}
                rules={[
                  {
                    required: true,
                    message: t('common.inputMsg'),
                  },
                ]}
              >
                <Input disabled placeholder={t('common.inputMsg')} />
              </Form.Item>
              <Form.Item
                name="config_type"
                label={t(
                  'node-manager.cloudregion.Configuration.configurationType'
                )}
                rules={[
                  {
                    required: true,
                    message: t('common.inputMsg'),
                  },
                ]}
              >
                <Input disabled placeholder={t('common.inputMsg')} />
              </Form.Item>
            </>
          ) : (
            <>
              <Form.Item
                name="name"
                label={t('common.name')}
                rules={[
                  {
                    required: true,
                    message: t('common.inputMsg'),
                  },
                ]}
              >
                <Input placeholder={t('common.inputMsg')} />
              </Form.Item>
              <Form.Item
                name="operating_system"
                label={t('node-manager.cloudregion.node.system')}
                rules={[
                  {
                    required: true,
                    message: t('common.selectMsg'),
                  },
                ]}
              >
                <Select
                  disabled={type !== 'add'}
                  options={OPERATE_SYSTEMS}
                  placeholder={t('common.selectMsg')}
                  onChange={() =>
                    configFormRef.current?.setFieldsValue({
                      collector_id: null,
                    })
                  }
                />
              </Form.Item>
              <Form.Item
                noStyle
                shouldUpdate={(prevValues, currentValues) =>
                  prevValues.operating_system !== currentValues.operating_system
                }
              >
                {({ getFieldValue }) => {
                  const collectorList = collectors.filter(
                    (item: TableDataItem) =>
                      item.node_operating_system ===
                      getFieldValue('operating_system')
                  );
                  return (
                    <Form.Item
                      name="collector_id"
                      label={t(
                        'node-manager.cloudregion.Configuration.sidecar'
                      )}
                      rules={[
                        {
                          required: true,
                          message: t('common.selectMsg'),
                        },
                      ]}
                    >
                      <Select
                        disabled={type !== 'add'}
                        placeholder={t('common.selectMsg')}
                        showSearch
                      >
                        {collectorList.map((item: TableDataItem) => (
                          <Option key={item.id} value={item.id}>
                            {item.name}
                          </Option>
                        ))}
                      </Select>
                    </Form.Item>
                  );
                }}
              </Form.Item>
            </>
          )}
          <Form.Item
            name="configInfo"
            label={t('node-manager.cloudregion.Configuration.template')}
            rules={[
              {
                required: true,
                message: t('common.inputMsg'),
              },
            ]}
          >
            {
              <ConfigEditorWithParams
                varDataSource={varDataSource}
                columns={columns}
                value={''}
                onChange={undefined}
              ></ConfigEditorWithParams>
            }
          </Form.Item>
        </Form>
      );
    };

    return (
      <OperateModal
        title={t(`${type === 'add' ? 'common.add' : 'common.edit'}`)}
        open={configVisible}
        onCancel={handleCancel}
        width={800}
        zIndex={999999}
        footer={
          <div>
            <Button
              type="primary"
              className="mr-[10px]"
              loading={confirmLoading}
              onClick={handleConfirm}
            >
              {t('common.confirm')}
            </Button>
            <Button onClick={handleCancel}>{t('common.cancel')}</Button>
          </div>
        }
      >
        {showConfigForm()}
      </OperateModal>
    );
  }
);

ConfigModal.displayName = 'ConfigModal';
export default ConfigModal;
