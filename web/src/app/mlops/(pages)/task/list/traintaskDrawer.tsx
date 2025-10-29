import { Drawer, message, Button } from "antd";
import { useTranslation } from "@/utils/i18n";
// import { Tooltip } from 'antd';
import useMlopsTaskApi from "@/app/mlops/api/task";
// import SimpleLineChart from "@/app/mlops/components/charts/simpleLineChart";
import TrainTaskHistory from "./traintaskHistory";
import TrainTaskDetail from "./traintaskDetail";
import { useEffect, useMemo, useState } from "react";
import styles from './index.module.scss'
import { LeftOutlined } from "@ant-design/icons";

const TrainTaskDrawer = ({ open, onCancel, selectId, activeTag }:
  {
    open: boolean,
    onCancel: () => void,
    selectId: number | null,
    activeTag: string[]
  }) => {
  const { t } = useTranslation();
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
          type="text"
          icon={<LeftOutlined />}
          onClick={() => setShowList(true)}
          className="back-to-list-btn"
        >
          返回列表
        </Button>
      ] : null}
    >
      <div className="drawer-content">
        {showList ?
          <TrainTaskHistory
            data={historyData}
            loading={tableLoading}
            openDetail={openDetail}
          /> :
          <TrainTaskDetail activeKey={key} backToList={() => setShowList(true)} metricData={currentDetail} />}
      </div>
    </Drawer>
  );
};

export default TrainTaskDrawer;