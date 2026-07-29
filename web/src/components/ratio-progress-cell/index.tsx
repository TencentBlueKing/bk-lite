import { Progress } from 'antd';

interface RatioProgressCellProps {
  value: unknown;
  strokeColor?: string;
}

const parsePercent = (value: unknown) => {
  const parsed = Number.parseFloat(String(value ?? '').replace('%', ''));
  return Number.isNaN(parsed) ? 0 : parsed;
};

const RatioProgressCell = ({
  value,
  strokeColor = '#1677ff',
}: RatioProgressCellProps) => {
  const percent = parsePercent(value);

  return (
    <div className="flex min-w-[112px] items-center gap-2">
      <Progress
        percent={percent}
        size="small"
        showInfo={false}
        strokeColor={strokeColor}
        trailColor="rgba(0, 0, 0, 0.06)"
        className="mb-0 min-w-0 flex-1"
      />
      <span className="min-w-[44px] text-xs text-[var(--color-text-2)]">
        {String(value || '--')}
      </span>
    </div>
  );
};

export default RatioProgressCell;
