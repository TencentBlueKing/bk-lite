declare module "@ant-design/charts" {
  import type { ComponentType } from "react";

  export type LineConfig = Record<string, unknown>;
  export const Line: ComponentType<any>;
}
