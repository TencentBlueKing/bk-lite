import React, {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';

export interface AutoFitMetricValueSize {
  width: number;
  height: number;
}

export interface AutoFitMetricValueProps {
  main: React.ReactNode;
  unit?: React.ReactNode;
  color?: string;
  unitColor?: string;
  className?: string;
  valueClassName?: string;
  unitClassName?: string;
  minFontSize?: number;
  unitScale?: number;
  gap?: number | ((fontSize: number) => number);
  textShadow?: string;
  fontVariantNumeric?: React.CSSProperties['fontVariantNumeric'];
  align?: 'baseline' | 'end';
  unitTransform?: string;
  resolveFontSize: (size: AutoFitMetricValueSize) => number;
  onFontSizeChange?: (fontSize: number) => void;
}

const resolveGap = (
  gap: AutoFitMetricValueProps['gap'],
  fontSize: number,
) => {
  if (typeof gap === 'function') {
    return gap(fontSize);
  }
  return gap ?? 0;
};

const AutoFitMetricValue: React.FC<AutoFitMetricValueProps> = ({
  main,
  unit,
  color = 'inherit',
  unitColor,
  className = '',
  valueClassName = '',
  unitClassName = '',
  minFontSize = 18,
  unitScale = 0.5,
  gap = 0,
  textShadow,
  fontVariantNumeric,
  align = 'baseline',
  unitTransform,
  resolveFontSize,
  onFontSizeChange,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const measureRef = useRef<HTMLDivElement>(null);
  const [fontSize, setFontSize] = useState(36);

  const updateFontSize = useCallback(() => {
    const container = containerRef.current;
    const measure = measureRef.current;
    if (!container || !measure) return;

    const width = container.clientWidth;
    const height = container.clientHeight;
    if (width <= 0) return;

    let nextFontSize = Math.max(minFontSize, resolveFontSize({ width, height }));
    const nextGap = resolveGap(gap, nextFontSize);
    measure.style.fontSize = `${nextFontSize}px`;
    measure.style.gap = `${nextGap}px`;

    while (nextFontSize > minFontSize && measure.scrollWidth > width) {
      nextFontSize -= 0.5;
      const shrinkingGap = resolveGap(gap, nextFontSize);
      measure.style.fontSize = `${nextFontSize}px`;
      measure.style.gap = `${shrinkingGap}px`;
    }

    setFontSize((prev) =>
      Math.abs(prev - nextFontSize) < 0.1 ? prev : nextFontSize,
    );
    onFontSizeChange?.(nextFontSize);
  }, [gap, minFontSize, onFontSizeChange, resolveFontSize]);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let frameId = 0;
    updateFontSize();

    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frameId);
      frameId = requestAnimationFrame(updateFontSize);
    });

    observer.observe(container);

    return () => {
      cancelAnimationFrame(frameId);
      observer.disconnect();
    };
  }, [updateFontSize, main, unit]);

  const resolvedGap = resolveGap(gap, fontSize);
  const alignClassName = align === 'end' ? 'items-end' : 'items-baseline';

  return (
    <div ref={containerRef} className={`relative min-w-0 max-w-full ${className}`}>
      <div
        className={`inline-flex max-w-full whitespace-nowrap leading-none ${alignClassName} ${valueClassName}`}
        style={{
          color,
          fontSize: `${fontSize}px`,
          gap: `${resolvedGap}px`,
          textShadow,
          fontVariantNumeric,
          letterSpacing: 0,
        }}
      >
        <span>{main}</span>
        {unit ? (
          <span
            className={`shrink-0 leading-none ${unitClassName}`}
            style={{
              color: unitColor,
              fontSize: `${unitScale}em`,
              transform: unitTransform,
            }}
          >
            {unit}
          </span>
        ) : null}
      </div>
      <div
        ref={measureRef}
        className={`pointer-events-none absolute left-0 top-0 inline-flex whitespace-nowrap leading-none opacity-0 ${alignClassName} ${valueClassName}`}
        aria-hidden
        style={{
          gap: `${resolvedGap}px`,
          fontVariantNumeric,
          letterSpacing: 0,
        }}
      >
        <span>{main}</span>
        {unit ? (
          <span
            className={`shrink-0 leading-none ${unitClassName}`}
            style={{
              fontSize: `${unitScale}em`,
              transform: unitTransform,
            }}
          >
            {unit}
          </span>
        ) : null}
      </div>
    </div>
  );
};

export default AutoFitMetricValue;
