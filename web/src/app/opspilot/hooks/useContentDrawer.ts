import { useState } from 'react';

const useContentDrawer = () => {
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [drawerContent, setDrawerContent] = useState('');

  const showDrawer = (content: string) => {
    setDrawerContent(content);
    setDrawerVisible(true);
  };

  const hideDrawer = () => {
    setDrawerVisible(false);
    setDrawerContent('');
  };

  return {
    drawerVisible,
    drawerContent,
    showDrawer,
    hideDrawer,
  };
};

export default useContentDrawer;