/** @type {import('tailwindcss').Config} */
module.exports = {
  // 嵌入宿主页时必须隔离：未 scoped 的工具类会压过宿主 @layer 响应式样式
  important: '#webchat-root',
  // 宿主已有 reset；base preflight 在 important 策略下仍可能泄漏到全局
  corePlugins: {
    preflight: false,
  },
  content: ['./src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      keyframes: {
        'webchat-neutral-pulse': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' },
        },
      },
      animation: {
        'neutral-pulse': 'webchat-neutral-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
};
