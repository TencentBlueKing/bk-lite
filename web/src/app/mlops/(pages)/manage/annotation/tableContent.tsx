import CustomTable from "@/components/custom-table";
import { useSearchParams } from 'next/navigation';
import { useEffect, useMemo, useState } from "react";
import { ColumnItem, TableDataItem } from "@/app/mlops/types";
import useMlopsManageApi from "@/app/mlops/api/manage";
import { useTranslation } from "@/utils/i18n";
import PermissionWrapper from '@/components/permission';
import { Button } from "antd";
import { cloneDeep } from "lodash";

const TableContent = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { getLogClusteringTrainDataInfo, updateLogClusteringTrainData, getClassificationTrainDataInfo, updateClassificationTrainData } = useMlopsManageApi();
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [dynamicColumns, setDynamicColumns] = useState<ColumnItem[]>([]);

  const {
    id,
    key
  } = useMemo(() => ({
    id: searchParams.get('id') || '',
    key: searchParams.get('activeTap') || ''
  }), [searchParams]);

  const baseColumns: Record<string, ColumnItem[]> = {
    'log_clustering': [
      {
        title: '日志内容',
        dataIndex: 'name',
        key: 'name',
        align: 'center'
      },
      {
        title: t(`common.action`),
        dataIndex: 'action',
        key: 'action',
        width: 120,
        align: 'center',
        render: (_, record) => {
          return (
            <PermissionWrapper requiredPermissions={['File Edit']}>
              <Button color="danger" variant="link" onClick={() => handleDelete(record)}>
                {t('common.delete')}
              </Button>
            </PermissionWrapper>
          )
        }
      }
    ]
  };

  const columns = useMemo(() => {
    if (key === 'classification') {
      return [
        ...dynamicColumns,
        {
          title: t(`common.action`),
          dataIndex: 'action',
          key: 'action',
          width: 120,
          align: 'center' as const,
          render: (_: any, record: any) => {
            return (
              <PermissionWrapper requiredPermissions={['File Edit']}>
                <Button color="danger" variant="link" onClick={() => handleDelete(record)}>
                  {t('common.delete')}
                </Button>
              </PermissionWrapper>
            )
          }
        }
      ];
    }
    return baseColumns[key] || [];
  }, [key, dynamicColumns, t]);

  const getTrainDataInfoMap: Record<string, any> = {
    'log_clustering': getLogClusteringTrainDataInfo,
    'classification': getClassificationTrainDataInfo
  };

  const updateTrainDataInfoMap: Record<string, any> = {
    'log_clustering': updateLogClusteringTrainData,
    'classification': updateClassificationTrainData
  };

  useEffect(() => {
    getTableData();
  }, [])

  const getTableData = async () => {
    setLoading(true);
    try {
      const data = await getTrainDataInfoMap[key](id, true, true);
      
      if (key === 'classification') {
        // 从metadata中提取headers
        const headers = data?.metadata?.headers || [];
        
        // 生成动态列
        const generatedColumns: ColumnItem[] = headers.map((header: string) => ({
          title: header,
          dataIndex: header,
          key: header,
          align: 'center' as const
        }));
        
        setDynamicColumns(generatedColumns);
        
        // 处理train_data，将数组转换为对象形式
        if (data?.train_data) {
          const _data = data.train_data.map((item: any, index: number) => {
            const rowData: Record<string, any> = { index };
            
            // 如果item是数组，按headers顺序映射
            if (Array.isArray(item)) {
              headers.forEach((header: string, idx: number) => {
                rowData[header] = item[idx];
              });
            } else if (typeof item === 'object') {
              // 如果item已经是对象，直接使用
              Object.assign(rowData, item);
            }
            
            return rowData;
          });
          setTableData(_data);
        } else {
          setTableData([]);
        }
      } else {
        // 处理log_clustering等其他类型
        if (data?.train_data) {
          const _data = data?.train_data?.map((item: any, index: number) => ({
            name: item,
            index
          }));
          setTableData(_data);
        } else {
          setTableData([]);
        }
      }
    } catch (e) {
      console.log(e);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (record: any) => {
    setLoading(true)
    try {
      let _data;
      
      if (key === 'classification') {
        // 对于classification，过滤并转换为适当的格式
        _data = cloneDeep(tableData)
          .filter((_, idx) => idx !== record?.index)
          .map((item: any) => {
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
            const { index, ...rest } = item;
            return rest;
          });
      } else {
        // 对于log_clustering等其他类型
        _data = cloneDeep(tableData)
          .filter((_, idx) => idx !== record?.index)
          .map((item: any) => item?.name);
      }
      
      await updateTrainDataInfoMap[key](id, { train_data: _data });
      await getTableData(); // 重新加载数据
    } catch (e) {
      console.log(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="p-2">
        <CustomTable
          columns={columns}
          rowKey='index'
          dataSource={tableData}
          loading={loading}
        />
      </div>
    </>
  )
};

export default TableContent;