export const CONVERSATION_DRAWER_OPEN_DISTANCE_RATIO = 0.38;
export const CONVERSATION_DRAWER_OPEN_VELOCITY = 0.45;

interface ShouldOpenConversationDrawerOptions {
  offset: number;
  drawerWidth: number;
  velocityX: number;
}

export const shouldOpenConversationDrawer = ({
  offset,
  drawerWidth,
  velocityX,
}: ShouldOpenConversationDrawerOptions): boolean => {
  if (drawerWidth <= 0) return false;
  if (velocityX <= -CONVERSATION_DRAWER_OPEN_VELOCITY) return false;
  if (velocityX >= CONVERSATION_DRAWER_OPEN_VELOCITY) return true;
  return offset >= drawerWidth * CONVERSATION_DRAWER_OPEN_DISTANCE_RATIO;
};
