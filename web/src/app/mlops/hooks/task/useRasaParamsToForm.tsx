import { useMemo } from 'react';
import { Form, Input, InputNumber, Select, Switch } from 'antd';
import { RASA_CONFIG } from '@/app/mlops/constants';
import type { Option } from '@/app/mlops/types';

interface RasaConfigItem {
  name: string;
  type: string;
  options?: Option[];
  dest?: string;
}

type FormFieldValue = string | number | boolean | null | undefined;

type ConfigData = Record<string, FormFieldValue>;

type FormData = Record<string, FormFieldValue>;

export const useRasaParamsToForm = () => {

  const configToForm = useMemo(() => {
    return (componentName: string, configData: ConfigData): FormData => {
      const componentConfig = RASA_CONFIG[componentName];
      if (!componentConfig) {
        // console.warn(`Unknown RASA component: ${componentName}`);
        return {};
      }

      const formData: FormData = {};

      componentConfig.forEach((configItem: RasaConfigItem) => {
        const { name, type } = configItem;
        const value = configData[name];

        if (value !== undefined) {
          switch (type) {
            case 'boolean':
              formData[name] = Boolean(value);
              break;
            case 'number':
              formData[name] = typeof value === 'string' ? parseFloat(value) : Number(value);
              break;
            case 'option':
              formData[name] = String(value);
              break;
            case 'string':
            case 'RegExp':
            default:
              formData[name] = String(value);
              break;
          }
        }
      });

      return formData;
    };
  }, []);

  const formToConfig = useMemo(() => {
    return (componentName: string, formData: FormData): ConfigData => {
      const componentConfig = RASA_CONFIG[componentName];
      if (!componentConfig) {
        console.warn(`Unknown RASA component: ${componentName}`);
        return {};
      }

      const configData: ConfigData = {};

      componentConfig.forEach((configItem: RasaConfigItem) => {
        const { name, type } = configItem;
        const value = formData[name];

        if (value !== undefined && value !== null && value !== '') {
          switch (type) {
            case 'boolean':
              configData[name] = Boolean(value);
              break;
            case 'number':
              configData[name] = Number(value);
              break;
            case 'option':
              // option类型保持字符串格式，特殊处理布尔值字符串
              if (value === 'True' || value === 'true') {
                configData[name] = true;
              } else if (value === 'False' || value === 'false') {
                configData[name] = false;
              } else {
                configData[name] = String(value);
              }
              break;
            case 'string':
            case 'RegExp':
            default:
              configData[name] = String(value);
              break;
          }
        }
      });

      return configData;
    };
  }, []);

  const generateFormField = useMemo(() => {
    const FormFieldGenerator = (
      componentName: string,
      configItem: RasaConfigItem
    ) => {
      const { name, type, options, dest } = configItem;
      const label = dest || name;

      switch (type) {
        case 'boolean':
          return (
            <Form.Item key={name} name={name} style={{ marginBottom: 0 }} valuePropName="checked">
              <div className='flex flex-col gap-[3px] items-start'>
                <span className='font-mini text-[#666]'>{label}</span>
                <Switch size="small" /> 
              </div>
            </Form.Item>
          );

        case 'number':
          return (
            <Form.Item key={name} name={name} style={{ marginBottom: 0 }}>
              <div className='flex flex-col'>
                <span className='font-mini text-[#666]'>{label}</span>
                <InputNumber
                  size="small"
                  style={{ width: '120px' }}
                  placeholder={label}
                />
              </div>
            </Form.Item>
          );

        case 'option':
          return (
            <Form.Item key={name} name={name} style={{ marginBottom: 0 }}>
              <div className='flex flex-col'>
                <span className='font-mini text-[#666]'>{label}</span>
                <Select
                  size="small"
                  style={{ width: '120px' }}
                  placeholder={label}
                  options={options}
                />
              </div>
            </Form.Item>
          );
        case 'string':
        case 'RegExp':
        default:
          return (
            <Form.Item key={name} name={name} style={{ marginBottom: 0 }}>
              <div className='flex flex-col'>
                <span className='font-mini text-[#666]'>{label}</span>
                <Input
                  size="small"
                  style={{ width: '120px' }}
                  placeholder={label}
                />
              </div>
            </Form.Item>
          );
      }
    };

    return FormFieldGenerator;
  }, []);

  const generateStandaloneFormField = useMemo(() => {
    const StandaloneFormFieldGenerator = (
      componentName: string,
      configItem: RasaConfigItem,
      value?: FormFieldValue,
      onChange?: (value: FormFieldValue) => void
    ) => {
      const { name, type, options, dest } = configItem;
      const label = dest || name;

      switch (type) {
        case 'boolean':
          return (
            <div key={name} className='flex flex-col gap-[3px]'>
              <span className='font-mini text-[#666]'>{label}</span>
              <Switch
                size="small"
                className='!w-[32px]'
                checked={Boolean(value)}
                onChange={onChange}
              />
            </div>
          );

        case 'number':
          return (
            <div key={name} className='flex flex-col'>
              <span className='font-mini text-[#666]'>{label}</span>
              <InputNumber
                key={name}
                size="small"
                style={{ width: '120px' }}
                min={0}
                value={typeof value === 'number' ? value : undefined}
                onChange={(val) => onChange?.(val)}
                placeholder={label}
              />
            </div>
          );

        case 'option':
          return (
            <div key={name} className='flex flex-col'>
              <span className='font-mini text-[#666]'>{label}</span>
              <Select
                size="small"
                style={{ width: '120px' }}
                value={value as string}
                onChange={onChange}
                placeholder={label}
                options={options}
              />
            </div>
          );
        case 'string':
        case 'RegExp':
        default:
          return (
            <div key={name} className='flex flex-col'>
              <span className='font-mini text-[#666]'>{label}</span>
              <Input
                key={name}
                size="small"
                style={{ width: '120px' }}
                value={value as string}
                onChange={(e) => onChange?.(e.target.value)}
                placeholder={label}
              />
            </div>
          );
      }
    };

    return StandaloneFormFieldGenerator;
  }, []);

  const generateStandaloneFormFields = useMemo(() => {
    return (
      componentName: string,
      formData: FormData = {},
      onFieldChange?: (fieldName: string, value: FormFieldValue) => void
    ) => {
      const componentConfig = RASA_CONFIG[componentName];
      if (!componentConfig) {
        return [];
      }

      return componentConfig.map((configItem: RasaConfigItem) => {
        return generateStandaloneFormField(
          componentName,
          configItem,
          formData[configItem.name],
          (value) => onFieldChange?.(configItem.name, value)
        );
      });
    };
  }, [generateStandaloneFormField]);

  const generateFormFields = useMemo(() => {
    return (componentName: string) => {
      const componentConfig = RASA_CONFIG[componentName];
      if (!componentConfig) {
        return [];
      }

      return componentConfig.map((configItem: RasaConfigItem) => {
        return generateFormField(componentName, configItem);
      });
    };
  }, [generateFormField]);

  const getConfigParamNames = useMemo(() => {
    return (componentName: string): string[] => {
      const componentConfig = RASA_CONFIG[componentName];
      if (!componentConfig) {
        return [];
      }
      return componentConfig.map(item => item.name);
    };
  }, []);

  const getSupportedComponents = useMemo(() => {
    return (): string[] => {
      return Object.keys(RASA_CONFIG);
    };
  }, []);

  const validateConfig = useMemo(() => {
    return (componentName: string, configData: ConfigData): {
      isValid: boolean;
      errors: string[]
    } => {
      const componentConfig = RASA_CONFIG[componentName];
      if (!componentConfig) {
        return { isValid: false, errors: [`Unknown component: ${componentName}`] };
      }

      const errors: string[] = [];

      componentConfig.forEach((configItem: RasaConfigItem) => {
        const { name, type } = configItem;
        const value = configData[name];

        if (value !== undefined) {
          switch (type) {
            case 'boolean':
              if (typeof value !== 'boolean') {
                errors.push(`${name} should be a boolean`);
              }
              break;
            case 'number':
              if (typeof value !== 'number' || isNaN(value)) {
                errors.push(`${name} should be a valid number`);
              }
              break;
            case 'option':
              if (configItem.options && !configItem.options.some(opt => opt.value === value)) {
                errors.push(`${name} should be one of: ${configItem.options.map(opt => opt.value).join(', ')}`);
              }
              break;
          }
        }
      });

      return { isValid: errors.length === 0, errors };
    };
  }, []);

  return {
    configToForm,
    formToConfig,
    generateFormField,
    generateFormFields,
    generateStandaloneFormField,
    generateStandaloneFormFields,
    getConfigParamNames,
    getSupportedComponents,
    validateConfig
  };
};

export type { RasaConfigItem, FormFieldValue, ConfigData, FormData };

export default useRasaParamsToForm;
