import React from 'react';
import { Input, Button, Space } from 'antd';
import { useTranslation } from '@/utils/i18n';

interface UrlInputWithButtonProps {
  value?: string;
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  disabled?: boolean;
  placeholder?: string;
  onFetch?: () => void;
  fetchLoading?: boolean;
  fetchButtonText?: string;
}

const UrlInputWithButton: React.FC<UrlInputWithButtonProps> = ({
  value,
  onChange,
  disabled = false,
  placeholder,
  onFetch,
  fetchLoading = false,
  fetchButtonText,
}) => {
  const { t } = useTranslation();
  return (
    <Space.Compact style={{ width: '100%' }}>
      <Input
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        disabled={disabled}
      />
      <Button 
        type="primary" 
        onClick={onFetch}
        loading={fetchLoading}
        disabled={disabled}
      >
        {fetchButtonText || t('tool.fetchButton', '获取工具')}
      </Button>
    </Space.Compact>
  );
};

export default UrlInputWithButton;
