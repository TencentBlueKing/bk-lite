import { Option } from "@/types";
import { Button, Drawer, Form, Select, Input, message } from "antd";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "@/utils/i18n";
import useMlopsManageApi from "@/app/mlops/api/manage";
import { Node } from "@xyflow/react";
import { FormInstance } from "antd/lib";

interface NodeOption extends Option {
  data: any
}

const NodeDetailDrawer = ({
  dataset,
  node,
  open = false,
  onChange,
  onClose,
  handleDelNode,
}: {
  dataset: string;
  node: Node;
  open: boolean;
  onChange: (data: any, type: string) => void;
  onClose: () => void;
  handleDelNode: () => void;
}) => {
  const { t } = useTranslation();
  const { getRasaIntentFileList, getRasaResponseFileList, getRasaSlotList, getRasaFormList, getRasaActionList } = useMlopsManageApi();
  const [loading, setLoading] = useState<boolean>(false);
  const [options, setOptions] = useState<NodeOption[]>([]);
  const [hasChanges, setHasChanges] = useState<boolean>(false); // 追踪是否有变更
  const formRef = useRef<FormInstance>(null);

  useEffect(() => {
    if (open) {
      getOptions();
      setHasChanges(false); // 重置变更状态
    }
  }, [open])

  const getOptions = async () => {
    setLoading(true);
    let data = [];
    try {
      switch (node?.type) {
        case 'intent':
          data = await getRasaIntentFileList({ dataset });
          break;
        case 'response':
          data = await getRasaResponseFileList({ dataset });
          break;
        case 'slot':
          data = await getRasaSlotList({ dataset });
          break;
        case 'form':
          data = await getRasaFormList({ dataset });
          break;
        case 'action':
          data = await getRasaActionList({ dataset })
        default:
          break;
      }

      const options = data?.map((item: any) => {
        return {
          label: item?.name,
          value: item?.id,
          data: {
            ...item
          }
        }
      });
      setOptions(options);
      if (node.data) {
        formRef.current?.setFieldsValue({
          name: node.data?.name || null
        });
      }
    } catch (e) {
      console.log(e)
    } finally {
      setLoading(false);
    }
  };

  // 处理选择变更 - 不再立即应用，只标记有变更
  const handleOptionChange = () => {
    setHasChanges(true);
  };

  const validateVariableName = (value: string) => {
    const variableNameRegex = /^[a-zA-Z_][a-zA-Z0-9_]*$/;
    return variableNameRegex.test(value);
  };

  // 处理输入变更 - 不再立即应用，只标记有变更
  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    setHasChanges(true);

    // 保留原有的验证逻辑，但不立即应用变更
    if (value !== '' && !validateVariableName(value)) {
      // 可以在这里添加实时验证提示，但不应用变更
      return;
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    const key = event.key;
    const currentValue = (event.target as HTMLInputElement).value;

    const allowedKeys = [
      'Backspace', 'Delete', 'ArrowLeft', 'ArrowRight',
      'ArrowUp', 'ArrowDown', 'Home', 'End', 'Tab', 'Enter'
    ];

    if (allowedKeys.includes(key)) {
      return;
    }

    if (key.length === 1) {
      if (currentValue === '' && /[0-9]/.test(key)) {
        event.preventDefault();
        return;
      }

      if (!/[a-zA-Z0-9_]/.test(key)) {
        event.preventDefault();
      }
    }
  };

  const handleInput = (event: React.FormEvent<HTMLInputElement>) => {
    const target = event.target as HTMLInputElement;
    const value = target.value;

    const filteredValue = value.replace(/[^a-zA-Z0-9_]/g, '');
    const finalValue = filteredValue.replace(/^[0-9]/, '');

    if (value !== finalValue) {
      target.value = finalValue;
      const syntheticEvent = {
        target: target,
        currentTarget: target
      } as React.ChangeEvent<HTMLInputElement>;
      handleInputChange(syntheticEvent);
    }
  };

  const handleSave = async () => {
    try {
      const values = await formRef.current?.validateFields();
      if (node?.type !== 'checkpoint') {
        const selectedValue = values.name;
        if (selectedValue) {
          const item = options.find(item => item.value === selectedValue);
          onChange(item?.data?.name, node.type as string);
        }
      } else {
        onChange(values.name, node.type as string);
      }
      setHasChanges(false);
      message.success(t('common.saveSuccess'));
      closeDrawer();
    } catch (error) {
      console.log(error);
      message.error(t(`common.saveFailed`))
    }
  };

  const closeDrawer = () => {
    onClose();
    setOptions([]);
    setHasChanges(false);
    formRef.current?.resetFields();
  };

  const delNode = () => {
    handleDelNode();
    closeDrawer();
  };

  return (
    <Drawer
      title={t(`mlops-common.nodeDetail`)}
      open={open}
      width={400}
      onClose={closeDrawer}
      footer={[
        <div key="footer" className="flex justify-between w-full">
          <Button
            key="save"
            type="primary"
            onClick={handleSave}
            disabled={!hasChanges} // 没有变更时禁用保存按钮
          >
            {t(`common.save`) || '保存'}
          </Button>
          <Button
            key="delete"
            danger
            onClick={delNode}
          >
            {t(`mlops-common.delNode`)}
          </Button>
        </div>
      ]}
    >
      <div className="w-full h-full">
        <Form ref={formRef} layout="vertical">
          <Form.Item
            label={t(`common.select`)}
            name="name"
            rules={[
              {
                validator: (_, value) => {
                  if (node.type === 'checkpoint') {
                    if (!value) {
                      return Promise.reject(new Error(t(`common.inputMsg`)));
                    }
                    if (!validateVariableName(value)) {
                      return Promise.reject(new Error(`格式错误`));
                    }
                    return Promise.resolve();
                  }
                  return Promise.resolve();
                }
              }
            ]}
          >
            {node?.type !== 'checkpoint'
              ? <Select
                options={options}
                placeholder={t(`common.selectMsg`)}
                onChange={handleOptionChange}
                loading={loading}
              />
              : <Input
                placeholder={t(`common.inputMsg`)}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                onInput={handleInput}
                maxLength={50}
              />
            }
          </Form.Item>
        </Form>
      </div>
    </Drawer>
  )
};

export default NodeDetailDrawer;