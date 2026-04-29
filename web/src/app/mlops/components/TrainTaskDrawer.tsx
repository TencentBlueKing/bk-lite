import { Drawer, message, Button } from "antd";
import { useTranslation } from "@/utils/i18n";
import { useAuth } from "@/context/auth";
import useMlopsTaskApi from "@/app/mlops/api/task";
import TrainTaskHistory from "./TrainTaskHistory";
import TrainTaskDetail from "./TrainTaskDetail";
import { useEffect, useMemo, useState, useCallback } from "react";
import { TRAINJOB_MAP } from "@/app/mlops/constants";
import { isValidAlgorithmType } from "@/app/mlops/types";
import type { TrainTaskHistory as TrainTaskHistoryItem } from "@/app/mlops/types";
import styles from './traintask.module.scss'

const TrainTaskDrawer = ({ open, onCancel, selectId, activeTag }:
  {
    open: boolean,
    onCancel: () => void,
    selectId: number | null,
    activeTag: string[]
  }) => {
  const { t } = useTranslation();
  const authContext = useAuth();
  const { getTrainTaskState, deleteTrainRun } = useMlopsTaskApi();
  const [showList, setShowList] = useState<boolean>(true);
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [historyData, setHistoryData] = useState<TrainTaskHistoryItem[]>([]);
  const [activeRunID, setActiveRunID] = useState<string>('');
  const [rawKey] = activeTag;
  const key = isValidAlgorithmType(rawKey) ? rawKey : undefined;

  // 分页状态
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 10,
  });

  const currentDetail = useMemo(() => {
    return historyData?.find((item) => item.run_id === activeRunID);
  }, [activeRunID, historyData]);

  useEffect(() => {
    if (open) {
      // 打开时重置分页到第一页
      setPagination(prev => ({ ...prev, current: 1 }));
      getStateData(1, pagination.pageSize);
    }
  }, [open]);

  // 分页变化时重新请求
  useEffect(() => {
    if (open && selectId) {
      getStateData(pagination.current, pagination.pageSize);
    }
  }, [pagination.current, pagination.pageSize]);

  const getStateData = useCallback(async (page: number = pagination.current, pageSize: number = pagination.pageSize) => {
    if (!selectId || !key) return;
    setTableLoading(true);
    try {
      const { items, count } = await getTrainTaskState({
        id: selectId,
        activeTap: key,
        page,
        page_size: pageSize
      });
      setHistoryData(items || []);
      setPagination(prev => ({
        ...prev,
        total: count || 0
      }));
    } catch (e) {
      console.error(e);
      message.error(t(`traintask.getTrainStatusFailed`));
      setHistoryData([]);
    } finally {
      setTableLoading(false);
    }
  }, [selectId, key, getTrainTaskState, t]);

  const handlePaginationChange = (value: { current: number; pageSize: number; total: number }) => {
    setPagination(value);
  };

  const openDetail = (record: TrainTaskHistoryItem) => {
    setActiveRunID(record?.run_id);
    setShowList(false);
  };

  const handleDeleteRun = async (record: TrainTaskHistoryItem) => {
    if (!selectId || !key) return;
    try {
      await deleteTrainRun(selectId, record.run_id, key);
      message.success(t('common.delSuccess'));
      const isLastItemOnPage = historyData.length === 1 && pagination.current > 1;
      const nextPage = isLastItemOnPage ? pagination.current - 1 : pagination.current;
      if (isLastItemOnPage) {
        setPagination(prev => ({ ...prev, current: nextPage }));
      }
      await getStateData(nextPage, pagination.pageSize);
    } catch (error) {
      console.error(error);
      message.error(t('common.delFailed'));
    }
  };

  const downloadModel = async (record: TrainTaskHistoryItem) => {
    const [tagName] = activeTag;
    try {
      message.info(t(`mlops-common.downloadStart`));

      const response = await fetch(
        `/api/proxy/mlops/${TRAINJOB_MAP[tagName]}/download_model/${record.run_id}/`,
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

  const handleRefresh = () => {
    getStateData(pagination.current, pagination.pageSize);
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
          onClick={() => setShowList(true)}
          className="float-right"
        >
          {t(`mlops-common.backToList`)}
        </Button>
      ] : [
        <Button key="refresh" type="primary" className="float-right" disabled={tableLoading} onClick={handleRefresh}>
          {t(`mlops-common.refreshList`)}
        </Button>
      ]}
    >
      <div className="drawer-content">
        {showList ?
          <TrainTaskHistory
            data={historyData}
            loading={tableLoading}
            pagination={pagination}
            onChange={handlePaginationChange}
            openDetail={openDetail}
            downloadModel={downloadModel}
            deleteRun={handleDeleteRun}
          /> :
          <TrainTaskDetail activeKey={key} backToList={() => setShowList(true)} metricData={currentDetail} />}
      </div>
    </Drawer>
  );
};

export default TrainTaskDrawer;
