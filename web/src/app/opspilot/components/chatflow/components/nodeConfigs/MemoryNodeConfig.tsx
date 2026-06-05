import React, {useEffect} from 'react';
import {Button, Form, InputNumber, Select} from 'antd';
import {PlusOutlined} from '@ant-design/icons';
import Link from 'next/link';
import {filterModelOption, getModelOptionText, renderModelOptionLabel} from '@/app/opspilot/utils/modelOption';
import type {MemoryNodeConfigProps} from './types';

const { Option } = Select;

export const MemoryNodeConfig: React.FC<MemoryNodeConfigProps> = ({
  t,
  memorySpaces,
  loadingMemorySpaces,
  form,
  nodeType,
  llmModels = [],
  loadingLlmModels = false,
}) => {
  const isWriteNode = nodeType === 'memory_write';
  const selectedMemorySpaceId = Form.useWatch('memorySpace', form);
  const selectedSpace = memorySpaces.find((s) => s.id === selectedMemorySpaceId);

  // 当选择记忆空间时，自动设置默认模型（仅写入节点）
  useEffect(() => {
    if (isWriteNode && selectedSpace?.default_model) {
      const currentModel = form.getFieldValue('llmModel');
      // 只在没有选择模型时设置默认值
      if (!currentModel) {
        const defaultModelId = Number(selectedSpace.default_model);
        const modelExists = llmModels.some((m) => m.id === defaultModelId);
        if (modelExists) {
          const model = llmModels.find((m) => m.id === defaultModelId);
          form.setFieldsValue({
            llmModel: defaultModelId,
            llmModelName: model?.name || '',
          });
        }
      }
    }
  }, [selectedSpace, isWriteNode, llmModels, form]);

  return (
    <>
      <div className="relative">
        <Form.Item
          name="memorySpace"
          label={t('chatflow.nodeConfig.selectMemorySpace')}
          rules={[{ required: true, message: t('chatflow.nodeConfig.pleaseSelectMemorySpace') }]}
        >
          <Select
            placeholder={t('chatflow.nodeConfig.pleaseSelectMemorySpace')}
            loading={loadingMemorySpaces}
            showSearch
            onChange={(memorySpaceId) => {
              const space = memorySpaces.find((s) => s.id === memorySpaceId);
              if (space) {
                form.setFieldsValue({ memorySpaceName: space.name });
                // 写入节点：切换记忆空间时，自动设置该空间的默认模型
                if (isWriteNode && space.default_model) {
                  const defaultModelId = Number(space.default_model);
                  const model = llmModels.find((m) => m.id === defaultModelId);
                  if (model) {
                    form.setFieldsValue({
                      llmModel: defaultModelId,
                      llmModelName: model.name,
                    });
                  }
                }
              }
            }}
            filterOption={(input, option) =>
              option?.label?.toString().toLowerCase().includes(input.toLowerCase()) ?? false
            }
          >
            {memorySpaces.map((space) => (
              <Option key={space.id} value={space.id} label={space.name}>
                <div className="flex items-center justify-between">
                  <span>{space.name}</span>
                  <span className="text-xs text-gray-400 ml-2">
                    {space.scope === 'personal' ? t('memory.personal') : t('memory.team')}
                  </span>
                </div>
              </Option>
            ))}
          </Select>
        </Form.Item>
        <Link href="/opspilot/memory" target="_blank" className="absolute right-0 top-0">
          <Button
            type="link"
            size="small"
            icon={<PlusOutlined />}
            className="text-blue-500 hover:text-blue-600 text-xs"
          >
            {t('chatflow.nodeConfig.addMemorySpace')}
          </Button>
        </Link>
      </div>
      <Form.Item name="memorySpaceName" className="hidden">
        <input type="hidden" />
      </Form.Item>

      {/* 写入节点显示模型选择器 */}
      {isWriteNode && (
        <>
          <Form.Item
            name="llmModel"
            label={t('chatflow.nodeConfig.llmModel')}
            tooltip={t('chatflow.nodeConfig.memoryWriteModelTooltip')}
            rules={[{ required: true, message: t('chatflow.nodeConfig.pleaseSelectLlmModel') }]}
          >
            <Select
              placeholder={t('chatflow.nodeConfig.pleaseSelectLlmModel')}
              loading={loadingLlmModels}
              showSearch
              filterOption={filterModelOption}
              onChange={(modelId) => {
                const model = llmModels.find((m) => m.id === modelId);
                form.setFieldsValue({ llmModelName: model?.name || '' });
              }}
            >
              {llmModels.map((model) => (
                <Option key={model.id} value={model.id} title={getModelOptionText(model)}>
                  {renderModelOptionLabel(model)}
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="llmModelName" className="hidden">
            <input type="hidden" />
          </Form.Item>

          <Form.Item
            name="writeBatchSize"
            label={t('chatflow.nodeConfig.memoryWriteBatchSize')}
            tooltip={t('chatflow.nodeConfig.memoryWriteBatchSizeTooltip')}
            rules={[{ required: true, message: t('chatflow.nodeConfig.pleaseEnterMemoryWriteBatchSize') }]}
          >
            <InputNumber min={1} max={500} precision={0} className="w-full" />
          </Form.Item>
        </>
      )}
    </>
  );
};
