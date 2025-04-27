import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
  useMemo,
} from 'react';
import { Tooltip } from 'antd';
import { HexagonData } from '@/app/monitor/types';

interface HexGridProps {
  data: HexagonData[];
}

const HexGrid: React.FC<HexGridProps> = ({ data }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hexPerRow, setHexPerRow] = useState(0); // 每行六边形数量

  // 计算每行可容纳的六边形数量
  const calculateItemsPerRow = useCallback(() => {
    if (!containerRef.current) return;
    const containerWidth = containerRef.current.clientWidth - 44;
    const hexWidth = 110; // 六边形宽度（104px） + 间距（6px）
    setHexPerRow(Math.floor(containerWidth / hexWidth));
  }, []);

  // 监听容器大小变化
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    calculateItemsPerRow();
    const resizeObserver = new ResizeObserver(() => {
      calculateItemsPerRow();
    });
    resizeObserver.observe(container);
    return () => {
      resizeObserver.disconnect();
    };
  }, [calculateItemsPerRow]);

  // 使用 useMemo 缓存 getRows 的结果，避免重复计算
  const rows = useMemo(() => {
    const result = [];
    if (data.length && hexPerRow) {
      for (let i = 0; i < data.length; i += hexPerRow) {
        result.push(data.slice(i, i + hexPerRow));
      }
    }
    return result;
  }, [data, hexPerRow]);

  // 渲染六边形组件
  const renderHexagon = (hex: HexagonData, index: number) => {
    return (
      <Tooltip key={index} title={hex.description} placement="top">
        <div
          className="w-[104px] h-[80px] flex justify-center items-center"
          style={{
            clipPath:
              'polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)',
            backgroundColor: hex.fill,
            color: 'white',
            fontWeight: 'bold',
            margin: '2px 2px 0px 2px',
            transform: 'scale(1, 1.3)',
          }}
        >
          {hex.name}
        </div>
      </Tooltip>
    );
  };

  return (
    <div ref={containerRef} className="h-full flex flex-col items-center pt-3">
      {rows.map((row, rowIndex) => (
        <div
          key={rowIndex}
          className={`flex self-start ${rowIndex % 2 === 1 ? 'ml-[53px]' : ''}`}
        >
          {row.map((hex, index) => renderHexagon(hex, index))}
        </div>
      ))}
    </div>
  );
};

export default HexGrid;
