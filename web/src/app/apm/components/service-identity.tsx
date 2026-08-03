import { AppstoreOutlined } from '@ant-design/icons';
import { Typography } from 'antd';

interface ServiceIdentityProps {
  namespace: string;
  name: string;
  secondary?: string;
}

const { Text } = Typography;

export default function ServiceIdentity({ namespace, name, secondary }: ServiceIdentityProps) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--color-primary-bg-active)] text-[var(--color-primary)]">
        <AppstoreOutlined aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <Text strong className="block truncate text-sm text-[var(--color-text-1)]">
          {name}
        </Text>
        <Text type="secondary" className="block truncate text-xs">
          {namespace || '未归类应用'}{secondary ? ` · ${secondary}` : ''}
        </Text>
      </div>
    </div>
  );
}
