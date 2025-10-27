import CustomTable from "@/components/custom-table";
import { useSearchParams } from 'next/navigation';
import { useEffect, useMemo, useState } from "react";
import { ColumnItem, TableDataItem, Pagination } from "@/app/mlops/types";
import useMlopsManageApi from "@/app/mlops/api/manage";
import { useTranslation } from "@/utils/i18n";
// import PermissionWrapper from '@/components/permission';
// import { Button } from "antd";
// import { cloneDeep } from "lodash";

const TableContent = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { 
    getLogClusteringTrainDataInfo, 
    // updateLogClusteringTrainData, 
    getClassificationTrainDataInfo, 
    // updateClassificationTrainData 
  } = useMlopsManageApi();
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [allData, setAllData] = useState<TableDataItem[]>([]); // 存储所有数据
  const [loading, setLoading] = useState<boolean>(false);
  const [dynamicColumns, setDynamicColumns] = useState<ColumnItem[]>([]);
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20,
  });
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
      // {
      //   title: t(`common.action`),
      //   dataIndex: 'action',
      //   key: 'action',
      //   width: 120,
      //   align: 'center',
      //   fiexd: 'right',
      //   render: (_, record) => {
      //     return (
      //       <PermissionWrapper requiredPermissions={['File Edit']}>
      //         <Button color="danger" variant="link" onClick={() => handleDelete(record)}>
      //           {t('common.delete')}
      //         </Button>
      //       </PermissionWrapper>
      //     )
      //   }
      // }
    ]
  };

  const columns = useMemo(() => {
    if (key === 'classification') {
      return [
        ...dynamicColumns,
        // {
        //   title: t(`common.action`),
        //   dataIndex: 'action',
        //   key: 'action',
        //   width: 120,
        //   align: 'center' as const,
        //   fiexd: 'right',
        //   render: (_: any, record: any) => {
        //     return (
        //       <PermissionWrapper requiredPermissions={['File Edit']}>
        //         <Button color="danger" variant="link" onClick={() => handleDelete(record)}>
        //           {t('common.delete')}
        //         </Button>
        //       </PermissionWrapper>
        //     )
        //   }
        // }
      ];
    }
    return baseColumns[key] || [];
  }, [key, dynamicColumns, t]);

  const getTrainDataInfoMap: Record<string, any> = {
    'log_clustering': getLogClusteringTrainDataInfo,
    'classification': getClassificationTrainDataInfo
  };

  // const updateTrainDataInfoMap: Record<string, any> = {
  //   'log_clustering': updateLogClusteringTrainData,
  //   'classification': updateClassificationTrainData
  // };

  useEffect(() => {
    getTableData();
  }, [])

  // 根据分页信息更新显示的数据
  const updateDisplayData = (allDataArray: TableDataItem[], currentPage: number, pageSize: number) => {
    const startIndex = (currentPage - 1) * pageSize;
    const endIndex = startIndex + pageSize;
    const paginatedData = allDataArray.slice(startIndex, endIndex);
    setTableData(paginatedData);
  };

  // 处理分页变化
  const handlePageChange = (page: number, pageSize?: number) => {
    const newPageSize = pageSize || pagination.pageSize;
    setPagination({
      ...pagination,
      current: page,
      pageSize: newPageSize,
    });
    updateDisplayData(allData, page, newPageSize);
  };

  const getTableData = async () => {
    setLoading(true);
    try {
      const data = await getTrainDataInfoMap[key](id, true, true);
      console.log(data);
      let processedData: TableDataItem[] = [];
      
      if (key === 'classification') {
        // 从metadata中提取headers
        const headers = data?.metadata?.headers || [];

        // 生成动态列
        const generatedColumns: ColumnItem[] = headers.map((header: string) => ({
          title: header,
          dataIndex: header,
          key: header,
          width: 150,
          // align: 'center' as const
        }));

        setDynamicColumns(generatedColumns);

        // 处理train_data，将数组转换为对象形式
        if (data?.train_data) {
          processedData = data.train_data.map((item: any, index: number) => {
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
        }
      } else {
        // 处理log_clustering等其他类型
        if (data?.train_data) {
          processedData = data?.train_data?.map((item: any, index: number) => ({
            name: item,
            index
          }));
        }
      }

      // 存储所有数据
      setAllData(processedData);
      
      // 更新分页信息
      const newPagination = {
        current: 1,
        total: processedData.length,
        pageSize: pagination.pageSize,
      };
      setPagination(newPagination);
      
      // 显示第一页数据
      updateDisplayData(processedData, 1, newPagination.pageSize);
    } catch (e) {
      console.log(e);
      setAllData([]);
      setTableData([]);
      setPagination({
        current: 1,
        total: 0,
        pageSize: pagination.pageSize,
      });
    } finally {
      setLoading(false);
    }
  };

  // const handleDelete = async (record: any) => {
  //   setLoading(true)
  //   try {
  //     let _data;

  //     if (key === 'classification') {
  //       // 对于classification，从所有数据中过滤
  //       _data = cloneDeep(allData)
  //         .filter((_, idx) => idx !== record?.index)
  //         // .map((item: any) => {
  //         //   // eslint-disable-next-line @typescript-eslint/no-unused-vars
  //         //   const { index, ...rest } = item;
  //         //   return rest;
  //         // });
  //     } else {
  //       // 对于log_clustering等其他类型，从所有数据中过滤
  //       _data = cloneDeep(allData)
  //         .filter((_, idx) => idx !== record?.index)
  //         .map((item: any) => item?.name);
  //     }

  //     await updateTrainDataInfoMap[key](id, { train_data: _data });
  //     await getTableData(); // 重新加载数据
  //   } catch (e) {
  //     console.log(e);
  //   } finally {
  //     setLoading(false);
  //   }
  // };

  return (
    <>
      <div className="h-full">
        <CustomTable
          rowKey='index'
          columns={columns}
          dataSource={tableData}
          scroll={{ y: 'calc(100vh - 240px)' }}
          pagination={{
            ...pagination,
            onChange: handlePageChange,
            onShowSizeChange: handlePageChange,
          }}
          loading={loading}
        />
      </div>
    </>
  )
};

export default TableContent;