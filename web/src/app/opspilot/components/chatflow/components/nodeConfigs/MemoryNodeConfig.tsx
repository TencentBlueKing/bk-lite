import React from 'react';
import { Form, Select, Button } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import Link from 'next/link';
import type { MemoryNodeConfigProps } from './types';

const { Option } = Select;

export const MemoryNodeConfig: React.FC<MemoryNodeConfigProps> = ({
  t,
  memorySpaces,
  loadingMemorySpaces,
  form,
}) => {
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
              const selectedSpace = memorySpaces.find((s) => s.id === memorySpaceId);
              if (selectedSpace) {
                form.setFieldsValue({ memorySpaceName: selectedSpace.name });
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
    </>
  );
};
