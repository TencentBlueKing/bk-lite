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
    extend: {},
  },
  plugins: [require('@tailwindcss/typography')],
};
