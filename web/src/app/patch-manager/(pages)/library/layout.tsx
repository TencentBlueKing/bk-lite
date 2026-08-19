import WithSideMenuLayout from '@/components/layout/sub-layout';
import type { MenuItem } from '@/types';
import { LIBRARY_ROUTE_NAVIGATION } from './_components/library-routes';

const navigationItems: MenuItem[] = LIBRARY_ROUTE_NAVIGATION.map(({ tab, title, url }) => ({
  name: `patch_library_${tab}`,
  title,
  url,
  icon: '',
  operation: [],
}));

export default function LibraryLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <WithSideMenuLayout
      layoutType="segmented"
      customMenuItems={navigationItems}
    >
      <div className="flex h-full min-h-0 flex-col">
        {children}
      </div>
    </WithSideMenuLayout>
  );
}
