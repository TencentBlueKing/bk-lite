'use client';

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react';
import { Form, Input, Select, message } from 'antd';
import { CloudUploadOutlined } from '@ant-design/icons';
import type { UploadProps } from 'antd';
import { FormInstance } from 'antd/lib';
import { useTranslation } from '@/utils/i18n';
import OperateFormModal from '@/components/operate-form-modal';
import SingleFileUploadPanel from '@/components/single-file-upload-panel';
import { cloneDeep } from 'lodash';
import type {
  NodeManagerCollectorPackageModalFormData,
  NodeManagerCollectorPackageModalRef,
  NodeManagerCollectorPackageModalSuccess,
} from './types';

const { TextArea } = Input;

const initData = {
  name: '',
  system: '',
  cpu_architecture: 'x86_64',
  description: '',
  service_type: '',
  executable_path: '',
  execute_parameters: '',
};

export interface NodeManagerCollectorPackageModalProps
  extends NodeManagerCollectorPackageModalSuccess {
  addCollectorAction: (params: any) => Promise<any>;
  editCollectorAction: (params: any) => Promise<any>;
  uploadPackageAction: (params: any) => Promise<any>;
  getControllerListAction: (params: any) => Promise<any>;
}

const NodeManagerCollectorPackageModal = forwardRef<
  NodeManagerCollectorPackageModalRef,
  NodeManagerCollectorPackageModalProps
