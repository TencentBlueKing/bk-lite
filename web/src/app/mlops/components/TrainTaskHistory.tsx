import CustomTable from "@/components/custom-table"
import { ColumnItem } from "@/types";
import { useTranslation } from "@/utils/i18n";
import { useLocalizedTime } from "@/hooks/useLocalizedTime";
import { Button, Popconfirm, Tag } from "antd";
import PermissionWrapper from '@/components/permission';
import type { TrainTaskHistory as TrainTaskHistoryItem } from "@/app/mlops/types";

interface TrainTaskHistoryProps {
  data: TrainTaskHistoryItem[],
  loading: boolean,
  pagination: { current: number; total: number; pageSize: number },
  onChange: (value: { current: number; pageSize: number; total: number }) => void,
  openDetail: (record: TrainTaskHistoryItem) => void,
  downloadModel: (record: TrainTaskHistoryItem) => void,
  deleteRun: (record: TrainTaskHistoryItem) => void,
}

const RUN_STATUS_MAP: Record<string, string> = {
  'RUNNING': 'blue',
  'FINISHED': 'green',
  'FAILED': 'red',
  'KILLED': 'volcano'
}

const RUN_TEXT_MAP: Record<string, string> = {
  'RUNNING': 'inProgress',
  'FINISHED': 'completed',
  'FAILED': 'failed',
  'KILLED': 'killed'
}

const TrainTaskHistory = ({
  data,
  loading,
  pagination,
  onChange,
  openDetail,
  downloadModel,
  deleteRun
}: TrainTaskHistoryProps) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const columns: ColumnItem[] = [
    {
      title: t(`common.name`),
      dataIndex: 'run_name',
      key: 'run_name'
    },
    {
      title: t(`mlops-common.createdAt`),
      dataIndex: 'start_time',
      key: 'start_time',
      render: (_, record) => {
        return (<p>{convertToLocalizedTime(record.start_time, 'YYYY-MM-DD HH:mm:ss')}</p>)
      }
    },
    {
      title: t(`traintask.executionTime`),
      dataIndex: 'duration_minutes',
      key: 'duration_minutes',
      render: (_, record) => {
        const duration = record?.duration_minutes || 0;
        return (
          <span>{duration.toFixed(2) + 'min'}</span>
        )
      }
    },
    {
      title: t('mlops-common.status'),
      key: 'status',
      dataIndex: 'status',
      width: 120,
      render: (_, record) => {
        return record.status ?
          (
            <Tag color={RUN_STATUS_MAP[record.status as string]}>
              {t(`mlops-common.${RUN_TEXT_MAP[record.status]}`)}
            </Tag>
          )
          : (<p>--</p>)
      }
    },
    {
      title: t(`common.action`),
      dataIndex: 'action',
      key: 'action',
      render: (_, record) => (
        <>
          <PermissionWrapper requiredPermissions={['View']}>
            <Button type="link" onClick={() => openDetail(record)} className="mr-2">{t(`common.detail`)}</Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['View']}>
            <Button type="link" disabled={record.status !== 'FINISHED'} onClick={() => downloadModel(record)} className="mr-2">{t(`common.download`)}</Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']}>
            <Popconfirm
              title={t('mlops-common.deleteRunConfirm')}
              description={t('mlops-common.deleteRunConfirmContent')}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              onConfirm={() => deleteRun(record)}
              disabled={!record.can_delete_run}
            >
              <Button type="link" danger disabled={!record.can_delete_run}>{t(`common.delete`)}</Button>
            </Popconfirm>
          </PermissionWrapper>
        </>
      )
    }
  ]

  return (
    <div className="w-full h-full p-2">
      <CustomTable
        rowKey="run_id"
        scroll={{ x: '100%', y: 'calc(100vh - 250px)' }}
        columns={columns}
        dataSource={data}
        pagination={pagination}
        loading={loading}
        onChange={onChange}
      />
    </div>
  )
};

export default TrainTaskHistory;