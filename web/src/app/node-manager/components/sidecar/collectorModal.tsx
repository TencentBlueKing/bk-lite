import React, {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react';
import {
  ModalRef,
  ModalSuccess,
  TableDataItem,
} from '@/app/node-manager/types';
import { Form, Button, Input, Select, Upload, message } from 'antd';
import { CloudUploadOutlined } from '@ant-design/icons';
import type { UploadProps } from 'antd';
import { FormInstance } from 'antd/lib';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import useApiCollector from '@/app/node-manager/api/collector';
import useApiNode from '@/app/node-manager/api';
import { cloneDeep } from 'lodash';
const { TextArea } = Input;
const { Dragger } = Upload;
const initData = {
  name: '',
  system: '',
  description: '',
  service_type: '',
  executable_path: '',
  execute_parameters: '',
};

const CollectorModal = forwardRef<ModalRef, ModalSuccess>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const { addCollector, editCollecttor } = useApiCollector();
    const { uploadPackage } = useApiNode();
    const formRef = useRef<FormInstance>(null);
    const [form] = Form.useForm();
    const [title, setTitle] = useState<string>('editCollector');
    const [type, setType] = useState<string>('edit');
    const [id, setId] = useState<string>('');
    const [key, setKey] = useState<string>('');
    const [visible, setVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [formData, setFormData] = useState<TableDataItem>(initData);
    const [fileList, setFileList] = useState<any>([]);

    useImperativeHandle(ref, () => ({
      showModal: ({ type, form, title, key }) => {
        const info = cloneDeep(form) as TableDataItem;
        const {
          name,
          tagList,
          description,
          executable_path,
          execute_parameters,
        } = form as TableDataItem;
        setKey(key as string);
        setId(form?.id as string);
        setType(type);
        setTitle(title as string);
        setVisible(true);
        info.name = name || null;
        info.system = tagList?.[0] || 'windows';
        info.description = description || null;
        info.executable_path = executable_path || null;
        info.execute_parameters = execute_parameters || null;
        setFormData(info);
      },
    }));

    useEffect(() => {
      formRef.current?.resetFields();
      formRef.current?.setFieldsValue(formData);
    }, [formRef, formData]);

    const handleCancel = () => {
      formRef.current?.resetFields();
      setVisible(false);
    };

    const errorCatch = (error: any) => {
      message.error(error.code);
      setConfirmLoading(false);
    };

    const handleObject: Record<string, (param: any) => Promise<any>> = {
      add: addCollector,
      edit: editCollecttor,
    };

    const onSubmit = () => {
      setConfirmLoading(true);
      formRef.current
        ?.validateFields()
        .then((values) => {
          const param = {
            id: id || `${values.name}_${values.system}`,
            name: values.name,
            service_type: formData.service_type || 'exec',
            node_operating_system: values.system,
            introduction: values.description,
            executable_path: values.executable_path || '',
            execute_parameters: values.execute_parameters || '',
          };

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
            handleUpload(values);
          }
        })
        .catch(() => {
          setConfirmLoading(false);
        });
    };

    const handleChange: UploadProps['onChange'] = ({ fileList }) => {
      setFileList(fileList);
    };

    const handleUpload = async (values: any) => {
      const file = fileList.length ? fileList[0] : '';
      if (!file) return;
      const fd = new FormData();
      const params = {
        name: file.name,
        os: formData.system,
        type: key,
        version: values.version,
        object: formData.name,
        file: file.originFileObj,
      };
      Object.entries(params).forEach(([k, v]) => {
        fd.append(k, v);
      });
      uploadPackage(params).then(() => {
        setConfirmLoading(false);
        message.success(t('node-manager.packetManage.uploadSuccess'));
        onSuccess('upload');
        setVisible(false);
      });
    };

    const props: UploadProps = {
      name: 'file',
      multiple: false,
      maxCount: 1,
      fileList: fileList,
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
        <OperateModal
          title={title}
          open={visible}
          onCancel={handleCancel}
          footer={
            <div>
              <Button
                type="primary"
                className="mr-[10px]"
                loading={confirmLoading}
                onClick={onSubmit}
              >
                {t('common.confirm')}
              </Button>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </div>
          }
        >
          <Form
            ref={formRef}
            form={form}
            initialValues={formData}
            layout="vertical"
          >
            {['edit', 'add'].includes(type) && (
              <>
                <Form.Item
                  label={t('common.name')}
                  name="name"
                  rules={[
                    { required: true, message: t('common.inputRequired') },
                  ]}
                >
                  <Input placeholder={t('common.inputMsg')} />
                </Form.Item>
                <Form.Item
                  label={t('node-manager.cloudregion.Configuration.system')}
                  name="system"
                  rules={[
                    { required: true, message: t('common.inputRequired') },
                  ]}
                >
                  <Select
                    disabled={type !== 'add'}
                    options={[
                      { value: 'linux', label: 'Linux' },
                      { value: 'windows', label: 'Windows' },
                    ]}
                    placeholder={t('common.selectMsg')}
                  ></Select>
                </Form.Item>
                <Form.Item
                  label={t('node-manager.collector.executeFilePath')}
                  name="executable_path"
                  rules={[
                    { required: true, message: t('common.inputRequired') },
                  ]}
                >
                  <Input placeholder={t('common.inputMsg')} />
                </Form.Item>
                <Form.Item
                  label={t('node-manager.collector.executeParameters')}
                  name="execute_parameters"
                  rules={[
                    { required: true, message: t('common.inputRequired') },
                  ]}
                >
                  <TextArea placeholder={t('common.inputMsg')} />
                </Form.Item>
                <Form.Item
                  label={t(
                    'node-manager.cloudregion.Configuration.description'
                  )}
                  name="description"
                  rules={[
                    { required: true, message: t('common.inputRequired') },
                  ]}
                >
                  <TextArea
                    disabled={type === 'delete'}
                    placeholder={t('common.inputMsg')}
                  />
                </Form.Item>
              </>
            )}
            {type === 'upload' && (
              <>
                <Form.Item
                  label={t('node-manager.packetManage.version')}
                  name="version"
                  rules={[
                    { required: true, message: t('common.inputRequired') },
                  ]}
                >
                  <Input placeholder={t('common.inputMsg')} />
                </Form.Item>
                <Form.Item
                  label={t('node-manager.packetManage.importFile')}
                  name="upload"
                  valuePropName="fileList"
                  getValueFromEvent={normFile}
                  rules={[{ required: true, validator: validateUpload }]}
                >
                  <Dragger {...props}>
                    <p className="ant-upload-drag-icon">
                      <CloudUploadOutlined />
                    </p>
                    <p className="flex justify-center content-center items-center">
                      {t('common.uploadText')}
                      <Button type="link">
                        {t('node-manager.packetManage.clickUpload')}
                      </Button>
                    </p>
                  </Dragger>
                </Form.Item>
              </>
            )}
          </Form>
        </OperateModal>
      </div>
    );
  }
);

CollectorModal.displayName = 'CollectorModal';
export default CollectorModal;
