import CustomTable from "@/components/custom-table"
import { ColumnItem } from "@/types";
import { useTranslation } from "@/utils/i18n";
import { useLocalizedTime } from "@/hooks/useLocalizedTime";
import { Button, Tag } from "antd";

interface TrainTaskHistoryProps {
  data: any[],
  loading: boolean,
  openDetail: (record: any) => void
}

const TrainTaskHistory = ({
  data,
  loading,
  openDetail
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
        return record.status ? (<Tag className=''>
          {record.status}
        </Tag>) : (<p>--</p>)
      }
    },
    {
      title: t(`common.action`),
      dataIndex: 'action',
      key: 'action',
      render: (_, record) => (
        <Button type="link" onClick={() => openDetail(record)}>{t(`common.detail`)}</Button>
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