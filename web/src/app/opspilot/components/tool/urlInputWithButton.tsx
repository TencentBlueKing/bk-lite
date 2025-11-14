import React from 'react';
import { Input, Button, Space } from 'antd';

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
  fetchButtonText = '获取工具',
}) => {
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
        {fetchButtonText}
      </Button>
    </Space.Compact>
  );
};

export default UrlInputWithButton;
