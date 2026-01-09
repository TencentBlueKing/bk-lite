import React, {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react';
import { Form, Button, Input, message, FormInstance, Alert } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
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
      proxy_address: '',
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
            proxy_address: cloudRegion.proxy_address,
          };
          await updateCloudIntro(cloudRegion.id, params);
          message.success(t('common.updateSuccess'));
        } else if (type === 'add') {
          const { name, introduction, proxy_address } = cloudRegion;
          await createCloudRegion({
            name,
            introduction,
            proxy_address,
          });
          message.success(t('common.addSuccess'));
        }
        onSuccess();
        setOpenEditCloudRegion(false);
        setFormData({
          name: '',
          introduction: '',
          proxy_address: '',
        });
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleCancel = () => {
      setOpenEditCloudRegion(false);
      setFormData({ name: '', introduction: '', proxy_address: '' });
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
                disabled={formData.originalName === 'default'}
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
                disabled={
                  formData?.originalName === 'default' || type === 'delete'
                }
                placeholder={t('common.inputMsg')}
              />
            </Form.Item>
            <Form.Item
              name={['cloudRegion', 'proxy_address']}
              label={t('node-manager.cloudregion.editform.proxyIpOrDomain')}
            >
              <Input
                disabled={type === 'edit'}
                placeholder={t(
                  'node-manager.cloudregion.editform.proxyIpOrDomainPlaceholder'
                )}
              />
            </Form.Item>
            <Alert
              message={t('node-manager.cloudregion.editform.proxyTips')}
              type="info"
              showIcon
              icon={<InfoCircleOutlined />}
              className="mb-4"
            />
            <Form.Item
              name={['cloudRegion', 'introduction']}
              label={t('node-manager.cloudregion.editform.Introduction')}
              rules={[{ required: true, message: t('common.inputRequired') }]}
            >
              <Input.TextArea
                disabled={
                  formData?.originalName === 'default' || type === 'delete'
                }
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
