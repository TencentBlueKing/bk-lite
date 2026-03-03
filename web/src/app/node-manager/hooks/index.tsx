import { message } from 'antd';
import { ColumnItem } from '@/types';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { Button, Popconfirm } from 'antd';
import Permission from '@/components/permission';

const useHandleCopy = () => {
  const { t } = useTranslation();
  const handleCopy = (config: {
    value: string;
    showSuccessMessage?: boolean;
  }) => {
    const { value, showSuccessMessage = true } = config;
    try {
      if (navigator?.clipboard?.writeText) {
        navigator.clipboard.writeText(value);
      } else {
        const textArea = document.createElement('textarea');
        textArea.value = value;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
      }
      if (showSuccessMessage) {
        message.success(t('common.copySuccess'));
      }
    } catch (error: any) {
      message.error(error + '');
    }
  };
  return {
    handleCopy
  };
};

const useDetailColumns = ({
  handleDelete
}: {
  handleDelete: (id: number) => void;
}): ColumnItem[] => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const detailColumns: ColumnItem[] = [
    {
      title: t('node-manager.packetManage.packageName'),
      dataIndex: 'name',
      key: 'name'
    },
    {
      title: t('node-manager.packetManage.version'),
      dataIndex: 'version',
      key: 'version'
    },
    {
      title: t('common.createdBy'),
      dataIndex: 'created_by',
      key: 'created_by'
    },
    {
      title: t('common.createdAt'),
      dataIndex: 'created_at',
      key: 'created_at',
      ellipsis: true,
      render: (value, { created_at }) => (
        <>
          {created_at
            ? convertToLocalizedTime(new Date(created_at) + '')
            : '--'}
        </>
      )
    },
    {
      title: t('common.actions'),
      key: 'action',
      dataIndex: 'action',
      width: 120,
      fixed: 'right',
      render: (_, { id }) => (
        <Permission requiredPermissions={['Delete']}>
          <Popconfirm
            title={t(`common.delete`)}
            description={t(`node-manager.packetManage.deleteInfo`)}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
            onConfirm={() => {
              handleDelete(id);
            }}
          >
            <Button type="link">{t('common.delete')}</Button>
          </Popconfirm>
        </Permission>
      )
    }
  ];

  return detailColumns;
};

export { useHandleCopy, useDetailColumns };
