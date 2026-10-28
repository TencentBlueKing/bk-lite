import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Box } from '@mui/material';
import { Gradient } from 'src/components/Gradient/Gradient';
import { ExpandButton } from './ExpandButton';
import { Label, Props as LabelProps } from './Label';

type Props = Omit<LabelProps, 'maxHeight'> & {
  onToggleExpand?: (isExpanded: boolean) => void;
  /** Skip the 80px clip. Used when the name card is showing metrics or hover detail. */
  uncapped?: boolean;
};

const STANDARD_LABEL_HEIGHT = 80;
const EXPAND_TOGGLE_HEIGHT = 85;

export const ExpandableLabel = ({
  children,
  onToggleExpand,
  uncapped = false,
  ...rest
}: Props) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const [contentHeight, setContentHeight] = useState(0);

  const containerMaxHeight = useMemo(() => {
    return uncapped || isExpanded ? undefined : STANDARD_LABEL_HEIGHT;
  }, [isExpanded, uncapped]);

  // 观察未被 maxHeight 限制的内容高度，描述修改后也能及时更新展开按钮
  useEffect(() => {
    const el = innerRef.current;
    if (!el) return;

    const observer = new ResizeObserver(() => {
      setContentHeight(el.offsetHeight);
    });
    observer.observe(el);

    return () => {
      observer.disconnect();
    };
  }, []);

  const isContentTruncated =
    !uncapped && !isExpanded && contentHeight > EXPAND_TOGGLE_HEIGHT;

  useEffect(() => {
    contentRef.current?.scrollTo({ top: 0 });
  }, [isExpanded]);

  return (
    <Label
      {...rest}
      maxHeight={containerMaxHeight}
      maxWidth={isExpanded ? rest.maxWidth * 1.5 : rest.maxWidth}
    >
      <Box
        ref={contentRef}
        sx={{
          '&::-webkit-scrollbar': {
            display: 'none'
          }
        }}
        style={{
          overflowY: isExpanded ? 'scroll' : 'hidden',
          maxHeight: containerMaxHeight
        }}
      >
        <div ref={innerRef}>{children}</div>

        {isContentTruncated && (
          <Gradient
            sx={{
              position: 'absolute',
              width: '100%',
              height: 50,
              bottom: 0,
              left: 0
            }}
          />
        )}
      </Box>

      {((!isExpanded && isContentTruncated) || isExpanded) && (
        <ExpandButton
          sx={{
            position: 'absolute',
            bottom: 0,
            right: 0,
            m: 0.5
          }}
          isExpanded={isExpanded}
          onClick={() => {
            setIsExpanded(!isExpanded);
            onToggleExpand?.(!isExpanded);
          }}
        />
      )}
    </Label>
  );
};
