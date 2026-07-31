'use client';

import { Alert, Card, Empty, Space, Typography } from 'antd';
import type { ReactNode } from 'react';

const { Paragraph, Title } = Typography;

interface ApmRouteShellProps {
  title: string;
  description: string;
  dependency?: 'metadata' | 'telemetry' | 'control';
  children?: ReactNode;
}

const dependencyCopy = {
  metadata: '接入与目录元数据可用；遥测数据将在数据面配置后出现。',
  telemetry: '遥测存储不可用时，本页会明确显示降级状态，不会将查询故障伪装成空数据。',
  control: '策略与告警事件由 APM 自己管理；外部通知渠道不可用不会影响事件查询。',
};

export default function ApmRouteShell({
  title,
  description,
  dependency = 'metadata',
  children,
}: ApmRouteShellProps) {
  return (
    <div className="p-6">
      <Space direction="vertical" size={16} className="w-full">
        <div>
          <Title level={3} className="!mb-1">
            {title}
          </Title>
          <Paragraph type="secondary" className="!mb-0">
            {description}
          </Paragraph>
        </div>
        <Alert type="info" showIcon message={dependencyCopy[dependency]} />
        <Card>
          {children ?? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="路由与权限壳已就绪，业务数据将在后续切片接入。"
            />
          )}
        </Card>
      </Space>
    </div>
  );
}
