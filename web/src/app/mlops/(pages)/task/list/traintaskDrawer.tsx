import { Drawer, message, Button } from "antd";
import { useTranslation } from "@/utils/i18n";
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
  const { getTrainTaskState, getTimeseriesPredictModelURL } = useMlopsTaskApi();
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
      message.info("等待数据包中")
      const data = await getTimeseriesPredictModelURL(record.run_id);
      const link = document.createElement('a');
      link.href = data.download.url;  // MinIO 预签名 URL
      link.download = data.download.filename;  // 建议的文件名
      link.click();
    } catch (e) {
      console.error(e);
      message.error(t(`common.errorFetch`))
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
          返回列表
        </Button>
      ] : [
        <Button key="refresh" type="primary" className="float-right" disabled={tableLoading} onClick={getStateData}>
          刷新列表
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