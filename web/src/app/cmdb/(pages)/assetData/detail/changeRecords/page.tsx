'use client';

import React, { useState, useEffect, useRef } from 'react';
import changeRecordsStyle from './index.module.scss';
import useApiClient from '@/utils/request';
import RecordDetail from './recordDetail';
import { DatePicker, Timeline, Spin, Empty } from 'antd';
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
  ModelItem,
  Organization,
  UserItem,
  AssoTypeItem,
} from '@/app/cmdb/types/assetManage';

const { RangePicker } = DatePicker;

const ChangeRecords: React.FC = () => {
  const { get, isLoading } = useApiClient();
  const { t } = useTranslation();
  const commonContext = useCommon();
  const authList = useRef(commonContext?.organizations || []);
  const organizationList: Organization[] = authList.current;
  const users = useRef(commonContext?.userList || []);
  const userList: UserItem[] = users.current;
  const detailRef = useRef<detailRef>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [enumList, setEnumList] = useState<RecordsEnum>({});
  const [recordList, setRecordList] = useState<RecordItem[]>([]);
  const [attrList, setAttrList] = useState<AttrFieldType[]>([]);
  const [modelList, setModelList] = useState<ModelItem[]>([]);
  const [assoTypes, setAssoTypes] = useState<AssoTypeItem[]>([]);
  const searchParams = useSearchParams();
  const modelId: string = searchParams.get('model_id') || '';
  const instId: string = searchParams.get('inst_id') || '';

  useEffect(() => {
    if (isLoading) return;
    // 初始加载数据
    initData();
  }, [isLoading]);

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
    const getChangeRecordLists = get('/cmdb/api/change_record/', {
      params: getParams(),
    });
    const getEnumData = get('/cmdb/api/change_record/enum_data/');
    const getAttrList = get(`/cmdb/api/model/${modelId}/attr_list/`);
    const getModelList = get('/cmdb/api/model/');
    const getAssoType = get('/cmdb/api/model/model_association_type/');
    try {
      setLoading(true);
      Promise.all([
        getChangeRecordLists,
        getEnumData,
        getAttrList,
        getModelList,
        getAssoType,
      ])
        .then((res) => {
          const enumData = res[1];
          setEnumList(enumData);
          dealRecordList(res[0]);
          setAttrList(res[2] || []);
          setModelList(res[3] || []);
          setAssoTypes(res[4] || []);
        })
        .finally(() => {
          setLoading(false);
        });
    } catch {
      setLoading(false);
    }
  };

  const getParams = () => {
    return {
      model_id: modelId,
      inst_id: instId,
    };
  };

  const dealRecordList = (data: RecordItemList[]) => {
    const recordData = data
      .map((item: RecordItemList) => ({
        ...item,
        created_at: new Date(item.created_at),
      }))
      .reduce((acc: any, item: any) => {
        const yearMonth = item.created_at.toISOString().slice(0, 7); // 获取年-月
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
          ), // 按内部列表时间倒序排序
      }))
      .sort(
        (a: any, b) => new Date(b.date).getTime() - new Date(a.date).getTime()
      ); // 按外部列表时间倒序排序
    setRecordList(records);
  };

  const handleDateChange = async (dateString: any = []) => {
    const params: any = getParams();
    params.created_at_after = dateString[0] || '';
    params.created_at_before = dateString[1] || '';
    setLoading(true);
    try {
      const data = await get('/cmdb/api/change_record/', {
        params,
      });
      dealRecordList(data);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Spin spinning={loading}>
      <div className={changeRecordsStyle.changeRecords}>
        <div className="flex justify-between items-center mb-4">
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
        groupList={organizationList}
        enumList={enumList}
        connectTypeList={assoTypes}
      />
    </Spin>
  );
};

export default ChangeRecords;
