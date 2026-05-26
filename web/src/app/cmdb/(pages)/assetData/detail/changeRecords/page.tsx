'use client';

import React, { useState, useEffect, useRef } from 'react';
import changeRecordsStyle from './index.module.scss';
import { useChangeRecordApi, useModelApi } from '@/app/cmdb/api';
import RecordDetail from './recordDetail';
import { DatePicker, Timeline, Spin, Empty, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useSearchParams } from 'next/navigation';
import { useCommon } from '@/app/cmdb/context/common';
import {
  RecordsEnum,
  RecordItemList,
  RecordItem,
  detailRef,
} from '@/app/cmdb/types/assetData';
import {
  AttrFieldType,
  UserItem,
  AssoTypeItem,
} from '@/app/cmdb/types/assetManage';

const { RangePicker } = DatePicker;

// 实例历史默认只展示高信号场景，避免被自动采集 / 模型管理变更淹没
const DEFAULT_INSTANCE_SCENARIOS = [
  'device_lifecycle',
  'relation_change',
  'ordinary_attribute_change',
];

const ChangeRecords: React.FC = () => {
  const changeRecordApi = useChangeRecordApi();
  const modelApi = useModelApi();
  const { t } = useTranslation();
  const commonContext = useCommon();
  const users = useRef(commonContext?.userList || []);
  const userList: UserItem[] = users.current;
  const modelList = commonContext?.modelList || [];
  const detailRef = useRef<detailRef>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [enumList, setEnumList] = useState<RecordsEnum>({});
  const [scenarioEnum, setScenarioEnum] = useState<Record<string, string>>({});
  const [recordList, setRecordList] = useState<RecordItem[]>([]);
  const [attrList, setAttrList] = useState<AttrFieldType[]>([]);
  const [assoTypes, setAssoTypes] = useState<AssoTypeItem[]>([]);
  const [scenarios, setScenarios] = useState<string[]>(DEFAULT_INSTANCE_SCENARIOS);
  const [dateRange, setDateRange] = useState<[string, string] | null>(null);
  const searchParams = useSearchParams();
  const modelId: string = searchParams.get('model_id') || '';
  const instId: string = searchParams.get('inst_id') || '';

  useEffect(() => {
    initData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const showDetailModal = (log: RecordItemList) => {
    detailRef.current?.showModal({
      title: enumList[log.type] + showModelName(log.model_id),
      subTitle: '',
      recordRow: log,
    });
  };

  const showModelName = (id: unknown) => {
    return modelList.find((item) => item.model_id === id)?.model_name || '--';
  };

  const initData = async () => {
    const getChangeRecordLists = changeRecordApi.getChangeRecords(
      getParams(scenarios, dateRange)
    );
    const getEnumData = changeRecordApi.getChangeRecordEnumData();
    const getScenarioEnum = changeRecordApi.getChangeRecordScenarioEnum();
    const getAttrList = modelApi.getModelAttrList(modelId);
    const getAssoType = modelApi.getModelAssociationTypes();
    try {
      setLoading(true);
      Promise.all([
        getChangeRecordLists,
        getEnumData,
        getAttrList,
        getAssoType,
        getScenarioEnum,
      ])
        .then((res) => {
          setEnumList(res[1]);
          dealRecordList(res[0]);
          setAttrList(res[2] || []);
          setAssoTypes(res[3] || []);
          setScenarioEnum(res[4] || {});
        })
        .finally(() => {
          setLoading(false);
        });
    } catch {
      setLoading(false);
    }
  };

  const getParams = (
    scenarioList: string[] = scenarios,
    range: [string, string] | null = dateRange
  ) => {
    const params: any = {
      model_id: modelId,
      inst_id: instId,
    };
    if (scenarioList?.length) {
      params.scenarios = scenarioList.join(',');
    }
    if (range && range[0]) params.created_at_after = range[0];
    if (range && range[1]) params.created_at_before = range[1];
    return params;
  };

  const reload = async (
    nextScenarios: string[] = scenarios,
    nextRange: [string, string] | null = dateRange
  ) => {
    setLoading(true);
    try {
      const data = await changeRecordApi.getChangeRecords(
        getParams(nextScenarios, nextRange)
      );
      dealRecordList(data);
    } finally {
      setLoading(false);
    }
  };

  const dealRecordList = (data: RecordItemList[]) => {
    const recordData = data
      .map((item: RecordItemList) => ({
        ...item,
        created_at: new Date(item.created_at),
      }))
      .reduce((acc: any, item: any) => {
        const yearMonth = item.created_at.toISOString().slice(0, 7);
        if (!acc[yearMonth]) {
          acc[yearMonth] = [];
        }
        acc[yearMonth].push(item);
        return acc;
      }, {});
    const records = Object.keys(recordData)
      .map((key) => ({
        date: key,
        list: recordData[key]
          .map((item: any) => ({
            ...item,
            type: item.type,
            created_at: item.created_at.toISOString(),
            operator: item.operator,
          }))
          .sort(
            (a: any, b: any) =>
              new Date(b.created_at).getTime() -
              new Date(a.created_at).getTime()
          ),
      }))
      .sort(
        (a: any, b) => new Date(b.date).getTime() - new Date(a.date).getTime()
      );
    setRecordList(records);
  };

  const handleDateChange = async (dateString: any = []) => {
    const range: [string, string] | null =
      dateString && (dateString[0] || dateString[1])
        ? [dateString[0] || '', dateString[1] || '']
        : null;
    setDateRange(range);
    reload(scenarios, range);
  };

  const handleScenarioChange = (value: string[]) => {
    const next = value || [];
    setScenarios(next);
    reload(next, dateRange);
  };

  const scenarioOptions = Object.keys(scenarioEnum).map((key) => ({
    label: scenarioEnum[key],
    value: key,
  }));

  return (
    <Spin spinning={loading}>
      <div className={changeRecordsStyle.changeRecords}>
        <div className="flex justify-between items-center mb-4 gap-4 flex-wrap">
          <Select
            mode="multiple"
            className="w-[360px]"
            placeholder={t('OperationLog.scenario')}
            value={scenarios}
            onChange={handleScenarioChange}
            options={scenarioOptions}
            allowClear
            maxTagCount="responsive"
          />
          <RangePicker
            className="w-[400px]"
            showTime
            onChange={(value, dateString) => handleDateChange(dateString)}
          />
        </div>
        {recordList.length ? (
          <div
            className={`bg-[var(--color-fill-2)] rounded-lg px-[20px] py-[10px] ${changeRecordsStyle.list}`}
          >
            {recordList.map((event, index) => (
              <div key={index}>
                <h4 className="text-[15px] font-semibold mb-[10px]">
                  {event.date}
                </h4>
                <Timeline>
                  {event.list.map((log, logIndex) => (
                    <Timeline.Item key={logIndex}>
                      <div
                        onClick={() => showDetailModal(log)}
                        className="cursor-pointer"
                      >
                        <div className="mb-[4px]">
                          {enumList[log.type] + showModelName(log.model_id)}
                          {log.scenario && scenarioEnum[log.scenario] ? (
                            <span className="ml-2 text-[12px] text-[var(--color-text-3)]">
                              [{scenarioEnum[log.scenario]}]
                            </span>
                          ) : null}
                        </div>
                        <div className="flex items-center text-[12px]">
                          <span className="text-[var(--color-text-3)]">
                            {log.created_at}
                          </span>
                          <span
                            className={`${changeRecordsStyle.operator} text-[var(--color-text-3)]`}
                          >
                            {t('Model.operator')}: {log.operator}
                          </span>
                        </div>
                      </div>
                    </Timeline.Item>
                  ))}
                </Timeline>
              </div>
            ))}
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </div>
      <RecordDetail
        ref={detailRef}
        userList={userList}
        propertyList={attrList}
        modelList={modelList}
        enumList={enumList}
        connectTypeList={assoTypes}
      />
    </Spin>
  );
};

export default ChangeRecords;
