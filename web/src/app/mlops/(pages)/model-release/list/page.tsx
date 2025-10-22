'use client';
import { useState, useRef, useEffect } from "react";
import useMlopsTaskApi from "@/app/mlops/api/task";
import useMlopsModelReleaseApi from "@/app/mlops/api/modelRelease";
import CustomTable from "@/components/custom-table";
import { useTranslation } from "@/utils/i18n";
import { Button, Popconfirm, Switch, message, Tree, type TreeDataNode } from "antd";
import { PlusOutlined } from '@ant-design/icons';
import PageLayout from '@/components/page-layout';
import TopSection from "@/components/top-section";
import ReleaseModal from "./releaseModal";
import PermissionWrapper from '@/components/permission';
import { ModalRef, Option, Pagination, TableData } from "@/app/mlops/types";
import { ColumnItem } from "@/types";
import { TrainJob } from "@/app/mlops/types/task";


const ModelRelease = () => {
  const { t } = useTranslation();
  const modalRef = useRef<ModalRef>(null);
  const { getAnomalyTaskList, getLogClusteringTaskList, getTimeSeriesTaskList, getClassificationTaskList } = useMlopsTaskApi();
  const {
    getAnomalyServingsList, deleteAnomalyServing, updateAnomalyServings,
    getTimeSeriesPredictServingsList, deleteTimeSeriesPredictServing, updateTimeSeriesPredictServings,
    getLogClusteringServingsList, deleteLogClusteringServing, updateLogClusteringServings,
    getClassificationServingsList, deleteClassificationServing, updateClassificationServings, classificationReason
  } = useMlopsModelReleaseApi();
  const [trainjobs, setTrainjobs] = useState<Option[]>([]);
  const [tableData, setTableData] = useState<TableData[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20
  });

  const treeData: TreeDataNode[] = [
    {
      title: t(`model-release.title`),
      key: 'modelRelease',
      selectable: false,
      children: [
        {
          title: t(`datasets.anomaly`),
          key: 'anomaly',
        },
        {
          title: t(`datasets.rasa`),
          key: 'rasa'
        },
        {
          title: t(`datasets.timeseriesPredict`),
          key: 'timeseries_predict'
        },
        {
          title: t(`datasets.logClustering`),
          key: 'log_clustering'
        },
        {
          title: t(`datasets.classification`),
          key: 'classification'
        }
      ]
    }
  ];

  const columns: ColumnItem[] = [
    {
      title: t(`model-release.modelName`),
      dataIndex: 'name',
      key: 'name'
    },
    {
      title: t(`model-release.modelDescription`),
      dataIndex: 'description',
      key: 'description'
    },
    {
      title: t(`model-release.publishStatus`),
      dataIndex: 'status',
      key: 'status',
      render: (_, record) => {
        return <Switch checked={record.status === 'active'} onChange={(value: boolean) => handleModelAcitve(record.id, value)} />
      }
    },
    {
      title: t(`common.action`),
      dataIndex: 'action',
      key: 'action',
      width: 180,
      render: (_, record: TableData) => {
        const [key] = selectedKeys;
        return (<>
          {key === 'classification' &&
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button type="link" className="mr-2" onClick={() => testPredirect(record)}>测试</Button>
            </PermissionWrapper>
          }
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button type="link" className="mr-2" onClick={() => handleEdit(record)}>{t(`common.edit`)}</Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']}>
            <Popconfirm
              title={t(`model-release.delModel`)}
              description={t(`model-release.delModelContent`)}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              onConfirm={() => handleDelete(record.id)}
            >
              <Button type="link" danger>{t(`common.delete`)}</Button>
            </Popconfirm>
          </PermissionWrapper>
        </>)
      }
    }
  ];

  const getServingsMap: Record<string, any> = {
    'anomaly': getAnomalyServingsList,
    'rasa': null, // RASA 类型留空
    'log_clustering': getLogClusteringServingsList,
    'timeseries_predict': getTimeSeriesPredictServingsList,
    'classification': getClassificationServingsList
  };

  const getTaskMap: Record<string, any> = {
    'anomaly': getAnomalyTaskList,
    'rasa': null, // RASA 类型留空
    'log_clustering': getLogClusteringTaskList,
    'timeseries_predict': getTimeSeriesTaskList,
    'classification': getClassificationTaskList
  };

  // 删除操作映射
  const deleteMap: Record<string, ((id: number) => Promise<void>) | null> = {
    'anomaly': deleteAnomalyServing,
    'rasa': null, // RASA 类型留空
    'log_clustering': deleteLogClusteringServing,
    'timeseries_predict': deleteTimeSeriesPredictServing,
    'classification': deleteClassificationServing
  };

  // 更新操作映射
  const updateMap: Record<string, ((id: number, params: any) => Promise<void>) | null> = {
    'anomaly': updateAnomalyServings,
    'rasa': null, // RASA 类型留空
    'log_clustering': updateLogClusteringServings,
    'timeseries_predict': updateTimeSeriesPredictServings,
    'classification': updateClassificationServings
  };

  const topSection = (
    <TopSection title={t('model-release.title')} content={t('model-release.detail')} />
  );

  const leftSection = (
    <div className='w-full'>
      <Tree
        treeData={treeData}
        showLine
        selectedKeys={selectedKeys}
        onSelect={(keys) => setSelectedKeys(keys as string[])}
        defaultExpandedKeys={['modelRelease']}
      />
    </div>
  );

  useEffect(() => {
    setSelectedKeys(['anomaly']);
  }, []);

  useEffect(() => {
    getModelServings();
  }, [selectedKeys])

  const publish = (record: any) => {
    modalRef.current?.showModal({ type: 'add', form: record })
  };

  const handleEdit = (record: any) => {
    modalRef.current?.showModal({ type: 'edit', form: record });
  };

  const getModelServings = async () => {
    const [activeTypes] = selectedKeys;
    if (!activeTypes || !getServingsMap[activeTypes] || !getTaskMap[activeTypes]) {
      setTableData([]);
      return;
    }

    setLoading(true);
    try {
      const params = {
        page: pagination.current,
        page_size: pagination.pageSize,
      };

      // 获取任务列表和服务列表
      const [taskList, { count, items }] = await Promise.all([
        getTaskMap[activeTypes]({}),
        getServingsMap[activeTypes](params)
      ]);

      const _data = taskList.map((item: TrainJob) => ({
        label: item.name,
        value: item.id
      }));

      setTrainjobs(_data);
      setTableData(items);
      setPagination((prev) => ({
        ...prev,
        total: count
      }));
    } catch (e) {
      console.log(e);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: number) => {
    const [activeTypes] = selectedKeys;
    if (!activeTypes || !deleteMap[activeTypes]) {
      return;
    }

    try {
      await deleteMap[activeTypes]!(id);
      getModelServings();
      message.success(t('common.delSuccess'));
    } catch (e) {
      console.log(e);
      message.error(t(`common.delFailed`));
    }
  };

  const handleModelAcitve = async (id: number, value: boolean) => {
    const [activeTypes] = selectedKeys;
    if (!activeTypes || !updateMap[activeTypes]) {
      return;
    }

    setLoading(true);
    try {
      const status = value ? 'active' : 'inactive';
      await updateMap[activeTypes]!(id, { status });
      message.success(t('common.updateSuccess'));
    } catch (e) {
      console.log(e);
      message.error(t('common.updateFailed'));
    } finally {
      getModelServings();
    }
  };

  // 测试推理
  const testPredirect = async (serving: any) => {
    const params = {
      serving_id: serving.id,
      model_name: `Classification_RandomForest_${serving.id}`,
      algorithm: "RandomForest",
      model_version: serving.model_version,
      data: [
        {
          "age": 58,
          "bmi": 30.5,
          "hba1c": 8.18,
          "index": 0,
          "gender": "Male",
          "ethnicity": "Asian",
          "diet_score": 5.7,
          "heart_rate": 68,
          "systolic_bp": 134,
          "diastolic_bp": 78,
          "income_level": "Lower-Middle",
          "insulin_level": 6.36,
          "triglycerides": 145,
          "diabetes_stage": "Type 2",
          "smoking_status": "Never",
          "education_level": "Highschool",
          "glucose_fasting": 136,
          "hdl_cholesterol": 41,
          "ldl_cholesterol": 160,
          "cholesterol_total": 239,
          "employment_status": "Employed",
          "waist_to_hip_ratio": 0.89,
          "diabetes_risk_score": 29.6,
          "sleep_hours_per_day": 7.9,
          "glucose_postprandial": 236,
          "hypertension_history": 0,
          "cardiovascular_history": 0,
          "family_history_diabetes": 0,
          "screen_time_hours_per_day": 7.9,
          "alcohol_consumption_per_week": 0,
          "physical_activity_minutes_per_week": 215
        },
        {
          "age": 48,
          "bmi": 23.1,
          "hba1c": 5.63,
          "index": 1,
          "gender": "Female",
          "ethnicity": "White",
          "diet_score": 6.7,
          "heart_rate": 67,
          "systolic_bp": 129,
          "diastolic_bp": 76,
          "income_level": "Middle",
          "insulin_level": 2,
          "triglycerides": 30,
          "diabetes_stage": "No Diabetes",
          "smoking_status": "Former",
          "education_level": "Highschool",
          "glucose_fasting": 93,
          "hdl_cholesterol": 55,
          "ldl_cholesterol": 50,
          "cholesterol_total": 116,
          "employment_status": "Employed",
          "waist_to_hip_ratio": 0.8,
          "diabetes_risk_score": 23,
          "sleep_hours_per_day": 6.5,
          "glucose_postprandial": 150,
          "hypertension_history": 0,
          "cardiovascular_history": 0,
          "family_history_diabetes": 0,
          "screen_time_hours_per_day": 8.7,
          "alcohol_consumption_per_week": 1,
          "physical_activity_minutes_per_week": 143
        },
        {
          "age": 60,
          "bmi": 22.2,
          "hba1c": 7.51,
          "index": 2,
          "gender": "Male",
          "ethnicity": "Hispanic",
          "diet_score": 6.4,
          "heart_rate": 74,
          "systolic_bp": 115,
          "diastolic_bp": 73,
          "income_level": "Middle",
          "insulin_level": 5.07,
          "triglycerides": 36,
          "diabetes_stage": "Type 2",
          "smoking_status": "Never",
          "education_level": "Highschool",
          "glucose_fasting": 118,
          "hdl_cholesterol": 66,
          "ldl_cholesterol": 99,
          "cholesterol_total": 213,
          "employment_status": "Unemployed",
          "waist_to_hip_ratio": 0.81,
          "diabetes_risk_score": 44.7,
          "sleep_hours_per_day": 10,
          "glucose_postprandial": 195,
          "hypertension_history": 0,
          "cardiovascular_history": 0,
          "family_history_diabetes": 1,
          "screen_time_hours_per_day": 8.1,
          "alcohol_consumption_per_week": 1,
          "physical_activity_minutes_per_week": 57
        },
        {
          "age": 74,
          "bmi": 26.8,
          "hba1c": 9.03,
          "index": 3,
          "gender": "Female",
          "ethnicity": "Black",
          "diet_score": 3.4,
          "heart_rate": 68,
          "systolic_bp": 120,
          "diastolic_bp": 93,
          "income_level": "Low",
          "insulin_level": 5.28,
          "triglycerides": 140,
          "diabetes_stage": "Type 2",
          "smoking_status": "Never",
          "education_level": "Highschool",
          "glucose_fasting": 139,
          "hdl_cholesterol": 50,
          "ldl_cholesterol": 79,
          "cholesterol_total": 171,
          "employment_status": "Retired",
          "waist_to_hip_ratio": 0.88,
          "diabetes_risk_score": 38.2,
          "sleep_hours_per_day": 6.6,
          "glucose_postprandial": 253,
          "hypertension_history": 0,
          "cardiovascular_history": 0,
          "family_history_diabetes": 0,
          "screen_time_hours_per_day": 5.2,
          "alcohol_consumption_per_week": 0,
          "physical_activity_minutes_per_week": 49
        },
        {
          "age": 46,
          "bmi": 21.2,
          "hba1c": 7.2,
          "index": 4,
          "gender": "Male",
          "ethnicity": "White",
          "diet_score": 7.2,
          "heart_rate": 67,
          "systolic_bp": 92,
          "diastolic_bp": 67,
          "income_level": "Middle",
          "insulin_level": 12.74,
          "triglycerides": 160,
          "diabetes_stage": "Type 2",
          "smoking_status": "Never",
          "education_level": "Graduate",
          "glucose_fasting": 137,
          "hdl_cholesterol": 52,
          "ldl_cholesterol": 125,
          "cholesterol_total": 210,
          "employment_status": "Retired",
          "waist_to_hip_ratio": 0.78,
          "diabetes_risk_score": 23.5,
          "sleep_hours_per_day": 7.4,
          "glucose_postprandial": 184,
          "hypertension_history": 0,
          "cardiovascular_history": 0,
          "family_history_diabetes": 0,
          "screen_time_hours_per_day": 5,
          "alcohol_consumption_per_week": 1,
          "physical_activity_minutes_per_week": 109
        },
        {
          "age": 46,
          "bmi": 26.1,
          "hba1c": 6.03,
          "index": 5,
          "gender": "Female",
          "ethnicity": "White",
          "diet_score": 9,
          "heart_rate": 57,
          "systolic_bp": 95,
          "diastolic_bp": 81,
          "income_level": "Upper-Middle",
          "insulin_level": 8.77,
          "triglycerides": 179,
          "diabetes_stage": "Pre-Diabetes",
          "smoking_status": "Never",
          "education_level": "Highschool",
          "glucose_fasting": 100,
          "hdl_cholesterol": 61,
          "ldl_cholesterol": 119,
          "cholesterol_total": 218,
          "employment_status": "Employed",
          "waist_to_hip_ratio": 0.85,
          "diabetes_risk_score": 23.5,
          "sleep_hours_per_day": 6.2,
          "glucose_postprandial": 133,
          "hypertension_history": 0,
          "cardiovascular_history": 0,
          "family_history_diabetes": 0,
          "screen_time_hours_per_day": 5.4,
          "alcohol_consumption_per_week": 2,
          "physical_activity_minutes_per_week": 124
        },
        {
          "age": 75,
          "bmi": 25.1,
          "hba1c": 5.24,
          "index": 6,
          "gender": "Female",
          "ethnicity": "White",
          "diet_score": 9.2,
          "heart_rate": 81,
          "systolic_bp": 129,
          "diastolic_bp": 77,
          "income_level": "Upper-Middle",
          "insulin_level": 10.14,
          "triglycerides": 155,
          "diabetes_stage": "Pre-Diabetes",
          "smoking_status": "Never",
          "education_level": "Graduate",
          "glucose_fasting": 101,
          "hdl_cholesterol": 46,
          "ldl_cholesterol": 161,
          "cholesterol_total": 238,
          "employment_status": "Retired",
          "waist_to_hip_ratio": 0.88,
          "diabetes_risk_score": 36.1,
          "sleep_hours_per_day": 7.8,
          "glucose_postprandial": 100,
          "hypertension_history": 1,
          "cardiovascular_history": 0,
          "family_history_diabetes": 0,
          "screen_time_hours_per_day": 8,
          "alcohol_consumption_per_week": 0,
          "physical_activity_minutes_per_week": 53
        },
        {
          "age": 62,
          "bmi": 23.9,
          "hba1c": 7.04,
          "index": 7,
          "gender": "Male",
          "ethnicity": "White",
          "diet_score": 4.1,
          "heart_rate": 76,
          "systolic_bp": 128,
          "diastolic_bp": 83,
          "income_level": "Middle",
          "insulin_level": 8.96,
          "triglycerides": 120,
          "diabetes_stage": "Type 2",
          "smoking_status": "Current",
          "education_level": "Postgraduate",
          "glucose_fasting": 110,
          "hdl_cholesterol": 49,
          "ldl_cholesterol": 159,
          "cholesterol_total": 241,
          "employment_status": "Unemployed",
          "waist_to_hip_ratio": 0.86,
          "diabetes_risk_score": 34.2,
          "sleep_hours_per_day": 9,
          "glucose_postprandial": 189,
          "hypertension_history": 1,
          "cardiovascular_history": 1,
          "family_history_diabetes": 0,
          "screen_time_hours_per_day": 12.9,
          "alcohol_consumption_per_week": 1,
          "physical_activity_minutes_per_week": 75
        },
        {
          "age": 42,
          "bmi": 24.7,
          "hba1c": 6.9,
          "index": 8,
          "gender": "Male",
          "ethnicity": "Black",
          "diet_score": 6.7,
          "heart_rate": 72,
          "systolic_bp": 103,
          "diastolic_bp": 71,
          "income_level": "Lower-Middle",
          "insulin_level": 5.7,
          "triglycerides": 98,
          "diabetes_stage": "Type 2",
          "smoking_status": "Current",
          "education_level": "Highschool",
          "glucose_fasting": 116,
          "hdl_cholesterol": 33,
          "ldl_cholesterol": 132,
          "cholesterol_total": 187,
          "employment_status": "Employed",
          "waist_to_hip_ratio": 0.84,
          "diabetes_risk_score": 26.7,
          "sleep_hours_per_day": 8.5,
          "glucose_postprandial": 172,
          "hypertension_history": 0,
          "cardiovascular_history": 1,
          "family_history_diabetes": 0,
          "screen_time_hours_per_day": 8.5,
          "alcohol_consumption_per_week": 1,
          "physical_activity_minutes_per_week": 114
        },
        {
          "age": 59,
          "bmi": 26.7,
          "hba1c": 4.99,
          "index": 9,
          "gender": "Female",
          "ethnicity": "White",
          "diet_score": 8.2,
          "heart_rate": 70,
          "systolic_bp": 124,
          "diastolic_bp": 81,
          "income_level": "Middle",
          "insulin_level": 4.49,
          "triglycerides": 104,
          "diabetes_stage": "No Diabetes",
          "smoking_status": "Current",
          "education_level": "Graduate",
          "glucose_fasting": 76,
          "hdl_cholesterol": 52,
          "ldl_cholesterol": 103,
          "cholesterol_total": 188,
          "employment_status": "Employed",
          "waist_to_hip_ratio": 0.81,
          "diabetes_risk_score": 30,
          "sleep_hours_per_day": 5.3,
          "glucose_postprandial": 109,
          "hypertension_history": 0,
          "cardiovascular_history": 0,
          "family_history_diabetes": 0,
          "screen_time_hours_per_day": 7.4,
          "alcohol_consumption_per_week": 3,
          "physical_activity_minutes_per_week": 86
        },
        {
          "age": 43,
          "bmi": 24.8,
          "hba1c": 7.34,
          "index": 10,
          "gender": "Female",
          "ethnicity": "White",
          "diet_score": 7.5,
          "heart_rate": 66,
          "systolic_bp": 109,
          "diastolic_bp": 85,
          "income_level": "Middle",
          "insulin_level": 14.48,
          "triglycerides": 182,
          "diabetes_stage": "Type 2",
          "smoking_status": "Never",
          "education_level": "Highschool",
          "glucose_fasting": 124,
          "hdl_cholesterol": 44,
          "ldl_cholesterol": 79,
          "cholesterol_total": 144,
          "employment_status": "Employed",
          "waist_to_hip_ratio": 0.86,
          "diabetes_risk_score": 25.3,
          "sleep_hours_per_day": 5.2,
          "glucose_postprandial": 177,
          "hypertension_history": 0,
          "cardiovascular_history": 0,
          "family_history_diabetes": 0,
          "screen_time_hours_per_day": 5.4,
          "alcohol_consumption_per_week": 1,
          "physical_activity_minutes_per_week": 118
        },
        {
          "age": 43,
          "bmi": 22.3,
          "hba1c": 7.4,
          "index": 11,
          "gender": "Female",
          "ethnicity": "White",
          "diet_score": 7.2,
          "heart_rate": 66,
          "systolic_bp": 119,
          "diastolic_bp": 69,
          "income_level": "Middle",
          "insulin_level": 12.93,
          "triglycerides": 49,
          "diabetes_stage": "Type 2",
          "smoking_status": "Former",
          "education_level": "Highschool",
          "glucose_fasting": 117,
          "hdl_cholesterol": 59,
          "ldl_cholesterol": 61,
          "cholesterol_total": 163,
          "employment_status": "Employed",
          "waist_to_hip_ratio": 0.76,
          "diabetes_risk_score": 18.5,
          "sleep_hours_per_day": 6.9,
          "glucose_postprandial": 183,
          "hypertension_history": 1,
          "cardiovascular_history": 0,
          "family_history_diabetes": 0,
          "screen_time_hours_per_day": 5.1,
          "alcohol_consumption_per_week": 1,
          "physical_activity_minutes_per_week": 167
        }
      ],
    };
    message.info('推理开始....')
    console.log('params: ', params);
    const result = await classificationReason(params);
    console.log('result: ', result);
    if (result.success) {
      message.success('推理成功')
    } else {
      message.error('推理失败')
    }
  };

  return (
    <>
      <PageLayout
        topSection={topSection}
        leftSection={leftSection}
        rightSection={
          (
            <>
              <div className="flex justify-end mb-2">
                <PermissionWrapper requiredPermissions={['Add']}>
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => publish({})}>{t(`model-release.modelRelease`)}</Button>
                </PermissionWrapper>
              </div>
              <div className="flex-1 relative">
                <div className="absolute w-full">
                  <CustomTable
                    scroll={{ x: '100%', y: 'calc(100vh - 420px)' }}
                    columns={columns}
                    dataSource={tableData}
                    loading={loading}
                    rowKey='id'
                    pagination={pagination}
                  />
                </div>
              </div>
            </>
          )
        }
      />
      <ReleaseModal ref={modalRef} trainjobs={trainjobs} activeTag={selectedKeys} onSuccess={() => getModelServings()} />
    </>
  )
};

export default ModelRelease;