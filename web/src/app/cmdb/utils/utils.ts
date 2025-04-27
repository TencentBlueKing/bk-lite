declare const require: {
  context: (
    path: string,
    deep?: boolean,
    filter?: RegExp
  ) => {
    keys: () => string[];
    (id: string): any;
  };
};
export function getSvgIcon() {
  const data = require
    .context('../public/assets/assetModelIcon', false, /\.svg$/)
    .keys();
  for (const i in data) {
    data[i] = data[i].replace(/\.\//g, '').replace(/\.svg/g, '');
  }
  return data.map((item) => {
    return {
      url: item,
      key: item.split('_')[0],
      describe: item.split('_')[1],
    };
  });
}
