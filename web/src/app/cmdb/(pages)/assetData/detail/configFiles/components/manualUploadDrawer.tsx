'use client';

import { Button, Drawer, Form, Input, Space, Typography, Upload } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useUnsavedConfirm from '@/hooks/useUnsavedConfirm';

const { Text } = Typography;

interface ManualUploadDrawerProps {
  open: boolean;
  loading: boolean;
  form: FormInstance;
  onClose: () => void;
  onSubmit: () => void;
}

const ManualUploadDrawer = ({
  open,
  loading,
  form,
  onClose,
  onSubmit,
}: ManualUploadDrawerProps) => {
  const { t } = useTranslation();
  const guardClose = useUnsavedConfirm();
  const handleClose = () => guardClose(form.isFieldsTouched(), onClose);

  const handleUploadFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      form.setFieldsValue({ content: text });
    };
    reader.readAsText(file);
    return false;
  };

  return (
    <Drawer
      title={t('ConfigFile.uploadDrawerTitle')}
      placement="right"
      width={600}
      open={open}
      maskClosable={false}
      onClose={handleClose}
      footer={
        <div style={{ textAlign: 'right' }}>
          <Space>
            <Button onClick={handleClose}>
              {t('ConfigFile.cancel')}
            </Button>
            <Button
              type="primary"
              loading={loading}
              onClick={onSubmit}
            >
              {t('ConfigFile.confirm')}
            </Button>
          </Space>
        </div>
      }
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="file_path"
          label={t('ConfigFile.filePath')}
          rules={[
            { required: true, message: t('ConfigFile.filePathRequired') },
            {
              pattern: /^\//,
              message: t('ConfigFile.filePathStartWithSlash'),
            },
          ]}
        >
          <Input placeholder={t('ConfigFile.filePathPlaceholder')} />
        </Form.Item>
        <div className="mb-2 flex items-center justify-between">
          <span>
            <span className="text-red-500 mr-1">*</span>
            {t('ConfigFile.fileContent')}
          </span>
          <Upload
            beforeUpload={handleUploadFile}
            showUploadList={false}
            accept=".conf,.yaml,.yml,.toml,.ini,.json,.xml,.properties,.cfg,.txt,.env,.sh"
          >
            <Button size="small" type="link" icon={<UploadOutlined />}>
              {t('ConfigFile.uploadFile')}
            </Button>
          </Upload>
        </div>
        <Form.Item
          name="content"
          className="mb-2"
          rules={[
            { required: true, message: t('ConfigFile.fileContentRequired') },
          ]}
        >
          <Input.TextArea
            rows={16}
            placeholder={t('ConfigFile.fileContentPlaceholder')}
            className="!bg-[#0f172a] !text-[#e2e8f0] !font-mono !text-xs !leading-6 !border-none !rounded-lg focus:!shadow-none placeholder:!text-[#64748b]"
            style={{
              fontFamily:
                'SFMono-Regular, Menlo, Monaco, Consolas, monospace',
              fontSize: 13,
              padding: 16,
            }}
          />
        </Form.Item>
        <Text type="secondary" className="text-xs">
          {t('ConfigFile.uploadHint')}
        </Text>
      </Form>
    </Drawer>
  );
};

export default ManualUploadDrawer;
