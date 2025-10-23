import { ModalRef, ModalProps, TableDataItem } from '@/app/log/types';
import { Form, Button, message, Spin } from 'antd';
import { cloneDeep } from 'lodash';
import React, {
  useState,
  useRef,
  useMemo,
  useImperativeHandle,
  useEffect,
  forwardRef,
} from 'react';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import useLogApi from '@/app/log/api/integration';
import { useCollectTypeConfig } from '@/app/log/hooks/integration/index';

const UpdateConfig = forwardRef<ModalRef, ModalProps>(({ onSuccess }, ref) => {
  const [form] = Form.useForm();
  const { t } = useTranslation();
  const { getConfigContent, updateInstanceCollectConfig } = useLogApi();
  const { getCollectTypeConfig } = useCollectTypeConfig();
  const formRef = useRef(null);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [modalVisible, setModalVisible] = useState<boolean>(false);
  const [title, setTitle] = useState<string>('');
  const [formData, setFormData] = useState<TableDataItem>({});
  const [configForm, setConfigForm] = useState<TableDataItem | null>(null);
  const [pageLoading, setPageLoading] = useState<boolean>(false);

  useImperativeHandle(ref, () => ({
    showModal: ({ form, title }) => {
      const _form = cloneDeep(form);
      setFormData(_form);
      setTitle(title);
      setModalVisible(true);
      setConfirmLoading(false);
      getContent(_form);
    },
  }));

  const getContent = async (data: any) => {
    setPageLoading(true);
    try {
      const res = await getConfigContent({
        ids: data.config_id,
      });
      setConfigForm(res || {});
    } finally {
      setPageLoading(false);
    }
  };

  const configsInfo = useMemo(() => {
    return getCollectTypeConfig({
      type: formData.collect_type__name,
      collector: formData.collect_type__collector,
      mode: 'edit',
    });
  }, [formData]);

  const formItems = useMemo(() => {
    return (
      configsInfo.formItems ||
      configsInfo.getFormItems({
        rowId: formData.id,
        ...configForm,
      })
    );
  }, [configsInfo, configForm, formData]);

  useEffect(() => {
    if (configsInfo?.getDefaultForm && configForm && formData) {
      initData({
        rowId: formData.id,
        ...configForm,
      });
    }
  }, [configsInfo, configForm, formData]);

  const initData = (row: TableDataItem) => {
    const formData: Record<string, any> = cloneDeep(
      row?.content?.env_config || {}
    );
    const activeFormData = configsInfo.getDefaultForm(row);
    form.setFieldsValue({
      ...formData,
      ...activeFormData,
    });
  };

  const handleCancel = () => {
    form.resetFields();
    setModalVisible(false);
    setPageLoading(false);
    setConfigForm(null);
  };

  const handleSubmit = () => {
    form.validateFields().then((values) => {
      operateConfig(values);
    });
  };

  const operateConfig = async (params: TableDataItem) => {
    try {
      const { id, content_data } = configsInfo.getParams(
        params,
        configForm
      ).child;
      const data = {
        instance_id: formData.id,
        collect_type_id: formData.collect_type_id,
        child: {
          id,
          content_data,
        },
      };
      setConfirmLoading(true);
      await updateInstanceCollectConfig(data);
      message.success(t('common.successfullyModified'));
      handleCancel();
      onSuccess();
    } catch (error) {
      console.log(error);
    } finally {
      setConfirmLoading(false);
    }
  };

  return (
    <OperateModal
      width={500}
      title={title}
      visible={modalVisible}
      onCancel={handleCancel}
      footer={
        <div>
          <Button
            className="mr-[10px]"
            type="primary"
            loading={confirmLoading}
            disabled={pageLoading}
            onClick={handleSubmit}
          >
            {t('common.confirm')}
          </Button>
          <Button onClick={handleCancel}>{t('common.cancel')}</Button>
        </div>
      }
    >
      <Spin spinning={pageLoading}>
        <div className="px-[10px]">
          <Form ref={formRef} form={form} name="basic" layout="vertical">
            {formItems}
          </Form>
        </div>
      </Spin>
    </OperateModal>
  );
});

UpdateConfig.displayName = 'UpdateConfig';

export default UpdateConfig;