>(
  (
    {
      onSuccess,
      addCollectorAction,
      editCollectorAction,
      uploadPackageAction,
      getControllerListAction,
    },
    ref,
  ) => {
    const { t } = useTranslation();
    const formRef = useRef<FormInstance>(null);
    const [form] = Form.useForm();
    const [title, setTitle] = useState<string>('editCollector');
    const [type, setType] = useState<string>('edit');
    const [id, setId] = useState<string>('');
    const [key, setKey] = useState<string>('');
    const [visible, setVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [formData, setFormData] = useState<NodeManagerCollectorPackageModalFormData>(initData);
    const [fileList, setFileList] = useState<any>([]);
    const [tags, setTags] = useState<string[]>([]);
    const [architectureOptions, setArchitectureOptions] = useState<
      Record<string, { label: string; value: string }[]>
    >({
      linux: [{ label: 'x86_64', value: 'x86_64' }],
      windows: [{ label: 'x86_64', value: 'x86_64' }],
    });

    const fetchArchitectureOptions = useCallback(async () => {
      try {
        const response = await getControllerListAction({});
        const controllerList = Array.isArray(response)
          ? response
          : response?.items || response?.results || [];
        const archMap: Record<string, Set<string>> = {};
        controllerList.forEach((item: any) => {
          const os = item.node_operating_system || item.os || 'linux';
          const arch = item.cpu_architecture || 'x86_64';
          if (!archMap[os]) archMap[os] = new Set();
          archMap[os].add(arch);
        });
        const options: Record<string, { label: string; value: string }[]> = {};
        for (const [os, archSet] of Object.entries(archMap)) {
          options[os] = Array.from(archSet).map((arch) => ({
            label: arch === 'arm64' ? 'ARM64' : arch,
            value: arch,
          }));
        }
        if (!options.linux) {
          options.linux = [{ label: 'x86_64', value: 'x86_64' }];
        }
        if (!options.windows) {
          options.windows = [{ label: 'x86_64', value: 'x86_64' }];
        }
        setArchitectureOptions(options);
      } catch {
        // Keep the last-known fallback options if the lookup fails.
      }
    }, [getControllerListAction]);

    useImperativeHandle(ref, () => ({
      showModal: ({ type, form, title, key, appTag }) => {
        void fetchArchitectureOptions();
        const info =
          type === 'add'
            ? { ...cloneDeep(initData), appTag }
            : (cloneDeep(form) as NodeManagerCollectorPackageModalFormData);
        const {
          display_name,
          display_introduction,
          originalTags = [],
          is_pre,
        } = (form || {}) as NodeManagerCollectorPackageModalFormData;
        setKey(key as string);
        setId(form?.id as string);
        setType(type);
        setTitle(title as string);
        setVisible(true);
        info.system = info.os || 'linux';
        info.cpu_architecture = info.cpu_architecture || 'x86_64';
        info.appTag = appTag;
        if (is_pre && type === 'edit') {
          info.name = display_name;
          info.description = display_introduction;
        }
        setFormData(info);
        setTags(originalTags);
      },
    }));

    useEffect(() => {
      formRef.current?.resetFields();
      formRef.current?.setFieldsValue(formData);
    }, [formData]);

    const handleCancel = () => {
      formRef.current?.resetFields();
      setVisible(false);
    };

    const errorCatch = (error: any) => {
      message.error(error.code);
      setConfirmLoading(false);
    };

    const handleObject: Record<string, (param: any) => Promise<any>> = {
      add: addCollectorAction,
      edit: editCollectorAction,
    };

    const handleChange: UploadProps['onChange'] = ({ fileList }) => {
      setFileList(fileList);
    };

    const handleUpload = async () => {
      const file = fileList.length ? fileList[0] : '';
      if (!file) {
        return;
      }
      const params = {
        name: file.name,
        os: formData.system,
        cpu_architecture: formData.cpu_architecture || '',
        type: key,
        object: formData.original_name || formData.name,
        file: file.originFileObj,
      };
      uploadPackageAction(params)
        .then(() => {
          message.success(t('node-manager.packetManage.uploadSuccess'));
          onSuccess('upload');
          setVisible(false);
        })
        .finally(() => {
          setConfirmLoading(false);
        });
    };

    const onSubmit = () => {
      setConfirmLoading(true);
      formRef.current
        ?.validateFields()
        .then((values) => {
          const param: Record<string, any> = {
            id:
              id ||
              `${values.name}_${values.system}_${values.cpu_architecture || 'x86_64'}`,
            name: values.name,
            service_type: formData.service_type || 'exec',
            node_operating_system: values.system,
            cpu_architecture: values.cpu_architecture || 'x86_64',
            introduction: values.description,
            executable_path: values.executable_path || '',
            execute_parameters: values.execute_parameters || '',
            tags,
          };
          if (type === 'edit' && formData.is_pre) {
            param.name = formData.original_name || param.name;
            param.introduction =
              formData.original_introduction || param.introduction;
          }
          if (type === 'add') {
            param.tags = [values.system, formData.appTag];
          }
          if (type !== 'upload') {
            handleObject[type](param)
              .then(() => {
                const msg = type === 'edit' ? 'updateSuccess' : 'addSuccess';
                setConfirmLoading(false);
                setVisible(false);
                message.success(t(`common.${msg}`));
                onSuccess();
              })
              .catch(errorCatch);
          } else {
            void handleUpload();
          }
        })
        .catch(() => {
          setConfirmLoading(false);
        });
    };

    const props: UploadProps = {
      name: 'file',
      multiple: false,
      maxCount: 1,
      fileList,
      onChange: handleChange,
      beforeUpload: () => false,
    };

    const validateUpload = async (_: any, value: any) => {
      if (!value) {
        return Promise.reject(new Error(t('common.inputRequired')));
      }
      return Promise.resolve();
    };

    const normFile = (e: any) => {
      if (Array.isArray(e)) {
        return e;
      }
      return e && e.fileList;
    };

    return (
      <div>
        <OperateFormModal
          title={title}
          open={visible}
          onCancel={handleCancel}
          confirmText={t('common.confirm')}
          cancelText={t('common.cancel')}
          onConfirm={onSubmit}
          confirmLoading={confirmLoading}
        >
          <Form ref={formRef} form={form} initialValues={formData} layout="vertical">
            {['edit', 'add'].includes(type) && (
              <>
                <Form.Item
                  label={t('common.name')}
                  name="name"
                  rules={[{ required: true, message: t('common.inputRequired') }]}
                >
                  <Input
                    placeholder={t('common.inputMsg')}
                    disabled={type === 'edit' && formData.is_pre}
                  />
                </Form.Item>
                <Form.Item
                  label={t('node-manager.cloudregion.Configuration.system')}
                  name="system"
                  rules={[{ required: true, message: t('common.inputRequired') }]}
                >
                  <Select
                    disabled={type !== 'add'}
                    options={[
                      { value: 'linux', label: 'Linux' },
                      { value: 'windows', label: 'Windows' },
                    ]}
                    placeholder={t('common.selectMsg')}
                  />
                </Form.Item>
                <Form.Item
                  label={t('node-manager.cloudregion.Configuration.cpuArchitecture')}
                  name="cpu_architecture"
                  rules={[{ required: true, message: t('common.selectMsg') }]}
                >
                  <Select
                    disabled={type !== 'add'}
                    options={architectureOptions[form.getFieldValue('system') || formData.system || 'linux']}
                    placeholder={t('common.selectMsg')}
                  />
                </Form.Item>
                <Form.Item label={t('common.desc')} name="description">
                  <TextArea rows={4} placeholder={t('common.inputMsg')} />
                </Form.Item>
                <Form.Item
                  label={t('node-manager.packetManage.executablePath')}
                  name="executable_path"
                >
                  <Input placeholder={t('common.inputMsg')} />
                </Form.Item>
                <Form.Item
                  label={t('node-manager.packetManage.executeParameters')}
                  name="execute_parameters"
                >
                  <Input placeholder={t('common.inputMsg')} />
                </Form.Item>
              </>
            )}

            {type === 'upload' && (
              <Form.Item
                label={t('node-manager.packetManage.importFile')}
                name="file"
                valuePropName="fileList"
                getValueFromEvent={normFile}
                rules={[{ validator: validateUpload }]}
              >
                <SingleFileUploadPanel
                  fileList={props.fileList}
                  onChange={props.onChange}
                  beforeUpload={props.beforeUpload}
                  maxCount={props.maxCount}
                  icon={<CloudUploadOutlined />}
                  uploadText={t('node-manager.packetManage.clickUpload')}
                />
              </Form.Item>
            )}
          </Form>
        </OperateFormModal>
      </div>
    );
  },
);

NodeManagerCollectorPackageModal.displayName = 'NodeManagerCollectorPackageModal';

export type { NodeManagerCollectorPackageModalSuccess } from './types';
export type {
  NodeManagerCollectorPackageModalFormData,
  NodeManagerCollectorPackageModalConfig,
  NodeManagerCollectorPackageModalRef,
} from './types';
export default NodeManagerCollectorPackageModal;
