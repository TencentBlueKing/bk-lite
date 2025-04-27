import { ColumnItem } from '@/types';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { Button, Popconfirm } from 'antd';
import Permission from '@/components/permission';

export const useDetailColumns = ({
  handleDelete,
}: {
  handleDelete: (id: number) => void;
}): ColumnItem[] => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const detailColumns: ColumnItem[] = [
    {
      title: t('node-manager.collector.packageName'),
      dataIndex: 'name',
      key: 'name',
      width: 120,
    },
    {
      title: t('node-manager.collector.version'),
      dataIndex: 'version',
      key: 'version',
      width: 120,
    },
    {
      title: t('common.createdBy'),
      dataIndex: 'created_by',
      key: 'created_by',
      width: 120,
    },
    {
      title: t('common.createdAt'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 120,
      ellipsis: true,
      render: (value, { created_at }) => (
        <>
          {created_at
            ? convertToLocalizedTime(new Date(created_at) + '')
            : '--'}
        </>
      ),
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
            title={t(`node-manager.collector.delete`)}
            description={t(`node-manager.collector.deleteInfo`)}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
            onConfirm={() => {
              handleDelete(id);
            }}
          >
            <Button type="link">{t('common.delete')}</Button>
          </Popconfirm>
        </Permission>
      ),
    },
  ];

  return detailColumns;
};
