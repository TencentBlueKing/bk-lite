import React, { useState, useEffect } from 'react';
import { Input, Button, Tooltip } from 'antd';
import { CopyOutlined, EditOutlined } from '@ant-design/icons';
import { useCopy } from '@/hooks/useCopy';
import { useTranslation } from '@/utils/i18n';

interface PasswordProps {
  style?: Record<string, string | number>;
  className?: string;
  placeholder?: string;
  value?: string;
  allowCopy?: boolean; // 是否显示复制图标
  disabled?: boolean;
  onChange?: (value: string) => void;
  onCopy?: (value: string) => void;
  onReset?: () => void;
}

const Password: React.FC<PasswordProps> = ({
  style = {},
  className = 'w-full',
  placeholder = '',
  value = '',
  allowCopy = false,
  disabled = false,
  onChange,
  onCopy,
  onReset,
}) => {
  const { t } = useTranslation();
  const { copy } = useCopy();
  const [password, setPassword] = useState<string>('');
  const [isEditing, setIsEditing] = useState<boolean>(false);

  useEffect(() => {
    setPassword(value);
  }, [value]);

  const handleEdit = () => {
    setPassword('');
    setIsEditing(true);
    onChange?.('');
    onReset?.();
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setPassword(newValue);
    onChange?.(newValue);
  };

  const copyPassword = () => {
    if (onCopy) {
      onCopy(password);
      return;
    }
    copy(value);
  };

  return (
    <Input
      className={className}
      style={style}
      type="password"
      value={password}
      disabled={!isEditing}
      placeholder={placeholder || t('common.inputPassword')}
      suffix={
        <div className="flex items-center">
          <Tooltip title={t('common.reset')}>
            <Button
              size="small"
              type="link"
              icon={<EditOutlined />}
              disabled={disabled}
              onClick={handleEdit}
            />
          </Tooltip>
          {allowCopy && (
            <Tooltip title={t('common.copy')}>
              <Button
                size="small"
                type="link"
                icon={<CopyOutlined />}
                disabled={!password}
                onClick={copyPassword}
              />
            </Tooltip>
          )}
        </div>
      }
      onChange={handleChange}
    />
  );
};

export default Password;
