import React from 'react';
import { Box, Typography, Paper } from '@mui/material';
import Isoflow from 'src/Isoflow';
import { initialData } from '../initialData';

export const FrameLimitedDrag = () => {
  return (
    <Box sx={{ width: '100vw', height: '100vh', p: 2, bgcolor: 'grey.100' }}>
      <Typography variant="h4" sx={{ mb: 2 }}>
        Frame-Limited Drag Example
      </Typography>
      <Typography variant="body1" sx={{ mb: 2 }}>
        This example shows Isoflow with drag interactions limited to the frame itself.
        Try dragging outside the frame - it won't work! This is useful for embedding in other pages.
      </Typography>
      
      <Paper 
        elevation={3} 
        sx={{ 
          width: '80%', 
          height: '70%', 
          mx: 'auto',
          overflow: 'hidden',
          position: 'relative'
        }}
      >
        <Isoflow
          initialData={initialData}
          width="100%"
          height="100%"
          enableGlobalDragHandlers={false}
          renderer={{
            showGrid: true,
            backgroundColor: '#fafafa'
          }}
        />
      </Paper>
      
      <Typography variant="body2" sx={{ mt: 2, textAlign: 'center', color: 'text.secondary' }}>
        The Isoflow component is now contained within this frame and won't capture mouse events outside of it.
      </Typography>
    </Box>
  );
}; 