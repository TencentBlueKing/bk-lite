import CustomTable from "@/components/custom-table";
import { useSearchParams } from 'next/navigation';
import { useEffect, useMemo, useState } from "react";
import { ColumnItem, TableDataItem, Pagination, DatasetType } from "@/app/mlops/types";
import useMlopsManageApi from "@/app/mlops/api/manage";
import { useTranslation } from "@/utils/i18n";

const TableContent = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const {
    getTrainDataInfo,
  } = useMlopsManageApi();
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [allData, setAllData] = useState<TableDataItem[]>([]); // 存储所有数据
  const [loading, setLoading] = useState<boolean>(false);
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
    [DatasetType.LOG_CLUSTERING]: [
      {
        title: '日志内容',
        dataIndex: 'log',
        key: 'log',
        align: 'center',
        render: (_, record) => { return (<>{record.log}</>) }
      },
    ],
    [DatasetType.CLASSIFICATION]: [
      {
        title: '文本内容',
        dataIndex: 'text',
        key: 'text',
        align: 'center',
      },
      {
        title: '标注',
        dataIndex: 'label',
        key: 'label',
        align: 'center'
      }
    ]
  };

  const columns = useMemo(() => {
    return baseColumns[key];
  }, [key, t]);


  useEffect(() => {
    getTableData();
  }, [searchParams])

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
      const data = await getTrainDataInfo(id, key as DatasetType, true, true);
      let processedData: TableDataItem[] = [];

      if (key === DatasetType.CLASSIFICATION) {
        // 文本分类数据
        processedData = data?.train_data;
      } else {
        // 处理log_clustering等其他类型
        if (data?.train_data) {
          processedData = data?.train_data?.map((item: any, index: number) => ({
            ...item,
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
      console.error(e);
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