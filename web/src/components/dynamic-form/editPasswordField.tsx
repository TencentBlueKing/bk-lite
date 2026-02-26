import React from 'react';
import { Input as AntdInput } from 'antd';
import { EditOutlined } from '@ant-design/icons';

interface EditablePasswordFieldProps {
  value?: string;
  onChange?: (value: string) => void;
}

const EditablePasswordField: React.FC<EditablePasswordFieldProps> = ({ value, onChange }) => {
  const [isEditable, setIsEditable] = React.useState(!value);
  const [internalValue, setInternalValue] = React.useState(value || '');
  const hasFilledRef = React.useRef(!!value);

  // Only handle external prefill: value set from outside when field was empty
  // This covers edit-mode backfill via form.setFieldsValue
  React.useEffect(() => {
    if (hasFilledRef.current) return;
    if (value && !internalValue) {
      hasFilledRef.current = true;
      setInternalValue(value);
      setIsEditable(false);
    }
  }, [value]);

  const handleEdit = () => {
    setIsEditable(true);
    setInternalValue('');
    if (onChange) {
      onChange('');
    }
  };

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
        disabled={!isEditable}
        visibilityToggle={false}
        className="flex-1"
        value={internalValue}
        onChange={handleChange}
      />
      {!isEditable && (
        <EditOutlined
          onClick={handleEdit}
          className="absolute right-2 top-1/2 transform -translate-y-1/2 text-gray-500 cursor-pointer"
        />
      )}
    </div>
  );
};

export default EditablePasswordField;
