import React, {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react';
import { Form, Button, Input, message, FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  ModalRef,
  ModalSuccess,
  TableDataItem,
} from '@/app/node-manager/types';
import OperateModal from '@/components/operate-modal';
import useNodeManagerApi from '@/app/node-manager/api';

const CloudRegionModal = forwardRef<ModalRef, ModalSuccess>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const { updateCloudIntro, createCloudRegion } = useNodeManagerApi();
    const cloudRegionFormRef = useRef<FormInstance>(null);
    const [openEditCloudRegion, setOpenEditCloudRegion] = useState(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [title, setTitle] = useState<string>('editform');
    const [type, setType] = useState<string>('edit');
    const [formData, setFormData] = useState<TableDataItem>({
      name: '',
      introduction: '',
    });

    useImperativeHandle(ref, () => ({
      showModal: ({ type, title, form }) => {
        setTitle(title as string);
        setType(type as string);
        setOpenEditCloudRegion(true);
        if (['edit', 'delete'].includes(type)) {
          setFormData(form as TableDataItem);
        }
      },
    }));

    useEffect(() => {
      cloudRegionFormRef.current?.resetFields();
      cloudRegionFormRef.current?.setFieldsValue({
        cloudRegion: formData,
      });
    }, [formData, openEditCloudRegion]);

    const handleFormOkClick = async () => {
      setConfirmLoading(true);
      try {
        await cloudRegionFormRef.current?.validateFields();
        const { cloudRegion } = cloudRegionFormRef.current?.getFieldsValue();
        if (type === 'edit') {
          const params = {
            name: cloudRegion.name,
            introduction: cloudRegion.introduction,
          };
          await updateCloudIntro(cloudRegion.id, params);
          message.success(t('common.updateSuccess'));
        } else if (type === 'add') {
          const { name, introduction } = cloudRegion;
          await createCloudRegion({
            name,
            introduction,
          });
          message.success(t('common.addSuccess'));
        }
        onSuccess();
        setOpenEditCloudRegion(false);
        setFormData({
          name: '',
          introduction: '',
        });
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleCancel = () => {
      setOpenEditCloudRegion(false);
      setFormData({ name: '', introduction: '' });
      setConfirmLoading(false);
    };

    return (
      <div>
        <OperateModal
          title={t(`node-manager.cloudregion.${title}.title`)}
          open={openEditCloudRegion}
          okText={t('common.confirm')}
          cancelText={t('common.cancel')}
          onCancel={handleCancel}
          footer={
            <div>
              <Button
                type="primary"
                className="mr-[10px]"
                disabled={formData.name === 'default'}
                loading={confirmLoading}
                onClick={handleFormOkClick}
              >
                {t('common.confirm')}
              </Button>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </div>
          }
        >
          <Form layout="vertical" ref={cloudRegionFormRef} name="nest-messages">
            <Form.Item name={['cloudRegion', 'id']} hidden>
              <Input />
            </Form.Item>
            <Form.Item
              name={['cloudRegion', 'name']}
              label={t('common.name')}
              rules={[{ required: true, message: t('common.inputRequired') }]}
            >
              <Input
                disabled={formData?.name === 'default' || type === 'delete'}
                placeholder={t('common.inputMsg')}
              />
            </Form.Item>
            <Form.Item
              name={['cloudRegion', 'introduction']}
              label={t('node-manager.cloudregion.editform.Introduction')}
              rules={[{ required: true, message: t('common.inputRequired') }]}
            >
              <Input.TextArea
                disabled={formData?.name === 'default' || type === 'delete'}
                rows={5}
                placeholder={t('common.inputMsg')}
              />
            </Form.Item>
          </Form>
        </OperateModal>
      </div>
    );
  }
);

CloudRegionModal.displayName = 'CloudRegionModal';
export default CloudRegionModal;
