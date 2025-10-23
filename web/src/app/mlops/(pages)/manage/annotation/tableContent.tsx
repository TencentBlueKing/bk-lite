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
  const { getLogClusteringTrainDataInfo, updateLogClusteringTrainData } = useMlopsManageApi();
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const columns: Record<string, ColumnItem[]> = {
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
    ],
    'classification': [
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

  const getTrainDataInfoMap: Record<string, any> = {
    'log_clustering': getLogClusteringTrainDataInfo
  };

  const updateTrainDataInfoMap: Record<string, any> = {
    'log_clustering': updateLogClusteringTrainData
  };

  useEffect(() => {
    getTableData();
  }, [])

  const {
    id,
    key
  } = useMemo(() => ({
    id: searchParams.get('id') || '',
    key: searchParams.get('activeTap') || ''
  }), [searchParams]);

  const getTableData = async () => {
    setLoading(true);
    try {
      const data = await getTrainDataInfoMap[key](id);
      if (data?.train_data) {
        const _data = data?.train_data?.map((item: any, index: number) => ({
          name: item,
          index
        }));
        setTableData(_data);
      } else {
        setTableData([]);
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
      const _data = cloneDeep(tableData).filter((_, idx) => idx !== record?.index).map((item: any) => item?.name);
      console.log(record?.index);
      await updateTrainDataInfoMap[key](id, { train_data: _data });
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
          columns={columns[key]}
          rowKey='index'
          dataSource={tableData}
          loading={loading}
        />
      </div>
    </>
  )
};

export default TableContent;