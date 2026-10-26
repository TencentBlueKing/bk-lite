import React from 'react';
import { Slider, Box, TextField } from '@mui/material';
import { ModelItem, ViewItem } from 'src/types';
import { MarkdownEditor } from 'src/components/MarkdownEditor/MarkdownEditor';
import { useModelItem } from 'src/hooks/useModelItem';
import { useLabels } from 'src/hooks/useLabels';
import { DEFAULT_NODE_NAME } from 'src/config';
import { DeleteButton } from '../../components/DeleteButton';
import { Section } from '../../components/Section';

export type NodeUpdates = {
  model: Partial<ModelItem>;
  view: Partial<ViewItem>;
};

interface Props {
  node: ViewItem;
  onModelItemUpdated: (updates: Partial<ModelItem>) => void;
  onViewItemUpdated: (updates: Partial<ViewItem>) => void;
  onDeleted: () => void;
  iconUrl?: string;
  onOpenIconPicker?: () => void;
  extra?: React.ReactNode;
}

export const NodeSettings = ({
  node,
  onModelItemUpdated,
  onViewItemUpdated,
  onDeleted,
  iconUrl,
  onOpenIconPicker,
  extra
}: Props) => {
  const modelItem = useModelItem(node.id);
  const labels = useLabels();
  // The stored default name is shown as a localized placeholder, not as text to delete.
  const isDefaultName = modelItem.name === DEFAULT_NODE_NAME;

  return (
    <>
      <Section title={labels.name}>
        <TextField
          fullWidth
          size="small"
          value={isDefaultName ? '' : modelItem.name}
          placeholder={isDefaultName ? labels.untitledNode : undefined}
          onChange={(e) => {
            const text = e.target.value as string;
            if (modelItem.name !== text) onModelItemUpdated({ name: text });
          }}
        />
      </Section>
      {iconUrl && onOpenIconPicker ? (
        <Section title={labels.icon}>
          <Box
            component="button"
            type="button"
            aria-label={labels.updateIcon}
            onClick={onOpenIconPicker}
            sx={{
              position: 'relative',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 72,
              height: 72,
              p: 1,
              overflow: 'hidden',
              border: '1px solid #DFE7F0',
              borderRadius: '8px',
              bgcolor: '#FFFFFF',
              cursor: 'pointer',
              '&:hover .icon-replace-mask, &:focus-visible .icon-replace-mask': {
                opacity: 1
              }
            }}
          >
            <Box
              component="img"
              src={iconUrl}
              alt=""
              sx={{ width: 44, height: 44, objectFit: 'contain' }}
            />
            <Box
              className="icon-replace-mask"
              sx={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                bgcolor: 'rgba(15, 23, 42, 0.45)',
                color: '#fff',
                fontSize: 12,
                lineHeight: 1,
                opacity: 0,
                transition: 'opacity 0.15s ease',
                pointerEvents: 'none'
              }}
            >
              {labels.replaceIcon}
            </Box>
          </Box>
        </Section>
      ) : null}
      {modelItem.name && (
        <Section title={labels.labelHeight}>
          <Slider
            step={20}
            min={20}
            max={280}
            value={node.labelHeight}
            sx={{
              boxSizing: 'content-box',
              width: 'calc(100% - 14px)',
              marginLeft: '7px'
            }}
            onChange={(e, newHeight) => {
              const labelHeight = newHeight as number;
              onViewItemUpdated({ labelHeight });
            }}
          />
        </Section>
      )}
      {extra ? <Section sx={{ pt: 2 }}>{extra}</Section> : null}
      <Section title={labels.description} sx={extra ? { pt: 3 } : undefined}>
        <MarkdownEditor
          height={82}
          placeholder={labels.descriptionPlaceholder}
          value={modelItem.description || ''}
          onChange={(text) => {
            if (modelItem.description !== text)
              onModelItemUpdated({ description: text });
          }}
        />
      </Section>
      <Section sx={{ pt: 2.5, pb: 0.5 }}>
        <Box sx={{ borderTop: '1px solid var(--color-border-1)', pt: 1.5 }}>
          <DeleteButton onClick={onDeleted} />
        </Box>
      </Section>
    </>
  );
};
