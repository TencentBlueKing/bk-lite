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
}

export const NodeSettings = ({
  node,
  onModelItemUpdated,
  onViewItemUpdated,
  onDeleted
}: Props) => {
  const modelItem = useModelItem(node.id);
  const labels = useLabels();
  // The stored default name is shown as a localized placeholder, not as text to delete.
  const isDefaultName = modelItem.name === DEFAULT_NODE_NAME;

  return (
    <>
      <Section title={labels.name}>
        <TextField
          value={isDefaultName ? '' : modelItem.name}
          placeholder={isDefaultName ? labels.untitledNode : undefined}
          onChange={(e) => {
            const text = e.target.value as string;
            if (modelItem.name !== text) onModelItemUpdated({ name: text });
          }}
        />
      </Section>
      <Section title={labels.description}>
        <MarkdownEditor
          height={100}
          placeholder={labels.descriptionPlaceholder}
          value={modelItem.description || ''}
          onChange={(text) => {
            if (modelItem.description !== text)
              onModelItemUpdated({ description: text });
          }}
        />
      </Section>
      {modelItem.name && (
        <Section title={labels.labelHeight}>
          <Slider
            marks
            step={20}
            min={60}
            max={280}
            value={node.labelHeight}
            onChange={(e, newHeight) => {
              const labelHeight = newHeight as number;
              onViewItemUpdated({ labelHeight });
            }}
          />
        </Section>
      )}
      <Section>
        <Box>
          <DeleteButton onClick={onDeleted} />
        </Box>
      </Section>
    </>
  );
};
