export interface CpuArchitectureOption {
  label: string;
  value: string;
}

const CPU_ARCHITECTURE_FALLBACK: Record<string, CpuArchitectureOption[]> = {
  linux: [{ label: 'x86_64', value: 'x86_64' }],
  windows: [{ label: 'x86_64', value: 'x86_64' }],
};

export { CPU_ARCHITECTURE_FALLBACK };
