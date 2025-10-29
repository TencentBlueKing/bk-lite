import { useEffect, useState, useImperativeHandle, forwardRef } from 'react';
import { ArrowLeftOutlined } from '@ant-design/icons';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import { Input } from 'antd';
import { useSubConfigColumns } from '@/app/node-manager/hooks/configuration';
import CustomTable from '@/components/custom-table';
import useNodeManagerApi from '@/app/node-manager/api';
import type { SubRef, SubProps } from '@/app/node-manager/types/cloudregion';
import type { GetProps } from 'antd';
import { Pagination } from '@/app/node-manager/types';
type SearchProps = GetProps<typeof Input.Search>;
const { Search } = Input;

const SubConfiguration = forwardRef<SubRef, SubProps>(
  ({ cancel, edit, nodeData }, ref) => {
    const { t } = useTranslation();
    const { getChildConfig } = useNodeManagerApi();
    const { isLoading } = useApiClient();
    const [tableLoading, setTableLoading] = useState<boolean>(false);
    const [tableData, setTableData] = useState<any[]>([]);
    const [searchText, setSearchText] = useState<string>('');
    const [pagination, setPagination] = useState<Pagination>({
      current: 1,
      total: 0,
      pageSize: 20,
    });
    const { columns } = useSubConfigColumns({
      nodeData,
      edit,
    });

    useImperativeHandle(ref, () => ({
      getChildConfig: () => {
        getChildConfigList(searchText);
      },
    }));

    useEffect(() => {
      if (isLoading) return;
      setTableLoading(true);
      getChildConfigList(searchText);
    }, [isLoading]);

    useEffect(() => {
      if (!isLoading) getChildConfigList(searchText);
    }, [pagination.current, pagination.pageSize]);

    const getChildConfigList = (search?: string) => {
      const param = {
        collector_config_id: nodeData.key,
        search,
        page: pagination.current,
        page_size: pagination.pageSize,
      };
      setTableLoading(true);
      getChildConfig(param)
        .then((res) => {
          const data = res.items.map((item: any) => {
            return {
              key: item.id,
              name: `${nodeData.nodes || '--'}_${nodeData.name}_子配置`,
              ...item,
            };
          });
          setTableData(data);
          setPagination((prev: Pagination) => ({
            ...prev,
            total: res?.count || 0,
          }));
        })
        .finally(() => {
          setTableLoading(false);
        });
    };

    const goBack = () => {
      cancel();
    };

    const onSearch: SearchProps['onSearch'] = (value) => {
      getChildConfigList(value);
      setSearchText(value);
    };

    const handleTableChange = (pagination: any) => {
      setPagination(pagination);
    };

    return (
      <div className="w-[calc(100vw-280px)]">
        <div className="flex justify-between">
          <div className="flex items-center">
            <ArrowLeftOutlined
              className="text-[var(--color-primary)] text-[20px] cursor-pointer mr-[10px]"
              onClick={goBack}
            />
            <span>
              {t('node-manager.cloudregion.Configuration.configurationList')}
            </span>
          </div>
          <Search
            className="w-[240px]"
            placeholder={t('common.search')}
            enterButton
            onSearch={onSearch}
          />
        </div>
        <div className="flex-1 relative">
          <CustomTable
            className="mt-3 absolute w-[100%]"
            columns={columns}
            pagination={pagination}
            dataSource={tableData}
            loading={tableLoading}
            scroll={{ y: 'calc(100vh - 376px)', x: 'calc(100vw - 432px)' }}
            onChange={handleTableChange}
          />
        </div>
      </div>
    );
  }
);
SubConfiguration.displayName = 'SubConfiguration';
export default SubConfiguration;
