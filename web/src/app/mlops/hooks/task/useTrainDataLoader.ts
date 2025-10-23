import useMlopsManageApi from "@/app/mlops/api/manage"
import { useCallback } from "react";
import { TrainData } from "@/app/mlops/types/manage";


const useTrainDataLoader = () => {
  const {
    getAnomalyTrainData,
    getLogClusteringTrainData,
    getTimeSeriesPredictTrainData,
    getClassificationTrainData,
    getAnomalyTrainDataInfo,
    getLogClusteringTrainDataInfo,
    getTimeSeriesPredictTrainDataInfo,
    getClassificationTrainDataInfo
  } = useMlopsManageApi();
  const getTrainData: Record<string, any> = {
    'anomaly': getAnomalyTrainData,
    'log_clustering': getLogClusteringTrainData,
    'timeseries_predict': getTimeSeriesPredictTrainData,
    'classification': getClassificationTrainData
  };
  const getTrainDataInfo: Record<string, any> = {
    'anomaly': getAnomalyTrainDataInfo,
    'log_clustering': getLogClusteringTrainDataInfo,
    'timeseries_predict': getTimeSeriesPredictTrainDataInfo,
    'classification': getClassificationTrainDataInfo
  };

  const loadTrainOptions = useCallback(async (datasetId: number, key: string) => {
    const trainData = await getTrainData[key]({ dataset: datasetId });

    return {
      trainOption: trainData.filter((item: TrainData) => item.is_train_data).map((item: TrainData) => ({
        label: item.name,
        value: item.id
      })),
      valOption: trainData.filter((item: TrainData) => item.is_val_data).map((item: TrainData) => ({
        label: item.name,
        value: item.id
      })),
      testOption: trainData.filter((item: TrainData) => item.is_test_data).map((item: TrainData) => ({
        label: item.name,
        value: item.id
      }))
    }
  }, [getAnomalyTrainData]);

  const getDatasetByTrainId = useCallback(async (trianDataId: number, key: string) => {
    const { dataset } = await getTrainDataInfo[key](trianDataId, false, false);
    return dataset;
  }, [getAnomalyTrainDataInfo]);

  return { loadTrainOptions, getDatasetByTrainId }
};

export default useTrainDataLoader;