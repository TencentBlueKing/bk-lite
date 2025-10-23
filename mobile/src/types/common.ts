// 选项类型
export interface Option {
  label: string;
  value: string;
}

// 列表项类型
export interface ListItem {
  title?: string;
  label?: string;
  name?: string;
  id?: string | number;
  value?: string | number;
}

// 语言选项类型
export interface LanguageOption {
  key: string;
  label: string;
  nativeLabel: string;
}

// 语言选择器属性类型
export interface LanguageSelectorProps {
  onSelect?: (language: string) => void;
}
// 表单字段属性类型
export interface FormFieldProps {
  label: string;
  children: React.ReactNode;
  error?: string;
}

// 错误提示属性类型
export interface ErrorAlertProps {
  message: string;
}
