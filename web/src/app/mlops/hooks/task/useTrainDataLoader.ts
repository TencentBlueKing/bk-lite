import useMlopsManageApi from "@/app/mlops/api/manage"
import { useCallback } from "react";
import { TrainData } from "@/app/mlops/types/manage";
import { DatasetReleaseKey } from "../../types";


const useTrainDataLoader = () => {
  const {
    getTrainDataByDataset,
    getTrainDataInfo,
  } = useMlopsManageApi();

  const loadTrainOptions = useCallback(async (datasetId: number, key: string) => {
    const trainData = await getTrainDataByDataset({ key: key as DatasetReleaseKey, dataset: datasetId });

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
  }, [getTrainDataByDataset]);

  const getDatasetByTrainId = useCallback(async (trianDataId: number, key: string) => {
    const { dataset, metadata } = await getTrainDataInfo(trianDataId, key as DatasetReleaseKey, false, true);
    return { dataset, metadata };
  }, [getTrainDataInfo]);

  return { loadTrainOptions, getDatasetByTrainId }
};

export default useTrainDataLoader;