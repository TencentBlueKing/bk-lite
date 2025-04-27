import React, { useRef, useState, useEffect } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';

interface GaugeChartProps {
  value: number; // 当前值
  max: number; // 最大值
  segments: { value: number; color: string }[]; // 区间和对应的颜色
  label?: string; // 底部说明文案
}

const GaugeChart: React.FC<GaugeChartProps> = ({
  value,
  max,
  segments,
  label,
}) => {
  // 计算外环区间的比例
  const cumulativeSegments = segments.map((segment, index) => ({
    ...segment,
    value:
      index === 0 ? segment.value : segment.value - segments[index - 1].value,
  }));

  // 定义内环的当前值和剩余部分
  const innerSegments = [
    {
      value: value,
      color:
        segments.find((segment) => value <= segment.value)?.color || '#F43B2C',
    }, // 根据值动态设置颜色
    { value: max - value, color: 'var(--color-fill-3)' }, // 透明的剩余部分
  ];

  // 获取当前值对应的颜色
  const currentColor =
    segments.find((segment) => value <= segment.value)?.color || '#F43B2C';
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    if (containerRef.current) {
      const { offsetWidth, offsetHeight } = containerRef.current;
      setContainerSize({ width: offsetWidth, height: offsetHeight });
    }
  }, []);

  return (
    <div className="w-full">
      <div style={{ position: 'relative', paddingBottom: '50%', height: 0 }}>
        <div
          ref={containerRef}
          className="bg-[var(--color-bg-1)]"
          style={{ position: 'absolute', width: '100%', height: '100%' }}
        >
          <ResponsiveContainer width="100%" height="100%">
            <PieChart
              margin={{
                top: 0,
                right: 0,
                left: 0,
                bottom: -containerSize.width * 0.5,
              }}
            >
              {/* 外环 */}
              <Pie
                data={cumulativeSegments}
                startAngle={180}
                endAngle={0}
                innerRadius="85%"
                outerRadius="95%"
                dataKey="value"
                isAnimationActive={false}
              >
                {cumulativeSegments.map((entry, index) => (
                  <Cell key={`outer-cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              {/* 内环 */}
              <Pie
                data={innerSegments}
                startAngle={180}
                endAngle={0}
                innerRadius="65%"
                outerRadius="85%"
                dataKey="value"
                isAnimationActive={false}
              >
                {innerSegments.map((entry, index) => (
                  <Cell key={`inner-cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          {/* 中间显示的数值 */}
          <div
            style={{
              position: 'absolute',
              top: '85%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              textAlign: 'center',
              color: currentColor,
            }}
          >
            <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{value}</div>
          </div>
        </div>
      </div>
      {label && (
        <div
          style={{ fontSize: '14px' }}
          className="text-center h-[40px] w-full leading-[40px] bg-[var(--color-bg-1)] text-[var(--color-text-3)]"
        >
          {label}
        </div>
      )}
    </div>
  );
};

export default GaugeChart;
