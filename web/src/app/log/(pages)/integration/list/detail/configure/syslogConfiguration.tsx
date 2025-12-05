import React, { useState, useEffect } from 'react';
import { Form, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import useIntegrationApi from '@/app/log/api/integration';
import { TableDataItem } from '@/app/log/types';

const SyslogConfiguration: React.FC = () => {
  const [form] = Form.useForm();
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { getLogNodeList } = useIntegrationApi();
  const [nodeList, setNodeList] = useState<TableDataItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [selectedNodeIp, setSelectedNodeIp] = useState<string>('');

  useEffect(() => {
    if (isLoading) return;
    initData();
  }, [isLoading]);

  const initData = () => {
    getNodeList();
  };

  const getNodeList = async () => {
    setLoading(true);
    try {
      const data = await getLogNodeList({
        cloud_region_id: 0,
        page: 1,
        page_size: -1,
        is_container: true,
        is_active: true,
      });
      const nodes = data.nodes || [];
      setNodeList(nodes);
      if (nodes.length > 0) {
        const firstNode = nodes[0];
        form.setFieldsValue({ node_id: firstNode.id });
        setSelectedNodeIp(firstNode.ip || '');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleNodeChange = (value: number) => {
    const selectedNode = nodeList.find((node) => node.id === value);
    if (selectedNode) {
      setSelectedNodeIp(selectedNode.ip || '');
    } else {
      setSelectedNodeIp('');
    }
  };

  return (
    <div className="px-[10px]">
      <Form form={form} name="syslogForm" layout="vertical" className="w-full">
        <Form.Item label={t('log.integration.node')} required>
          <Form.Item
            noStyle
            name="node_id"
            rules={[{ required: true, message: t('common.required') }]}
          >
            <Select
              style={{ width: 600 }}
              className="mr-[10px]"
              placeholder={t('common.selectMsg')}
              loading={loading}
              onChange={handleNodeChange}
              options={nodeList.map((node) => ({
                label: `${node.name} (${node.ip})`,
                value: node.id,
              }))}
            />
          </Form.Item>
          <span className="text-[12px] text-[var(--color-text-3)]">
            {t('log.integration.syslogNodeDes')}
          </span>
        </Form.Item>

        {selectedNodeIp && (
          <div className="p-[20px] bg-[var(--color-fill-1)] w-full">
            <div className="mb-[10px] font-bold text-[16px]">
              {t('log.integration.syslogAccessGuide')}
            </div>
            <div className="mb-[10px]">{t('log.integration.syslogStep1')}</div>
            <div className="text-[12px] text-[var(--color-text-3)] mb-[10px]">
              {t('log.integration.syslogStep1Des')}
            </div>
            <div className="bg-[var(--color-bg-1)] mt-[10px] p-[10px]">
              <div className="pb-[10px] mb-[10px] border-b border-[var(--color-border-1)]">
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('log.integration.syslogTargetIp')}:
                </span>
                <span className="ml-[10px] text-[var(--color-primary)] font-mono font-semibold">
                  {selectedNodeIp}
                </span>
              </div>
              <div className="pb-[10px] mb-[10px] border-b border-[var(--color-border-1)]">
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('log.integration.syslogTargetPort')}:
                </span>
                <span className="ml-[10px] text-[var(--color-primary)] font-mono font-semibold">
                  514(UDP) / 1514(TCP)
                </span>
              </div>
            </div>
          </div>
        )}
      </Form>
    </div>
  );
};

export default SyslogConfiguration;
