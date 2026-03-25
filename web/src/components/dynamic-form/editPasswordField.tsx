import React from 'react';
import { Input as AntdInput } from 'antd';
import { KeyOutlined } from '@ant-design/icons';

interface EditablePasswordFieldProps {
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  size?: 'large' | 'middle' | 'small';
  showPrefixIcon?: boolean;
}

const EditablePasswordField: React.FC<EditablePasswordFieldProps> = ({
  value,
  onChange,
  placeholder,
  size = 'large',
  showPrefixIcon = false,
}) => {
  const [internalValue, setInternalValue] = React.useState(value || '');

  React.useEffect(() => {
    setInternalValue(value || '');
  }, [value]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setInternalValue(newValue);
    if (onChange) {
      onChange(newValue);
    }
  };

  return (
    <div className="relative flex items-center">
      <AntdInput.Password
        allowClear
        visibilityToggle
        size={size}
        className="flex-1"
        value={internalValue}
        placeholder={placeholder}
        prefix={showPrefixIcon ? <KeyOutlined style={{ color: 'var(--color-text-4)' }} /> : undefined}
        autoComplete="new-password"
        onChange={handleChange}
      />
    </div>
  );
};

export default EditablePasswordField;
