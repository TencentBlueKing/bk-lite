import React, { useState, useEffect } from 'react';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { randomColorForLegend } from '@/app/log/utils/randomColorForChart';
import { useTranslation } from '@/utils/i18n';

interface LegendItem {
  name: string;
  [key: string]: any;
}

interface ChartLegendProps {
  chart?: any;
  data: LegendItem[];
  colors?: string[];
  onToggleSelect?: (name: string) => void;
}

const ChartLegend: React.FC<ChartLegendProps> = ({
  chart,
  data = [],
  colors = randomColorForLegend(),
  onToggleSelect
}) => {
  const { t } = useTranslation();
  const [selectedLegend, setSelectedLegend] = useState<string[]>([]);

  const legendData = data
    .map((item) => item.name)
    .filter((item) => ![undefined, null, ''].includes(item));

  useEffect(() => {
    // 初始化时清空选择
    setSelectedLegend([]);
  }, [data]);

  const handleLegend = (item: string) => {
    const selected = selectedLegend.includes(item);
    let newSelectedLegend: string[] = [...selectedLegend];

    if (selected) {
      // 如果已选中，则取消选择
      const index = newSelectedLegend.findIndex((r) => r === item);
      newSelectedLegend.splice(index, 1);

      if (newSelectedLegend.length === 0) {
        // 如果没有选中项，则显示全部
        changeVisible(true);
      } else {
        // 隐藏当前项
        changeVisible(false, [item]);
      }
    } else {
      // 如果未选中，则添加到选择
      newSelectedLegend.push(item);

      if (newSelectedLegend.length === 1) {
        // 第一次选择：隐藏其他所有项，只显示当前项
        const unSelected = legendData.filter(
          (row) => !newSelectedLegend.includes(row)
        );
        changeVisible(false, unSelected);
        changeVisible(true, [item]);
      } else {
        // 累加选择：显示当前项
        changeVisible(true, [item]);
      }

      // 如果选择了全部项，则重置为空（显示全部）
      if (legendData.length === newSelectedLegend.length) {
        newSelectedLegend = [];
        changeVisible(true);
      }
    }

    setSelectedLegend(newSelectedLegend);
  };

  const changeVisible = (flag: boolean, items?: string[]) => {
    if (!chart) return;

    if (items) {
      // 对指定项目进行显示/隐藏
      items.forEach((item) => {
        chart.dispatchAction({
          type: flag ? 'legendSelect' : 'legendUnSelect',
          name: item
        });
      });
    } else {
      // 显示/隐藏全部
      legendData.forEach((item) => {
        chart.dispatchAction({
          type: flag ? 'legendSelect' : 'legendUnSelect',
          name: item
        });
      });
    }

    // 触发外部回调
    if (onToggleSelect) {
      onToggleSelect(selectedLegend.join(','));
    }
  };

  const isActive = (item: string) => {
    return selectedLegend.includes(item) || selectedLegend.length === 0;
  };

  return (
    <div className="chart-legend h-full min-w-0 flex flex-col overflow-hidden">
      <div className="flex-shrink-0">
        <table className="chart-legend-table w-full table-fixed border-collapse">
          <thead>
            <tr>
              <th className="text-left px-2 py-1.5 text-xs text-gray-600 border-b border-gray-200 bg-gray-50">
                {t('log.analysis.dimension')}
                <span className="text-gray-400">({legendData.length})</span>
              </th>
            </tr>
          </thead>
        </table>
      </div>
      <div className="flex-1 min-h-0 overflow-x-hidden overflow-y-auto pr-1">
        <table className="chart-legend-table w-full table-fixed border-collapse">
          <tbody>
            {legendData.map((item, index) => (
              <tr
                key={item}
                className={`
                  cursor-pointer transition-all duration-200
                  ${isActive(item) ? 'opacity-100' : 'opacity-50'}
                  hover:bg-blue-50
                  ${index % 2 === 0 ? 'bg-gray-50' : 'bg-white'}
                `}
                onClick={() => handleLegend(item)}
              >
                <td className="w-full max-w-0 px-2 py-1">
                  <div className="flex w-full min-w-0 items-center gap-2">
                    <div
                      className="w-4 h-1 flex-shrink-0"
                      style={{
                        backgroundColor: isActive(item)
                          ? colors[index % colors.length]
                          : '#d1d5db'
                      }}
                    />
                    <div className="flex-1 min-w-0 max-w-full">
                      <EllipsisWithTooltip
                        className="block w-full min-w-0 max-w-full overflow-hidden text-ellipsis whitespace-nowrap text-xs leading-relaxed text-gray-700"
                        text={item || '--'}
                      />
                    </div>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default ChartLegend;
