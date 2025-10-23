import OperateModal from "@/components/operate-modal";
import { useTranslation } from "@/utils/i18n";
import usePlayroundApi from '@/app/playground/api';
import { forwardRef, useImperativeHandle, useState, useRef, useCallback, useEffect } from 'react';
import { Button, Form, FormInstance, Input, message, Switch, Select } from 'antd';
import { ModalRef } from "@/app/playground/types";
import { Option } from "@/types";
const { TextArea } = Input;

interface ModalProps {
  id: number;
  name: string;
  categoryID: number;
  categoryType: string;
  description?: string;
  parent?: number;
  is_active?: boolean;
  url?: string;
  level?: number;
  config?: any;
}

const CategoryManageModal = forwardRef<ModalRef, any>(({ onSuccess }, ref) => {
  const { t } = useTranslation();
  const formRef = useRef<FormInstance>(null);
  const {
    getAnomalyServingsList,
    getTimeSeriesPredictServingsList,
    getLogClusteringServingsList,
    getClassificationServingsList,
    createCategory,
    createCapability,
    updateCapability,
    updateCategory
  } = usePlayroundApi();
  const [open, setOpen] = useState<boolean>(false);
  const [selectLoading, setSelectLoading] = useState<boolean>(false);
  const [confirm, setConfirm] = useState<boolean>(false);
  const [servingsOptions, setServingsOptions] = useState<Option[]>([]);
  const [servingConfig, setServingConfig] = useState<any>(null);
  const [title, setTitle] = useState<string>('addCategory');
  const [type, setType] = useState<string>('');
  const [formData, setFormData] = useState<ModalProps | null>(null);
  const CapabilityType = ['addCapability', 'updateCapability'];

  useImperativeHandle(ref, () => ({
    showModal: ({ type, title, form }) => {
      setOpen(true);
      setType(type);
      setTitle(title as string);
      setFormData(form);
    }
  }));

  useEffect(() => {
    if (open) {
      initForm();
    }
  }, [open]);

  const initForm = useCallback(async () => {
    if (!formRef.current) return;
    // if (!formData?.categoryID) return;
    formRef.current?.resetFields();
    if (type.trim().startsWith('update')) {
      formRef.current?.setFieldsValue({
        name: formData?.name,
        description: formData?.description,
        url: formData?.url,
        is_active: formData?.is_active
      });
    };
    await renderServingsOption();
  }, [type, formData]);

  const handleAdd: Record<string, any> = {
    'addCategory': async (data: any) => await createCategory(data),
    'addCapability': async (data: any) => await createCapability(data),
    'updateCategory': async (id: number, data: any) => await updateCategory(id, data),
    'updateCapability': async (id: number, data: any) => await updateCapability(id, data),
  };

  const getServingsList: Record<string, any> = {
    'anomaly': getAnomalyServingsList,
    'timeseries_predict': getTimeSeriesPredictServingsList,
    'log_clustering': getLogClusteringServingsList,
    'classification': getClassificationServingsList
  };

  const renderServingsOption = async () => {
    setSelectLoading(true);
    try {
      if (!formData?.categoryType) return;
      const data = await getServingsList[formData.categoryType]();
      const options = data?.filter((item: any) => item?.status === 'active').map((item: any) => {
        return {
          label: item?.name,
          value: item?.id,
          data: {
            serving_id: item.id,
            model_name: `RandomForest_${item.id}`,
            model_version: item.model_version,
            algorithm: "RandomForest",
            anomaly_threshold: item.anomaly_threshold
          }
        }
      });
      setServingsOptions(options);
      if (type.startsWith('update')) {
        const servingID = formData?.config?.serving_id;
        const config = options.find((k: any) => k.value === servingID)?.data || {};
        formRef.current?.setFieldValue('serving_id', servingID);
        setServingConfig(config)
      }
    } catch (e) {
      console.log(e);
      message.error(t(`common.fetchFailed`));
    } finally {
      setSelectLoading(false);
    }
  };

  const handleSubmit = async () => {
    setConfirm(true);
    try {
      if (!formData?.categoryID && type === 'addCapability') return message.error(t(`manage.missID`));
      const data = await formRef.current?.validateFields();
      const params = {
        ...data,
        config: servingConfig,
        category: formData?.categoryID
      };
      if (type.trim().startsWith('add')) {
        await handleAdd[type](params);
      } else {
        await handleAdd[type](formData?.id, params);
      }
      setOpen(false);
      message.success(t(`manage.${title}Success`));
      onSuccess();
    } catch (e) {
      console.log(e);
    } finally {
      setConfirm(false);
    }
  };

  const handleCancel = () => {
    setOpen(false);
    setConfirm(false);
    setFormData(null);
    setServingsOptions([]);
  };

  return (
    <OperateModal
      title={t(`manage.${title}`)}
      open={open}
      onCancel={handleCancel}
      footer={[
        <Button key="submit" loading={confirm} type="primary" onClick={handleSubmit}>
          {t('common.confirm')}
        </Button>,
        <Button key="cancel" onClick={handleCancel}>
          {t('common.cancel')}
        </Button>,
      ]}
    >
      <Form ref={formRef} layout="vertical">
        <Form.Item
          name='name'
          label={t(`common.name`)}
          rules={[{ required: true, message: t('common.inputMsg') }]}
        >
          <Input placeholder={t(`common.inputMsg`)} />
        </Form.Item>
        {CapabilityType.includes(type) && (
          <>
            <Form.Item
              name='url'
              label={t(`playground-common.url`)}
              rules={[{ required: true, message: t('common.inputMsg') }]}
            >
              <Input placeholder={t(`common.inputMsg`)} />
            </Form.Item>
            <Form.Item
              name='serving_id'
              label={t(`manage.servingsSelect`)}
              rules={[{ required: true, message: t('common.selectMsg') }]}
            >
              <Select
                options={servingsOptions}
                loading={selectLoading}
                onChange={(value, option) => {
                  if (option && typeof option === 'object' && 'data' in option) {
                    setServingConfig(option.data);
                  }
                }}
                placeholder={t(`manage.servingsMsg`)}
                allowClear
              />
            </Form.Item>
            <Form.Item
              name='is_active'
              label={t(`playground-common.onlineStatus`)}
              rules={[{ required: true, message: t('common.selectMsg') }]}
              layout="horizontal"
            >
              <Switch checkedChildren="是" unCheckedChildren="否" />
            </Form.Item>
          </>
        )}
        <Form.Item
          name='description'
          label={t(`common.description`)}
          rules={[{ required: true, message: t('common.inputMsg') }]}
        >
          <TextArea rows={3} />
        </Form.Item>
      </Form>
    </OperateModal>
  )
})

CategoryManageModal.displayName = 'CategoryManageModal';
export default CategoryManageModal;