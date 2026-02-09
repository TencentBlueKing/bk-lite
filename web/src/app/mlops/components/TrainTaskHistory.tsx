import CustomTable from "@/components/custom-table"
import { ColumnItem } from "@/types";
import { useTranslation } from "@/utils/i18n";
import { useLocalizedTime } from "@/hooks/useLocalizedTime";
import { Button, Tag } from "antd";
import PermissionWrapper from '@/components/permission';

interface TrainTaskHistoryProps {
  data: any[],
  loading: boolean,
  openDetail: (record: any) => void,
  downloadModel: (record: any) => void,
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
  openDetail,
  downloadModel
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
            <Button type="link" onClick={() => downloadModel(record)}>{t(`common.download`)}</Button>
          </PermissionWrapper>
        </>
      )
    }
  ]

  return (
    <div className="w-full h-full p-2">
      <CustomTable
        rowKey="run_id"
        columns={columns}
        dataSource={data}
        loading={loading}
      />
    </div>
  )
};

export default TrainTaskHistory;