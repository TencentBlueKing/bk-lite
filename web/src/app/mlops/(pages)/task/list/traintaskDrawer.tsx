import { Drawer, message, Button } from "antd";
import { useTranslation } from "@/utils/i18n";
import { useAuth } from "@/context/auth";
// import { Tooltip } from 'antd';
import useMlopsTaskApi from "@/app/mlops/api/task";
// import SimpleLineChart from "@/app/mlops/components/charts/simpleLineChart";
import TrainTaskHistory from "./traintaskHistory";
import TrainTaskDetail from "./traintaskDetail";
import { useEffect, useMemo, useState } from "react";
import styles from './index.module.scss'

const TrainTaskDrawer = ({ open, onCancel, selectId, activeTag }:
  {
    open: boolean,
    onCancel: () => void,
    selectId: number | null,
    activeTag: string[]
  }) => {
  const { t } = useTranslation();
  const authContext = useAuth();
  const { getTrainTaskState } = useMlopsTaskApi();
  const [showList, setShowList] = useState<boolean>(true);
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [historyData, setHistoryData] = useState<any[]>([]);
  const [activeRunID, setActiveRunID] = useState<string>('');
  const [key] = activeTag;

  const currentDetail = useMemo(() => {
    return historyData?.find((item: any) => item.run_id === activeRunID);
  }, [activeRunID]);

  useEffect(() => {
    if (open) {
      getStateData();
    }
  }, [open]);

  const getStateData = async () => {
    setTableLoading(true);
    try {
      const { data } = await getTrainTaskState(selectId as number, key);
      setHistoryData(data);
      // setHistoryData(Object.entries(data?.metrics_history) || []);
    } catch (e) {
      console.log(e);
      message.error(t(`traintask.getTrainStatusFailed`));
      setHistoryData([]);
    } finally {
      setTableLoading(false);
    }
  };

  const openDetail = (record: any) => {
    setActiveRunID(record?.run_id);
    setShowList(false);
  };

  const downloadModel = async (record: any) => {
    try {
      message.info(t(`traintask.downloadStart`));
      
      const response = await fetch(
        `/api/proxy/mlops/timeseries_predict_train_jobs/download_model/${record.run_id}/`,
        {
          method: 'GET',
          headers: {
            Authorization: `Bearer ${authContext?.token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error(`下载失败: ${response.status}`);
      }

      const blob = await response.blob();
      
      // 从 Content-Disposition 头提取文件名
      const contentDisposition = response.headers.get('content-disposition');
      let fileName = `model_${record.run_id.substring(0, 8)}.zip`;
      if (contentDisposition) {
        const match = contentDisposition.match(/filename[^;=\n]*=(['\"]?)([^'"\n]*?)\1/);
        if (match && match[2]) {
          fileName = match[2];
        }
      }

      // 创建下载链接
      const fileUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = fileUrl;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(fileUrl);
    } catch (error: any) {
      console.error(t(`traintask.downloadFailed`), error);
      message.error(error.message || t('common.errorFetch'));
    }
  };

  return (
    <Drawer
      className={`${styles.drawer}`}
      width={1000}
      title={t('traintask.trainDetail')}
      open={open}
      onClose={() => {
        setShowList(true);
        onCancel();
      }}
      footer={!showList ? [
        <Button
          key='back'
          type="primary"
          // icon={<LeftOutlined />}
          onClick={() => setShowList(true)}
          className="float-right"
        >
          {t(`mlops-common.backToList`)}
        </Button>
      ] : [
        <Button key="refresh" type="primary" className="float-right" disabled={tableLoading} onClick={getStateData}>
          {t(`mlops-common.refreshList`)}
        </Button>
      ]}
    >
      <div className="drawer-content">
        {showList ?
          <TrainTaskHistory
            data={historyData}
            loading={tableLoading}
            openDetail={openDetail}
            downloadModel={downloadModel}
          /> :
          <TrainTaskDetail activeKey={key} backToList={() => setShowList(true)} metricData={currentDetail} />}
      </div>
    </Drawer>
  );
};

export default TrainTaskDrawer;