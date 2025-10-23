// 生成图表颜色
const COLOR_LIST = ['84,112,198', '145,204,117', '250,200,88', '238,102,102', '115,192,222', '59,162,114', '252,132,82', '154,96,180', '234,124,204', '50,197,233', '204,117,117', '204,117,181', '163,117,204', '117,154,204', '117,166,204', '117,198,204', '117,204,169', '142,204,117', '193,204,117', '204,147,117']

function getRandomColor() {
  let rgb, _saturation, _lightness
  do {
    const [hue, saturation, lightness] = [
      Math.floor(Math.random() * 360), // 0-359
      Math.floor(Math.random() * 81) + 10, // 10-90
      Math.floor(Math.random() * 51) + 50 // 50-100
    ]
    const [r, g, b] = hslToRgb(hue, saturation, lightness)
    rgb = { r, g, b }
    _saturation = saturation
    _lightness = lightness
  } while (
    (rgb.r === 255 && rgb.g === 255 && rgb.b === 255) || // 纯白色
    (rgb.r === rgb.g && rgb.g === rgb.b) || // 灰色
    _saturation < 20 || // 饱和度不够
    _lightness > 90
  )
  return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 1)`
}

function hslToRgb(hue: number, saturation: number, lightness: number) {
  const s = saturation / 100
  const l = lightness / 100
  const c = (1 - Math.abs(2 * l - 1)) * s
  const x = c * (1 - Math.abs(((hue / 60) % 2) - 1))
  const m = l - c / 2
  const p = Math.floor(hue / 60)
  const rgb =
    p === 0
      ? [c, x, 0]
      : p === 1
        ? [x, c, 0]
        : p === 2
          ? [0, c, x]
          : p === 3
            ? [0, x, c]
            : p === 4
              ? [x, 0, c]
              : [c, 0, x]
  return [
    Math.round((rgb[0] + m) * 255),
    Math.round((rgb[1] + m) * 255),
    Math.round((rgb[2] + m) * 255)
  ]
}

export const randomColorForLegend = () => {
  const MAX_COLORS_TOTAL = 1000
  const MAX_COLORS_COUNT = 80
  const CUSTOM_COLORS_ROW = 4
  let colors: string[] = []
  const opacity = [1, 0.8, 0.6, 0.4]
  for (let i = 0; i < CUSTOM_COLORS_ROW; i++) {
    colors = colors.concat(COLOR_LIST.map(r => `rgba(${r}, ${opacity[i]})`))
  }
  if (MAX_COLORS_TOTAL > MAX_COLORS_COUNT) {
    for (let i = 0; i < MAX_COLORS_TOTAL - MAX_COLORS_COUNT; i++) {
      colors.push(getRandomColor())
    }
  }
  return colors
}
