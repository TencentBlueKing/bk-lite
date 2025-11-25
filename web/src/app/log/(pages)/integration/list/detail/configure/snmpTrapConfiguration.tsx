import React, { useState, useEffect } from 'react';
import { Form, Select, Steps } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import useIntegrationApi from '@/app/log/api/integration';
import { TableDataItem } from '@/app/log/types';

const SnmpTrapConfiguration: React.FC = () => {
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
      <Form
        form={form}
        name="snmpTrapForm"
        layout="vertical"
        className="w-full"
      >
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
            {t('log.integration.snmpTrapNodeDes')}
          </span>
        </Form.Item>

        {selectedNodeIp && (
          <div className="p-[20px] bg-[var(--color-fill-1)] w-full">
            <div className="mb-[10px] font-bold text-[16px]">
              {t('log.integration.snmpTrapAccessGuide')}
            </div>
            <Steps
              direction="vertical"
              current={1}
              items={[
                {
                  status: 'process',
                  title: t('log.integration.snmpTrapStep1'),
                  description: (
                    <div>
                      <div className="text-[12px] text-[var(--color-text-3)] mb-[10px">
                        {t('log.integration.snmpTrapStep1Des')}
                      </div>
                      <div className="bg-[var(--color-bg-1)] mt-[10px] p-[10px]">
                        <div className="pb-[10px] mb-[10px] border-b border-[var(--color-border-1)]">
                          <span className="text-[12px] text-[var(--color-text-3)]">
                            {t('log.integration.snmpTrapTargetIp')}:
                          </span>
                          <span className="ml-[10px] text-[var(--color-primary)] font-mono font-semibold">
                            {selectedNodeIp}
                          </span>
                        </div>
                        <div>
                          <span className="text-[12px] text-[var(--color-text-3)]">
                            {t('log.integration.snmpTrapTargetPort')}:
                          </span>
                          <span className="ml-[10px] text-[var(--color-primary)] font-mono font-semibold">
                            162
                          </span>
                        </div>
                      </div>
                    </div>
                  ),
                },
                {
                  status: 'process',
                  title: t('log.integration.snmpTrapStep2'),
                  description: (
                    <div>
                      <div className="text-[12px] text-[var(--color-text-3)] mb-[10px">
                        {t('log.integration.snmpTrapStep2Des')}
                      </div>
                      <div className="bg-[var(--color-bg-1)] mt-[10px] p-[10px]">
                        <div>
                          <span className="text-[12px] text-[var(--color-text-3)]">
                            {t('log.integration.auditBeatPaths')}:
                          </span>
                          <span className="ml-[10px] text-[var(--color-primary)] font-mono font-semibold">
                            /usr/share/mibs
                          </span>
                        </div>
                      </div>
                    </div>
                  ),
                },
              ]}
            />
          </div>
        )}
      </Form>
    </div>
  );
};

export default SnmpTrapConfiguration;
