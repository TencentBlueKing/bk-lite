/**
 * jsdom 缺少 X6 视图渲染所需的 SVG 矩阵 API。
 * 必须在 import `@antv/x6` 之前加载。
 */
const identityMatrix = () => ({
  a: 1,
  b: 0,
  c: 0,
  d: 1,
  e: 0,
  f: 0,
  multiply() {
    return identityMatrix();
  },
  inverse() {
    return identityMatrix();
  },
  translate() {
    return identityMatrix();
  },
  scale() {
    return identityMatrix();
  },
  rotate() {
    return identityMatrix();
  },
  flipX() {
    return identityMatrix();
  },
  flipY() {
    return identityMatrix();
  },
  skewX() {
    return identityMatrix();
  },
  skewY() {
    return identityMatrix();
  },
});

const ensureSvgMethod = (
  name: 'createSVGMatrix' | 'createSVGPoint' | 'createSVGTransform',
  factory: () => unknown,
) => {
  const proto = SVGSVGElement.prototype as SVGSVGElement & Record<string, unknown>;
  if (typeof proto[name] !== 'function') {
    proto[name] = factory;
  }
};

ensureSvgMethod('createSVGMatrix', () => identityMatrix());
ensureSvgMethod('createSVGPoint', () => ({
  x: 0,
  y: 0,
  matrixTransform() {
    return { x: this.x, y: this.y };
  },
}));
ensureSvgMethod('createSVGTransform', () => ({
  setMatrix() {},
  setTranslate() {},
  setScale() {},
  setRotate() {},
}));

if (typeof HTMLCanvasElement !== 'undefined') {
  HTMLCanvasElement.prototype.getContext = (() => ({
    fillRect() {},
    clearRect() {},
    getImageData() {
      return { data: [] };
    },
    putImageData() {},
    createImageData() {
      return [];
    },
    setTransform() {},
    drawImage() {},
    save() {},
    restore() {},
    beginPath() {},
    moveTo() {},
    lineTo() {},
    closePath() {},
    stroke() {},
    fill() {},
    measureText() {
      return { width: 0 };
    },
    transform() {},
    translate() {},
    scale() {},
    rotate() {},
    arc() {},
    fillText() {},
    strokeText() {},
  })) as typeof HTMLCanvasElement.prototype.getContext;
}
