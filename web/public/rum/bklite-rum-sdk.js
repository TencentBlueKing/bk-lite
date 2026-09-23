(() => {
  var __create = Object.create;
  var __getProtoOf = Object.getPrototypeOf;
  var __defProp = Object.defineProperty;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __toESM = (mod, isNodeMode, target) => {
    target = mod != null ? __create(__getProtoOf(mod)) : {};
    const to = isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target;
    for (let key of __getOwnPropNames(mod))
      if (!__hasOwnProp.call(to, key))
        __defProp(to, key, {
          get: () => mod[key],
          enumerable: true
        });
    return to;
  };
  var __commonJS = (cb, mod) => () => (mod || cb((mod = { exports: {} }).exports, mod), mod.exports);

  // node_modules/ua-parser-js/src/ua-parser.js
  var require_ua_parser = __commonJS((exports, module) => {
    (function(window2, undefined2) {
      var LIBVERSION = "1.0.41", EMPTY = "", UNKNOWN = "?", FUNC_TYPE = "function", UNDEF_TYPE = "undefined", OBJ_TYPE = "object", STR_TYPE = "string", MAJOR = "major", MODEL = "model", NAME = "name", TYPE = "type", VENDOR = "vendor", VERSION2 = "version", ARCHITECTURE = "architecture", CONSOLE = "console", MOBILE = "mobile", TABLET = "tablet", SMARTTV = "smarttv", WEARABLE = "wearable", EMBEDDED = "embedded", UA_MAX_LENGTH = 500;
      var AMAZON = "Amazon", APPLE = "Apple", ASUS = "ASUS", BLACKBERRY = "BlackBerry", BROWSER = "Browser", CHROME = "Chrome", EDGE = "Edge", FIREFOX = "Firefox", GOOGLE = "Google", HONOR = "Honor", HUAWEI = "Huawei", LENOVO = "Lenovo", LG = "LG", MICROSOFT = "Microsoft", MOTOROLA = "Motorola", NVIDIA = "Nvidia", ONEPLUS = "OnePlus", OPERA = "Opera", OPPO = "OPPO", SAMSUNG = "Samsung", SHARP = "Sharp", SONY = "Sony", XIAOMI = "Xiaomi", ZEBRA = "Zebra", FACEBOOK = "Facebook", CHROMIUM_OS = "Chromium OS", MAC_OS = "Mac OS", SUFFIX_BROWSER = " Browser";
      var extend = function(regexes2, extensions) {
        var mergedRegexes = {};
        for (var i in regexes2) {
          if (extensions[i] && extensions[i].length % 2 === 0) {
            mergedRegexes[i] = extensions[i].concat(regexes2[i]);
          } else {
            mergedRegexes[i] = regexes2[i];
          }
        }
        return mergedRegexes;
      }, enumerize = function(arr) {
        var enums = {};
        for (var i = 0;i < arr.length; i++) {
          enums[arr[i].toUpperCase()] = arr[i];
        }
        return enums;
      }, has = function(str1, str2) {
        return typeof str1 === STR_TYPE ? lowerize(str2).indexOf(lowerize(str1)) !== -1 : false;
      }, lowerize = function(str) {
        return str.toLowerCase();
      }, majorize = function(version) {
        return typeof version === STR_TYPE ? version.replace(/[^\d\.]/g, EMPTY).split(".")[0] : undefined2;
      }, trim = function(str, len) {
        if (typeof str === STR_TYPE) {
          str = str.replace(/^\s\s*/, EMPTY);
          return typeof len === UNDEF_TYPE ? str : str.substring(0, UA_MAX_LENGTH);
        }
      };
      var rgxMapper = function(ua, arrays) {
        var i = 0, j, k, p, q, matches, match;
        while (i < arrays.length && !matches) {
          var regex = arrays[i], props = arrays[i + 1];
          j = k = 0;
          while (j < regex.length && !matches) {
            if (!regex[j]) {
              break;
            }
            matches = regex[j++].exec(ua);
            if (!!matches) {
              for (p = 0;p < props.length; p++) {
                match = matches[++k];
                q = props[p];
                if (typeof q === OBJ_TYPE && q.length > 0) {
                  if (q.length === 2) {
                    if (typeof q[1] == FUNC_TYPE) {
                      this[q[0]] = q[1].call(this, match);
                    } else {
                      this[q[0]] = q[1];
                    }
                  } else if (q.length === 3) {
                    if (typeof q[1] === FUNC_TYPE && !(q[1].exec && q[1].test)) {
                      this[q[0]] = match ? q[1].call(this, match, q[2]) : undefined2;
                    } else {
                      this[q[0]] = match ? match.replace(q[1], q[2]) : undefined2;
                    }
                  } else if (q.length === 4) {
                    this[q[0]] = match ? q[3].call(this, match.replace(q[1], q[2])) : undefined2;
                  }
                } else {
                  this[q] = match ? match : undefined2;
                }
              }
            }
          }
          i += 2;
        }
      }, strMapper = function(str, map) {
        for (var i in map) {
          if (typeof map[i] === OBJ_TYPE && map[i].length > 0) {
            for (var j = 0;j < map[i].length; j++) {
              if (has(map[i][j], str)) {
                return i === UNKNOWN ? undefined2 : i;
              }
            }
          } else if (has(map[i], str)) {
            return i === UNKNOWN ? undefined2 : i;
          }
        }
        return map.hasOwnProperty("*") ? map["*"] : str;
      };
      var oldSafariMap = {
        "1.0": "/8",
        "1.2": "/1",
        "1.3": "/3",
        "2.0": "/412",
        "2.0.2": "/416",
        "2.0.3": "/417",
        "2.0.4": "/419",
        "?": "/"
      }, windowsVersionMap = {
        ME: "4.90",
        "NT 3.11": "NT3.51",
        "NT 4.0": "NT4.0",
        "2000": "NT 5.0",
        XP: ["NT 5.1", "NT 5.2"],
        Vista: "NT 6.0",
        "7": "NT 6.1",
        "8": "NT 6.2",
        "8.1": "NT 6.3",
        "10": ["NT 6.4", "NT 10.0"],
        RT: "ARM"
      };
      var regexes = {
        browser: [
          [
            /\b(?:crmo|crios)\/([\w\.]+)/i
          ],
          [VERSION2, [NAME, "Chrome"]],
          [
            /edg(?:e|ios|a)?\/([\w\.]+)/i
          ],
          [VERSION2, [NAME, "Edge"]],
          [
            /(opera mini)\/([-\w\.]+)/i,
            /(opera [mobiletab]{3,6})\b.+version\/([-\w\.]+)/i,
            /(opera)(?:.+version\/|[\/ ]+)([\w\.]+)/i
          ],
          [NAME, VERSION2],
          [
            /opios[\/ ]+([\w\.]+)/i
          ],
          [VERSION2, [NAME, OPERA + " Mini"]],
          [
            /\bop(?:rg)?x\/([\w\.]+)/i
          ],
          [VERSION2, [NAME, OPERA + " GX"]],
          [
            /\bopr\/([\w\.]+)/i
          ],
          [VERSION2, [NAME, OPERA]],
          [
            /\bb[ai]*d(?:uhd|[ub]*[aekoprswx]{5,6})[\/ ]?([\w\.]+)/i
          ],
          [VERSION2, [NAME, "Baidu"]],
          [
            /\b(?:mxbrowser|mxios|myie2)\/?([-\w\.]*)\b/i
          ],
          [VERSION2, [NAME, "Maxthon"]],
          [
            /(kindle)\/([\w\.]+)/i,
            /(lunascape|maxthon|netfront|jasmine|blazer|sleipnir)[\/ ]?([\w\.]*)/i,
            /(avant|iemobile|slim(?:browser|boat|jet))[\/ ]?([\d\.]*)/i,
            /(?:ms|\()(ie) ([\w\.]+)/i,
            /(flock|rockmelt|midori|epiphany|silk|skyfire|ovibrowser|bolt|iron|vivaldi|iridium|phantomjs|bowser|qupzilla|falkon|rekonq|puffin|brave|whale(?!.+naver)|qqbrowserlite|duckduckgo|klar|helio|(?=comodo_)?dragon)\/([-\w\.]+)/i,
            /(heytap|ovi|115)browser\/([\d\.]+)/i,
            /(weibo)__([\d\.]+)/i
          ],
          [NAME, VERSION2],
          [
            /quark(?:pc)?\/([-\w\.]+)/i
          ],
          [VERSION2, [NAME, "Quark"]],
          [
            /\bddg\/([\w\.]+)/i
          ],
          [VERSION2, [NAME, "DuckDuckGo"]],
          [
            /(?:\buc? ?browser|(?:juc.+)ucweb)[\/ ]?([\w\.]+)/i
          ],
          [VERSION2, [NAME, "UC" + BROWSER]],
          [
            /microm.+\bqbcore\/([\w\.]+)/i,
            /\bqbcore\/([\w\.]+).+microm/i,
            /micromessenger\/([\w\.]+)/i
          ],
          [VERSION2, [NAME, "WeChat"]],
          [
            /konqueror\/([\w\.]+)/i
          ],
          [VERSION2, [NAME, "Konqueror"]],
          [
            /trident.+rv[: ]([\w\.]{1,9})\b.+like gecko/i
          ],
          [VERSION2, [NAME, "IE"]],
          [
            /ya(?:search)?browser\/([\w\.]+)/i
          ],
          [VERSION2, [NAME, "Yandex"]],
          [
            /slbrowser\/([\w\.]+)/i
          ],
          [VERSION2, [NAME, "Smart Lenovo " + BROWSER]],
          [
            /(avast|avg)\/([\w\.]+)/i
          ],
          [[NAME, /(.+)/, "$1 Secure " + BROWSER], VERSION2],
          [
            /\bfocus\/([\w\.]+)/i
          ],
          [VERSION2, [NAME, FIREFOX + " Focus"]],
          [
            /\bopt\/([\w\.]+)/i
          ],
          [VERSION2, [NAME, OPERA + " Touch"]],
          [
            /coc_coc\w+\/([\w\.]+)/i
          ],
          [VERSION2, [NAME, "Coc Coc"]],
          [
            /dolfin\/([\w\.]+)/i
          ],
          [VERSION2, [NAME, "Dolphin"]],
          [
            /coast\/([\w\.]+)/i
          ],
          [VERSION2, [NAME, OPERA + " Coast"]],
          [
            /miuibrowser\/([\w\.]+)/i
          ],
          [VERSION2, [NAME, "MIUI" + SUFFIX_BROWSER]],
          [
            /fxios\/([\w\.-]+)/i
          ],
          [VERSION2, [NAME, FIREFOX]],
          [
            /\bqihoobrowser\/?([\w\.]*)/i
          ],
          [VERSION2, [NAME, "360"]],
          [
            /\b(qq)\/([\w\.]+)/i
          ],
          [[NAME, /(.+)/, "$1Browser"], VERSION2],
          [
            /(oculus|sailfish|huawei|vivo|pico)browser\/([\w\.]+)/i
          ],
          [[NAME, /(.+)/, "$1" + SUFFIX_BROWSER], VERSION2],
          [
            /samsungbrowser\/([\w\.]+)/i
          ],
          [VERSION2, [NAME, SAMSUNG + " Internet"]],
          [
            /metasr[\/ ]?([\d\.]+)/i
          ],
          [VERSION2, [NAME, "Sogou Explorer"]],
          [
            /(sogou)mo\w+\/([\d\.]+)/i
          ],
          [[NAME, "Sogou Mobile"], VERSION2],
          [
            /(electron)\/([\w\.]+) safari/i,
            /(tesla)(?: qtcarbrowser|\/(20\d\d\.[-\w\.]+))/i,
            /m?(qqbrowser|2345(?=browser|chrome|explorer))\w*[\/ ]?v?([\w\.]+)/i
          ],
          [NAME, VERSION2],
          [
            /(lbbrowser|rekonq)/i,
            /\[(linkedin)app\]/i
          ],
          [NAME],
          [
            /ome\/([\w\.]+) \w* ?(iron) saf/i,
            /ome\/([\w\.]+).+qihu (360)[es]e/i
          ],
          [VERSION2, NAME],
          [
            /((?:fban\/fbios|fb_iab\/fb4a)(?!.+fbav)|;fbav\/([\w\.]+);)/i
          ],
          [[NAME, FACEBOOK], VERSION2],
          [
            /(Klarna)\/([\w\.]+)/i,
            /(kakao(?:talk|story))[\/ ]([\w\.]+)/i,
            /(naver)\(.*?(\d+\.[\w\.]+).*\)/i,
            /(daum)apps[\/ ]([\w\.]+)/i,
            /safari (line)\/([\w\.]+)/i,
            /\b(line)\/([\w\.]+)\/iab/i,
            /(alipay)client\/([\w\.]+)/i,
            /(twitter)(?:and| f.+e\/([\w\.]+))/i,
            /(chromium|instagram|snapchat)[\/ ]([-\w\.]+)/i
          ],
          [NAME, VERSION2],
          [
            /\bgsa\/([\w\.]+) .*safari\//i
          ],
          [VERSION2, [NAME, "GSA"]],
          [
            /musical_ly(?:.+app_?version\/|_)([\w\.]+)/i
          ],
          [VERSION2, [NAME, "TikTok"]],
          [
            /headlesschrome(?:\/([\w\.]+)| )/i
          ],
          [VERSION2, [NAME, CHROME + " Headless"]],
          [
            / wv\).+(chrome)\/([\w\.]+)/i
          ],
          [[NAME, CHROME + " WebView"], VERSION2],
          [
            /droid.+ version\/([\w\.]+)\b.+(?:mobile safari|safari)/i
          ],
          [VERSION2, [NAME, "Android " + BROWSER]],
          [
            /(chrome|omniweb|arora|[tizenoka]{5} ?browser)\/v?([\w\.]+)/i
          ],
          [NAME, VERSION2],
          [
            /version\/([\w\.\,]+) .*mobile\/\w+ (safari)/i
          ],
          [VERSION2, [NAME, "Mobile Safari"]],
          [
            /version\/([\w(\.|\,)]+) .*(mobile ?safari|safari)/i
          ],
          [VERSION2, NAME],
          [
            /webkit.+?(mobile ?safari|safari)(\/[\w\.]+)/i
          ],
          [NAME, [VERSION2, strMapper, oldSafariMap]],
          [
            /(webkit|khtml)\/([\w\.]+)/i
          ],
          [NAME, VERSION2],
          [
            /(navigator|netscape\d?)\/([-\w\.]+)/i
          ],
          [[NAME, "Netscape"], VERSION2],
          [
            /(wolvic|librewolf)\/([\w\.]+)/i
          ],
          [NAME, VERSION2],
          [
            /mobile vr; rv:([\w\.]+)\).+firefox/i
          ],
          [VERSION2, [NAME, FIREFOX + " Reality"]],
          [
            /ekiohf.+(flow)\/([\w\.]+)/i,
            /(swiftfox)/i,
            /(icedragon|iceweasel|camino|chimera|fennec|maemo browser|minimo|conkeror)[\/ ]?([\w\.\+]+)/i,
            /(seamonkey|k-meleon|icecat|iceape|firebird|phoenix|palemoon|basilisk|waterfox)\/([-\w\.]+)$/i,
            /(firefox)\/([\w\.]+)/i,
            /(mozilla)\/([\w\.]+) .+rv\:.+gecko\/\d+/i,
            /(amaya|dillo|doris|icab|ladybird|lynx|mosaic|netsurf|obigo|polaris|w3m|(?:go|ice|up)[\. ]?browser)[-\/ ]?v?([\w\.]+)/i,
            /\b(links) \(([\w\.]+)/i
          ],
          [NAME, [VERSION2, /_/g, "."]],
          [
            /(cobalt)\/([\w\.]+)/i
          ],
          [NAME, [VERSION2, /master.|lts./, ""]]
        ],
        cpu: [
          [
            /\b((amd|x|x86[-_]?|wow|win)64)\b/i
          ],
          [[ARCHITECTURE, "amd64"]],
          [
            /(ia32(?=;))/i,
            /\b((i[346]|x)86)(pc)?\b/i
          ],
          [[ARCHITECTURE, "ia32"]],
          [
            /\b(aarch64|arm(v?[89]e?l?|_?64))\b/i
          ],
          [[ARCHITECTURE, "arm64"]],
          [
            /\b(arm(v[67])?ht?n?[fl]p?)\b/i
          ],
          [[ARCHITECTURE, "armhf"]],
          [
            /( (ce|mobile); ppc;|\/[\w\.]+arm\b)/i
          ],
          [[ARCHITECTURE, "arm"]],
          [
            /((ppc|powerpc)(64)?)( mac|;|\))/i
          ],
          [[ARCHITECTURE, /ower/, EMPTY, lowerize]],
          [
            / sun4\w[;\)]/i
          ],
          [[ARCHITECTURE, "sparc"]],
          [
            /\b(avr32|ia64(?=;)|68k(?=\))|\barm(?=v([1-7]|[5-7]1)l?|;|eabi)|(irix|mips|sparc)(64)?\b|pa-risc)/i
          ],
          [[ARCHITECTURE, lowerize]]
        ],
        device: [
          [
            /\b(sch-i[89]0\d|shw-m380s|sm-[ptx]\w{2,4}|gt-[pn]\d{2,4}|sgh-t8[56]9|nexus 10)/i
          ],
          [MODEL, [VENDOR, SAMSUNG], [TYPE, TABLET]],
          [
            /\b((?:s[cgp]h|gt|sm)-(?![lr])\w+|sc[g-]?[\d]+a?|galaxy nexus)/i,
            /samsung[- ]((?!sm-[lr])[-\w]+)/i,
            /sec-(sgh\w+)/i
          ],
          [MODEL, [VENDOR, SAMSUNG], [TYPE, MOBILE]],
          [
            /(?:\/|\()(ip(?:hone|od)[\w, ]*)(?:\/|;)/i
          ],
          [MODEL, [VENDOR, APPLE], [TYPE, MOBILE]],
          [
            /\((ipad);[-\w\),; ]+apple/i,
            /applecoremedia\/[\w\.]+ \((ipad)/i,
            /\b(ipad)\d\d?,\d\d?[;\]].+ios/i
          ],
          [MODEL, [VENDOR, APPLE], [TYPE, TABLET]],
          [
            /(macintosh);/i
          ],
          [MODEL, [VENDOR, APPLE]],
          [
            /\b(sh-?[altvz]?\d\d[a-ekm]?)/i
          ],
          [MODEL, [VENDOR, SHARP], [TYPE, MOBILE]],
          [
            /\b((?:brt|eln|hey2?|gdi|jdn)-a?[lnw]09|(?:ag[rm]3?|jdn2|kob2)-a?[lw]0[09]hn)(?: bui|\)|;)/i
          ],
          [MODEL, [VENDOR, HONOR], [TYPE, TABLET]],
          [
            /honor([-\w ]+)[;\)]/i
          ],
          [MODEL, [VENDOR, HONOR], [TYPE, MOBILE]],
          [
            /\b((?:ag[rs][2356]?k?|bah[234]?|bg[2o]|bt[kv]|cmr|cpn|db[ry]2?|jdn2|got|kob2?k?|mon|pce|scm|sht?|[tw]gr|vrd)-[ad]?[lw][0125][09]b?|605hw|bg2-u03|(?:gem|fdr|m2|ple|t1)-[7a]0[1-4][lu]|t1-a2[13][lw]|mediapad[\w\. ]*(?= bui|\)))\b(?!.+d\/s)/i
          ],
          [MODEL, [VENDOR, HUAWEI], [TYPE, TABLET]],
          [
            /(?:huawei)([-\w ]+)[;\)]/i,
            /\b(nexus 6p|\w{2,4}e?-[atu]?[ln][\dx][012359c][adn]?)\b(?!.+d\/s)/i
          ],
          [MODEL, [VENDOR, HUAWEI], [TYPE, MOBILE]],
          [
            /oid[^\)]+; (2[\dbc]{4}(182|283|rp\w{2})[cgl]|m2105k81a?c)(?: bui|\))/i,
            /\b((?:red)?mi[-_ ]?pad[\w- ]*)(?: bui|\))/i
          ],
          [[MODEL, /_/g, " "], [VENDOR, XIAOMI], [TYPE, TABLET]],
          [
            /\b(poco[\w ]+|m2\d{3}j\d\d[a-z]{2})(?: bui|\))/i,
            /\b; (\w+) build\/hm\1/i,
            /\b(hm[-_ ]?note?[_ ]?(?:\d\w)?) bui/i,
            /\b(redmi[\-_ ]?(?:note|k)?[\w_ ]+)(?: bui|\))/i,
            /oid[^\)]+; (m?[12][0-389][01]\w{3,6}[c-y])( bui|; wv|\))/i,
            /\b(mi[-_ ]?(?:a\d|one|one[_ ]plus|note lte|max|cc)?[_ ]?(?:\d?\w?)[_ ]?(?:plus|se|lite|pro)?)(?: bui|\))/i,
            / ([\w ]+) miui\/v?\d/i
          ],
          [[MODEL, /_/g, " "], [VENDOR, XIAOMI], [TYPE, MOBILE]],
          [
            /; (\w+) bui.+ oppo/i,
            /\b(cph[12]\d{3}|p(?:af|c[al]|d\w|e[ar])[mt]\d0|x9007|a101op)\b/i
          ],
          [MODEL, [VENDOR, OPPO], [TYPE, MOBILE]],
          [
            /\b(opd2(\d{3}a?))(?: bui|\))/i
          ],
          [MODEL, [VENDOR, strMapper, { OnePlus: ["304", "403", "203"], "*": OPPO }], [TYPE, TABLET]],
          [
            /vivo (\w+)(?: bui|\))/i,
            /\b(v[12]\d{3}\w?[at])(?: bui|;)/i
          ],
          [MODEL, [VENDOR, "Vivo"], [TYPE, MOBILE]],
          [
            /\b(rmx[1-3]\d{3})(?: bui|;|\))/i
          ],
          [MODEL, [VENDOR, "Realme"], [TYPE, MOBILE]],
          [
            /\b(milestone|droid(?:[2-4x]| (?:bionic|x2|pro|razr))?:?( 4g)?)\b[\w ]+build\//i,
            /\bmot(?:orola)?[- ](\w*)/i,
            /((?:moto(?! 360)[\w\(\) ]+|xt\d{3,4}|nexus 6)(?= bui|\)))/i
          ],
          [MODEL, [VENDOR, MOTOROLA], [TYPE, MOBILE]],
          [
            /\b(mz60\d|xoom[2 ]{0,2}) build\//i
          ],
          [MODEL, [VENDOR, MOTOROLA], [TYPE, TABLET]],
          [
            /((?=lg)?[vl]k\-?\d{3}) bui| 3\.[-\w; ]{10}lg?-([06cv9]{3,4})/i
          ],
          [MODEL, [VENDOR, LG], [TYPE, TABLET]],
          [
            /(lm(?:-?f100[nv]?|-[\w\.]+)(?= bui|\))|nexus [45])/i,
            /\blg[-e;\/ ]+((?!browser|netcast|android tv|watch)\w+)/i,
            /\blg-?([\d\w]+) bui/i
          ],
          [MODEL, [VENDOR, LG], [TYPE, MOBILE]],
          [
            /(ideatab[-\w ]+|602lv|d-42a|a101lv|a2109a|a3500-hv|s[56]000|pb-6505[my]|tb-?x?\d{3,4}(?:f[cu]|xu|[av])|yt\d?-[jx]?\d+[lfmx])( bui|;|\)|\/)/i,
            /lenovo ?(b[68]0[08]0-?[hf]?|tab(?:[\w- ]+?)|tb[\w-]{6,7})( bui|;|\)|\/)/i
          ],
          [MODEL, [VENDOR, LENOVO], [TYPE, TABLET]],
          [
            /(nokia) (t[12][01])/i
          ],
          [VENDOR, MODEL, [TYPE, TABLET]],
          [
            /(?:maemo|nokia).*(n900|lumia \d+|rm-\d+)/i,
            /nokia[-_ ]?(([-\w\. ]*))/i
          ],
          [[MODEL, /_/g, " "], [TYPE, MOBILE], [VENDOR, "Nokia"]],
          [
            /(pixel (c|tablet))\b/i
          ],
          [MODEL, [VENDOR, GOOGLE], [TYPE, TABLET]],
          [
            /droid.+; (pixel[\daxl ]{0,6})(?: bui|\))/i
          ],
          [MODEL, [VENDOR, GOOGLE], [TYPE, MOBILE]],
          [
            /droid.+; (a?\d[0-2]{2}so|[c-g]\d{4}|so[-gl]\w+|xq-a\w[4-7][12])(?= bui|\).+chrome\/(?![1-6]{0,1}\d\.))/i
          ],
          [MODEL, [VENDOR, SONY], [TYPE, MOBILE]],
          [
            /sony tablet [ps]/i,
            /\b(?:sony)?sgp\w+(?: bui|\))/i
          ],
          [[MODEL, "Xperia Tablet"], [VENDOR, SONY], [TYPE, TABLET]],
          [
            / (kb2005|in20[12]5|be20[12][59])\b/i,
            /(?:one)?(?:plus)? (a\d0\d\d)(?: b|\))/i
          ],
          [MODEL, [VENDOR, ONEPLUS], [TYPE, MOBILE]],
          [
            /(alexa)webm/i,
            /(kf[a-z]{2}wi|aeo(?!bc)\w\w)( bui|\))/i,
            /(kf[a-z]+)( bui|\)).+silk\//i
          ],
          [MODEL, [VENDOR, AMAZON], [TYPE, TABLET]],
          [
            /((?:sd|kf)[0349hijorstuw]+)( bui|\)).+silk\//i
          ],
          [[MODEL, /(.+)/g, "Fire Phone $1"], [VENDOR, AMAZON], [TYPE, MOBILE]],
          [
            /(playbook);[-\w\),; ]+(rim)/i
          ],
          [MODEL, VENDOR, [TYPE, TABLET]],
          [
            /\b((?:bb[a-f]|st[hv])100-\d)/i,
            /\(bb10; (\w+)/i
          ],
          [MODEL, [VENDOR, BLACKBERRY], [TYPE, MOBILE]],
          [
            /(?:\b|asus_)(transfo[prime ]{4,10} \w+|eeepc|slider \w+|nexus 7|padfone|p00[cj])/i
          ],
          [MODEL, [VENDOR, ASUS], [TYPE, TABLET]],
          [
            / (z[bes]6[027][012][km][ls]|zenfone \d\w?)\b/i
          ],
          [MODEL, [VENDOR, ASUS], [TYPE, MOBILE]],
          [
            /(nexus 9)/i
          ],
          [MODEL, [VENDOR, "HTC"], [TYPE, TABLET]],
          [
            /(htc)[-;_ ]{1,2}([\w ]+(?=\)| bui)|\w+)/i,
            /(zte)[- ]([\w ]+?)(?: bui|\/|\))/i,
            /(alcatel|geeksphone|nexian|panasonic(?!(?:;|\.))|sony(?!-bra))[-_ ]?([-\w]*)/i
          ],
          [VENDOR, [MODEL, /_/g, " "], [TYPE, MOBILE]],
          [
            /droid [\w\.]+; ((?:8[14]9[16]|9(?:0(?:48|60|8[01])|1(?:3[27]|66)|2(?:6[69]|9[56])|466))[gqswx])\w*(\)| bui)/i
          ],
          [MODEL, [VENDOR, "TCL"], [TYPE, TABLET]],
          [
            /(itel) ((\w+))/i
          ],
          [[VENDOR, lowerize], MODEL, [TYPE, strMapper, { tablet: ["p10001l", "w7001"], "*": "mobile" }]],
          [
            /droid.+; ([ab][1-7]-?[0178a]\d\d?)/i
          ],
          [MODEL, [VENDOR, "Acer"], [TYPE, TABLET]],
          [
            /droid.+; (m[1-5] note) bui/i,
            /\bmz-([-\w]{2,})/i
          ],
          [MODEL, [VENDOR, "Meizu"], [TYPE, MOBILE]],
          [
            /; ((?:power )?armor(?:[\w ]{0,8}))(?: bui|\))/i
          ],
          [MODEL, [VENDOR, "Ulefone"], [TYPE, MOBILE]],
          [
            /; (energy ?\w+)(?: bui|\))/i,
            /; energizer ([\w ]+)(?: bui|\))/i
          ],
          [MODEL, [VENDOR, "Energizer"], [TYPE, MOBILE]],
          [
            /; cat (b35);/i,
            /; (b15q?|s22 flip|s48c|s62 pro)(?: bui|\))/i
          ],
          [MODEL, [VENDOR, "Cat"], [TYPE, MOBILE]],
          [
            /((?:new )?andromax[\w- ]+)(?: bui|\))/i
          ],
          [MODEL, [VENDOR, "Smartfren"], [TYPE, MOBILE]],
          [
            /droid.+; (a(?:015|06[35]|142p?))/i
          ],
          [MODEL, [VENDOR, "Nothing"], [TYPE, MOBILE]],
          [
            /; (x67 5g|tikeasy \w+|ac[1789]\d\w+)( b|\))/i,
            /archos ?(5|gamepad2?|([\w ]*[t1789]|hello) ?\d+[\w ]*)( b|\))/i
          ],
          [MODEL, [VENDOR, "Archos"], [TYPE, TABLET]],
          [
            /archos ([\w ]+)( b|\))/i,
            /; (ac[3-6]\d\w{2,8})( b|\))/i
          ],
          [MODEL, [VENDOR, "Archos"], [TYPE, MOBILE]],
          [
            /(imo) (tab \w+)/i,
            /(infinix) (x1101b?)/i
          ],
          [VENDOR, MODEL, [TYPE, TABLET]],
          [
            /(blackberry|benq|palm(?=\-)|sonyericsson|acer|asus(?! zenw)|dell|jolla|meizu|motorola|polytron|infinix|tecno|micromax|advan)[-_ ]?([-\w]*)/i,
            /; (hmd|imo) ([\w ]+?)(?: bui|\))/i,
            /(hp) ([\w ]+\w)/i,
            /(microsoft); (lumia[\w ]+)/i,
            /(lenovo)[-_ ]?([-\w ]+?)(?: bui|\)|\/)/i,
            /(oppo) ?([\w ]+) bui/i
          ],
          [VENDOR, MODEL, [TYPE, MOBILE]],
          [
            /(kobo)\s(ereader|touch)/i,
            /(hp).+(touchpad(?!.+tablet)|tablet)/i,
            /(kindle)\/([\w\.]+)/i,
            /(nook)[\w ]+build\/(\w+)/i,
            /(dell) (strea[kpr\d ]*[\dko])/i,
            /(le[- ]+pan)[- ]+(\w{1,9}) bui/i,
            /(trinity)[- ]*(t\d{3}) bui/i,
            /(gigaset)[- ]+(q\w{1,9}) bui/i,
            /(vodafone) ([\w ]+)(?:\)| bui)/i
          ],
          [VENDOR, MODEL, [TYPE, TABLET]],
          [
            /(surface duo)/i
          ],
          [MODEL, [VENDOR, MICROSOFT], [TYPE, TABLET]],
          [
            /droid [\d\.]+; (fp\du?)(?: b|\))/i
          ],
          [MODEL, [VENDOR, "Fairphone"], [TYPE, MOBILE]],
          [
            /(u304aa)/i
          ],
          [MODEL, [VENDOR, "AT&T"], [TYPE, MOBILE]],
          [
            /\bsie-(\w*)/i
          ],
          [MODEL, [VENDOR, "Siemens"], [TYPE, MOBILE]],
          [
            /\b(rct\w+) b/i
          ],
          [MODEL, [VENDOR, "RCA"], [TYPE, TABLET]],
          [
            /\b(venue[\d ]{2,7}) b/i
          ],
          [MODEL, [VENDOR, "Dell"], [TYPE, TABLET]],
          [
            /\b(q(?:mv|ta)\w+) b/i
          ],
          [MODEL, [VENDOR, "Verizon"], [TYPE, TABLET]],
          [
            /\b(?:barnes[& ]+noble |bn[rt])([\w\+ ]*) b/i
          ],
          [MODEL, [VENDOR, "Barnes & Noble"], [TYPE, TABLET]],
          [
            /\b(tm\d{3}\w+) b/i
          ],
          [MODEL, [VENDOR, "NuVision"], [TYPE, TABLET]],
          [
            /\b(k88) b/i
          ],
          [MODEL, [VENDOR, "ZTE"], [TYPE, TABLET]],
          [
            /\b(nx\d{3}j) b/i
          ],
          [MODEL, [VENDOR, "ZTE"], [TYPE, MOBILE]],
          [
            /\b(gen\d{3}) b.+49h/i
          ],
          [MODEL, [VENDOR, "Swiss"], [TYPE, MOBILE]],
          [
            /\b(zur\d{3}) b/i
          ],
          [MODEL, [VENDOR, "Swiss"], [TYPE, TABLET]],
          [
            /\b((zeki)?tb.*\b) b/i
          ],
          [MODEL, [VENDOR, "Zeki"], [TYPE, TABLET]],
          [
            /\b([yr]\d{2}) b/i,
            /\b(dragon[- ]+touch |dt)(\w{5}) b/i
          ],
          [[VENDOR, "Dragon Touch"], MODEL, [TYPE, TABLET]],
          [
            /\b(ns-?\w{0,9}) b/i
          ],
          [MODEL, [VENDOR, "Insignia"], [TYPE, TABLET]],
          [
            /\b((nxa|next)-?\w{0,9}) b/i
          ],
          [MODEL, [VENDOR, "NextBook"], [TYPE, TABLET]],
          [
            /\b(xtreme\_)?(v(1[045]|2[015]|[3469]0|7[05])) b/i
          ],
          [[VENDOR, "Voice"], MODEL, [TYPE, MOBILE]],
          [
            /\b(lvtel\-)?(v1[12]) b/i
          ],
          [[VENDOR, "LvTel"], MODEL, [TYPE, MOBILE]],
          [
            /\b(ph-1) /i
          ],
          [MODEL, [VENDOR, "Essential"], [TYPE, MOBILE]],
          [
            /\b(v(100md|700na|7011|917g).*\b) b/i
          ],
          [MODEL, [VENDOR, "Envizen"], [TYPE, TABLET]],
          [
            /\b(trio[-\w\. ]+) b/i
          ],
          [MODEL, [VENDOR, "MachSpeed"], [TYPE, TABLET]],
          [
            /\btu_(1491) b/i
          ],
          [MODEL, [VENDOR, "Rotor"], [TYPE, TABLET]],
          [
            /((?:tegranote|shield t(?!.+d tv))[\w- ]*?)(?: b|\))/i
          ],
          [MODEL, [VENDOR, NVIDIA], [TYPE, TABLET]],
          [
            /(sprint) (\w+)/i
          ],
          [VENDOR, MODEL, [TYPE, MOBILE]],
          [
            /(kin\.[onetw]{3})/i
          ],
          [[MODEL, /\./g, " "], [VENDOR, MICROSOFT], [TYPE, MOBILE]],
          [
            /droid.+; (cc6666?|et5[16]|mc[239][23]x?|vc8[03]x?)\)/i
          ],
          [MODEL, [VENDOR, ZEBRA], [TYPE, TABLET]],
          [
            /droid.+; (ec30|ps20|tc[2-8]\d[kx])\)/i
          ],
          [MODEL, [VENDOR, ZEBRA], [TYPE, MOBILE]],
          [
            /smart-tv.+(samsung)/i
          ],
          [VENDOR, [TYPE, SMARTTV]],
          [
            /hbbtv.+maple;(\d+)/i
          ],
          [[MODEL, /^/, "SmartTV"], [VENDOR, SAMSUNG], [TYPE, SMARTTV]],
          [
            /(nux; netcast.+smarttv|lg (netcast\.tv-201\d|android tv))/i
          ],
          [[VENDOR, LG], [TYPE, SMARTTV]],
          [
            /(apple) ?tv/i
          ],
          [VENDOR, [MODEL, APPLE + " TV"], [TYPE, SMARTTV]],
          [
            /crkey/i
          ],
          [[MODEL, CHROME + "cast"], [VENDOR, GOOGLE], [TYPE, SMARTTV]],
          [
            /droid.+aft(\w+)( bui|\))/i
          ],
          [MODEL, [VENDOR, AMAZON], [TYPE, SMARTTV]],
          [
            /(shield \w+ tv)/i
          ],
          [MODEL, [VENDOR, NVIDIA], [TYPE, SMARTTV]],
          [
            /\(dtv[\);].+(aquos)/i,
            /(aquos-tv[\w ]+)\)/i
          ],
          [MODEL, [VENDOR, SHARP], [TYPE, SMARTTV]],
          [
            /(bravia[\w ]+)( bui|\))/i
          ],
          [MODEL, [VENDOR, SONY], [TYPE, SMARTTV]],
          [
            /(mi(tv|box)-?\w+) bui/i
          ],
          [MODEL, [VENDOR, XIAOMI], [TYPE, SMARTTV]],
          [
            /Hbbtv.*(technisat) (.*);/i
          ],
          [VENDOR, MODEL, [TYPE, SMARTTV]],
          [
            /\b(roku)[\dx]*[\)\/]((?:dvp-)?[\d\.]*)/i,
            /hbbtv\/\d+\.\d+\.\d+ +\([\w\+ ]*; *([\w\d][^;]*);([^;]*)/i
          ],
          [[VENDOR, trim], [MODEL, trim], [TYPE, SMARTTV]],
          [
            /droid.+; ([\w- ]+) (?:android tv|smart[- ]?tv)/i
          ],
          [MODEL, [TYPE, SMARTTV]],
          [
            /\b(android tv|smart[- ]?tv|opera tv|tv; rv:)\b/i
          ],
          [[TYPE, SMARTTV]],
          [
            /(ouya)/i,
            /(nintendo) ([wids3utch]+)/i
          ],
          [VENDOR, MODEL, [TYPE, CONSOLE]],
          [
            /droid.+; (shield)( bui|\))/i
          ],
          [MODEL, [VENDOR, NVIDIA], [TYPE, CONSOLE]],
          [
            /(playstation \w+)/i
          ],
          [MODEL, [VENDOR, SONY], [TYPE, CONSOLE]],
          [
            /\b(xbox(?: one)?(?!; xbox))[\); ]/i
          ],
          [MODEL, [VENDOR, MICROSOFT], [TYPE, CONSOLE]],
          [
            /\b(sm-[lr]\d\d[0156][fnuw]?s?|gear live)\b/i
          ],
          [MODEL, [VENDOR, SAMSUNG], [TYPE, WEARABLE]],
          [
            /((pebble))app/i,
            /(asus|google|lg|oppo) ((pixel |zen)?watch[\w ]*)( bui|\))/i
          ],
          [VENDOR, MODEL, [TYPE, WEARABLE]],
          [
            /(ow(?:19|20)?we?[1-3]{1,3})/i
          ],
          [MODEL, [VENDOR, OPPO], [TYPE, WEARABLE]],
          [
            /(watch)(?: ?os[,\/]|\d,\d\/)[\d\.]+/i
          ],
          [MODEL, [VENDOR, APPLE], [TYPE, WEARABLE]],
          [
            /(opwwe\d{3})/i
          ],
          [MODEL, [VENDOR, ONEPLUS], [TYPE, WEARABLE]],
          [
            /(moto 360)/i
          ],
          [MODEL, [VENDOR, MOTOROLA], [TYPE, WEARABLE]],
          [
            /(smartwatch 3)/i
          ],
          [MODEL, [VENDOR, SONY], [TYPE, WEARABLE]],
          [
            /(g watch r)/i
          ],
          [MODEL, [VENDOR, LG], [TYPE, WEARABLE]],
          [
            /droid.+; (wt63?0{2,3})\)/i
          ],
          [MODEL, [VENDOR, ZEBRA], [TYPE, WEARABLE]],
          [
            /droid.+; (glass) \d/i
          ],
          [MODEL, [VENDOR, GOOGLE], [TYPE, WEARABLE]],
          [
            /(pico) (4|neo3(?: link|pro)?)/i
          ],
          [VENDOR, MODEL, [TYPE, WEARABLE]],
          [
            /; (quest( \d| pro)?)/i
          ],
          [MODEL, [VENDOR, FACEBOOK], [TYPE, WEARABLE]],
          [
            /(tesla)(?: qtcarbrowser|\/[-\w\.]+)/i
          ],
          [VENDOR, [TYPE, EMBEDDED]],
          [
            /(aeobc)\b/i
          ],
          [MODEL, [VENDOR, AMAZON], [TYPE, EMBEDDED]],
          [
            /(homepod).+mac os/i
          ],
          [MODEL, [VENDOR, APPLE], [TYPE, EMBEDDED]],
          [
            /windows iot/i
          ],
          [[TYPE, EMBEDDED]],
          [
            /droid .+?; ([^;]+?)(?: bui|; wv\)|\) applew).+? mobile safari/i
          ],
          [MODEL, [TYPE, MOBILE]],
          [
            /droid .+?; ([^;]+?)(?: bui|\) applew).+?(?! mobile) safari/i
          ],
          [MODEL, [TYPE, TABLET]],
          [
            /\b((tablet|tab)[;\/]|focus\/\d(?!.+mobile))/i
          ],
          [[TYPE, TABLET]],
          [
            /(phone|mobile(?:[;\/]| [ \w\/\.]*safari)|pda(?=.+windows ce))/i
          ],
          [[TYPE, MOBILE]],
          [
            /droid .+?; ([\w\. -]+)( bui|\))/i
          ],
          [MODEL, [VENDOR, "Generic"]]
        ],
        engine: [
          [
            /windows.+ edge\/([\w\.]+)/i
          ],
          [VERSION2, [NAME, EDGE + "HTML"]],
          [
            /(arkweb)\/([\w\.]+)/i
          ],
          [NAME, VERSION2],
          [
            /webkit\/537\.36.+chrome\/(?!27)([\w\.]+)/i
          ],
          [VERSION2, [NAME, "Blink"]],
          [
            /(presto)\/([\w\.]+)/i,
            /(webkit|trident|netfront|netsurf|amaya|lynx|w3m|goanna|servo)\/([\w\.]+)/i,
            /ekioh(flow)\/([\w\.]+)/i,
            /(khtml|tasman|links)[\/ ]\(?([\w\.]+)/i,
            /(icab)[\/ ]([23]\.[\d\.]+)/i,
            /\b(libweb)/i
          ],
          [NAME, VERSION2],
          [
            /ladybird\//i
          ],
          [[NAME, "LibWeb"]],
          [
            /rv\:([\w\.]{1,9})\b.+(gecko)/i
          ],
          [VERSION2, NAME]
        ],
        os: [
          [
            /microsoft (windows) (vista|xp)/i
          ],
          [NAME, VERSION2],
          [
            /(windows (?:phone(?: os)?|mobile|iot))[\/ ]?([\d\.\w ]*)/i
          ],
          [NAME, [VERSION2, strMapper, windowsVersionMap]],
          [
            /windows nt 6\.2; (arm)/i,
            /windows[\/ ]([ntce\d\. ]+\w)(?!.+xbox)/i,
            /(?:win(?=3|9|n)|win 9x )([nt\d\.]+)/i
          ],
          [[VERSION2, strMapper, windowsVersionMap], [NAME, "Windows"]],
          [
            /[adehimnop]{4,7}\b(?:.*os ([\w]+) like mac|; opera)/i,
            /(?:ios;fbsv\/|iphone.+ios[\/ ])([\d\.]+)/i,
            /cfnetwork\/.+darwin/i
          ],
          [[VERSION2, /_/g, "."], [NAME, "iOS"]],
          [
            /(mac os x) ?([\w\. ]*)/i,
            /(macintosh|mac_powerpc\b)(?!.+haiku)/i
          ],
          [[NAME, MAC_OS], [VERSION2, /_/g, "."]],
          [
            /droid ([\w\.]+)\b.+(android[- ]x86|harmonyos)/i
          ],
          [VERSION2, NAME],
          [
            /(ubuntu) ([\w\.]+) like android/i
          ],
          [[NAME, /(.+)/, "$1 Touch"], VERSION2],
          [
            /(android|bada|blackberry|kaios|maemo|meego|openharmony|qnx|rim tablet os|sailfish|series40|symbian|tizen|webos)\w*[-\/; ]?([\d\.]*)/i
          ],
          [NAME, VERSION2],
          [
            /\(bb(10);/i
          ],
          [VERSION2, [NAME, BLACKBERRY]],
          [
            /(?:symbian ?os|symbos|s60(?=;)|series ?60)[-\/ ]?([\w\.]*)/i
          ],
          [VERSION2, [NAME, "Symbian"]],
          [
            /mozilla\/[\d\.]+ \((?:mobile|tablet|tv|mobile; [\w ]+); rv:.+ gecko\/([\w\.]+)/i
          ],
          [VERSION2, [NAME, FIREFOX + " OS"]],
          [
            /web0s;.+rt(tv)/i,
            /\b(?:hp)?wos(?:browser)?\/([\w\.]+)/i
          ],
          [VERSION2, [NAME, "webOS"]],
          [
            /watch(?: ?os[,\/]|\d,\d\/)([\d\.]+)/i
          ],
          [VERSION2, [NAME, "watchOS"]],
          [
            /crkey\/([\d\.]+)/i
          ],
          [VERSION2, [NAME, CHROME + "cast"]],
          [
            /(cros) [\w]+(?:\)| ([\w\.]+)\b)/i
          ],
          [[NAME, CHROMIUM_OS], VERSION2],
          [
            /panasonic;(viera)/i,
            /(netrange)mmh/i,
            /(nettv)\/(\d+\.[\w\.]+)/i,
            /(nintendo|playstation) ([wids345portablevuch]+)/i,
            /(xbox); +xbox ([^\);]+)/i,
            /\b(joli|palm)\b ?(?:os)?\/?([\w\.]*)/i,
            /(mint)[\/\(\) ]?(\w*)/i,
            /(mageia|vectorlinux)[; ]/i,
            /([kxln]?ubuntu|debian|suse|opensuse|gentoo|arch(?= linux)|slackware|fedora|mandriva|centos|pclinuxos|red ?hat|zenwalk|linpus|raspbian|plan 9|minix|risc os|contiki|deepin|manjaro|elementary os|sabayon|linspire)(?: gnu\/linux)?(?: enterprise)?(?:[- ]linux)?(?:-gnu)?[-\/ ]?(?!chrom|package)([-\w\.]*)/i,
            /(hurd|linux)(?: arm\w*| x86\w*| ?)([\w\.]*)/i,
            /(gnu) ?([\w\.]*)/i,
            /\b([-frentopcghs]{0,5}bsd|dragonfly)[\/ ]?(?!amd|[ix346]{1,2}86)([\w\.]*)/i,
            /(haiku) (\w+)/i
          ],
          [NAME, VERSION2],
          [
            /(sunos) ?([\w\.\d]*)/i
          ],
          [[NAME, "Solaris"], VERSION2],
          [
            /((?:open)?solaris)[-\/ ]?([\w\.]*)/i,
            /(aix) ((\d)(?=\.|\)| )[\w\.])*/i,
            /\b(beos|os\/2|amigaos|morphos|openvms|fuchsia|hp-ux|serenityos)/i,
            /(unix) ?([\w\.]*)/i
          ],
          [NAME, VERSION2]
        ]
      };
      var UAParser = function(ua, extensions) {
        if (typeof ua === OBJ_TYPE) {
          extensions = ua;
          ua = undefined2;
        }
        if (!(this instanceof UAParser)) {
          return new UAParser(ua, extensions).getResult();
        }
        var _navigator = typeof window2 !== UNDEF_TYPE && window2.navigator ? window2.navigator : undefined2;
        var _ua = ua || (_navigator && _navigator.userAgent ? _navigator.userAgent : EMPTY);
        var _uach = _navigator && _navigator.userAgentData ? _navigator.userAgentData : undefined2;
        var _rgxmap = extensions ? extend(regexes, extensions) : regexes;
        var _isSelfNav = _navigator && _navigator.userAgent == _ua;
        this.getBrowser = function() {
          var _browser = {};
          _browser[NAME] = undefined2;
          _browser[VERSION2] = undefined2;
          rgxMapper.call(_browser, _ua, _rgxmap.browser);
          _browser[MAJOR] = majorize(_browser[VERSION2]);
          if (_isSelfNav && _navigator && _navigator.brave && typeof _navigator.brave.isBrave == FUNC_TYPE) {
            _browser[NAME] = "Brave";
          }
          return _browser;
        };
        this.getCPU = function() {
          var _cpu = {};
          _cpu[ARCHITECTURE] = undefined2;
          rgxMapper.call(_cpu, _ua, _rgxmap.cpu);
          return _cpu;
        };
        this.getDevice = function() {
          var _device = {};
          _device[VENDOR] = undefined2;
          _device[MODEL] = undefined2;
          _device[TYPE] = undefined2;
          rgxMapper.call(_device, _ua, _rgxmap.device);
          if (_isSelfNav && !_device[TYPE] && _uach && _uach.mobile) {
            _device[TYPE] = MOBILE;
          }
          if (_isSelfNav && _device[MODEL] == "Macintosh" && _navigator && typeof _navigator.standalone !== UNDEF_TYPE && _navigator.maxTouchPoints && _navigator.maxTouchPoints > 2) {
            _device[MODEL] = "iPad";
            _device[TYPE] = TABLET;
          }
          return _device;
        };
        this.getEngine = function() {
          var _engine = {};
          _engine[NAME] = undefined2;
          _engine[VERSION2] = undefined2;
          rgxMapper.call(_engine, _ua, _rgxmap.engine);
          return _engine;
        };
        this.getOS = function() {
          var _os = {};
          _os[NAME] = undefined2;
          _os[VERSION2] = undefined2;
          rgxMapper.call(_os, _ua, _rgxmap.os);
          if (_isSelfNav && !_os[NAME] && _uach && _uach.platform && _uach.platform != "Unknown") {
            _os[NAME] = _uach.platform.replace(/chrome os/i, CHROMIUM_OS).replace(/macos/i, MAC_OS);
          }
          return _os;
        };
        this.getResult = function() {
          return {
            ua: this.getUA(),
            browser: this.getBrowser(),
            engine: this.getEngine(),
            os: this.getOS(),
            device: this.getDevice(),
            cpu: this.getCPU()
          };
        };
        this.getUA = function() {
          return _ua;
        };
        this.setUA = function(ua2) {
          _ua = typeof ua2 === STR_TYPE && ua2.length > UA_MAX_LENGTH ? trim(ua2, UA_MAX_LENGTH) : ua2;
          return this;
        };
        this.setUA(_ua);
        return this;
      };
      UAParser.VERSION = LIBVERSION;
      UAParser.BROWSER = enumerize([NAME, VERSION2, MAJOR]);
      UAParser.CPU = enumerize([ARCHITECTURE]);
      UAParser.DEVICE = enumerize([MODEL, VENDOR, TYPE, CONSOLE, MOBILE, SMARTTV, TABLET, WEARABLE, EMBEDDED]);
      UAParser.ENGINE = UAParser.OS = enumerize([NAME, VERSION2]);
      if (typeof exports !== UNDEF_TYPE) {
        if (typeof module !== UNDEF_TYPE && module.exports) {
          exports = module.exports = UAParser;
        }
        exports.UAParser = UAParser;
      } else {
        if (typeof define === FUNC_TYPE && define.amd) {
          define(function() {
            return UAParser;
          });
        } else if (typeof window2 !== UNDEF_TYPE) {
          window2.UAParser = UAParser;
        }
      }
      var $ = typeof window2 !== UNDEF_TYPE && (window2.jQuery || window2.Zepto);
      if ($ && !$.ua) {
        var parser = new UAParser;
        $.ua = parser.getResult();
        $.ua.get = function() {
          return parser.getUA();
        };
        $.ua.set = function(ua) {
          parser.setUA(ua);
          var result = parser.getResult();
          for (var prop in result) {
            $.ua[prop] = result[prop];
          }
        };
      }
    })(typeof window === "object" ? window : exports);
  });

  // node_modules/@grafana/faro-core/dist/esm/transports/batchExecutor.js
  var DEFAULT_SEND_TIMEOUT_MS = 250;
  var DEFAULT_BATCH_ITEM_LIMIT = 50;

  class BatchExecutor {
    constructor(sendFn, options) {
      var _a, _b;
      this.signalBuffer = [];
      this.itemLimit = (_a = options === null || options === undefined ? undefined : options.itemLimit) !== null && _a !== undefined ? _a : DEFAULT_BATCH_ITEM_LIMIT;
      this.sendTimeout = (_b = options === null || options === undefined ? undefined : options.sendTimeout) !== null && _b !== undefined ? _b : DEFAULT_SEND_TIMEOUT_MS;
      this.paused = (options === null || options === undefined ? undefined : options.paused) || false;
      this.sendFn = sendFn;
      if (!this.paused) {
        this.start();
      }
      if (typeof document !== "undefined") {
        document.addEventListener("visibilitychange", () => {
          if (document.visibilityState === "hidden") {
            this.flush();
          }
        });
      }
    }
    addItem(item) {
      if (this.paused) {
        return;
      }
      this.signalBuffer.push(item);
      if (this.signalBuffer.length >= this.itemLimit) {
        this.flush();
      }
    }
    start() {
      this.paused = false;
      if (this.sendTimeout > 0) {
        this.flushInterval = setInterval(() => this.flush(), this.sendTimeout);
      }
    }
    pause() {
      this.paused = true;
      clearInterval(this.flushInterval);
    }
    groupItems(items) {
      const itemMap = new Map;
      items.forEach((item) => {
        const metaKey = JSON.stringify(item.meta);
        let currentItems = itemMap.get(metaKey);
        if (currentItems === undefined) {
          currentItems = [item];
        } else {
          currentItems = [...currentItems, item];
        }
        itemMap.set(metaKey, currentItems);
      });
      return Array.from(itemMap.values());
    }
    flush() {
      if (this.paused || this.signalBuffer.length === 0) {
        return;
      }
      const itemGroups = this.groupItems(this.signalBuffer);
      itemGroups.forEach(this.sendFn);
      this.signalBuffer = [];
    }
  }

  // node_modules/@grafana/faro-core/dist/esm/transports/const.js
  var TransportItemType;
  (function(TransportItemType2) {
    TransportItemType2["EXCEPTION"] = "exception";
    TransportItemType2["LOG"] = "log";
    TransportItemType2["MEASUREMENT"] = "measurement";
    TransportItemType2["TRACE"] = "trace";
    TransportItemType2["EVENT"] = "event";
  })(TransportItemType || (TransportItemType = {}));
  var transportItemTypeToBodyKey = {
    [TransportItemType.EXCEPTION]: "exceptions",
    [TransportItemType.LOG]: "logs",
    [TransportItemType.MEASUREMENT]: "measurements",
    [TransportItemType.TRACE]: "traces",
    [TransportItemType.EVENT]: "events"
  };

  // node_modules/@grafana/faro-core/dist/esm/transports/initialize.js
  function initializeTransports(unpatchedConsole, internalLogger, config, metas) {
    var _a;
    internalLogger.debug("Initializing transports");
    const transports = [];
    let paused = config.paused;
    let beforeSendHooks = [];
    const add = (...newTransports) => {
      internalLogger.debug("Adding transports");
      newTransports.forEach((newTransport) => {
        internalLogger.debug(`Adding "${newTransport.name}" transport`);
        const exists = transports.some((existingTransport) => existingTransport === newTransport);
        if (exists) {
          internalLogger.warn(`Transport ${newTransport.name} is already added`);
          return;
        }
        newTransport.unpatchedConsole = unpatchedConsole;
        newTransport.internalLogger = internalLogger;
        newTransport.config = config;
        newTransport.metas = metas;
        transports.push(newTransport);
      });
    };
    const addBeforeSendHooks = (...newBeforeSendHooks) => {
      internalLogger.debug(`Adding beforeSendHooks
`, beforeSendHooks);
      newBeforeSendHooks.forEach((beforeSendHook) => {
        if (beforeSendHook) {
          beforeSendHooks.push(beforeSendHook);
        }
      });
    };
    const applyBeforeSendHooks = (items) => {
      let filteredItems = items;
      for (const hook of beforeSendHooks) {
        const modified = filteredItems.map(hook).filter(Boolean);
        if (modified.length === 0) {
          return [];
        }
        filteredItems = sanitizeItems(modified, config);
      }
      return filteredItems;
    };
    const batchedSend = (items) => {
      const filteredItems = applyBeforeSendHooks(items);
      if (filteredItems.length === 0) {
        return;
      }
      for (const transport of transports) {
        internalLogger.debug(`Transporting item using ${transport.name}
`, filteredItems);
        if (transport.isBatched()) {
          transport.send(filteredItems);
        }
      }
    };
    const instantSend = (item) => {
      var _a2, _b;
      if (((_a2 = config.batching) === null || _a2 === undefined ? undefined : _a2.enabled) && transports.every((transport) => transport.isBatched())) {
        return;
      }
      const [filteredItem] = applyBeforeSendHooks([item]);
      if (filteredItem === undefined) {
        return;
      }
      for (const transport of transports) {
        internalLogger.debug(`Transporting item using ${transport.name}
`, filteredItem);
        if (!transport.isBatched()) {
          transport.send(filteredItem);
        } else if (!((_b = config.batching) === null || _b === undefined ? undefined : _b.enabled)) {
          transport.send([filteredItem]);
        }
      }
    };
    let batchExecutor;
    if ((_a = config.batching) === null || _a === undefined ? undefined : _a.enabled) {
      batchExecutor = new BatchExecutor(batchedSend, {
        sendTimeout: config.batching.sendTimeout,
        itemLimit: config.batching.itemLimit,
        paused
      });
    }
    const execute = (item) => {
      var _a2;
      if (paused) {
        return;
      }
      if ((_a2 = config.batching) === null || _a2 === undefined ? undefined : _a2.enabled) {
        batchExecutor === null || batchExecutor === undefined || batchExecutor.addItem(item);
      }
      instantSend(item);
    };
    const getBeforeSendHooks = () => [...beforeSendHooks];
    const isPaused = () => paused;
    const pause = () => {
      internalLogger.debug("Pausing transports");
      batchExecutor === null || batchExecutor === undefined || batchExecutor.pause();
      paused = true;
    };
    const remove = (...transportsToRemove) => {
      internalLogger.debug("Removing transports");
      transportsToRemove.forEach((transportToRemove) => {
        internalLogger.debug(`Removing "${transportToRemove.name}" transport`);
        const existingTransportIndex = transports.indexOf(transportToRemove);
        if (existingTransportIndex === -1) {
          internalLogger.warn(`Transport "${transportToRemove.name}" is not added`);
          return;
        }
        transports.splice(existingTransportIndex, 1);
      });
    };
    const removeBeforeSendHooks = (...beforeSendHooksToRemove) => {
      beforeSendHooks.filter((beforeSendHook) => !beforeSendHooksToRemove.includes(beforeSendHook));
    };
    const unpause = () => {
      internalLogger.debug("Unpausing transports");
      batchExecutor === null || batchExecutor === undefined || batchExecutor.start();
      paused = false;
    };
    return {
      add,
      addBeforeSendHooks,
      getBeforeSendHooks,
      execute,
      isPaused,
      pause,
      remove,
      removeBeforeSendHooks,
      get transports() {
        return [...transports];
      },
      unpause
    };
  }
  function sanitizeItems(filteredItems, config) {
    if (config.preserveOriginalError) {
      for (const item of filteredItems) {
        if (item.type === TransportItemType.EXCEPTION) {
          delete item.payload.originalError;
        }
      }
    }
    return filteredItems;
  }
  // node_modules/@grafana/faro-core/dist/esm/utils/sampling.js
  function clampSamplingRate(samplingRate) {
    return Math.min(1, Math.max(0, samplingRate));
  }
  // node_modules/@grafana/faro-core/dist/esm/utils/is.js
  function isTypeof(value, type) {
    return typeof value === type;
  }
  function isToString(value, type) {
    return Object.prototype.toString.call(value) === `[object ${type}]`;
  }
  function isInstanceOf(value, reference) {
    try {
      return value instanceof reference;
    } catch (_err) {
      return false;
    }
  }
  var isNull = (value) => isTypeof(value, "null");
  var isString = (value) => isTypeof(value, "string");
  var isNumber = (value) => isTypeof(value, "number") && !isNaN(value) || isTypeof(value, "bigint");
  var isBoolean = (value) => isTypeof(value, "boolean");
  var isObject = (value) => !isNull(value) && isTypeof(value, "object");
  var isFunction = (value) => isTypeof(value, "function");
  var isArray = (value) => isToString(value, "Array");
  var isPrimitive = (value) => !isObject(value) && !isFunction(value);
  var isEventDefined = typeof Event !== "undefined";
  var isEvent = (value) => isEventDefined && isInstanceOf(value, Event);
  var isErrorDefined = typeof Error !== "undefined";
  var isError = (value) => isErrorDefined && isInstanceOf(value, Error);
  var isErrorEvent = (value) => isToString(value, "ErrorEvent");
  var isDomError = (value) => isToString(value, "DOMError");
  var isDomException = (value) => isToString(value, "DOMException");
  function isEmpty(value) {
    if (value == null) {
      return true;
    }
    if (isArray(value) || isString(value)) {
      return value.length === 0;
    }
    if (isObject(value)) {
      return Object.keys(value).length === 0;
    }
    return false;
  }

  // node_modules/@grafana/faro-core/dist/esm/utils/deepEqual.js
  function deepEqual(a, b) {
    if (a === b) {
      return true;
    }
    if (isTypeof(a, "number") && isNaN(a)) {
      return isTypeof(b, "number") && isNaN(b);
    }
    const aIsArray = isArray(a);
    const bIsArray = isArray(b);
    if (aIsArray !== bIsArray) {
      return false;
    }
    if (aIsArray && bIsArray) {
      const length = a.length;
      if (length !== b.length) {
        return false;
      }
      for (let idx = length;idx-- !== 0; ) {
        if (!deepEqual(a[idx], b[idx])) {
          return false;
        }
      }
      return true;
    }
    const aIsObject = isObject(a);
    const bIsObject = isObject(b);
    if (aIsObject !== bIsObject) {
      return false;
    }
    if (a && b && aIsObject && bIsObject) {
      const aKeys = Object.keys(a);
      const bKeys = Object.keys(b);
      const aLength = aKeys.length;
      const bLength = bKeys.length;
      if (aLength !== bLength) {
        return false;
      }
      for (let aKey of aKeys) {
        if (!bKeys.includes(aKey)) {
          return false;
        }
      }
      for (let aKey of aKeys) {
        if (!deepEqual(a[aKey], b[aKey])) {
          return false;
        }
      }
      return true;
    }
    return false;
  }
  // node_modules/@grafana/faro-core/dist/esm/utils/date.js
  function dateNow() {
    return Date.now();
  }
  function monoNow() {
    if (typeof performance !== "undefined" && typeof performance.now === "function") {
      return performance.now();
    }
    return Date.now();
  }
  function getCurrentTimestamp() {
    return new Date().toISOString();
  }
  function timestampToIsoString(value) {
    return new Date(value).toISOString();
  }
  // node_modules/@grafana/faro-core/dist/esm/utils/logLevels.js
  var LogLevel;
  (function(LogLevel2) {
    LogLevel2["TRACE"] = "trace";
    LogLevel2["DEBUG"] = "debug";
    LogLevel2["INFO"] = "info";
    LogLevel2["LOG"] = "log";
    LogLevel2["WARN"] = "warn";
    LogLevel2["ERROR"] = "error";
  })(LogLevel || (LogLevel = {}));
  var defaultLogLevel = LogLevel.LOG;
  var allLogLevels = [
    LogLevel.TRACE,
    LogLevel.DEBUG,
    LogLevel.INFO,
    LogLevel.LOG,
    LogLevel.WARN,
    LogLevel.ERROR
  ];
  // node_modules/@grafana/faro-core/dist/esm/utils/noop.js
  function noop() {}
  // node_modules/@grafana/faro-core/dist/esm/utils/promiseBuffer.js
  function createPromiseBuffer(options) {
    const { size, concurrency } = options;
    const buffer = [];
    let inProgress = 0;
    const work = () => {
      if (inProgress < concurrency && buffer.length) {
        const { producer, resolve, reject } = buffer.shift();
        inProgress++;
        producer().then((result) => {
          inProgress--;
          work();
          resolve(result);
        }, (reason) => {
          inProgress--;
          work();
          reject(reason);
        });
      }
    };
    const add = (promiseProducer) => {
      if (buffer.length + inProgress >= size) {
        throw new Error("Task buffer full");
      }
      return new Promise((resolve, reject) => {
        buffer.push({
          producer: promiseProducer,
          resolve,
          reject
        });
        work();
      });
    };
    return {
      add
    };
  }
  // node_modules/@grafana/faro-core/dist/esm/utils/shortId.js
  var alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ0123456789";
  function genShortID(length = 10) {
    const values = new Uint32Array(length);
    const cryptoObj = typeof globalThis !== "undefined" ? globalThis.crypto : undefined;
    if (cryptoObj === null || cryptoObj === undefined ? undefined : cryptoObj.getRandomValues) {
      cryptoObj.getRandomValues(values);
    } else {
      for (let i = 0;i < length; i++) {
        values[i] = Math.floor(Math.random() * 4294967296);
      }
    }
    let result = "";
    for (let i = 0;i < length; i++) {
      result += alphabet[values[i] % alphabet.length];
    }
    return result;
  }
  // node_modules/@grafana/faro-core/dist/esm/globalObject/globalObject.js
  var globalObject = typeof globalThis !== "undefined" ? globalThis : typeof global !== "undefined" ? global : typeof self !== "undefined" ? self : undefined;
  // node_modules/@grafana/faro-core/dist/esm/utils/sourceMaps.js
  function getBundleId(appName) {
    const key = `__faroBundleId_${appName}`;
    const fromGlobal = globalObject === null || globalObject === undefined ? undefined : globalObject[key];
    if (typeof fromGlobal === "string" && fromGlobal !== "") {
      return fromGlobal;
    }
    const fromWindow = typeof window !== "undefined" ? window[key] : undefined;
    if (typeof fromWindow === "string" && fromWindow !== "") {
      return fromWindow;
    }
    return;
  }
  function getGitHash(appName) {
    return globalObject === null || globalObject === undefined ? undefined : globalObject[`__faroGitHash_${appName}`];
  }
  // node_modules/@grafana/faro-core/dist/esm/utils/json.js
  function getCircularDependencyReplacer() {
    const valueSeen = new WeakSet;
    return function(_key, value) {
      if (isObject(value) && value !== null) {
        if (valueSeen.has(value)) {
          return null;
        }
        valueSeen.add(value);
      }
      return value;
    };
  }
  function stringifyExternalJson(json = {}) {
    return JSON.stringify(json !== null && json !== undefined ? json : {}, getCircularDependencyReplacer());
  }
  function stringifyObjectValues(obj = {}) {
    const o = {};
    for (const [key, value] of Object.entries(obj)) {
      o[key] = isObject(value) && value !== null ? stringifyExternalJson(value) : String(value);
    }
    return o;
  }
  // node_modules/@grafana/faro-core/dist/esm/utils/reactive.js
  class Observable {
    constructor() {
      this.subscribers = [];
    }
    subscribe(subscriber) {
      this.subscribers.push(subscriber);
      return {
        unsubscribe: () => this.unsubscribe(subscriber)
      };
    }
    unsubscribe(subscriber) {
      this.subscribers = this.subscribers.filter((sub) => sub !== subscriber);
    }
    notify(value) {
      this.subscribers.forEach((subscriber) => subscriber(value));
    }
    first() {
      const result = new Observable;
      const internalSubscriber = (data) => {
        result.notify(data);
        subscription.unsubscribe();
      };
      const subscription = this.subscribe(internalSubscriber);
      const resultUnsubscribeFn = result.unsubscribe.bind(result);
      return this.withUnsubscribeOverride(result, resultUnsubscribeFn, internalSubscriber);
    }
    takeWhile(predicate) {
      const result = new Observable;
      const internalSubscriber = (value) => {
        if (predicate(value)) {
          result.notify(value);
        } else {
          result.unsubscribe(internalSubscriber);
        }
      };
      this.subscribe(internalSubscriber);
      const resultUnsubscribeFn = result.unsubscribe.bind(result);
      return this.withUnsubscribeOverride(result, resultUnsubscribeFn, internalSubscriber);
    }
    filter(predicate) {
      const result = new Observable;
      const internalSubscriber = (value) => {
        if (predicate(value)) {
          result.notify(value);
        }
      };
      this.subscribe(internalSubscriber);
      const resultUnsubscribeFn = result.unsubscribe.bind(result);
      return this.withUnsubscribeOverride(result, resultUnsubscribeFn, internalSubscriber);
    }
    merge(...observables) {
      const mergerObservable = new Observable;
      const subscriptions = [];
      observables.forEach((observable) => {
        const subscription = observable.subscribe((value) => {
          mergerObservable.notify(value);
        });
        subscriptions.push(subscription);
      });
      const originalUnsubscribeAll = mergerObservable.unsubscribeAll.bind(mergerObservable);
      mergerObservable.unsubscribe = () => {
        subscriptions.forEach((subscription) => subscription.unsubscribe());
        originalUnsubscribeAll();
      };
      return mergerObservable;
    }
    withUnsubscribeOverride(observable, resultUnsubscribeFn, internalSubscriber) {
      observable.unsubscribe = (subscriber) => {
        resultUnsubscribeFn(subscriber);
        this.unsubscribe(internalSubscriber);
      };
      return observable;
    }
    unsubscribeAll() {
      this.subscribers = [];
    }
  }
  // node_modules/@grafana/faro-core/dist/esm/internalLogger/const.js
  var InternalLoggerLevel;
  (function(InternalLoggerLevel2) {
    InternalLoggerLevel2[InternalLoggerLevel2["OFF"] = 0] = "OFF";
    InternalLoggerLevel2[InternalLoggerLevel2["ERROR"] = 1] = "ERROR";
    InternalLoggerLevel2[InternalLoggerLevel2["WARN"] = 2] = "WARN";
    InternalLoggerLevel2[InternalLoggerLevel2["INFO"] = 3] = "INFO";
    InternalLoggerLevel2[InternalLoggerLevel2["VERBOSE"] = 4] = "VERBOSE";
  })(InternalLoggerLevel || (InternalLoggerLevel = {}));
  var defaultInternalLoggerPrefix = "Faro";
  var defaultInternalLogger = {
    debug: noop,
    error: noop,
    info: noop,
    prefix: defaultInternalLoggerPrefix,
    warn: noop
  };
  var defaultInternalLoggerLevel = InternalLoggerLevel.ERROR;
  // node_modules/@grafana/faro-core/dist/esm/unpatchedConsole/const.js
  var defaultUnpatchedConsole = Object.assign({}, console);
  // node_modules/@grafana/faro-core/dist/esm/unpatchedConsole/initialize.js
  var unpatchedConsole = defaultUnpatchedConsole;
  function initializeUnpatchedConsole(config) {
    var _a;
    unpatchedConsole = (_a = config.unpatchedConsole) !== null && _a !== undefined ? _a : unpatchedConsole;
    return unpatchedConsole;
  }
  // node_modules/@grafana/faro-core/dist/esm/internalLogger/createInternalLogger.js
  function createInternalLogger(unpatchedConsole2 = defaultUnpatchedConsole, internalLoggerLevel = defaultInternalLoggerLevel) {
    const internalLogger = defaultInternalLogger;
    if (internalLoggerLevel > InternalLoggerLevel.OFF) {
      internalLogger.error = internalLoggerLevel >= InternalLoggerLevel.ERROR ? function(...args) {
        unpatchedConsole2.error(`${internalLogger.prefix}
`, ...args);
      } : noop;
      internalLogger.warn = internalLoggerLevel >= InternalLoggerLevel.WARN ? function(...args) {
        unpatchedConsole2.warn(`${internalLogger.prefix}
`, ...args);
      } : noop;
      internalLogger.info = internalLoggerLevel >= InternalLoggerLevel.INFO ? function(...args) {
        unpatchedConsole2.info(`${internalLogger.prefix}
`, ...args);
      } : noop;
      internalLogger.debug = internalLoggerLevel >= InternalLoggerLevel.VERBOSE ? function(...args) {
        unpatchedConsole2.debug(`${internalLogger.prefix}
`, ...args);
      } : noop;
    }
    return internalLogger;
  }
  // node_modules/@grafana/faro-core/dist/esm/internalLogger/initialize.js
  var internalLogger = defaultInternalLogger;
  function initializeInternalLogger(unpatchedConsole2, config) {
    internalLogger = createInternalLogger(unpatchedConsole2, config.internalLoggerLevel);
    return internalLogger;
  }
  // node_modules/@grafana/faro-core/dist/esm/extensions/baseExtension.js
  class BaseExtension {
    constructor() {
      this.unpatchedConsole = defaultUnpatchedConsole;
      this.internalLogger = defaultInternalLogger;
      this.config = {};
      this.metas = {};
    }
    logDebug(...args) {
      this.internalLogger.debug(`${this.name}
`, ...args);
    }
    logInfo(...args) {
      this.internalLogger.info(`${this.name}
`, ...args);
    }
    logWarn(...args) {
      this.internalLogger.warn(`${this.name}
`, ...args);
    }
    logError(...args) {
      this.internalLogger.error(`${this.name}
`, ...args);
    }
  }
  // node_modules/@grafana/faro-core/dist/esm/transports/base.js
  class BaseTransport extends BaseExtension {
    isBatched() {
      return false;
    }
    getIgnoreUrls() {
      return [];
    }
  }
  // node_modules/@grafana/faro-core/dist/esm/transports/registerInitial.js
  function registerInitialTransports(faro) {
    faro.transports.add(...faro.config.transports);
    faro.transports.addBeforeSendHooks(faro.config.beforeSend);
  }
  // node_modules/@grafana/faro-core/dist/esm/transports/utils.js
  function mergeResourceSpans(traces, resourceSpans) {
    var _a, _b;
    if (resourceSpans === undefined) {
      return traces;
    }
    if (traces === undefined) {
      return {
        resourceSpans
      };
    }
    const currentResource = (_a = traces.resourceSpans) === null || _a === undefined ? undefined : _a[0];
    if (currentResource === undefined) {
      return traces;
    }
    const currentSpans = (currentResource === null || currentResource === undefined ? undefined : currentResource.scopeSpans) || [];
    const newSpans = ((_b = resourceSpans === null || resourceSpans === undefined ? undefined : resourceSpans[0]) === null || _b === undefined ? undefined : _b.scopeSpans) || [];
    return Object.assign(Object.assign({}, traces), { resourceSpans: [
      Object.assign(Object.assign({}, currentResource), { scopeSpans: [...currentSpans, ...newSpans] })
    ] });
  }
  function getTransportBody(item) {
    let body = {
      meta: {}
    };
    if (item[0] !== undefined) {
      body.meta = item[0].meta;
    }
    item.forEach((currentItem) => {
      switch (currentItem.type) {
        case TransportItemType.LOG:
        case TransportItemType.EVENT:
        case TransportItemType.EXCEPTION:
        case TransportItemType.MEASUREMENT: {
          const bk = transportItemTypeToBodyKey[currentItem.type];
          const signals = body[bk];
          body = Object.assign(Object.assign({}, body), { [bk]: signals === undefined ? [currentItem.payload] : [...signals, currentItem.payload] });
          break;
        }
        case TransportItemType.TRACE: {
          body = Object.assign(Object.assign({}, body), { traces: mergeResourceSpans(body.traces, currentItem.payload.resourceSpans) });
          break;
        }
      }
    });
    return body;
  }
  // node_modules/@grafana/faro-core/dist/esm/api/userActions/const.js
  var userActionStartByApiCallEventName = "faroApiCall";
  var userActionStart = "user_action_start";
  var UserActionImportance = {
    Normal: "normal",
    Critical: "critical"
  };
  var userActionEventName = "faro.user.action";

  // node_modules/@grafana/faro-core/dist/esm/api/userActions/types.js
  var UserActionState;
  (function(UserActionState2) {
    UserActionState2[UserActionState2["Started"] = 0] = "Started";
    UserActionState2[UserActionState2["Halted"] = 1] = "Halted";
    UserActionState2[UserActionState2["Cancelled"] = 2] = "Cancelled";
    UserActionState2[UserActionState2["Ended"] = 3] = "Ended";
  })(UserActionState || (UserActionState = {}));

  // node_modules/@grafana/faro-core/dist/esm/api/ItemBuffer.js
  class ItemBuffer {
    constructor() {
      this.buffer = [];
    }
    addItem(item) {
      this.buffer.push(item);
    }
    flushBuffer(cb) {
      if (isFunction(cb)) {
        for (const item of this.buffer) {
          cb(item);
        }
      }
      this.buffer.length = 0;
    }
    size() {
      return this.buffer.length;
    }
  }

  // node_modules/@grafana/faro-core/dist/esm/api/userActions/userAction.js
  class UserAction extends Observable {
    constructor({ name, parentId, trigger, transports, attributes, trackUserActionsExcludeItem, importance = UserActionImportance.Normal, pushEvent }) {
      super();
      this.name = name;
      this.attributes = attributes;
      this.id = genShortID();
      this.trigger = trigger;
      this.parentId = parentId !== null && parentId !== undefined ? parentId : this.id;
      this.trackUserActionsExcludeItem = trackUserActionsExcludeItem;
      this.importance = importance;
      this._pushEvent = pushEvent;
      this._itemBuffer = new ItemBuffer;
      this._transports = transports;
      this._state = UserActionState.Started;
      this._start();
    }
    addItem(item) {
      if (this._state === UserActionState.Started) {
        this._itemBuffer.addItem(item);
        return true;
      }
      return false;
    }
    _start() {
      this._state = UserActionState.Started;
      if (this._state === UserActionState.Started) {
        this.startTime = dateNow();
        this._startTimeMono = monoNow();
      }
    }
    halt() {
      if (this._state !== UserActionState.Started) {
        return;
      }
      this._state = UserActionState.Halted;
      this.notify(this._state);
    }
    cancel() {
      if (this._state === UserActionState.Started) {
        this._itemBuffer.flushBuffer((item) => {
          this._transports.execute(item);
        });
      }
      this._state = UserActionState.Cancelled;
      this.notify(this._state);
    }
    end() {
      if (this._state === UserActionState.Cancelled) {
        return;
      }
      const endTime = dateNow();
      const duration = monoNow() - this._startTimeMono;
      this._state = UserActionState.Ended;
      this._itemBuffer.flushBuffer((item) => {
        if (isExcludeFromUserAction(item, this.trackUserActionsExcludeItem)) {
          this._transports.execute(item);
          return;
        }
        const userActionItem = Object.assign(Object.assign({}, item), { payload: Object.assign(Object.assign({}, item.payload), { action: {
          parentId: this.id,
          name: this.name
        } }) });
        this._transports.execute(userActionItem);
      });
      this._state = UserActionState.Ended;
      this.notify(this._state);
      this._pushEvent(userActionEventName, Object.assign({ userActionName: this.name, userActionStartTime: this.startTime.toString(), userActionEndTime: endTime.toString(), userActionDuration: duration.toString(), userActionTrigger: this.trigger, userActionImportance: this.importance }, stringifyObjectValues(this.attributes)), undefined, {
        timestampOverwriteMs: this.startTime,
        customPayloadTransformer: (payload) => {
          payload.action = {
            id: this.id,
            name: this.name
          };
          return payload;
        }
      });
    }
    getState() {
      return this._state;
    }
  }
  function isExcludeFromUserAction(item, trackUserActionsExcludeItem) {
    return (trackUserActionsExcludeItem === null || trackUserActionsExcludeItem === undefined ? undefined : trackUserActionsExcludeItem(item)) || item.type === TransportItemType.MEASUREMENT && item.payload.type === "web-vitals";
  }

  // node_modules/@grafana/faro-core/dist/esm/api/userActions/initialize.js
  var userActionsMessageBus = new Observable;
  function initializeUserActionsAPI({ transports, internalLogger: internalLogger2, config, pushEvent }) {
    var _a;
    const trackUserActionsExcludeItem = (_a = config.userActionsInstrumentation) === null || _a === undefined ? undefined : _a.excludeItem;
    let activeUserAction;
    const startUserAction = (name, attributes, options) => {
      const currentRunningUserAction = getActiveUserAction();
      if (currentRunningUserAction === undefined) {
        const userAction = new UserAction({
          name,
          transports,
          attributes,
          trigger: (options === null || options === undefined ? undefined : options.triggerName) || userActionStartByApiCallEventName,
          importance: (options === null || options === undefined ? undefined : options.importance) || UserActionImportance.Normal,
          trackUserActionsExcludeItem,
          pushEvent
        });
        userAction.filter((v) => [UserActionState.Ended, UserActionState.Cancelled].includes(v)).first().subscribe(() => {
          activeUserAction = undefined;
        });
        userActionsMessageBus.notify({
          type: userActionStart,
          userAction
        });
        activeUserAction = userAction;
        return activeUserAction;
      } else {
        internalLogger2.error("Attempted to create a new user action while one is already running. This is not possible.");
        return;
      }
    };
    const getActiveUserAction = () => {
      return activeUserAction;
    };
    const api = {
      startUserAction,
      getActiveUserAction
    };
    return api;
  }
  function addItemToUserActionBuffer(userAction, item) {
    if (!userAction) {
      return false;
    }
    const state = userAction === null || userAction === undefined ? undefined : userAction.getState();
    if (state !== UserActionState.Started) {
      return false;
    }
    userAction.addItem(item);
    return true;
  }

  // node_modules/@grafana/faro-core/dist/esm/api/events/initialize.js
  function initializeEventsAPI({ internalLogger: internalLogger2, config, metas, transports, tracesApi, userActionsApi }) {
    let lastPayload = null;
    const pushEvent = (name, attributes, domain, { skipDedupe, spanContext, timestampOverwriteMs, customPayloadTransformer = (payload) => payload } = {}) => {
      try {
        const attrs = stringifyObjectValues(attributes);
        const item = {
          meta: metas.value,
          payload: customPayloadTransformer({
            name,
            domain: domain !== null && domain !== undefined ? domain : config.eventDomain,
            attributes: isEmpty(attrs) ? undefined : attrs,
            timestamp: timestampOverwriteMs ? timestampToIsoString(timestampOverwriteMs) : getCurrentTimestamp(),
            trace: spanContext ? {
              trace_id: spanContext.traceId,
              span_id: spanContext.spanId
            } : tracesApi.getTraceContext()
          }),
          type: TransportItemType.EVENT
        };
        const testingPayload = {
          name: item.payload.name,
          attributes: item.payload.attributes,
          domain: item.payload.domain
        };
        if (!skipDedupe && config.dedupe && !isNull(lastPayload) && deepEqual(testingPayload, lastPayload)) {
          internalLogger2.debug(`Skipping event push because it is the same as the last one
`, item.payload);
          return;
        }
        lastPayload = testingPayload;
        internalLogger2.debug(`Pushing event
`, item);
        if (!addItemToUserActionBuffer(userActionsApi.getActiveUserAction(), item)) {
          transports.execute(item);
        }
      } catch (err) {
        internalLogger2.error("Error pushing event", err);
      }
    };
    return {
      pushEvent
    };
  }
  // node_modules/@grafana/faro-core/dist/esm/api/exceptions/const.js
  var defaultExceptionType = "Error";
  var defaultErrorArgsSerializer = (args) => {
    return args.map((arg) => {
      if (isObject(arg)) {
        return stringifyExternalJson(arg);
      }
      return String(arg);
    }).join(" ");
  };
  // node_modules/@grafana/faro-core/dist/esm/api/utils.js
  function shouldIgnoreEvent(patterns, msg) {
    return patterns.some((pattern) => {
      return isString(pattern) ? msg.includes(pattern) : !!msg.match(pattern);
    });
  }

  // node_modules/@grafana/faro-core/dist/esm/api/exceptions/initialize.js
  var stacktraceParser;
  function initializeExceptionsAPI({ internalLogger: internalLogger2, config, metas, transports, tracesApi, userActionsApi }) {
    var _a;
    internalLogger2.debug("Initializing exceptions API");
    let lastPayload = null;
    stacktraceParser = (_a = config.parseStacktrace) !== null && _a !== undefined ? _a : stacktraceParser;
    const changeStacktraceParser = (newStacktraceParser) => {
      internalLogger2.debug("Changing stacktrace parser");
      stacktraceParser = newStacktraceParser !== null && newStacktraceParser !== undefined ? newStacktraceParser : stacktraceParser;
    };
    const getStacktraceParser = () => stacktraceParser;
    const { ignoreErrors = [], preserveOriginalError } = config;
    const pushError = (error, { skipDedupe, stackFrames, type, context, spanContext, timestampOverwriteMs, originalError, fingerprint, fatal } = {}) => {
      var _a2;
      if (isErrorIgnored(ignoreErrors, originalError !== null && originalError !== undefined ? originalError : error)) {
        return;
      }
      try {
        const ctx = stringifyObjectValues(Object.assign(Object.assign({}, parseCause(originalError !== null && originalError !== undefined ? originalError : error)), context !== null && context !== undefined ? context : {}));
        const item = {
          meta: metas.value,
          payload: Object.assign(Object.assign(Object.assign(Object.assign({ type: type || error.name || defaultExceptionType, value: error.message, timestamp: timestampOverwriteMs ? timestampToIsoString(timestampOverwriteMs) : getCurrentTimestamp(), trace: spanContext ? {
            trace_id: spanContext.traceId,
            span_id: spanContext.spanId
          } : tracesApi.getTraceContext() }, isEmpty(ctx) ? {} : { context: ctx }), preserveOriginalError ? { originalError } : {}), fingerprint ? { fingerprint } : {}), fatal !== undefined ? { fatal } : {}),
          type: TransportItemType.EXCEPTION
        };
        stackFrames = stackFrames !== null && stackFrames !== undefined ? stackFrames : error.stack ? stacktraceParser === null || stacktraceParser === undefined ? undefined : stacktraceParser(error).frames : undefined;
        if (stackFrames === null || stackFrames === undefined ? undefined : stackFrames.length) {
          item.payload.stacktrace = {
            frames: stackFrames
          };
        }
        const testingPayload = {
          type: item.payload.type,
          value: item.payload.value,
          stacktrace: item.payload.stacktrace,
          context: item.payload.context,
          fingerprint: item.payload.fingerprint,
          fatal: (_a2 = item.payload.fatal) !== null && _a2 !== undefined ? _a2 : false
        };
        if (!skipDedupe && config.dedupe && !isNull(lastPayload) && deepEqual(testingPayload, lastPayload)) {
          internalLogger2.debug(`Skipping error push because it is the same as the last one
`, item.payload);
          return;
        }
        lastPayload = testingPayload;
        internalLogger2.debug(`Pushing exception
`, item);
        if (!addItemToUserActionBuffer(userActionsApi.getActiveUserAction(), item)) {
          transports.execute(item);
        }
      } catch (err) {
        internalLogger2.error("Error pushing event", err);
      }
    };
    changeStacktraceParser(config.parseStacktrace);
    return {
      changeStacktraceParser,
      getStacktraceParser,
      pushError
    };
  }
  function parseCause(error) {
    let cause = error.cause;
    if (isError(cause)) {
      cause = error.cause.toString();
    } else if (cause !== null && (isObject(error.cause) || isArray(error.cause))) {
      cause = stringifyExternalJson(error.cause);
    } else if (cause != null) {
      cause = error.cause.toString();
    }
    return cause == null ? {} : { cause };
  }
  function isErrorIgnored(ignoreErrors, error) {
    const { message, name, stack } = error;
    return shouldIgnoreEvent(ignoreErrors, message + " " + name + " " + stack);
  }
  // node_modules/@grafana/faro-core/dist/esm/api/logs/const.js
  var defaultLogArgsSerializer = (args) => args.map((arg) => {
    try {
      return String(arg);
    } catch (_err) {
      return "";
    }
  }).join(" ");
  // node_modules/@grafana/faro-core/dist/esm/api/logs/initialize.js
  function initializeLogsAPI({ internalLogger: internalLogger2, config, metas, transports, tracesApi, userActionsApi }) {
    var _a;
    internalLogger2.debug("Initializing logs API");
    let lastPayload = null;
    const logArgsSerializer = (_a = config.logArgsSerializer) !== null && _a !== undefined ? _a : defaultLogArgsSerializer;
    const pushLog = (args, { context, level, skipDedupe, spanContext, timestampOverwriteMs } = {}) => {
      try {
        const ctx = stringifyObjectValues(context);
        const item = {
          type: TransportItemType.LOG,
          payload: {
            message: logArgsSerializer(args),
            level: level !== null && level !== undefined ? level : defaultLogLevel,
            context: isEmpty(ctx) ? undefined : ctx,
            timestamp: timestampOverwriteMs ? timestampToIsoString(timestampOverwriteMs) : getCurrentTimestamp(),
            trace: spanContext ? {
              trace_id: spanContext.traceId,
              span_id: spanContext.spanId
            } : tracesApi.getTraceContext()
          },
          meta: metas.value
        };
        const testingPayload = {
          message: item.payload.message,
          level: item.payload.level,
          context: item.payload.context
        };
        if (!skipDedupe && config.dedupe && !isNull(lastPayload) && deepEqual(testingPayload, lastPayload)) {
          internalLogger2.debug(`Skipping log push because it is the same as the last one
`, item.payload);
          return;
        }
        lastPayload = testingPayload;
        internalLogger2.debug(`Pushing log
`, item);
        if (!addItemToUserActionBuffer(userActionsApi.getActiveUserAction(), item)) {
          transports.execute(item);
        }
      } catch (err) {
        internalLogger2.error(`Error pushing log
`, err);
      }
    };
    return {
      pushLog
    };
  }
  // node_modules/@grafana/faro-core/dist/esm/api/measurements/initialize.js
  function initializeMeasurementsAPI({ internalLogger: internalLogger2, config, metas, transports, tracesApi, userActionsApi }) {
    internalLogger2.debug("Initializing measurements API");
    let lastPayload = null;
    const pushMeasurement = (payload, { skipDedupe, context, spanContext, timestampOverwriteMs } = {}) => {
      try {
        const ctx = stringifyObjectValues(context);
        const item = {
          type: TransportItemType.MEASUREMENT,
          payload: Object.assign(Object.assign({}, payload), { trace: spanContext ? {
            trace_id: spanContext.traceId,
            span_id: spanContext.spanId
          } : tracesApi.getTraceContext(), timestamp: timestampOverwriteMs ? timestampToIsoString(timestampOverwriteMs) : getCurrentTimestamp(), context: isEmpty(ctx) ? undefined : ctx }),
          meta: metas.value
        };
        const testingPayload = {
          type: item.payload.type,
          values: item.payload.values,
          context: item.payload.context
        };
        if (!skipDedupe && config.dedupe && !isNull(lastPayload) && deepEqual(testingPayload, lastPayload)) {
          internalLogger2.debug(`Skipping measurement push because it is the same as the last one
`, item.payload);
          return;
        }
        lastPayload = testingPayload;
        internalLogger2.debug(`Pushing measurement
`, item);
        if (!addItemToUserActionBuffer(userActionsApi.getActiveUserAction(), item)) {
          transports.execute(item);
        }
      } catch (err) {
        internalLogger2.error(`Error pushing measurement
`, err);
      }
    };
    return {
      pushMeasurement
    };
  }
  // node_modules/@grafana/faro-core/dist/esm/api/meta/initialize.js
  function initializeMetaAPI({ internalLogger: internalLogger2, metas }) {
    internalLogger2.debug("Initializing meta API");
    let metaSession = undefined;
    let metaUser = undefined;
    let metaView = undefined;
    let metaPage = undefined;
    const setUser = (user) => {
      if (metaUser) {
        metas.remove(metaUser);
      }
      metaUser = {
        user
      };
      metas.add(metaUser);
    };
    const setSession = (session, options) => {
      var _a;
      const newOverrides = options === null || options === undefined ? undefined : options.overrides;
      const overrides = newOverrides ? {
        overrides: Object.assign(Object.assign({}, (_a = metaSession === null || metaSession === undefined ? undefined : metaSession.session) === null || _a === undefined ? undefined : _a.overrides), newOverrides)
      } : {};
      if (metaSession) {
        metas.remove(metaSession);
      }
      metaSession = {
        session: Object.assign(Object.assign({}, isEmpty(session) ? undefined : session), overrides)
      };
      metas.add(metaSession);
    };
    const getSession = () => metas.value.session;
    const setView = (view, options) => {
      var _a;
      if (options === null || options === undefined ? undefined : options.overrides) {
        setSession(getSession(), { overrides: options.overrides });
      }
      if (((_a = metaView === null || metaView === undefined ? undefined : metaView.view) === null || _a === undefined ? undefined : _a.name) === (view === null || view === undefined ? undefined : view.name)) {
        return;
      }
      const previousView = metaView;
      metaView = {
        view
      };
      metas.add(metaView);
      if (previousView) {
        metas.remove(previousView);
      }
    };
    const getView = () => metas.value.view;
    const setPage = (page) => {
      var _a;
      const pageMeta = isString(page) ? Object.assign(Object.assign({}, (_a = metaPage === null || metaPage === undefined ? undefined : metaPage.page) !== null && _a !== undefined ? _a : getPage()), { id: page }) : page;
      if (metaPage) {
        metas.remove(metaPage);
      }
      metaPage = {
        page: pageMeta
      };
      metas.add(metaPage);
    };
    const getPage = () => metas.value.page;
    return {
      setUser,
      resetUser: setUser,
      setSession,
      resetSession: setSession,
      getSession,
      setView,
      getView,
      setPage,
      getPage
    };
  }
  // node_modules/@grafana/faro-core/dist/esm/api/traces/initialize.js
  function initializeTracesAPI(_unpatchedConsole, internalLogger2, _config, metas, transports) {
    internalLogger2.debug("Initializing traces API");
    let otel = undefined;
    const initOTEL = (trace, context) => {
      internalLogger2.debug("Initializing OpenTelemetry");
      otel = {
        trace,
        context
      };
    };
    const getTraceContext = () => {
      const ctx = otel === null || otel === undefined ? undefined : otel.trace.getSpanContext(otel.context.active());
      return !ctx ? undefined : {
        trace_id: ctx.traceId,
        span_id: ctx.spanId
      };
    };
    const pushTraces = (payload) => {
      try {
        const item = {
          type: TransportItemType.TRACE,
          payload,
          meta: metas.value
        };
        internalLogger2.debug(`Pushing trace
`, item);
        transports.execute(item);
      } catch (err) {
        internalLogger2.error(`Error pushing trace
`, err);
      }
    };
    const getOTEL = () => otel;
    const isOTELInitialized = () => !!otel;
    return {
      getOTEL,
      getTraceContext,
      initOTEL,
      isOTELInitialized,
      pushTraces
    };
  }
  // node_modules/@grafana/faro-core/dist/esm/api/initialize.js
  function initializeAPI(unpatchedConsole2, internalLogger2, config, metas, transports) {
    internalLogger2.debug("Initializing API");
    let pushEventImpl = null;
    const pushEventWrapper = (name, attributes, domain, options) => {
      if (pushEventImpl) {
        pushEventImpl(name, attributes, domain, options);
      } else {
        internalLogger2.warn("pushEventImpl is not initialized. Event dropped:", { name, attributes, domain, options });
      }
    };
    const userActionsApi = initializeUserActionsAPI({
      transports,
      config,
      internalLogger: internalLogger2,
      pushEvent: pushEventWrapper
    });
    const tracesApi = initializeTracesAPI(unpatchedConsole2, internalLogger2, config, metas, transports);
    const props = {
      unpatchedConsole: unpatchedConsole2,
      internalLogger: internalLogger2,
      userActionsApi,
      config,
      metas,
      transports,
      tracesApi
    };
    const eventsApi = initializeEventsAPI(props);
    pushEventImpl = eventsApi.pushEvent;
    return Object.assign(Object.assign(Object.assign(Object.assign(Object.assign(Object.assign(Object.assign({}, tracesApi), initializeExceptionsAPI(props)), initializeMetaAPI(props)), initializeLogsAPI(props)), initializeMeasurementsAPI(props)), eventsApi), userActionsApi);
  }
  // node_modules/@grafana/faro-core/dist/esm/api/noop.js
  function getNoopAPI() {
    return {
      pushLog: () => {},
      pushError: () => {},
      changeStacktraceParser: () => {},
      getStacktraceParser: () => {
        return;
      },
      pushMeasurement: () => {},
      pushTraces: () => {},
      getOTEL: () => {
        return;
      },
      getTraceContext: () => {
        return;
      },
      initOTEL: () => {},
      isOTELInitialized: () => false,
      setUser: () => {},
      resetUser: () => {},
      setSession: () => {},
      resetSession: () => {},
      getSession: () => {
        return;
      },
      setView: () => {},
      getView: () => {
        return;
      },
      setPage: () => {},
      getPage: () => {
        return;
      },
      pushEvent: () => {},
      startUserAction: () => {
        return;
      },
      getActiveUserAction: () => {
        return;
      }
    };
  }
  // node_modules/@grafana/faro-core/dist/esm/instrumentations/base.js
  class BaseInstrumentation extends BaseExtension {
    constructor() {
      super(...arguments);
      this.api = {};
      this.transports = {};
    }
  }
  // node_modules/@grafana/faro-core/dist/esm/instrumentations/initialize.js
  function initializeInstrumentations(unpatchedConsole2, internalLogger2, config, metas, transports, api) {
    internalLogger2.debug("Initializing instrumentations");
    const instrumentations = [];
    const add = (...newInstrumentations) => {
      internalLogger2.debug("Adding instrumentations");
      newInstrumentations.forEach((newInstrumentation) => {
        internalLogger2.debug(`Adding "${newInstrumentation.name}" instrumentation`);
        const exists = instrumentations.some((existingInstrumentation) => existingInstrumentation.name === newInstrumentation.name);
        if (exists) {
          internalLogger2.warn(`Instrumentation ${newInstrumentation.name} is already added`);
          return;
        }
        newInstrumentation.unpatchedConsole = unpatchedConsole2;
        newInstrumentation.internalLogger = internalLogger2;
        newInstrumentation.config = config;
        newInstrumentation.metas = metas;
        newInstrumentation.transports = transports;
        newInstrumentation.api = api;
        instrumentations.push(newInstrumentation);
        newInstrumentation.initialize();
      });
    };
    const remove = (...instrumentationsToRemove) => {
      internalLogger2.debug("Removing instrumentations");
      instrumentationsToRemove.forEach((instrumentationToRemove) => {
        var _a, _b;
        internalLogger2.debug(`Removing "${instrumentationToRemove.name}" instrumentation`);
        const existingInstrumentationIndex = instrumentations.reduce((acc, existingInstrumentation, existingTransportIndex) => {
          if (acc === null && existingInstrumentation.name === instrumentationToRemove.name) {
            return existingTransportIndex;
          }
          return null;
        }, null);
        if (existingInstrumentationIndex === null) {
          internalLogger2.warn(`Instrumentation "${instrumentationToRemove.name}" is not added`);
          return;
        }
        (_b = (_a = instrumentations[existingInstrumentationIndex]).destroy) === null || _b === undefined || _b.call(_a);
        instrumentations.splice(existingInstrumentationIndex, 1);
      });
    };
    return {
      add,
      get instrumentations() {
        return [...instrumentations];
      },
      remove
    };
  }
  // node_modules/@grafana/faro-core/dist/esm/instrumentations/registerInitial.js
  function registerInitialInstrumentations(faro) {
    faro.instrumentations.add(...faro.config.instrumentations);
  }
  // node_modules/@grafana/faro-core/dist/esm/metas/initialize.js
  function initializeMetas(_unpatchedConsole, internalLogger2, _config) {
    let items = [];
    let listeners = [];
    const getValue = () => items.reduce((acc, item) => Object.assign(acc, isFunction(item) ? item() : item), {});
    const notifyListeners = () => {
      if (listeners.length) {
        const value = getValue();
        listeners.forEach((listener) => listener(value));
      }
    };
    const add = (...newItems) => {
      internalLogger2.debug(`Adding metas
`, newItems);
      items.push(...newItems);
      notifyListeners();
    };
    const remove = (...itemsToRemove) => {
      internalLogger2.debug(`Removing metas
`, itemsToRemove);
      items = items.filter((currentItem) => !itemsToRemove.includes(currentItem));
      notifyListeners();
    };
    const addListener = (listener) => {
      internalLogger2.debug(`Adding metas listener
`, listener);
      listeners.push(listener);
    };
    const removeListener = (listener) => {
      internalLogger2.debug(`Removing metas listener
`, listener);
      listeners = listeners.filter((currentListener) => currentListener !== listener);
    };
    return {
      add,
      remove,
      addListener,
      removeListener,
      get value() {
        return getValue();
      }
    };
  }
  // node_modules/@grafana/faro-core/dist/esm/version.js
  var VERSION = "2.8.2";

  // node_modules/@grafana/faro-core/dist/esm/metas/registerInitial.js
  function registerInitialMetas(faro) {
    var _a, _b;
    const appName = faro.config.app.name;
    const gitHash = appName ? getGitHash(appName) : undefined;
    const initial = {
      sdk: {
        version: VERSION,
        name: "faro"
      },
      app: Object.assign({ bundleId: appName && getBundleId(appName) }, gitHash !== undefined ? { gitHash } : {})
    };
    const session = (_a = faro.config.sessionTracking) === null || _a === undefined ? undefined : _a.session;
    if (session) {
      faro.api.setSession(session);
    }
    if (faro.config.app) {
      initial.app = Object.assign(Object.assign({}, faro.config.app), initial.app);
    }
    if (faro.config.user) {
      initial.user = faro.config.user;
    }
    if (faro.config.view) {
      initial.view = faro.config.view;
    }
    faro.metas.add(initial, ...(_b = faro.config.metas) !== null && _b !== undefined ? _b : []);
  }
  // node_modules/@grafana/faro-core/dist/esm/sdk/const.js
  var internalGlobalObjectKey = "_faroInternal";

  // node_modules/@grafana/faro-core/dist/esm/sdk/faroGlobalObject.js
  function setFaroOnGlobalObject(faro) {
    if (!faro.config.preventGlobalExposure) {
      faro.internalLogger.debug(`Registering public faro reference in the global scope using "${faro.config.globalObjectKey}" key`);
      if (faro.config.globalObjectKey in globalObject) {
        faro.internalLogger.warn(`Skipping global registration due to key "${faro.config.globalObjectKey}" being used already. Please set "globalObjectKey" to something else or set "preventGlobalExposure" to "true"`);
        return;
      }
      Object.defineProperty(globalObject, faro.config.globalObjectKey, {
        configurable: false,
        writable: false,
        value: faro
      });
    } else {
      faro.internalLogger.debug("Skipping registering public Faro instance in the global scope");
    }
  }

  // node_modules/@grafana/faro-core/dist/esm/sdk/internalFaroGlobalObject.js
  function setInternalFaroOnGlobalObject(faro) {
    if (!faro.config.isolate) {
      faro.internalLogger.debug("Registering internal Faro instance on global object");
      Object.defineProperty(globalObject, internalGlobalObjectKey, {
        configurable: false,
        enumerable: false,
        writable: false,
        value: faro
      });
    } else {
      faro.internalLogger.debug("Skipping registering internal Faro instance on global object");
    }
  }
  function isInternalFaroOnGlobalObject() {
    return internalGlobalObjectKey in globalObject;
  }

  // node_modules/@grafana/faro-core/dist/esm/sdk/registerFaro.js
  var faro = { api: getNoopAPI() };
  function registerFaro(unpatchedConsole2, internalLogger2, config, metas, transports, api, instrumentations) {
    internalLogger2.debug("Initializing Faro");
    faro = {
      api,
      config,
      instrumentations,
      internalLogger: internalLogger2,
      metas,
      pause: transports.pause,
      transports,
      unpatchedConsole: unpatchedConsole2,
      unpause: transports.unpause
    };
    setInternalFaroOnGlobalObject(faro);
    setFaroOnGlobalObject(faro);
    return faro;
  }
  // node_modules/@grafana/faro-core/dist/esm/initialize.js
  function initializeFaro(config) {
    const unpatchedConsole2 = initializeUnpatchedConsole(config);
    const internalLogger2 = initializeInternalLogger(unpatchedConsole2, config);
    if (isInternalFaroOnGlobalObject() && !config.isolate) {
      internalLogger2.error('Faro is already registered. Either add instrumentations, transports etc. to the global faro instance or use the "isolate" property');
      return;
    }
    internalLogger2.debug("Initializing");
    const metas = initializeMetas(unpatchedConsole2, internalLogger2, config);
    const transports = initializeTransports(unpatchedConsole2, internalLogger2, config, metas);
    const api = initializeAPI(unpatchedConsole2, internalLogger2, config, metas, transports);
    const instrumentations = initializeInstrumentations(unpatchedConsole2, internalLogger2, config, metas, transports, api);
    const faro2 = registerFaro(unpatchedConsole2, internalLogger2, config, metas, transports, api, instrumentations);
    registerInitialMetas(faro2);
    registerInitialTransports(faro2);
    registerInitialInstrumentations(faro2);
    return faro2;
  }
  // node_modules/@grafana/faro-core/dist/esm/config/const.js
  var defaultGlobalObjectKey = "faro";
  var defaultBatchingConfig = {
    enabled: true,
    sendTimeout: 250,
    itemLimit: 50
  };
  // node_modules/@grafana/faro-core/dist/esm/semantic.js
  var EVENT_VIEW_CHANGED = "view_changed";
  var EVENT_SESSION_START = "session_start";
  var EVENT_SESSION_RESUME = "session_resume";
  var EVENT_SESSION_EXTEND = "session_extend";
  var EVENT_OVERRIDES_SERVICE_NAME = "service_name_override";
  // node_modules/@grafana/faro-core/dist/esm/consts.js
  var unknownString = "unknown";
  // node_modules/@grafana/faro-web-sdk/dist/esm/metas/shared/uaParser.js
  var import_ua_parser_js = __toESM(require_ua_parser(), 1);
  var cachedUA;
  var cachedResult;
  function getUAResult() {
    const currentUA = typeof navigator !== "undefined" ? navigator.userAgent : "";
    if (cachedUA !== currentUA || !cachedResult) {
      cachedResult = new import_ua_parser_js.UAParser(currentUA).getResult();
      cachedUA = currentUA;
    }
    return cachedResult;
  }
  // node_modules/@grafana/faro-web-sdk/dist/esm/metas/browser/meta.js
  var browserMeta = () => {
    const { browser, os, ua: userAgent } = getUAResult();
    const { name, version } = browser;
    const { name: osName, version: osVersion } = os;
    const language = navigator.language;
    const mobile = userAgent.includes("Mobi");
    const brands = getBrands();
    return {
      browser: {
        name: name !== null && name !== undefined ? name : unknownString,
        version: version !== null && version !== undefined ? version : unknownString,
        os: `${osName !== null && osName !== undefined ? osName : unknownString} ${osVersion !== null && osVersion !== undefined ? osVersion : unknownString}`,
        userAgent: userAgent !== null && userAgent !== undefined ? userAgent : unknownString,
        language: language !== null && language !== undefined ? language : unknownString,
        mobile,
        brands: brands !== null && brands !== undefined ? brands : unknownString,
        viewportWidth: `${window.innerWidth}`,
        viewportHeight: `${window.innerHeight}`
      }
    };
    function getBrands() {
      if (!name || !version) {
        return;
      }
      if ("userAgentData" in navigator && navigator.userAgentData) {
        return navigator.userAgentData.brands;
      }
      return;
    }
  };
  // node_modules/@grafana/faro-web-sdk/dist/esm/metas/os/meta.js
  var osMeta = () => {
    const { name, version } = getUAResult().os;
    if (!name && !version) {
      return {};
    }
    const os = {};
    if (name) {
      os.name = name;
    }
    if (version) {
      os.version = version;
    }
    return { os };
  };
  // node_modules/@grafana/faro-web-sdk/dist/esm/metas/session/createSession.js
  function createSession(attributes) {
    var _a, _b, _c, _d;
    return {
      id: (_d = (_c = (_b = (_a = faro.config) === null || _a === undefined ? undefined : _a.sessionTracking) === null || _b === undefined ? undefined : _b.generateSessionId) === null || _c === undefined ? undefined : _c.call(_b)) !== null && _d !== undefined ? _d : genShortID(),
      attributes
    };
  }
  // node_modules/@grafana/faro-web-sdk/dist/esm/metas/sdk/meta.js
  var sdkMeta = () => ({
    sdk: {
      name: "faro-web",
      version: VERSION
    }
  });
  // node_modules/@grafana/faro-web-sdk/dist/esm/utils/webStorage.js
  var webStorageType = {
    session: "sessionStorage",
    local: "localStorage"
  };
  function isWebStorageAvailable(type) {
    var _a;
    try {
      let storage;
      storage = window[type];
      const testItem = "__faro_storage_test__";
      storage.setItem(testItem, testItem);
      storage.removeItem(testItem);
      return true;
    } catch (error) {
      (_a = faro.internalLogger) === null || _a === undefined || _a.info(`Web storage of type ${type} is not available. Reason: ${error}`);
      return false;
    }
  }
  function getItem(key, webStorageMechanism) {
    if (isWebStorageTypeAvailable(webStorageMechanism)) {
      return window[webStorageMechanism].getItem(key);
    }
    return null;
  }
  function setItem(key, value, webStorageMechanism) {
    if (isWebStorageTypeAvailable(webStorageMechanism)) {
      try {
        window[webStorageMechanism].setItem(key, value);
      } catch (_error) {}
    }
  }
  function removeItem(key, webStorageMechanism) {
    if (isWebStorageTypeAvailable(webStorageMechanism)) {
      window[webStorageMechanism].removeItem(key);
    }
  }
  var isLocalStorageAvailable = isWebStorageAvailable(webStorageType.local);
  var isSessionStorageAvailable = isWebStorageAvailable(webStorageType.session);
  function isWebStorageTypeAvailable(webStorageMechanism) {
    if (webStorageMechanism === webStorageType.local) {
      return isLocalStorageAvailable;
    }
    if (webStorageMechanism === webStorageType.session) {
      return isSessionStorageAvailable;
    }
    return false;
  }
  // node_modules/@grafana/faro-web-sdk/dist/esm/utils/throttle.js
  function throttle(callback, delay) {
    let pause = false;
    let lastPending;
    const timeoutBehavior = () => {
      if (lastPending == null) {
        pause = false;
        return;
      }
      callback(...lastPending);
      lastPending = null;
      setTimeout(timeoutBehavior, delay);
    };
    return (...args) => {
      if (pause) {
        lastPending = args;
        return;
      }
      callback(...args);
      pause = true;
      setTimeout(timeoutBehavior, delay);
    };
  }
  // node_modules/@grafana/faro-web-sdk/dist/esm/utils/url.js
  function getIgnoreUrls() {
    return faro.transports.transports.flatMap((transport) => transport.getIgnoreUrls());
  }
  function isUrlIgnored(url = "") {
    return getIgnoreUrls().some((ignoredUrl) => url && url.match(ignoredUrl) != null);
  }
  function getUrlFromResource(resource) {
    if (isString(resource)) {
      return resource;
    }
    if (resource instanceof URL) {
      return resource.href;
    }
    if (!isEmpty(resource) && isFunction(resource === null || resource === undefined ? undefined : resource.toString)) {
      return resource.toString();
    }
    return;
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/session/sessionManager/sessionConstants.js
  var STORAGE_KEY = "com.grafana.faro.session";
  var SESSION_EXPIRATION_TIME = 4 * 60 * 60 * 1000;
  var SESSION_INACTIVITY_TIME = 15 * 60 * 1000;
  var STORAGE_UPDATE_DELAY = 1 * 1000;
  var MAX_SESSION_PERSISTENCE_TIME = SESSION_INACTIVITY_TIME;
  var defaultSessionTrackingConfig = {
    enabled: true,
    persistent: false,
    maxSessionPersistenceTime: MAX_SESSION_PERSISTENCE_TIME
  };

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/session/sessionManager/sampling.js
  function isSampled() {
    var _a, _b, _c;
    const sendAllSignals = 1;
    const sessionTracking = faro.config.sessionTracking;
    const rawSamplingRate = (_c = (_b = (_a = sessionTracking === null || sessionTracking === undefined ? undefined : sessionTracking.sampler) === null || _a === undefined ? undefined : _a.call(sessionTracking, { metas: faro.metas.value })) !== null && _b !== undefined ? _b : sessionTracking === null || sessionTracking === undefined ? undefined : sessionTracking.samplingRate) !== null && _c !== undefined ? _c : sendAllSignals;
    const samplingRate = typeof rawSamplingRate === "number" ? clampSamplingRate(rawSamplingRate) : 0;
    return Math.random() < samplingRate;
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/session/sessionManager/sessionManagerUtils.js
  function createUserSessionObject({ sessionId, started, lastActivity, isSampled: isSampled2 = true } = {}) {
    var _a, _b;
    const now = dateNow();
    const generateSessionId = (_b = (_a = faro.config) === null || _a === undefined ? undefined : _a.sessionTracking) === null || _b === undefined ? undefined : _b.generateSessionId;
    if (sessionId == null) {
      sessionId = typeof generateSessionId === "function" ? generateSessionId() : genShortID();
    }
    return {
      sessionId,
      lastActivity: lastActivity !== null && lastActivity !== undefined ? lastActivity : now,
      started: started !== null && started !== undefined ? started : now,
      isSampled: isSampled2
    };
  }
  function isUserSessionValid(session) {
    if (session == null) {
      return false;
    }
    const now = dateNow();
    const lifetimeValid = now - session.started < SESSION_EXPIRATION_TIME;
    if (!lifetimeValid) {
      return false;
    }
    const inactivityPeriodValid = now - session.lastActivity < SESSION_INACTIVITY_TIME;
    return inactivityPeriodValid;
  }
  function getUserSessionUpdater({ fetchUserSession, storeUserSession, adoptSession }) {
    return function updateSession({ forceSessionExtend } = { forceSessionExtend: false }) {
      var _a, _b, _c, _d;
      if (!fetchUserSession || !storeUserSession) {
        return;
      }
      const sessionTrackingConfig = faro.config.sessionTracking;
      const isPersistentSessions = sessionTrackingConfig === null || sessionTrackingConfig === undefined ? undefined : sessionTrackingConfig.persistent;
      if (isPersistentSessions && !isLocalStorageAvailable || !isPersistentSessions && !isSessionStorageAvailable) {
        return;
      }
      const sessionFromStorage = fetchUserSession();
      if (forceSessionExtend === false && isUserSessionValid(sessionFromStorage)) {
        storeUserSession(Object.assign(Object.assign({}, sessionFromStorage), { lastActivity: dateNow() }));
        const inMemorySessionId = (_a = faro.metas.value.session) === null || _a === undefined ? undefined : _a.id;
        if (adoptSession != null && sessionFromStorage.sessionMeta != null && sessionFromStorage.sessionId !== inMemorySessionId) {
          adoptSession(sessionFromStorage.sessionMeta);
        }
      } else {
        let newSession = addSessionMetadataToNextSession(createUserSessionObject({ isSampled: isSampled() }), sessionFromStorage);
        storeUserSession(newSession);
        (_b = faro.api) === null || _b === undefined || _b.setSession(newSession.sessionMeta);
        (_c = sessionTrackingConfig === null || sessionTrackingConfig === undefined ? undefined : sessionTrackingConfig.onSessionChange) === null || _c === undefined || _c.call(sessionTrackingConfig, (_d = sessionFromStorage === null || sessionFromStorage === undefined ? undefined : sessionFromStorage.sessionMeta) !== null && _d !== undefined ? _d : null, newSession.sessionMeta);
      }
    };
  }
  function addSessionMetadataToNextSession(newSession, previousSession) {
    var _a, _b, _c, _d, _e, _f, _g;
    const sessionWithMeta = Object.assign(Object.assign({}, newSession), { sessionMeta: {
      id: newSession.sessionId,
      attributes: removeUndefinedValues(Object.assign(Object.assign(Object.assign({}, (_b = (_a = faro.config.sessionTracking) === null || _a === undefined ? undefined : _a.session) === null || _b === undefined ? undefined : _b.attributes), (_d = (_c = faro.metas.value.session) === null || _c === undefined ? undefined : _c.attributes) !== null && _d !== undefined ? _d : {}), { isSampled: newSession.isSampled.toString() }))
    } });
    const overrides = (_f = (_e = faro.metas.value.session) === null || _e === undefined ? undefined : _e.overrides) !== null && _f !== undefined ? _f : (_g = previousSession === null || previousSession === undefined ? undefined : previousSession.sessionMeta) === null || _g === undefined ? undefined : _g.overrides;
    if (!isEmpty(overrides)) {
      sessionWithMeta.sessionMeta.overrides = overrides;
    }
    const previousSessionId = previousSession === null || previousSession === undefined ? undefined : previousSession.sessionId;
    if (previousSessionId != null) {
      sessionWithMeta.sessionMeta.attributes["previousSession"] = previousSessionId;
    }
    return sessionWithMeta;
  }
  function getSessionMetaUpdateHandler({ fetchUserSession, storeUserSession }) {
    let isSyncing = false;
    return function syncSessionIfChangedExternally(meta) {
      if (isSyncing) {
        return;
      }
      const session = meta.session;
      const sessionFromSessionStorage = fetchUserSession();
      let sessionId = session === null || session === undefined ? undefined : session.id;
      const sessionAttributes = session === null || session === undefined ? undefined : session.attributes;
      const sessionOverrides = session === null || session === undefined ? undefined : session.overrides;
      const storedSessionMeta = sessionFromSessionStorage === null || sessionFromSessionStorage === undefined ? undefined : sessionFromSessionStorage.sessionMeta;
      const storedSessionMetaOverrides = storedSessionMeta === null || storedSessionMeta === undefined ? undefined : storedSessionMeta.overrides;
      const hasSessionOverridesChanged = !!sessionOverrides && !deepEqual(sessionOverrides, storedSessionMetaOverrides);
      const hasAttributesChanged = !!sessionAttributes && !deepEqual(sessionAttributes, storedSessionMeta === null || storedSessionMeta === undefined ? undefined : storedSessionMeta.attributes);
      const hasSessionIdChanged = !!session && sessionId !== (sessionFromSessionStorage === null || sessionFromSessionStorage === undefined ? undefined : sessionFromSessionStorage.sessionId);
      if (hasSessionIdChanged || hasAttributesChanged || hasSessionOverridesChanged) {
        const userSession = addSessionMetadataToNextSession(createUserSessionObject({ sessionId, isSampled: isSampled() }), sessionFromSessionStorage);
        storeUserSession(userSession);
        sendOverrideEvent(hasSessionOverridesChanged, sessionOverrides, storedSessionMetaOverrides);
        isSyncing = true;
        try {
          faro.api.setSession(userSession.sessionMeta);
        } finally {
          isSyncing = false;
        }
      }
    };
  }
  function removeUndefinedValues(obj) {
    const result = {};
    for (const key of Object.keys(obj)) {
      const value = obj[key];
      if (value !== undefined) {
        result[key] = value;
      }
    }
    return result;
  }
  function sendOverrideEvent(hasSessionOverridesChanged, sessionOverrides = {}, storedSessionOverrides = {}) {
    var _a, _b, _c;
    if (!hasSessionOverridesChanged) {
      return;
    }
    const serviceName = sessionOverrides.serviceName;
    const previousServiceName = (_c = (_a = storedSessionOverrides.serviceName) !== null && _a !== undefined ? _a : (_b = faro.metas.value.app) === null || _b === undefined ? undefined : _b.name) !== null && _c !== undefined ? _c : "";
    if (serviceName && serviceName !== previousServiceName) {
      faro.api.pushEvent(EVENT_OVERRIDES_SERVICE_NAME, {
        serviceName,
        previousServiceName
      });
    }
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/session/sessionManager/PersistentSessionsManager.js
  class PersistentSessionsManager {
    constructor() {
      this.adopting = false;
      this.isAdopting = () => this.adopting;
      this.adoptSession = (sessionMeta) => {
        var _a;
        this.adopting = true;
        try {
          (_a = faro.api) === null || _a === undefined || _a.setSession(sessionMeta);
        } finally {
          this.adopting = false;
        }
      };
      this.updateSession = throttle(() => this.updateUserSession(), STORAGE_UPDATE_DELAY);
      this.updateUserSession = getUserSessionUpdater({
        fetchUserSession: PersistentSessionsManager.fetchUserSession,
        storeUserSession: PersistentSessionsManager.storeUserSession,
        adoptSession: this.adoptSession
      });
      this.init();
    }
    static removeUserSession() {
      removeItem(STORAGE_KEY, PersistentSessionsManager.storageTypeLocal);
    }
    static storeUserSession(session) {
      setItem(STORAGE_KEY, stringifyExternalJson(session), PersistentSessionsManager.storageTypeLocal);
    }
    static fetchUserSession() {
      const storedSession = getItem(STORAGE_KEY, PersistentSessionsManager.storageTypeLocal);
      if (storedSession) {
        return JSON.parse(storedSession);
      }
      return null;
    }
    init() {
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
          this.updateSession();
        }
      });
      faro.metas.addListener(getSessionMetaUpdateHandler({
        fetchUserSession: PersistentSessionsManager.fetchUserSession,
        storeUserSession: PersistentSessionsManager.storeUserSession
      }));
    }
  }
  PersistentSessionsManager.storageTypeLocal = webStorageType.local;

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/session/sessionManager/VolatileSessionManager.js
  class VolatileSessionsManager {
    constructor() {
      this.isAdopting = () => false;
      this.updateSession = throttle(() => this.updateUserSession(), STORAGE_UPDATE_DELAY);
      this.updateUserSession = getUserSessionUpdater({
        fetchUserSession: VolatileSessionsManager.fetchUserSession,
        storeUserSession: VolatileSessionsManager.storeUserSession
      });
      this.init();
    }
    static removeUserSession() {
      removeItem(STORAGE_KEY, VolatileSessionsManager.storageTypeSession);
    }
    static storeUserSession(session) {
      setItem(STORAGE_KEY, stringifyExternalJson(session), VolatileSessionsManager.storageTypeSession);
    }
    static fetchUserSession() {
      const storedSession = getItem(STORAGE_KEY, VolatileSessionsManager.storageTypeSession);
      if (storedSession) {
        return JSON.parse(storedSession);
      }
      return null;
    }
    init() {
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
          this.updateSession();
        }
      });
      faro.metas.addListener(getSessionMetaUpdateHandler({
        fetchUserSession: VolatileSessionsManager.fetchUserSession,
        storeUserSession: VolatileSessionsManager.storeUserSession
      }));
    }
  }
  VolatileSessionsManager.storageTypeSession = webStorageType.session;
  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/session/sessionManager/getSessionManagerByConfig.js
  function getSessionManagerByConfig(sessionTrackingConfig) {
    return (sessionTrackingConfig === null || sessionTrackingConfig === undefined ? undefined : sessionTrackingConfig.persistent) ? PersistentSessionsManager : VolatileSessionsManager;
  }
  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/session/instrumentation.js
  class SessionInstrumentation extends BaseInstrumentation {
    constructor() {
      super(...arguments);
      this.name = "@grafana/faro-web-sdk:instrumentation-session";
      this.version = VERSION;
      this.isAdoptingSession = () => false;
    }
    sendSessionStartEvent(meta) {
      var _a, _b;
      const session = meta.session;
      if (session && session.id !== ((_a = this.notifiedSession) === null || _a === undefined ? undefined : _a.id)) {
        if (this.isAdoptingSession()) {
          this.notifiedSession = session;
          return;
        }
        if (this.notifiedSession && this.notifiedSession.id === ((_b = session.attributes) === null || _b === undefined ? undefined : _b["previousSession"])) {
          this.api.pushEvent(EVENT_SESSION_EXTEND, {}, undefined, { skipDedupe: true });
          this.notifiedSession = session;
          return;
        }
        this.notifiedSession = session;
        this.api.pushEvent(EVENT_SESSION_START, {}, undefined, { skipDedupe: true });
      }
    }
    createInitialSession(SessionManager, sessionsConfig) {
      var _a, _b, _c, _d, _e, _f;
      let storedUserSession = SessionManager.fetchUserSession();
      if (sessionsConfig.persistent && sessionsConfig.maxSessionPersistenceTime && storedUserSession) {
        const now = dateNow();
        const shouldClearPersistentSession = storedUserSession.lastActivity < now - sessionsConfig.maxSessionPersistenceTime;
        if (shouldClearPersistentSession) {
          PersistentSessionsManager.removeUserSession();
          storedUserSession = null;
        }
      }
      let lifecycleType;
      let initialSession;
      if (isUserSessionValid(storedUserSession)) {
        const sessionId = storedUserSession === null || storedUserSession === undefined ? undefined : storedUserSession.sessionId;
        initialSession = createUserSessionObject({
          sessionId,
          isSampled: storedUserSession.isSampled || false,
          started: storedUserSession === null || storedUserSession === undefined ? undefined : storedUserSession.started
        });
        const storedUserSessionMeta = storedUserSession === null || storedUserSession === undefined ? undefined : storedUserSession.sessionMeta;
        const overrides = Object.assign(Object.assign({}, (_a = sessionsConfig.session) === null || _a === undefined ? undefined : _a.overrides), storedUserSessionMeta === null || storedUserSessionMeta === undefined ? undefined : storedUserSessionMeta.overrides);
        initialSession.sessionMeta = Object.assign(Object.assign({}, sessionsConfig.session), { id: sessionId, attributes: Object.assign(Object.assign(Object.assign({}, (_b = sessionsConfig.session) === null || _b === undefined ? undefined : _b.attributes), storedUserSessionMeta === null || storedUserSessionMeta === undefined ? undefined : storedUserSessionMeta.attributes), {
          isSampled: initialSession.isSampled.toString()
        }), overrides });
        lifecycleType = EVENT_SESSION_RESUME;
      } else {
        const sessionId = (_d = (_c = sessionsConfig.session) === null || _c === undefined ? undefined : _c.id) !== null && _d !== undefined ? _d : createSession().id;
        initialSession = createUserSessionObject({
          sessionId,
          isSampled: isSampled()
        });
        const overrides = (_e = sessionsConfig.session) === null || _e === undefined ? undefined : _e.overrides;
        initialSession.sessionMeta = Object.assign({ id: sessionId, attributes: Object.assign({ isSampled: initialSession.isSampled.toString() }, (_f = sessionsConfig.session) === null || _f === undefined ? undefined : _f.attributes) }, overrides ? { overrides } : {});
        lifecycleType = EVENT_SESSION_START;
      }
      return { initialSession, lifecycleType };
    }
    registerBeforeSendHook(SessionManager) {
      var _a;
      const sessionManager = new SessionManager;
      this.isAdoptingSession = sessionManager.isAdopting;
      const { updateSession } = sessionManager;
      let lastRotation;
      (_a = this.transports) === null || _a === undefined || _a.addBeforeSendHooks((item) => {
        var _a2, _b, _c, _d;
        const previousSessionId = (_a2 = this.metas.value.session) === null || _a2 === undefined ? undefined : _a2.id;
        updateSession();
        const currentSession = this.metas.value.session;
        if (currentSession != null && previousSessionId != null && currentSession.id !== previousSessionId) {
          lastRotation = { from: previousSessionId, to: currentSession };
        }
        const reStamp = lastRotation != null && ((_b = item.meta.session) === null || _b === undefined ? undefined : _b.id) === lastRotation.from;
        const session = reStamp ? lastRotation.to : item.meta.session;
        const attributes = session === null || session === undefined ? undefined : session.attributes;
        if (attributes && (attributes === null || attributes === undefined ? undefined : attributes["isSampled"]) === "true") {
          let newItem = JSON.parse(JSON.stringify(item));
          if (reStamp) {
            newItem.meta.session = JSON.parse(JSON.stringify(lastRotation.to));
          }
          const newAttributes = (_c = newItem.meta.session) === null || _c === undefined ? undefined : _c.attributes;
          newAttributes === null || newAttributes === undefined || delete newAttributes["isSampled"];
          if (Object.keys(newAttributes !== null && newAttributes !== undefined ? newAttributes : {}).length === 0) {
            (_d = newItem.meta.session) === null || _d === undefined || delete _d.attributes;
          }
          return newItem;
        }
        return null;
      });
    }
    initialize() {
      this.logDebug("init session instrumentation");
      const sessionTrackingConfig = this.config.sessionTracking;
      if (sessionTrackingConfig === null || sessionTrackingConfig === undefined ? undefined : sessionTrackingConfig.enabled) {
        const SessionManager = getSessionManagerByConfig(sessionTrackingConfig);
        this.registerBeforeSendHook(SessionManager);
        const { initialSession, lifecycleType } = this.createInitialSession(SessionManager, sessionTrackingConfig);
        SessionManager.storeUserSession(initialSession);
        const initialSessionMeta = initialSession.sessionMeta;
        this.notifiedSession = initialSessionMeta;
        this.api.setSession(initialSessionMeta);
        if (lifecycleType === EVENT_SESSION_START) {
          this.api.pushEvent(EVENT_SESSION_START, {}, undefined, { skipDedupe: true });
        }
        if (lifecycleType === EVENT_SESSION_RESUME) {
          this.api.pushEvent(EVENT_SESSION_RESUME, {}, undefined, { skipDedupe: true });
        }
      }
      this.metas.addListener(this.sendSessionStartEvent.bind(this));
    }
  }
  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/_internal/monitors/const.js
  var MESSAGE_TYPE_RESOURCE_ENTRY = "resource-entry";
  var MESSAGE_TYPE_HTTP_REQUEST_START = "http-request-start";
  var MESSAGE_TYPE_HTTP_REQUEST_END = "http-request-end";
  var MESSAGE_TYPE_DOM_MUTATION = "dom-mutation";
  var MESSAGE_TYPE_CONSOLE = "console";

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/_internal/monitors/consoleMonitor.js
  var consoleObservable;
  var isInstrumented = false;
  function monitorConsole(unpatchedConsole2) {
    if (!consoleObservable) {
      consoleObservable = new Observable;
    }
    if (!isInstrumented) {
      const originalConsole = unpatchedConsole2 !== null && unpatchedConsole2 !== undefined ? unpatchedConsole2 : defaultUnpatchedConsole;
      allLogLevels.forEach((level) => {
        console[level] = (...args) => {
          var _a;
          consoleObservable.notify({
            type: MESSAGE_TYPE_CONSOLE,
            level,
            args
          });
          (_a = originalConsole[level]) === null || _a === undefined || _a.apply(console, args);
        };
      });
      isInstrumented = true;
    }
    return consoleObservable;
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/errors/const.js
  var primitiveUnhandledValue = "Non-Error promise rejection captured with value:";
  var primitiveUnhandledType = "UnhandledRejection";
  var domErrorType = "DOMError";
  var domExceptionType = "DOMException";
  var objectEventValue = "Non-Error exception captured with keys:";
  var unknownSymbolString = "?";
  var valueTypeRegex = /^(?:[Uu]ncaught (?:exception: )?)?(?:((?:Eval|Internal|Range|Reference|Syntax|Type|URI|)Error): )?(.*)$/i;

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/errors/getValueAndTypeFromMessage.js
  function getValueAndTypeFromMessage(message) {
    var _a, _b;
    const groups = message.match(valueTypeRegex);
    const type = (_a = groups === null || groups === undefined ? undefined : groups[1]) !== null && _a !== undefined ? _a : defaultExceptionType;
    const value = (_b = groups === null || groups === undefined ? undefined : groups[2]) !== null && _b !== undefined ? _b : message;
    return [value, type];
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/errors/stackFrames/const.js
  var newLineString = `
`;
  var evalString = "eval";
  var unknownSymbolString2 = "?";
  var atString = "@";
  var webkitLineRegex = /^\s*at (?:(?![a-z]+:\/\/)([^(]+?) ?\((?:address at )?)?((?:file|https?|blob|chrome-extension|address|native|eval|webpack|<anonymous>|[-a-z]+:|.*bundle|\/)?.*?)(?::(\d+))?(?::(\d+))?\)?\s*$/i;
  var webkitEvalRegex = /\((\S*)(?::(\d+))(?::(\d+))\)/;
  var webkitEvalString = "eval";
  var webkitAddressAtString = "address at ";
  var webkitAddressAtStringLength = webkitAddressAtString.length;
  var firefoxLineRegex = /^\s*(.*?)(?:\((.*?)\))?(?:^|@)?((?:file|https?|blob|chrome|webpack|resource|moz-extension|safari-extension|safari-web-extension|capacitor)?:\/.*?|\[native code]|[^@]*(?:bundle|\d+\.js)|\/[\w\-. /=]+)(?::(\d+))?(?::(\d+))?\s*$/i;
  var firefoxEvalRegex = /(\S+) line (\d+)(?: > eval line \d+)* > eval/i;
  var firefoxEvalString = " > eval";
  var safariExtensionString = "safari-extension";
  var safariWebExtensionString = "safari-web-extension";
  var reactMinifiedRegex = /Minified React error #\d+;/i;

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/errors/stackFrames/buildStackFrame.js
  function buildStackFrame(filename, func, lineno, colno) {
    const stackFrame = {
      filename: filename || document.location.href,
      function: func || unknownSymbolString2
    };
    if (lineno !== undefined) {
      stackFrame.lineno = lineno;
    }
    if (colno !== undefined) {
      stackFrame.colno = colno;
    }
    return stackFrame;
  }
  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/errors/stackFrames/getDataFromSafariExtensions.js
  function getDataFromSafariExtensions(func, filename) {
    const isSafariExtension = func === null || func === undefined ? undefined : func.includes(safariExtensionString);
    const isSafariWebExtension = !isSafariExtension && (func === null || func === undefined ? undefined : func.includes(safariWebExtensionString));
    if (!isSafariExtension && !isSafariWebExtension) {
      return [func, filename];
    }
    return [
      (func === null || func === undefined ? undefined : func.includes(atString)) ? func.split(atString)[0] : func,
      isSafariExtension ? `${safariExtensionString}:${filename}` : `${safariWebExtensionString}:${filename}`
    ];
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/errors/stackFrames/getStackFramesFromError.js
  var MAX_STACK_LINE_LENGTH = 1024;
  function getStackFramesFromError(error) {
    let lines = [];
    if (error.stacktrace) {
      lines = error.stacktrace.split(newLineString).filter((_line, idx) => idx % 2 === 0);
    } else if (error.stack) {
      lines = error.stack.split(newLineString);
    }
    const stackFrames = lines.reduce((acc, line, idx) => {
      if (line.length > MAX_STACK_LINE_LENGTH) {
        return acc;
      }
      let parts;
      let func;
      let filename;
      let lineno;
      let colno;
      if (parts = webkitLineRegex.exec(line)) {
        func = parts[1];
        filename = parts[2];
        lineno = parts[3];
        colno = parts[4];
        if (filename === null || filename === undefined ? undefined : filename.startsWith(webkitEvalString)) {
          const submatch = webkitEvalRegex.exec(filename);
          if (submatch) {
            filename = submatch[1];
            lineno = submatch[2];
            colno = submatch[3];
          }
        }
        filename = (filename === null || filename === undefined ? undefined : filename.startsWith(webkitAddressAtString)) ? filename.substring(webkitAddressAtStringLength) : filename;
        [func, filename] = getDataFromSafariExtensions(func, filename);
      } else if (parts = firefoxLineRegex.exec(line)) {
        func = parts[1];
        filename = parts[3];
        lineno = parts[4];
        colno = parts[5];
        if (!!filename && filename.includes(firefoxEvalString)) {
          const submatch = firefoxEvalRegex.exec(filename);
          if (submatch) {
            func = func || evalString;
            filename = submatch[1];
            lineno = submatch[2];
          }
        } else if (idx === 0 && !colno && isNumber(error.columnNumber)) {
          colno = String(error.columnNumber + 1);
        }
        [func, filename] = getDataFromSafariExtensions(func, filename);
      }
      if (filename || func) {
        acc.push(buildStackFrame(filename, func, lineno ? Number(lineno) : undefined, colno ? Number(colno) : undefined));
      }
      return acc;
    }, []);
    if (reactMinifiedRegex.test(error.message)) {
      return stackFrames.slice(1);
    }
    return stackFrames;
  }
  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/errors/stackFrames/parseStacktrace.js
  function parseStacktrace(error) {
    return {
      frames: getStackFramesFromError(error)
    };
  }
  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/errors/getErrorDetails.js
  function getErrorDetails(evt) {
    let value;
    let type;
    let stackFrames = [];
    let isDomErrorRes;
    let isEventRes;
    if (isErrorEvent(evt) && evt.error) {
      value = evt.error.message;
      type = evt.error.name;
      stackFrames = getStackFramesFromError(evt.error);
    } else if ((isDomErrorRes = isDomError(evt)) || isDomException(evt)) {
      const { name, message } = evt;
      type = name !== null && name !== undefined ? name : isDomErrorRes ? domErrorType : domExceptionType;
      value = message ? `${type}: ${message}` : type;
    } else if (isError(evt)) {
      type = evt.name;
      value = evt.message;
      stackFrames = getStackFramesFromError(evt);
    } else if (isObject(evt) || (isEventRes = isEvent(evt))) {
      type = isEventRes ? evt.constructor.name : undefined;
      value = `${objectEventValue} ${Object.keys(evt)}`;
    }
    return [value, type, stackFrames];
  }
  function getDetailsFromErrorArgs(args) {
    const [evt, source, lineno, colno, error] = args;
    let value;
    let type;
    let stackFrames = [];
    const eventIsString = isString(evt);
    const initialStackFrame = buildStackFrame(source, unknownSymbolString, lineno, colno);
    if (error || !eventIsString) {
      [value, type, stackFrames] = getErrorDetails(error !== null && error !== undefined ? error : evt);
      if (stackFrames.length === 0) {
        stackFrames = [initialStackFrame];
      }
    } else if (eventIsString) {
      [value, type] = getValueAndTypeFromMessage(evt);
      stackFrames = [initialStackFrame];
    }
    return { value, type, stackFrames };
  }
  function getDetailsFromConsoleErrorArgs(args, serializer) {
    if (isError(args[0])) {
      return getDetailsFromErrorArgs(args);
    } else {
      return { value: serializer(args) };
    }
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/console/instrumentation.js
  class ConsoleInstrumentation extends BaseInstrumentation {
    constructor() {
      super(...arguments);
      this.name = "@grafana/faro-web-sdk:instrumentation-console";
      this.version = VERSION;
      this.errorSerializer = defaultLogArgsSerializer;
    }
    initialize() {
      var _a, _b;
      const instrumentationOptions = this.config.consoleInstrumentation;
      const serializeErrors = (instrumentationOptions === null || instrumentationOptions === undefined ? undefined : instrumentationOptions.serializeErrors) || !!(instrumentationOptions === null || instrumentationOptions === undefined ? undefined : instrumentationOptions.errorSerializer);
      this.errorSerializer = serializeErrors ? (_a = instrumentationOptions === null || instrumentationOptions === undefined ? undefined : instrumentationOptions.errorSerializer) !== null && _a !== undefined ? _a : defaultErrorArgsSerializer : defaultLogArgsSerializer;
      const disabledLevels = (_b = instrumentationOptions === null || instrumentationOptions === undefined ? undefined : instrumentationOptions.disabledLevels) !== null && _b !== undefined ? _b : ConsoleInstrumentation.defaultDisabledLevels;
      const consoleMonitor = monitorConsole(this.unpatchedConsole);
      this.subscription = consoleMonitor.subscribe(({ level, args }) => {
        if (disabledLevels.includes(level)) {
          return;
        }
        try {
          if (level === LogLevel.ERROR && !(instrumentationOptions === null || instrumentationOptions === undefined ? undefined : instrumentationOptions.consoleErrorAsLog)) {
            const { value, type, stackFrames } = getDetailsFromConsoleErrorArgs(args, this.errorSerializer);
            if (value && !type && !stackFrames) {
              this.api.pushError(new Error(ConsoleInstrumentation.consoleErrorPrefix + value));
              return;
            }
            this.api.pushError(new Error(ConsoleInstrumentation.consoleErrorPrefix + value), { type, stackFrames });
          } else if (level === LogLevel.ERROR && (instrumentationOptions === null || instrumentationOptions === undefined ? undefined : instrumentationOptions.consoleErrorAsLog)) {
            const { value, type, stackFrames } = getDetailsFromConsoleErrorArgs(args, this.errorSerializer);
            this.api.pushLog(value ? [ConsoleInstrumentation.consoleErrorPrefix + value] : args, {
              level,
              context: {
                value: value !== null && value !== undefined ? value : "",
                type: type !== null && type !== undefined ? type : "",
                stackFrames: (stackFrames === null || stackFrames === undefined ? undefined : stackFrames.length) ? defaultErrorArgsSerializer(stackFrames) : ""
              }
            });
          } else {
            this.api.pushLog(args, { level });
          }
        } catch (err) {
          this.logError(err);
        }
      });
    }
    destroy() {
      var _a;
      (_a = this.subscription) === null || _a === undefined || _a.unsubscribe();
      this.subscription = undefined;
    }
  }
  ConsoleInstrumentation.defaultDisabledLevels = [LogLevel.DEBUG, LogLevel.TRACE, LogLevel.LOG];
  ConsoleInstrumentation.consoleErrorPrefix = "console.error: ";
  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/errors/registerOnerror.js
  function registerOnerror(api) {
    const oldOnerror = window.onerror;
    window.onerror = (...args) => {
      try {
        const { value, type, stackFrames } = getDetailsFromErrorArgs(args);
        const originalError = args[4];
        if (value) {
          const options = { type, stackFrames };
          if (originalError != null) {
            options.originalError = originalError;
          }
          api.pushError(new Error(value), options);
        }
      } finally {
        oldOnerror === null || oldOnerror === undefined || oldOnerror.apply(window, args);
      }
    };
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/errors/registerOnunhandledrejection.js
  var registeredHandlers = [];
  function registerOnunhandledrejection(api) {
    const handler = (evt) => {
      var _a, _b;
      let error = evt;
      if (error.reason) {
        error = evt.reason;
      } else if ((_a = evt.detail) === null || _a === undefined ? undefined : _a.reason) {
        error = (_b = evt.detail) === null || _b === undefined ? undefined : _b.reason;
      }
      let value;
      let type;
      let stackFrames = [];
      if (isPrimitive(error)) {
        value = `${primitiveUnhandledValue} ${String(error)}`;
        type = primitiveUnhandledType;
      } else {
        [value, type, stackFrames] = getErrorDetails(error);
      }
      if (value) {
        api.pushError(new Error(value), { type, stackFrames });
      }
    };
    window.addEventListener("unhandledrejection", handler);
    registeredHandlers.push(handler);
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/errors/instrumentation.js
  class ErrorsInstrumentation extends BaseInstrumentation {
    constructor() {
      super(...arguments);
      this.name = "@grafana/faro-web-sdk:instrumentation-errors";
      this.version = VERSION;
    }
    initialize() {
      this.logDebug("Initializing");
      registerOnerror(this.api);
      registerOnunhandledrejection(this.api);
    }
  }
  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/view/instrumentation.js
  class ViewInstrumentation extends BaseInstrumentation {
    constructor() {
      super(...arguments);
      this.name = "@grafana/faro-web-sdk:instrumentation-view";
      this.version = VERSION;
    }
    sendViewChangedEvent(meta) {
      var _a, _b, _c, _d;
      const view = meta.view;
      if (view && view.name !== ((_a = this.notifiedView) === null || _a === undefined ? undefined : _a.name)) {
        this.api.pushEvent(EVENT_VIEW_CHANGED, {
          fromView: (_c = (_b = this.notifiedView) === null || _b === undefined ? undefined : _b.name) !== null && _c !== undefined ? _c : unknownString,
          toView: (_d = view.name) !== null && _d !== undefined ? _d : unknownString
        }, undefined, { skipDedupe: true });
        this.notifiedView = view;
      }
    }
    initialize() {
      this.metas.addListener(this.sendViewChangedEvent.bind(this));
    }
  }
  // node_modules/web-vitals/dist/web-vitals.attribution.js
  class t {
    t;
    o = 0;
    i = [];
    u(t2) {
      if (t2.hadRecentInput)
        return;
      const e = this.i[0], n = this.i.at(-1);
      this.o && e && n && t2.startTime - n.startTime < 1000 && t2.startTime - e.startTime < 5000 ? (this.o += t2.value, this.i.push(t2)) : (this.o = t2.value, this.i = [t2]), this.t?.(t2);
    }
  }
  var e = () => {
    const t2 = performance.getEntriesByType("navigation")[0];
    if (t2 && t2.responseStart > 0 && t2.responseStart < performance.now())
      return t2;
  };
  var n = (t2) => {
    if (document.readyState === "loading")
      return "loading";
    const n2 = e();
    if (n2) {
      if (t2 < n2.domInteractive)
        return "loading";
      if (n2.domContentLoadedEventStart === 0 || t2 < n2.domContentLoadedEventStart)
        return "dom-interactive";
      if (n2.domComplete === 0 || t2 < n2.domComplete)
        return "dom-content-loaded";
    }
    return "complete";
  };
  var o = (t2) => {
    const e2 = t2.nodeName;
    return t2.nodeType === 1 ? e2.toLowerCase() : e2.toUpperCase().replace(/^#/, "");
  };
  var i = (t2) => {
    let e2 = "";
    try {
      for (;t2?.nodeType !== 9; ) {
        const n2 = t2, i2 = n2.id ? "#" + n2.id : [o(n2), ...Array.from(n2.classList).sort()].join(".");
        if (e2.length + i2.length > 99)
          return e2 || i2;
        if (e2 = e2 ? i2 + ">" + e2 : i2, n2.id)
          break;
        t2 = n2.parentNode;
      }
    } catch {}
    return e2;
  };
  var r = new WeakMap;
  function s(t2, e2) {
    let n2 = r.get(e2);
    return n2 || (n2 = new WeakMap, r.set(e2, n2)), n2.get(t2) || n2.set(t2, new e2), n2.get(t2);
  }
  var a = -1;
  var c = () => a;
  var u = (t2) => {
    addEventListener("pageshow", (e2) => {
      e2.persisted && (a = e2.timeStamp, t2(e2));
    }, true);
  };
  var f = (t2, e2, n2, o2) => {
    let i2, r2;
    return (s2) => {
      e2.value >= 0 && (s2 || o2) && (r2 = e2.value - (i2 ?? 0), (r2 || i2 === undefined) && (i2 = e2.value, e2.delta = r2, e2.rating = ((t3, e3) => t3 > e3[1] ? "poor" : t3 > e3[0] ? "needs-improvement" : "good")(e2.value, n2), t2(e2)));
    };
  };
  var l = (t2) => {
    requestAnimationFrame(() => requestAnimationFrame(t2));
  };
  var d = () => e()?.activationStart ?? 0;
  var h = (t2, n2 = -1) => {
    const o2 = e();
    let i2 = "navigate";
    c() >= 0 ? i2 = "back-forward-cache" : o2 && (document.prerendering || d() > 0 ? i2 = "prerender" : document.wasDiscarded ? i2 = "restore" : o2.type && (i2 = o2.type.replace(/_/g, "-")));
    return { name: t2, value: n2, rating: "good", delta: 0, entries: [], id: `v5-${Date.now()}-${Math.floor(8999999999999 * Math.random()) + 1000000000000}`, navigationType: i2 };
  };
  var m = (t2, e2, n2 = {}) => {
    try {
      if (PerformanceObserver.supportedEntryTypes.includes(t2)) {
        const o2 = new PerformanceObserver((t3) => {
          queueMicrotask(() => {
            e2(t3.getEntries());
          });
        });
        return o2.observe({ type: t2, buffered: true, ...n2 }), o2;
      }
    } catch {}
  };
  var g = (t2) => {
    let e2 = false;
    return () => {
      e2 || (t2(), e2 = true);
    };
  };
  var p = -1;
  var y = new Set;
  var v = () => document.visibilityState !== "hidden" || document.prerendering ? 1 / 0 : 0;
  var b = (t2) => {
    if (document.visibilityState === "hidden") {
      if (t2.type === "visibilitychange")
        for (const t3 of y)
          t3();
      isFinite(p) || (p = t2.type === "visibilitychange" ? t2.timeStamp : 0, removeEventListener("prerenderingchange", b, true));
    }
  };
  var M = () => {
    if (p < 0) {
      const t2 = d(), e2 = document.prerendering ? undefined : globalThis.performance.getEntriesByType("visibility-state").find((e3) => e3.name === "hidden" && e3.startTime >= t2)?.startTime;
      p = e2 ?? v(), addEventListener("visibilitychange", b, true), addEventListener("prerenderingchange", b, true), u(() => {
        setTimeout(() => {
          p = v();
        });
      });
    }
    return { get firstHiddenTime() {
      return p;
    }, onHidden(t2) {
      y.add(t2);
    } };
  };
  var T = (t2) => {
    document.prerendering ? addEventListener("prerenderingchange", t2, true) : t2();
  };
  var E = [1800, 3000];
  var D = (t2, e2 = {}) => {
    T(() => {
      const n2 = M();
      let o2, i2 = h("FCP");
      const r2 = m("paint", (t3) => {
        for (const e3 of t3)
          e3.name === "first-contentful-paint" && (r2.disconnect(), e3.startTime < n2.firstHiddenTime && (i2.value = Math.max(e3.startTime - d(), 0), i2.entries.push(e3), o2(true)));
      });
      r2 && (o2 = f(t2, i2, E, e2.reportAllChanges), u((n3) => {
        i2 = h("FCP"), o2 = f(t2, i2, E, e2.reportAllChanges), l(() => {
          i2.value = performance.now() - n3.timeStamp, o2(true);
        });
      }));
    });
  };
  var L = [0.1, 0.25];
  var S = (t2) => t2.find((t3) => t3.node?.nodeType === 1) || t2[0];
  var P = (e2, o2 = {}) => {
    const r2 = s(o2 = Object.assign({}, o2), t), a2 = new WeakMap;
    r2.t = (t2) => {
      if (t2?.sources?.length) {
        const e3 = S(t2.sources), n2 = e3?.node;
        if (n2) {
          const t3 = o2.generateTarget?.(n2) ?? i(n2);
          a2.set(e3, t3);
        }
      }
    };
    ((e3, n2 = {}) => {
      const o3 = M();
      D(g(() => {
        let i2, r3 = h("CLS", 0);
        const a3 = s(n2, t), c2 = (t2) => {
          for (const e4 of t2)
            a3.u(e4);
          a3.o > r3.value && (r3.value = a3.o, r3.entries = a3.i, i2());
        }, d2 = m("layout-shift", c2);
        d2 && (i2 = f(e3, r3, L, n2.reportAllChanges), o3.onHidden(() => {
          c2(d2.takeRecords()), i2(true);
        }), u(() => {
          a3.o = 0, r3 = h("CLS", 0), i2 = f(e3, r3, L, n2.reportAllChanges), l(i2);
        }), setTimeout(i2));
      }));
    })((t2) => {
      e2(((t3) => {
        let e3 = {};
        if (t3.entries.length) {
          const o3 = t3.entries.reduce((t4, e4) => t4.value > e4.value ? t4 : e4);
          if (o3?.sources?.length) {
            const t4 = S(o3.sources);
            t4 && (e3 = { largestShiftTarget: a2.get(t4), largestShiftTime: o3.startTime, largestShiftValue: o3.value, largestShiftSource: t4, largestShiftEntry: o3, loadState: n(o3.startTime) });
          }
        }
        return Object.assign(t3, { attribution: e3 });
      })(t2));
    }, o2);
  };
  var w = (t2, o2 = {}) => {
    D((o3) => {
      t2(((t3) => {
        let o4 = { timeToFirstByte: 0, firstByteToFCP: t3.value, loadState: n(c()) };
        if (t3.entries.length) {
          const i2 = e(), r2 = t3.entries.at(-1);
          if (i2) {
            const e2 = i2.activationStart || 0, s2 = Math.max(0, i2.responseStart - e2);
            o4 = { timeToFirstByte: s2, firstByteToFCP: t3.value - s2, loadState: n(t3.entries[0].startTime), navigationEntry: i2, fcpEntry: r2 };
          }
        }
        return Object.assign(t3, { attribution: o4 });
      })(o3));
    }, o2);
  };
  var k = 0;
  var _ = 1 / 0;
  var F = 0;
  var B = (t2) => {
    for (const e2 of t2)
      e2.interactionId && (_ = Math.min(_, e2.interactionId), F = Math.max(F, e2.interactionId), k = F ? (F - _) / 7 + 1 : 0);
  };
  var C;
  var O = () => C ? k : performance.interactionCount ?? 0;
  var j = () => {
    "interactionCount" in performance || C || (C = m("event", B, { durationThreshold: 0 }));
  };
  var I = 0;

  class A {
    l = [];
    h = new Map;
    m;
    p;
    v() {
      I = O(), this.l.length = 0, this.h.clear();
    }
    M() {
      const t2 = Math.min(this.l.length - 1, Math.floor((O() - I) / 50));
      return this.l[t2];
    }
    u(t2) {
      if (this.m?.(t2), !t2.interactionId && t2.entryType !== "first-input")
        return;
      const e2 = this.l.at(-1);
      let n2 = this.h.get(t2.interactionId);
      if (n2 || this.l.length < 10 || t2.duration > e2.T) {
        if (n2 ? t2.duration > n2.T ? (n2.entries = [t2], n2.T = t2.duration) : t2.duration === n2.T && t2.startTime === n2.entries[0].startTime && n2.entries.push(t2) : (n2 = { id: t2.interactionId, entries: [t2], T: t2.duration }, this.h.set(n2.id, n2), this.l.push(n2)), this.l.sort((t3, e3) => e3.T - t3.T), this.l.length > 10) {
          const t3 = this.l.splice(10);
          for (const e3 of t3)
            this.h.delete(e3.id);
        }
        this.p?.(n2);
      }
    }
  }
  var W = (t2) => {
    const e2 = globalThis.requestIdleCallback || setTimeout, n2 = globalThis.cancelIdleCallback || clearTimeout;
    if (document.visibilityState === "hidden")
      t2();
    else {
      const o2 = g(t2);
      let i2 = -1;
      const r2 = () => {
        n2(i2), o2();
      };
      addEventListener("visibilitychange", r2, { once: true, capture: true }), i2 = e2(() => {
        removeEventListener("visibilitychange", r2, { capture: true }), o2();
      });
    }
  };
  var q = [200, 500];
  var x = (t2, e2 = {}) => {
    const o2 = s(e2 = Object.assign({}, e2), A);
    let r2 = [], a2 = [], c2 = 0;
    const l2 = new WeakMap, d2 = new WeakMap;
    let g2 = false;
    const p2 = () => {
      g2 || (W(y2), g2 = true);
    }, y2 = () => {
      const t3 = new Set(o2.l.map((t4) => l2.get(t4.entries[0]))), e3 = a2.length - 10;
      a2 = a2.filter((n3, o3) => o3 >= e3 || t3.has(n3));
      const n2 = new Set;
      for (const t4 of a2) {
        const e4 = v2(t4.startTime, t4.processingEnd);
        for (const t5 of e4)
          n2.add(t5);
      }
      r2 = r2.filter((t4) => t4.startTime > c2 || n2.has(t4)), g2 = false;
    };
    o2.m = (t3) => {
      const n2 = t3.startTime + t3.duration;
      let o3;
      c2 = Math.max(c2, t3.processingEnd);
      for (let i2 = a2.length - 1;i2 >= 0; i2--) {
        const r3 = a2[i2];
        if (Math.abs(n2 - r3.renderTime) <= 8) {
          o3 = r3, o3.startTime = Math.min(t3.startTime, o3.startTime), o3.processingStart = Math.min(t3.processingStart, o3.processingStart), o3.processingEnd = Math.max(t3.processingEnd, o3.processingEnd), e2.includeProcessedEventEntries !== false && o3.entries.push(t3);
          break;
        }
      }
      o3 || (o3 = { startTime: t3.startTime, processingStart: t3.processingStart, processingEnd: t3.processingEnd, renderTime: n2, entries: e2.includeProcessedEventEntries !== false ? [t3] : [] }, a2.push(o3)), (t3.interactionId || t3.entryType === "first-input") && l2.set(t3, o3), p2();
    }, o2.p = (t3) => {
      if (!d2.get(t3)) {
        const n2 = t3.entries.find((t4) => t4.target)?.target;
        if (n2) {
          const o3 = e2.generateTarget?.(n2) ?? i(n2);
          d2.set(t3, o3);
        } else {
          const e3 = t3.entries.find((t4) => t4.targetSelector)?.targetSelector;
          e3 && d2.set(t3, e3);
        }
      }
    };
    const v2 = (t3, e3) => {
      const n2 = [];
      for (const o3 of r2)
        if (!(o3.startTime + o3.duration < t3)) {
          if (o3.startTime > e3)
            break;
          n2.push(o3);
        }
      return n2;
    }, b2 = (t3) => {
      const e3 = t3.entries[0], i2 = l2.get(e3), r3 = e3.processingStart, s2 = Math.max(e3.startTime + e3.duration, r3), a3 = Math.min(i2.processingEnd, s2), c3 = i2.entries.sort((t4, e4) => t4.processingStart - e4.processingStart), u2 = v2(e3.startTime, a3), f2 = o2.h.get(e3.interactionId), h2 = { interactionTarget: d2.get(f2), interactionType: e3.name.startsWith("key") ? "keyboard" : "pointer", interactionTime: e3.startTime, nextPaintTime: s2, processedEventEntries: c3, longAnimationFrameEntries: u2, inputDelay: r3 - e3.startTime, processingDuration: a3 - r3, presentationDelay: s2 - a3, loadState: n(e3.startTime), longestScript: undefined, totalScriptDuration: undefined, totalStyleAndLayoutDuration: undefined, totalPaintDuration: undefined, totalUnattributedDuration: undefined };
      return ((t4) => {
        if (!t4.longAnimationFrameEntries?.length)
          return;
        const { interactionTime: e4, inputDelay: n2, processingDuration: o3 } = t4;
        let i3, r4, s3 = 0, a4 = 0, c4 = 0, u3 = 0;
        for (const c5 of t4.longAnimationFrameEntries) {
          a4 = a4 + c5.startTime + c5.duration - c5.styleAndLayoutStart;
          for (const t5 of c5.scripts) {
            const c6 = t5.startTime + t5.duration;
            if (c6 < e4)
              continue;
            const f4 = c6 - Math.max(e4, t5.startTime), l4 = t5.duration ? f4 / t5.duration * t5.forcedStyleAndLayoutDuration : 0;
            s3 += f4 - l4, a4 += l4, f4 > u3 && (r4 = t5.startTime < e4 + n2 ? "input-delay" : t5.startTime >= e4 + n2 + o3 ? "presentation-delay" : "processing-duration", i3 = t5, u3 = f4);
          }
        }
        const f3 = t4.longAnimationFrameEntries.at(-1), l3 = f3 ? f3.startTime + f3.duration : 0;
        l3 >= e4 + n2 + o3 && (c4 = t4.nextPaintTime - l3), i3 && r4 && (t4.longestScript = { entry: i3, subpart: r4, intersectingDuration: u3 }), t4.totalScriptDuration = s3, t4.totalStyleAndLayoutDuration = a4, t4.totalPaintDuration = c4, t4.totalUnattributedDuration = t4.nextPaintTime - e4 - s3 - a4 - c4;
      })(h2), Object.assign(t3, { attribution: h2 });
    };
    m("long-animation-frame", (t3) => {
      r2 = r2.concat(t3), p2();
    }), ((t3, e3 = {}) => {
      if (!globalThis.PerformanceEventTiming || !("interactionId" in PerformanceEventTiming.prototype))
        return;
      const n2 = M();
      T(() => {
        j();
        let o3, i2 = h("INP");
        const r3 = s(e3, A), a3 = (t4) => {
          W(() => {
            for (const e5 of t4)
              r3.u(e5);
            const e4 = r3.M();
            e4 && e4.T !== i2.value && (i2.value = e4.T, i2.entries = e4.entries, o3());
          });
        }, c3 = m("event", a3, { durationThreshold: e3.durationThreshold ?? 40 });
        o3 = f(t3, i2, q, e3.reportAllChanges), c3 && (c3.observe({ type: "first-input", buffered: true }), n2.onHidden(() => {
          a3(c3.takeRecords()), o3(true);
        }), u(() => {
          r3.v(), i2 = h("INP"), o3 = f(t3, i2, q, e3.reportAllChanges);
        }));
      });
    })((e3) => {
      t2(b2(e3));
    }, e2);
  };

  class N {
    m;
    u(t2) {
      this.m?.(t2);
    }
  }
  var $ = [2500, 4000];
  var H = (t2, n2 = {}) => {
    const o2 = s(n2 = Object.assign({}, n2), N), r2 = new WeakMap;
    o2.m = (t3) => {
      const e2 = t3.element;
      if (e2) {
        const o3 = n2.generateTarget?.(e2) ?? i(e2);
        r2.set(t3, o3);
      } else
        t3.id && r2.set(t3, `#${t3.id}`);
    };
    ((t3, e2 = {}) => {
      T(() => {
        const n3 = M();
        let o3, i2 = h("LCP");
        const r3 = s(e2, N), a2 = (t4) => {
          e2.reportAllChanges || (t4 = t4.slice(-1));
          for (const e3 of t4)
            r3.u(e3), e3.startTime < n3.firstHiddenTime && (i2.value = Math.max(e3.startTime - d(), 0), i2.entries = [e3], o3());
        }, c2 = m("largest-contentful-paint", a2);
        if (c2) {
          o3 = f(t3, i2, $, e2.reportAllChanges);
          const n4 = g(() => {
            a2(c2.takeRecords()), c2.disconnect(), o3(true);
          }), r4 = (t4) => {
            t4.isTrusted && (W(n4), removeEventListener(t4.type, r4, { capture: true }));
          };
          for (const t4 of ["keydown", "click", "visibilitychange"])
            addEventListener(t4, r4, { capture: true });
          u((n5) => {
            i2 = h("LCP"), o3 = f(t3, i2, $, e2.reportAllChanges), l(() => {
              i2.value = performance.now() - n5.timeStamp, o3(true);
            });
          });
        }
      });
    })((n3) => {
      t2(((t3) => {
        let n4 = { timeToFirstByte: 0, resourceLoadDelay: 0, resourceLoadDuration: 0, elementRenderDelay: t3.value };
        if (t3.entries.length) {
          const o3 = t3.entries.at(-1), i2 = o3.url && performance.getEntriesByType("resource").find((t4) => t4.name === o3.url);
          n4.target = r2.get(o3), n4.lcpEntry = o3, o3.url && (n4.url = o3.url), i2 && (n4.lcpResourceEntry = i2);
          const s2 = e();
          if (s2) {
            const e2 = s2.activationStart || 0, o4 = Math.max(0, s2.responseStart - e2), r3 = Math.max(o4, i2 ? (i2.requestStart || i2.startTime) - e2 : 0), a2 = Math.min(t3.value, Math.max(r3, i2 ? i2.responseEnd - e2 : 0));
            n4 = { ...n4, timeToFirstByte: o4, resourceLoadDelay: r3 - o4, resourceLoadDuration: a2 - r3, elementRenderDelay: t3.value - a2, navigationEntry: s2 };
          }
        }
        return Object.assign(t3, { attribution: n4 });
      })(n3));
    }, n2);
  };
  var R = [800, 1800];
  var U = (t2) => {
    document.prerendering ? T(() => U(t2)) : document.readyState !== "complete" ? addEventListener("load", () => U(t2), true) : setTimeout(t2);
  };
  var V = (t2, n2 = {}) => {
    ((t3, n3 = {}) => {
      let o2 = h("TTFB"), i2 = f(t3, o2, R, n3.reportAllChanges);
      U(() => {
        const r2 = e();
        r2 && (o2.value = Math.max(r2.responseStart - d(), 0), o2.entries = [r2], i2(true), u(() => {
          o2 = h("TTFB", 0), i2 = f(t3, o2, R, n3.reportAllChanges), i2(true);
        }));
      });
    })((e2) => {
      t2(((t3) => {
        let e3 = { waitingDuration: 0, cacheDuration: 0, dnsDuration: 0, connectionDuration: 0, requestDuration: 0 };
        if (t3.entries.length) {
          const n3 = t3.entries[0], o2 = n3.activationStart || 0, i2 = Math.max((n3.workerStart || n3.fetchStart) - o2, 0), r2 = Math.max(n3.domainLookupStart - o2, 0), s2 = Math.max(n3.connectStart - o2, 0), a2 = Math.max(n3.connectEnd - o2, 0);
          e3 = { waitingDuration: i2, cacheDuration: r2 - i2, dnsDuration: s2 - r2, connectionDuration: a2 - s2, requestDuration: t3.value - a2, navigationEntry: n3 };
        }
        return Object.assign(t3, { attribution: e3 });
      })(e2));
    }, n2);
  };

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/instrumentationConstants.js
  var NAVIGATION_ID_STORAGE_KEY = "com.grafana.faro.lastNavigationId";

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/webVitals/webVitalsWithAttribution.js
  var loadStateKey = "load_state";
  var timeToFirstByteKey = "time_to_first_byte";

  class WebVitalsWithAttribution {
    constructor(corePushMeasurement, webVitalConfig) {
      this.corePushMeasurement = corePushMeasurement;
      this.webVitalConfig = webVitalConfig;
    }
    initialize() {
      this.measureCLS();
      this.measureFCP();
      this.measureINP();
      this.measureLCP();
      this.measureTTFB();
    }
    measureCLS() {
      var _a;
      P((metric) => {
        const { loadState, largestShiftValue, largestShiftTime, largestShiftTarget } = metric.attribution;
        const values = this.buildInitialValues(metric);
        this.addIfPresent(values, "largest_shift_value", largestShiftValue);
        this.addIfPresent(values, "largest_shift_time", largestShiftTime);
        const context = this.buildInitialContext(metric);
        this.addIfPresent(context, loadStateKey, loadState);
        this.addIfPresent(context, "largest_shift_target", largestShiftTarget);
        this.pushMeasurement(values, context);
      }, { reportAllChanges: (_a = this.webVitalConfig) === null || _a === undefined ? undefined : _a.reportAllChanges });
    }
    measureFCP() {
      var _a;
      w((metric) => {
        const { firstByteToFCP, timeToFirstByte, loadState } = metric.attribution;
        const values = this.buildInitialValues(metric);
        this.addIfPresent(values, "first_byte_to_fcp", firstByteToFCP);
        this.addIfPresent(values, timeToFirstByteKey, timeToFirstByte);
        const context = this.buildInitialContext(metric);
        this.addIfPresent(context, loadStateKey, loadState);
        this.pushMeasurement(values, context);
      }, { reportAllChanges: (_a = this.webVitalConfig) === null || _a === undefined ? undefined : _a.reportAllChanges });
    }
    measureINP() {
      var _a;
      x((metric) => {
        const { interactionTime, presentationDelay, inputDelay, processingDuration, nextPaintTime, loadState, interactionTarget, interactionType } = metric.attribution;
        const values = this.buildInitialValues(metric);
        this.addIfPresent(values, "interaction_time", interactionTime);
        this.addIfPresent(values, "presentation_delay", presentationDelay);
        this.addIfPresent(values, "input_delay", inputDelay);
        this.addIfPresent(values, "processing_duration", processingDuration);
        this.addIfPresent(values, "next_paint_time", nextPaintTime);
        const context = this.buildInitialContext(metric);
        this.addIfPresent(context, loadStateKey, loadState);
        this.addIfPresent(context, "interaction_target", interactionTarget);
        this.addIfPresent(context, "interaction_type", interactionType);
        this.pushMeasurement(values, context);
      }, { reportAllChanges: (_a = this.webVitalConfig) === null || _a === undefined ? undefined : _a.reportAllChanges });
    }
    measureLCP() {
      var _a;
      H((metric) => {
        const { elementRenderDelay, resourceLoadDelay, resourceLoadDuration, timeToFirstByte, target } = metric.attribution;
        const values = this.buildInitialValues(metric);
        this.addIfPresent(values, "element_render_delay", elementRenderDelay);
        this.addIfPresent(values, "resource_load_delay", resourceLoadDelay);
        this.addIfPresent(values, "resource_load_duration", resourceLoadDuration);
        this.addIfPresent(values, timeToFirstByteKey, timeToFirstByte);
        const context = this.buildInitialContext(metric);
        this.addIfPresent(context, "element", target);
        this.pushMeasurement(values, context);
      }, { reportAllChanges: (_a = this.webVitalConfig) === null || _a === undefined ? undefined : _a.reportAllChanges });
    }
    measureTTFB() {
      var _a;
      V((metric) => {
        const { dnsDuration, connectionDuration, requestDuration, waitingDuration, cacheDuration } = metric.attribution;
        const values = this.buildInitialValues(metric);
        this.addIfPresent(values, "dns_duration", dnsDuration);
        this.addIfPresent(values, "connection_duration", connectionDuration);
        this.addIfPresent(values, "request_duration", requestDuration);
        this.addIfPresent(values, "waiting_duration", waitingDuration);
        this.addIfPresent(values, "cache_duration", cacheDuration);
        const context = this.buildInitialContext(metric);
        this.pushMeasurement(values, context);
      }, { reportAllChanges: (_a = this.webVitalConfig) === null || _a === undefined ? undefined : _a.reportAllChanges });
    }
    buildInitialValues(metric) {
      const indicator = metric.name.toLowerCase();
      return {
        [indicator]: metric.value,
        delta: metric.delta
      };
    }
    buildInitialContext(metric) {
      var _a;
      const navigationEntryId = (_a = getItem(NAVIGATION_ID_STORAGE_KEY, webStorageType.session)) !== null && _a !== undefined ? _a : unknownString;
      return {
        id: metric.id,
        rating: metric.rating,
        navigation_type: metric.navigationType,
        navigation_entry_id: navigationEntryId
      };
    }
    pushMeasurement(values, context) {
      const type = "web-vitals";
      this.corePushMeasurement({ type, values }, { context });
    }
    addIfPresent(source, key, metric) {
      if (metric) {
        source[key] = metric;
      }
    }
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/webVitals/instrumentation.js
  class WebVitalsInstrumentation extends BaseInstrumentation {
    constructor() {
      super(...arguments);
      this.name = "@grafana/faro-web-sdk:instrumentation-web-vitals";
      this.version = VERSION;
    }
    initialize() {
      this.logDebug("Initializing");
      const webVitals = new WebVitalsWithAttribution(this.api.pushMeasurement, this.config.webVitalsInstrumentation);
      webVitals.initialize();
    }
  }
  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/performance/performanceConstants.js
  var NAVIGATION_ENTRY = "navigation";
  var RESOURCE_ENTRY = "resource";

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/performance/performanceUtils.js
  var w3cTraceparentFormat = /^00-[a-f0-9]{32}-[a-f0-9]{16}-[0-9]{1,2}$/;
  function getSpanContextFromServerTiming(serverTimings = []) {
    for (const serverEntry of serverTimings) {
      if (serverEntry.name === "traceparent") {
        if (!w3cTraceparentFormat.test(serverEntry.description)) {
          continue;
        }
        const [, traceId, spanId] = serverEntry.description.split("-");
        if (traceId != null && spanId != null) {
          return { traceId, spanId };
        }
        break;
      }
    }
    return;
  }
  function performanceObserverSupported() {
    return "PerformanceObserver" in window;
  }
  function onDocumentReady(handleReady) {
    if (document.readyState === "complete") {
      handleReady();
    } else {
      const readyStateCompleteHandler = () => {
        if (document.readyState === "complete") {
          handleReady();
          document.removeEventListener("readystatechange", readyStateCompleteHandler);
        }
      };
      document.addEventListener("readystatechange", readyStateCompleteHandler);
    }
  }
  function includePerformanceEntry(performanceEntryJSON, allowProps = {}) {
    for (const [allowPropKey, allowPropValue] of Object.entries(allowProps)) {
      const perfEntryPropVal = performanceEntryJSON[allowPropKey];
      if (perfEntryPropVal == null) {
        return false;
      }
      if (isArray(allowPropValue)) {
        return allowPropValue.includes(perfEntryPropVal);
      }
      return perfEntryPropVal === allowPropValue;
    }
    return true;
  }
  function createFaroResourceTiming(resourceEntryRaw) {
    const {
      connectEnd,
      connectStart,
      decodedBodySize,
      domainLookupEnd,
      domainLookupStart,
      duration,
      encodedBodySize,
      fetchStart,
      initiatorType,
      name,
      nextHopProtocol,
      redirectEnd,
      redirectStart,
      renderBlockingStatus: rbs,
      requestStart,
      responseEnd,
      responseStart,
      responseStatus,
      secureConnectionStart,
      transferSize,
      workerStart
    } = resourceEntryRaw;
    return {
      name,
      httpHost: getHostFromUrl(name),
      duration: toFaroPerformanceTimingString(duration),
      tcpHandshakeTime: toFaroPerformanceTimingString(connectEnd - connectStart),
      dnsLookupTime: toFaroPerformanceTimingString(domainLookupEnd - domainLookupStart),
      tlsNegotiationTime: toFaroPerformanceTimingString(connectEnd - secureConnectionStart),
      responseStatus: toFaroPerformanceTimingString(responseStatus),
      redirectTime: toFaroPerformanceTimingString(redirectEnd - redirectStart),
      requestTime: toFaroPerformanceTimingString(responseStart - requestStart),
      responseTime: toFaroPerformanceTimingString(responseEnd - responseStart),
      fetchTime: toFaroPerformanceTimingString(responseEnd - fetchStart),
      serviceWorkerTime: toFaroPerformanceTimingString(workerStart > 0 ? fetchStart - workerStart : 0),
      decodedBodySize: toFaroPerformanceTimingString(decodedBodySize),
      encodedBodySize: toFaroPerformanceTimingString(encodedBodySize),
      cacheHitStatus: getCacheType(),
      renderBlockingStatus: toFaroPerformanceTimingString(rbs),
      protocol: nextHopProtocol,
      initiatorType,
      visibilityState: document.visibilityState,
      ttfb: toFaroPerformanceTimingString(responseStart - requestStart),
      transferSize: toFaroPerformanceTimingString(transferSize)
    };
    function getCacheType() {
      let cacheType = "fullLoad";
      if (transferSize === 0) {
        if (decodedBodySize > 0) {
          cacheType = "cache";
        }
      } else {
        if (responseStatus != null) {
          if (responseStatus === 304) {
            cacheType = "conditionalFetch";
          }
        } else if (encodedBodySize > 0 && transferSize < encodedBodySize) {
          cacheType = "conditionalFetch";
        }
      }
      return cacheType;
    }
  }
  function createFaroNavigationTiming(navigationEntryRaw) {
    const { activationStart, domComplete, domContentLoadedEventEnd, domContentLoadedEventStart, domInteractive, fetchStart, loadEventEnd, loadEventStart, responseStart, type } = navigationEntryRaw;
    const parserStart = getDocumentParsingTime();
    return Object.assign(Object.assign({}, createFaroResourceTiming(navigationEntryRaw)), {
      pageLoadTime: toFaroPerformanceTimingString(domComplete - fetchStart),
      documentParsingTime: toFaroPerformanceTimingString(parserStart ? domInteractive - parserStart : null),
      domProcessingTime: toFaroPerformanceTimingString(domComplete - domInteractive),
      domContentLoadHandlerTime: toFaroPerformanceTimingString(domContentLoadedEventEnd - domContentLoadedEventStart),
      onLoadTime: toFaroPerformanceTimingString(loadEventEnd - loadEventStart),
      ttfb: toFaroPerformanceTimingString(Math.max(responseStart - (activationStart !== null && activationStart !== undefined ? activationStart : 0), 0)),
      type
    });
  }
  function getDocumentParsingTime() {
    var _a;
    if (((_a = performance.timing) === null || _a === undefined ? undefined : _a.domLoading) != null) {
      return performance.timing.domLoading - performance.timeOrigin;
    }
    return null;
  }
  function getHostFromUrl(url) {
    try {
      return new URL(url).host || unknownString;
    } catch (_a) {
      return unknownString;
    }
  }
  function toFaroPerformanceTimingString(v2) {
    if (v2 == null) {
      return unknownString;
    }
    if (typeof v2 === "number") {
      return Math.round(v2 > 0 ? v2 : 0).toString();
    }
    return v2.toString();
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/performance/navigation.js
  function getNavigationTimings(pushEvent) {
    let faroNavigationEntryResolve;
    const faroNavigationEntryPromise = new Promise((resolve) => {
      faroNavigationEntryResolve = resolve;
    });
    const observer = new PerformanceObserver((observedEntries) => {
      var _a;
      const [navigationEntryRaw] = observedEntries.getEntries();
      if (navigationEntryRaw == null || isUrlIgnored(navigationEntryRaw.name)) {
        return;
      }
      const navEntryJson = navigationEntryRaw.toJSON();
      let spanContext = getSpanContextFromServerTiming(navEntryJson === null || navEntryJson === undefined ? undefined : navEntryJson.serverTiming);
      const faroPreviousNavigationId = (_a = getItem(NAVIGATION_ID_STORAGE_KEY, webStorageType.session)) !== null && _a !== undefined ? _a : unknownString;
      const faroNavigationEntry = Object.assign(Object.assign({}, createFaroNavigationTiming(navEntryJson)), { faroNavigationId: genShortID(), faroPreviousNavigationId });
      setItem(NAVIGATION_ID_STORAGE_KEY, faroNavigationEntry.faroNavigationId, webStorageType.session);
      pushEvent("faro.performance.navigation", faroNavigationEntry, undefined, {
        spanContext,
        timestampOverwriteMs: performance.timeOrigin + navEntryJson.startTime
      });
      faroNavigationEntryResolve(faroNavigationEntry);
    });
    observer.observe({
      type: NAVIGATION_ENTRY,
      buffered: true
    });
    return faroNavigationEntryPromise;
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/performance/resource.js
  var DEFAULT_TRACK_RESOURCES = { initiatorType: ["xmlhttprequest", "fetch"] };
  function observeResourceTimings(faroNavigationId, pushEvent, observable) {
    const trackResources = faro.config.trackResources;
    const observer = new PerformanceObserver((observedEntries) => {
      const entries = observedEntries.getEntries();
      for (const resourceEntryRaw of entries) {
        if (isUrlIgnored(resourceEntryRaw.name)) {
          continue;
        }
        observable === null || observable === undefined || observable.notify({
          type: RESOURCE_ENTRY
        });
        const resourceEntryJson = resourceEntryRaw.toJSON();
        let spanContext = getSpanContextFromServerTiming(resourceEntryJson === null || resourceEntryJson === undefined ? undefined : resourceEntryJson.serverTiming);
        if (trackResources == null && includePerformanceEntry(resourceEntryJson, DEFAULT_TRACK_RESOURCES) || trackResources) {
          const faroResourceEntry = Object.assign(Object.assign({}, createFaroResourceTiming(resourceEntryJson)), { faroNavigationId, faroResourceId: genShortID() });
          pushEvent("faro.performance.resource", faroResourceEntry, undefined, {
            spanContext,
            timestampOverwriteMs: performance.timeOrigin + resourceEntryJson.startTime
          });
        }
      }
    });
    observer.observe({
      type: RESOURCE_ENTRY,
      buffered: true
    });
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/performance/instrumentation.js
  var __awaiter = function(thisArg, _arguments, P2, generator) {
    function adopt(value) {
      return value instanceof P2 ? value : new P2(function(resolve) {
        resolve(value);
      });
    }
    return new (P2 || (P2 = Promise))(function(resolve, reject) {
      function fulfilled(value) {
        try {
          step(generator.next(value));
        } catch (e2) {
          reject(e2);
        }
      }
      function rejected(value) {
        try {
          step(generator["throw"](value));
        } catch (e2) {
          reject(e2);
        }
      }
      function step(result) {
        result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected);
      }
      step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
  };
  var performanceEntriesSubscription = new Observable;

  class PerformanceInstrumentation extends BaseInstrumentation {
    constructor() {
      super(...arguments);
      this.name = "@grafana/faro-web-sdk:instrumentation-performance";
      this.version = VERSION;
    }
    initialize() {
      if (!performanceObserverSupported()) {
        this.logDebug("performance observer not supported. Disable performance instrumentation.");
        return;
      }
      onDocumentReady(() => __awaiter(this, undefined, undefined, function* () {
        const pushEvent = this.api.pushEvent;
        const { faroNavigationId } = yield getNavigationTimings(pushEvent);
        if (faroNavigationId != null) {
          observeResourceTimings(faroNavigationId, pushEvent, performanceEntriesSubscription);
        }
      }));
    }
  }
  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/userActions/const.js
  var userActionDataAttributeParsed = "faroUserActionName";
  var userActionDataAttribute = "data-faro-user-action-name";

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/_internal/monitors/domMutationMonitor.js
  var domMutationObservable;
  var domMutationObserver;
  function monitorDomMutations() {
    if (!domMutationObservable) {
      domMutationObservable = new Observable;
    }
    if (!domMutationObserver) {
      domMutationObserver = new MutationObserver((_mutationsList, _observer) => {
        domMutationObservable.notify({ type: MESSAGE_TYPE_DOM_MUTATION });
      });
      domMutationObserver.observe(document, {
        attributes: true,
        childList: true,
        subtree: true,
        characterData: true
      });
    }
    return domMutationObservable;
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/_internal/monitors/httpRequestMonitor.js
  var apiTypeFetch = "fetch";
  var apiTypeXhr = "xhr";
  var httpRequestObservable;
  var isInstrumented2 = false;
  var originalXhrOpen;
  var originalFetchFn;
  function monitorHttpRequests() {
    if (httpRequestObservable) {
      return httpRequestObservable;
    }
    httpRequestObservable = new Observable;
    function emitStartMessage(requestProps) {
      httpRequestObservable.notify({
        type: MESSAGE_TYPE_HTTP_REQUEST_START,
        request: requestProps
      });
    }
    function emitEndMessage(requestProps) {
      httpRequestObservable.notify({
        type: MESSAGE_TYPE_HTTP_REQUEST_END,
        request: requestProps
      });
    }
    if (!isInstrumented2) {
      monitorFetch({
        onRequestStart: emitStartMessage,
        onRequestEnd: emitEndMessage
      });
      monitorXhr({
        onRequestStart: emitStartMessage,
        onRequestEnd: emitEndMessage
      });
      isInstrumented2 = true;
    }
    return httpRequestObservable;
  }
  function monitorXhr({ onRequestStart, onRequestEnd }) {
    if (!originalXhrOpen) {
      originalXhrOpen = XMLHttpRequest.prototype.open;
    }
    XMLHttpRequest.prototype.open = function() {
      const url = arguments[1];
      const isIgnoredUrl = isUrlIgnored(url);
      const method = arguments[0];
      const requestId = genShortID();
      this.addEventListener("loadstart", function() {
        if (!isIgnoredUrl) {
          onRequestStart({ url, method, requestId, apiType: apiTypeXhr });
        }
      });
      this.addEventListener("load", function() {
        if (!isIgnoredUrl) {
          onRequestEnd({ url, method, requestId, apiType: apiTypeXhr });
        }
      });
      this.addEventListener("error", function() {
        if (!isIgnoredUrl) {
          onRequestEnd({ url, method, requestId, apiType: apiTypeXhr });
        }
      });
      this.addEventListener("abort", function() {
        if (!isIgnoredUrl) {
          onRequestEnd({ url, method, requestId, apiType: apiTypeXhr });
        }
      });
      originalXhrOpen.apply(this, arguments);
    };
  }
  function monitorFetch({ onRequestEnd, onRequestStart }) {
    if (!originalFetchFn) {
      originalFetchFn = window.fetch;
    }
    window.fetch = function() {
      var _a, _b;
      const url = (_a = getUrlFromResource(arguments[0])) !== null && _a !== undefined ? _a : "";
      const isIgnoredUrl = isUrlIgnored(url);
      const method = ((_b = arguments[1]) !== null && _b !== undefined ? _b : {}).method;
      const requestId = genShortID();
      if (!isIgnoredUrl) {
        onRequestStart({ url, method, requestId, apiType: apiTypeFetch });
      }
      return originalFetchFn.apply(this, arguments).then((response) => {
        if (!isIgnoredUrl) {
          onRequestEnd({ url, method, requestId, apiType: apiTypeFetch });
        }
        return response;
      }).catch((error) => {
        if (!isIgnoredUrl) {
          onRequestEnd({ url, method, requestId, apiType: apiTypeFetch });
        }
        throw error;
      });
    };
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/_internal/monitors/performanceEntriesMonitor.js
  var performanceObservable;
  var isSubscribed = false;
  var subscription;
  function monitorPerformanceEntries() {
    if (!performanceObservable) {
      performanceObservable = new Observable;
    }
    if (!isSubscribed) {
      subscription = performanceEntriesSubscription.subscribe((data) => {
        if (data.type === RESOURCE_ENTRY) {
          performanceObservable.notify({ type: MESSAGE_TYPE_RESOURCE_ENTRY });
        }
      });
      isSubscribed = true;
    }
    return performanceObservable;
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/userActions/util.js
  function convertDataAttributeName(userActionDataAttribute2) {
    const withoutData = userActionDataAttribute2.split("data-")[1];
    const withUpperCase = withoutData === null || withoutData === undefined ? undefined : withoutData.replace(/-(.)/g, (_2, char) => char.toUpperCase());
    return withUpperCase === null || withUpperCase === undefined ? undefined : withUpperCase.replace(/-/g, "");
  }
  function startTimeout(timeoutId, cb, delay) {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
    timeoutId = setTimeout(() => {
      cb();
    }, delay);
    return timeoutId;
  }
  function isRequestStartMessage(msg) {
    return msg.type === MESSAGE_TYPE_HTTP_REQUEST_START;
  }
  function isRequestEndMessage(msg) {
    return msg.type === MESSAGE_TYPE_HTTP_REQUEST_END;
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/userActions/userActionController.js
  var defaultFollowUpActionTimeRange = 100;
  var defaultHaltTimeout = 10 * 1000;

  class UserActionController {
    constructor(userAction) {
      this.userAction = userAction;
      this.http = monitorHttpRequests();
      this.dom = monitorDomMutations();
      this.perf = monitorPerformanceEntries();
      this.isValid = false;
      this.runningRequests = new Map;
    }
    attach() {
      this.allMonitorsSub = new Observable().merge(this.http, this.dom, this.perf).takeWhile(() => [UserActionState.Started, UserActionState.Halted].includes(this.userAction.getState())).filter((msg) => {
        if (this.userAction.getState() === UserActionState.Halted && !(isRequestEndMessage(msg) && this.runningRequests.has(msg.request.requestId))) {
          return false;
        }
        return true;
      }).subscribe((msg) => {
        if (isRequestStartMessage(msg)) {
          this.runningRequests.set(msg.request.requestId, msg.request);
        }
        if (isRequestEndMessage(msg)) {
          this.runningRequests.delete(msg.request.requestId);
        }
        if (!isRequestEndMessage(msg)) {
          if (!this.isValid) {
            this.isValid = true;
          }
          this.scheduleFollowUp();
        } else if (this.userAction.getState() === UserActionState.Halted && this.runningRequests.size === 0) {
          this.endAction();
        }
      });
      this.stateSub = this.userAction.filter((s2) => [UserActionState.Ended, UserActionState.Cancelled].includes(s2)).first().subscribe(() => this.cleanup());
      this.scheduleFollowUp();
    }
    scheduleFollowUp() {
      this.clearTimer(this.followUpTid);
      this.followUpTid = setTimeout(() => {
        if (this.userAction.getState() === UserActionState.Started && this.runningRequests.size > 0) {
          this.haltAction();
          return;
        }
        if (this.isValid) {
          this.endAction();
          return;
        }
        this.cancelAction();
      }, defaultFollowUpActionTimeRange);
    }
    haltAction() {
      if (this.userAction.getState() !== UserActionState.Started) {
        return;
      }
      this.userAction.halt();
      this.startHaltTimeout();
    }
    startHaltTimeout() {
      this.clearTimer(this.haltTid);
      this.haltTid = startTimeout(this.haltTid, () => {
        if (this.userAction.getState() === UserActionState.Halted) {
          this.endAction();
        }
      }, defaultHaltTimeout);
    }
    endAction() {
      this.userAction.end();
      this.cleanup();
    }
    cancelAction() {
      this.userAction.cancel();
      this.cleanup();
    }
    cleanup() {
      var _a, _b;
      this.clearTimer(this.followUpTid);
      this.clearTimer(this.haltTid);
      (_a = this.allMonitorsSub) === null || _a === undefined || _a.unsubscribe();
      (_b = this.stateSub) === null || _b === undefined || _b.unsubscribe();
      this.allMonitorsSub = undefined;
      this.stateSub = undefined;
      this.runningRequests.clear();
    }
    clearTimer(id) {
      if (id) {
        clearTimeout(id);
      }
    }
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/userActions/processUserActionEventHandler.js
  function getUserEventHandler(faro2) {
    const { api, config } = faro2;
    function processUserEvent(event) {
      var _a, _b;
      const userActionName = getUserActionNameFromElement(event.target, (_b = (_a = config.userActionsInstrumentation) === null || _a === undefined ? undefined : _a.dataAttributeName) !== null && _b !== undefined ? _b : userActionDataAttributeParsed);
      if (!userActionName) {
        return;
      }
      const userAction = api.startUserAction(userActionName, {}, { triggerName: event.type });
      if (userAction) {
        processUserActionStarted(userAction);
      }
    }
    function processUserActionStarted(userAction) {
      const internalUserAction = userAction;
      new UserActionController(internalUserAction).attach();
    }
    return { processUserEvent, processUserActionStarted };
  }
  function getUserActionNameFromElement(element, dataAttributeName) {
    const parsedDataAttributeName = convertDataAttributeName(dataAttributeName);
    const dataset = element.dataset;
    for (const key in dataset) {
      if (key === parsedDataAttributeName) {
        return dataset[key];
      }
    }
    return;
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/userActions/instrumentation.js
  class UserActionInstrumentation extends BaseInstrumentation {
    constructor() {
      super(...arguments);
      this.name = "@grafana/faro-web-sdk:instrumentation-user-action";
      this.version = VERSION;
    }
    initialize() {
      const { processUserEvent, processUserActionStarted } = getUserEventHandler(faro);
      window.addEventListener("pointerdown", processUserEvent);
      window.addEventListener("keydown", (ev) => {
        if ([" ", "Enter"].includes(ev.key)) {
          processUserEvent(ev);
        }
      });
      this._userActionSub = userActionsMessageBus.subscribe(({ type, userAction }) => {
        if (type === "user_action_start") {
          processUserActionStarted(userAction);
        }
      });
    }
    destroy() {
      var _a;
      (_a = this._userActionSub) === null || _a === undefined || _a.unsubscribe();
    }
  }
  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/csp/instrumentation.js
  class CSPInstrumentation extends BaseInstrumentation {
    constructor() {
      super();
      this.name = "@grafana/faro-web-sdk:instrumentation-csp";
      this.version = VERSION;
    }
    initialize() {
      document.addEventListener("securitypolicyviolation", this.securitypolicyviolationHandler.bind(this));
    }
    destroy() {
      document.removeEventListener("securitypolicyviolation", this.securitypolicyviolationHandler);
    }
    securitypolicyviolationHandler(ev) {
      const attributes = {
        blockedURI: ev.blockedURI,
        columnNumber: ev.columnNumber,
        disposition: ev.disposition,
        documentURI: ev.documentURI,
        effectiveDirective: ev.effectiveDirective,
        lineNumber: ev.lineNumber,
        originalPolicy: ev.originalPolicy,
        referrer: ev.referrer,
        sample: ev.sample,
        sourceFile: ev.sourceFile,
        statusCode: ev.statusCode,
        violatedDirective: ev.violatedDirective
      };
      this.api.pushEvent("securitypolicyviolation", stringifyObjectValues(attributes));
    }
  }
  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/_internal/activityWindowTracker.js
  function isRequestStartMessage2(msg) {
    return msg.type === MESSAGE_TYPE_HTTP_REQUEST_START;
  }
  function isRequestEndMessage2(msg) {
    return msg.type === MESSAGE_TYPE_HTTP_REQUEST_END;
  }

  class ActivityWindowTracker extends Observable {
    constructor(eventsObservable, options) {
      var _a, _b, _c, _d;
      super();
      this._tracking = false;
      this.eventsObservable = eventsObservable;
      this._options = {
        inactivityMs: (_a = options === null || options === undefined ? undefined : options.inactivityMs) !== null && _a !== undefined ? _a : 100,
        drainTimeoutMs: (_b = options === null || options === undefined ? undefined : options.drainTimeoutMs) !== null && _b !== undefined ? _b : 10 * 1000,
        isOperationStart: (_c = options === null || options === undefined ? undefined : options.isOperationStart) !== null && _c !== undefined ? _c : () => {
          return;
        },
        isOperationEnd: (_d = options === null || options === undefined ? undefined : options.isOperationEnd) !== null && _d !== undefined ? _d : () => {
          return;
        }
      };
      this._initialize();
    }
    _initialize() {
      this.eventsObservable.filter(() => {
        return this._tracking;
      }).subscribe((event) => {
        var _a, _b, _c;
        this._lastEventTime = monoNow();
        (_a = this._currentEvents) === null || _a === undefined || _a.push(event);
        const startKey = this._options.isOperationStart(event);
        if (startKey) {
          (_b = this._activeOperations) === null || _b === undefined || _b.set(startKey, true);
        }
        const endKey = this._options.isOperationEnd(event);
        if (endKey) {
          (_c = this._activeOperations) === null || _c === undefined || _c.delete(endKey);
        }
        this._scheduleInactivityCheck();
      });
    }
    startTracking() {
      if (this._tracking) {
        return;
      }
      this._tracking = true;
      this._startTime = monoNow();
      this._lastEventTime = this._startTime;
      this.notify({
        message: "tracking-started"
      });
      this._currentEvents = [];
      this._activeOperations = new Map;
      this._scheduleInactivityCheck();
    }
    stopTracking() {
      this._tracking = false;
      this._clearTimer(this._inactivityTid);
      this._clearTimer(this._drainTid);
      let duration;
      if (this.hasActiveOperations()) {
        duration = monoNow() - this._startTime;
      } else {
        duration = this._lastEventTime ? this._lastEventTime - this._startTime : 0;
      }
      this.notify({
        message: "tracking-ended",
        events: this._currentEvents,
        duration
      });
    }
    _scheduleInactivityCheck() {
      this._inactivityTid = startTimeout2(this._inactivityTid, () => {
        if (this.hasActiveOperations()) {
          this._startDrainTimeout();
        } else {
          this.stopTracking();
        }
      }, this._options.inactivityMs);
    }
    _startDrainTimeout() {
      this._drainTid = startTimeout2(this._drainTid, () => {
        this.stopTracking();
      }, this._options.drainTimeoutMs);
    }
    hasActiveOperations() {
      return !!this._activeOperations && this._activeOperations.size > 0;
    }
    _clearTimer(id) {
      if (id) {
        clearTimeout(id);
      }
    }
  }
  function startTimeout2(timeoutId, cb, delay) {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
    timeoutId = setTimeout(() => {
      cb();
    }, delay);
    return timeoutId;
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/_internal/monitors/interactionMonitor.js
  var MESSAGE_TYPE_INTERACTION = "interaction";
  var interactionObservable;
  var registeredEventNames = new Set;
  var eventNameToHandler = new Map;
  function monitorInteractions(eventNames) {
    if (!interactionObservable) {
      interactionObservable = new Observable;
    }
    eventNames.forEach((eventName) => {
      if (!registeredEventNames.has(eventName)) {
        const handler = () => {
          interactionObservable.notify({ type: MESSAGE_TYPE_INTERACTION, name: eventName });
        };
        window.addEventListener(eventName, handler);
        registeredEventNames.add(eventName);
        eventNameToHandler.set(eventName, handler);
      }
    });
    return interactionObservable;
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/_internal/monitors/urlChangeMonitor.js
  var MESSAGE_TYPE_URL_CHANGE = "url-change";
  var urlChangeObservable;
  var isInstrumented3 = false;
  var lastHref;
  var originalPushState;
  var originalReplaceState;
  var onPopStateHandler;
  var onHashChangeHandler;
  var onNavigateHandler;
  var originalNavigateEventIntercept;
  function monitorUrlChanges() {
    if (!urlChangeObservable) {
      urlChangeObservable = new Observable;
      lastHref = location.href;
    }
    function emit(trigger, toOverride) {
      const next = toOverride !== null && toOverride !== undefined ? toOverride : location.href;
      if (next !== lastHref) {
        urlChangeObservable.notify({ type: MESSAGE_TYPE_URL_CHANGE, from: lastHref, to: next, trigger });
        lastHref = next;
      }
    }
    if (!isInstrumented3) {
      const hasNavigation = "navigation" in window && "NavigateEvent" in window;
      if (hasNavigation) {
        onNavigateHandler = (e2) => {
          try {
            const destination = e2 === null || e2 === undefined ? undefined : e2.destination;
            if ((destination === null || destination === undefined ? undefined : destination.sameDocument) && typeof destination.url === "string") {
              emit("navigate", destination.url);
            }
          } catch (_err) {}
        };
        window.navigation.addEventListener("navigate", onNavigateHandler);
        const NavigateEventConstructor = window.NavigateEvent;
        if (NavigateEventConstructor && NavigateEventConstructor.prototype && typeof NavigateEventConstructor.prototype.intercept === "function") {
          if (!originalNavigateEventIntercept) {
            originalNavigateEventIntercept = NavigateEventConstructor.prototype.intercept;
          }
          NavigateEventConstructor.prototype.intercept = function(options) {
            try {
              const canIntercept = !!(this === null || this === undefined ? undefined : this.canIntercept);
              const destination = this === null || this === undefined ? undefined : this.destination;
              if (canIntercept && destination && destination.sameDocument === false && typeof destination.url === "string") {
                emit("navigate-intercept", destination.url);
              }
            } catch (_err) {}
            return originalNavigateEventIntercept.call(this, options);
          };
        }
        isInstrumented3 = true;
      } else {
        if (!originalPushState) {
          originalPushState = window.history.pushState;
        }
        window.history.pushState = function(...args) {
          const result = originalPushState.apply(window.history, args);
          emit("pushState");
          return result;
        };
        if (!originalReplaceState) {
          originalReplaceState = window.history.replaceState;
        }
        window.history.replaceState = function(...args) {
          const result = originalReplaceState.apply(window.history, args);
          emit("replaceState");
          return result;
        };
        onPopStateHandler = () => emit("popstate");
        onHashChangeHandler = () => emit("hashchange");
        window.addEventListener("popstate", onPopStateHandler);
        window.addEventListener("hashchange", onHashChangeHandler);
        isInstrumented3 = true;
      }
    }
    return urlChangeObservable;
  }

  // node_modules/@grafana/faro-web-sdk/dist/esm/instrumentations/navigation/instrumentation.js
  class NavigationInstrumentation extends BaseInstrumentation {
    constructor() {
      super(...arguments);
      this.name = "@grafana/faro-web-sdk:instrumentation-navigation";
      this.version = VERSION;
    }
    initialize() {
      const httpMonitor = monitorHttpRequests();
      const domMutationsMonitor = monitorDomMutations();
      const urlMonitor = monitorUrlChanges();
      const interactionMonitor = monitorInteractions(["pointerdown", "keydown"]);
      const activityWindowTracker = new ActivityWindowTracker(new Observable().merge(httpMonitor, domMutationsMonitor, urlMonitor), {
        inactivityMs: 100,
        drainTimeoutMs: 10 * 1000,
        isOperationStart: (msg) => isRequestStartMessage2(msg) ? msg.request.requestId : undefined,
        isOperationEnd: (msg) => isRequestEndMessage2(msg) ? msg.request.requestId : undefined
      });
      activityWindowTracker.filter((msg) => {
        return msg.message === "tracking-ended";
      }).subscribe((msg) => {
        var _a, _b, _c;
        if (((_a = msg.events) === null || _a === undefined ? undefined : _a.some((e2) => e2.type === "url-change")) && ((_b = msg.events) === null || _b === undefined ? undefined : _b.some((e2) => e2.type === "dom-mutation"))) {
          const urlChange = (_c = msg.events) === null || _c === undefined ? undefined : _c.find((e2) => e2.type === "url-change");
          faro.api.pushEvent("faro.navigation", {
            fromUrl: urlChange === null || urlChange === undefined ? undefined : urlChange.from,
            toUrl: urlChange === null || urlChange === undefined ? undefined : urlChange.to,
            sameDocument: String(true),
            duration: msg.duration
          });
        }
      });
      interactionMonitor.subscribe(() => {
        activityWindowTracker.startTracking();
      });
    }
  }
  // node_modules/@grafana/faro-web-sdk/dist/esm/config/getWebInstrumentations.js
  function getWebInstrumentations(options = {}) {
    const instrumentations = [
      new UserActionInstrumentation,
      new ErrorsInstrumentation,
      new WebVitalsInstrumentation,
      new SessionInstrumentation,
      new ViewInstrumentation,
      new NavigationInstrumentation
    ];
    if (options.enablePerformanceInstrumentation !== false) {
      instrumentations.unshift(new PerformanceInstrumentation);
    }
    if (options.enableContentSecurityPolicyInstrumentation !== false) {
      instrumentations.push(new CSPInstrumentation);
    }
    if (options.captureConsole !== false) {
      instrumentations.push(new ConsoleInstrumentation);
    }
    return instrumentations;
  }
  // node_modules/@grafana/faro-web-sdk/dist/esm/consts.js
  var defaultEventDomain = "browser";

  // node_modules/@grafana/faro-web-sdk/dist/esm/metas/k6/meta.js
  var k6Meta = () => {
    const k6Properties = window.k6;
    return {
      k6: Object.assign({
        isK6Browser: true
      }, (k6Properties === null || k6Properties === undefined ? undefined : k6Properties.testRunId) && { testRunId: k6Properties === null || k6Properties === undefined ? undefined : k6Properties.testRunId })
    };
  };
  // node_modules/@grafana/faro-web-sdk/dist/esm/metas/page/meta.js
  var currentHref;
  var pageId;
  function createPageMeta({ generatePageId, initialPageMeta } = {}) {
    const pageMeta = () => {
      const locationHref = location.href;
      if (isFunction(generatePageId) && currentHref !== locationHref) {
        currentHref = locationHref;
        pageId = generatePageId(location);
      }
      return {
        page: Object.assign(Object.assign({ url: locationHref }, pageId ? { id: pageId } : {}), initialPageMeta)
      };
    };
    return pageMeta;
  }
  // node_modules/@grafana/faro-web-sdk/dist/esm/transports/fetch/transport.js
  var __awaiter2 = function(thisArg, _arguments, P2, generator) {
    function adopt(value) {
      return value instanceof P2 ? value : new P2(function(resolve) {
        resolve(value);
      });
    }
    return new (P2 || (P2 = Promise))(function(resolve, reject) {
      function fulfilled(value) {
        try {
          step(generator.next(value));
        } catch (e2) {
          reject(e2);
        }
      }
      function rejected(value) {
        try {
          step(generator["throw"](value));
        } catch (e2) {
          reject(e2);
        }
      }
      function step(result) {
        result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected);
      }
      step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
  };
  var __rest = function(s2, e2) {
    var t2 = {};
    for (var p2 in s2)
      if (Object.prototype.hasOwnProperty.call(s2, p2) && e2.indexOf(p2) < 0)
        t2[p2] = s2[p2];
    if (s2 != null && typeof Object.getOwnPropertySymbols === "function")
      for (var i2 = 0, p2 = Object.getOwnPropertySymbols(s2);i2 < p2.length; i2++) {
        if (e2.indexOf(p2[i2]) < 0 && Object.prototype.propertyIsEnumerable.call(s2, p2[i2]))
          t2[p2[i2]] = s2[p2[i2]];
      }
    return t2;
  };
  var DEFAULT_BUFFER_SIZE = 30;
  var DEFAULT_CONCURRENCY = 5;
  var DEFAULT_RATE_LIMIT_BACKOFF_MS = 5000;
  var BEACON_BODY_SIZE_LIMIT = 60000;
  var MAX_KEEPALIVE_REQUESTS = 9;
  var TOO_MANY_REQUESTS = 429;
  var ACCEPTED = 202;
  var pendingKeepaliveBodySize = 0;
  var pendingKeepaliveRequests = 0;

  class FetchTransport extends BaseTransport {
    constructor(options) {
      var _a, _b, _c, _d, _e;
      super();
      this.options = options;
      this.name = "@grafana/faro-web-sdk:transport-fetch";
      this.version = VERSION;
      this.disabledUntil = new Date(0);
      this.rateLimitBackoffMs = (_a = options.defaultRateLimitBackoffMs) !== null && _a !== undefined ? _a : DEFAULT_RATE_LIMIT_BACKOFF_MS;
      this.getNow = (_b = options.getNow) !== null && _b !== undefined ? _b : () => Date.now();
      const requestCompression = (_c = options.requestCompression) !== null && _c !== undefined ? _c : false;
      if (requestCompression && typeof CompressionStream === "undefined") {
        this.compressionEnabled = false;
        this.logWarn("requestCompression is enabled but CompressionStream is not available. Falling back to uncompressed.");
      } else {
        this.compressionEnabled = requestCompression;
      }
      this.promiseBuffer = createPromiseBuffer({
        size: (_d = options.bufferSize) !== null && _d !== undefined ? _d : DEFAULT_BUFFER_SIZE,
        concurrency: (_e = options.concurrency) !== null && _e !== undefined ? _e : DEFAULT_CONCURRENCY
      });
    }
    send(items) {
      return __awaiter2(this, undefined, undefined, function* () {
        try {
          if (this.disabledUntil > new Date(this.getNow())) {
            this.logWarn(`Dropping transport item due to too many requests. Backoff until ${this.disabledUntil}`);
            return Promise.resolve();
          }
          yield this.promiseBuffer.add(() => __awaiter2(this, undefined, undefined, function* () {
            const jsonBody = JSON.stringify(getTransportBody(items));
            const { url, requestOptions, apiKey } = this.options;
            const _a = requestOptions !== null && requestOptions !== undefined ? requestOptions : {}, { headers = {} } = _a, restOfRequestOptions = __rest(_a, ["headers"]);
            const { keepalive: configuredKeepalive } = restOfRequestOptions, requestOptionsWithoutKeepalive = __rest(restOfRequestOptions, ["keepalive"]);
            let sessionId;
            const sessionMeta = this.metas.value.session;
            if (sessionMeta != null) {
              sessionId = sessionMeta.id;
            }
            const resolvedHeaders = {};
            for (const [key, value] of Object.entries(headers)) {
              resolvedHeaders[key] = typeof value === "function" ? yield Promise.resolve(value()) : value;
            }
            let body = jsonBody;
            let bodySize = jsonBody.length;
            const compressionHeaders = {};
            if (this.compressionEnabled) {
              body = yield this.compress(jsonBody);
              bodySize = body.size;
              compressionHeaders["Content-Encoding"] = "gzip";
            }
            const requestInit = Object.assign({ method: "POST", headers: Object.assign(Object.assign(Object.assign(Object.assign({ "Content-Type": "application/json" }, compressionHeaders), resolvedHeaders), apiKey ? { "x-api-key": apiKey } : {}), sessionId ? { "x-faro-session-id": sessionId } : {}), body }, requestOptionsWithoutKeepalive !== null && requestOptionsWithoutKeepalive !== undefined ? requestOptionsWithoutKeepalive : {});
            return this.fetchWithKeepaliveRetry(url, requestInit, bodySize, configuredKeepalive).catch((err) => {
              this.logError(`Failed sending payload to the receiver
`, JSON.parse(jsonBody), err);
            });
          }));
        } catch (err) {
          this.logError(err);
        }
      });
    }
    getIgnoreUrls() {
      var _a;
      return [this.options.url].concat((_a = this.config.ignoreUrls) !== null && _a !== undefined ? _a : []);
    }
    isBatched() {
      return true;
    }
    getRetryAfterDate(response) {
      const now = this.getNow();
      const retryAfterHeader = response.headers.get("Retry-After");
      if (retryAfterHeader) {
        const delay = Number(retryAfterHeader);
        if (!isNaN(delay)) {
          return new Date(delay * 1000 + now);
        }
        const date = Date.parse(retryAfterHeader);
        if (!isNaN(date)) {
          return new Date(date);
        }
      }
      return new Date(now + this.rateLimitBackoffMs);
    }
    reserveKeepalive(bodySize, configuredKeepalive) {
      if (configuredKeepalive === false) {
        return {
          keepalive: false,
          release: noop
        };
      }
      if (bodySize > BEACON_BODY_SIZE_LIMIT || pendingKeepaliveBodySize + bodySize > BEACON_BODY_SIZE_LIMIT || pendingKeepaliveRequests >= MAX_KEEPALIVE_REQUESTS) {
        this.logDebug("Disabling keepalive because the pending keepalive request budget would be exceeded.");
        return {
          keepalive: false,
          release: noop
        };
      }
      pendingKeepaliveBodySize += bodySize;
      pendingKeepaliveRequests++;
      let released = false;
      return {
        keepalive: true,
        release: () => {
          if (released) {
            return;
          }
          released = true;
          pendingKeepaliveBodySize = Math.max(0, pendingKeepaliveBodySize - bodySize);
          pendingKeepaliveRequests = Math.max(0, pendingKeepaliveRequests - 1);
        }
      };
    }
    fetchWithKeepaliveRetry(url, requestInit, bodySize, configuredKeepalive) {
      return __awaiter2(this, undefined, undefined, function* () {
        const keepaliveReservation = this.reserveKeepalive(bodySize, configuredKeepalive);
        try {
          const response = yield fetch(url, Object.assign(Object.assign({}, requestInit), { keepalive: keepaliveReservation.keepalive }));
          return this.handleResponse(response);
        } catch (err) {
          if (keepaliveReservation.keepalive && this.isFetchNetworkError(err)) {
            this.logDebug("Retrying failed keepalive request with keepalive disabled.");
            const response = yield fetch(url, Object.assign(Object.assign({}, requestInit), { keepalive: false }));
            return this.handleResponse(response);
          }
          throw err;
        } finally {
          keepaliveReservation.release();
        }
      });
    }
    handleResponse(response) {
      return __awaiter2(this, undefined, undefined, function* () {
        if (response.status === ACCEPTED) {
          const sessionExpired = response.headers.get("X-Faro-Session-Status") === "invalid";
          if (sessionExpired) {
            this.extendFaroSession(this.config, this.logDebug);
          }
        }
        if (response.status === TOO_MANY_REQUESTS) {
          this.disabledUntil = this.getRetryAfterDate(response);
          this.logWarn(`Too many requests, backing off until ${this.disabledUntil}`);
        }
        response.text().catch(noop);
        return response;
      });
    }
    isFetchNetworkError(err) {
      return err instanceof TypeError;
    }
    compress(body) {
      return __awaiter2(this, undefined, undefined, function* () {
        const stream = new ReadableStream({
          start(controller) {
            controller.enqueue(new TextEncoder().encode(body));
            controller.close();
          }
        }).pipeThrough(new CompressionStream("gzip"));
        const reader = stream.getReader();
        const chunks = [];
        for (;; ) {
          const { done, value } = yield reader.read();
          if (done) {
            break;
          }
          chunks.push(value);
        }
        return new Blob(chunks);
      });
    }
    extendFaroSession(config, logDebug) {
      const SessionExpiredString = `Session expired`;
      const sessionTrackingConfig = config.sessionTracking;
      if (sessionTrackingConfig === null || sessionTrackingConfig === undefined ? undefined : sessionTrackingConfig.enabled) {
        const { fetchUserSession, storeUserSession } = getSessionManagerByConfig(sessionTrackingConfig);
        getUserSessionUpdater({ fetchUserSession, storeUserSession })({ forceSessionExtend: true });
        logDebug(`${SessionExpiredString} created new session.`);
      } else {
        logDebug(`${SessionExpiredString}.`);
      }
    }
  }
  // node_modules/@grafana/faro-web-sdk/dist/esm/config/makeCoreConfig.js
  var __rest2 = function(s2, e2) {
    var t2 = {};
    for (var p2 in s2)
      if (Object.prototype.hasOwnProperty.call(s2, p2) && e2.indexOf(p2) < 0)
        t2[p2] = s2[p2];
    if (s2 != null && typeof Object.getOwnPropertySymbols === "function")
      for (var i2 = 0, p2 = Object.getOwnPropertySymbols(s2);i2 < p2.length; i2++) {
        if (e2.indexOf(p2[i2]) < 0 && Object.prototype.propertyIsEnumerable.call(s2, p2[i2]))
          t2[p2[i2]] = s2[p2[i2]];
      }
    return t2;
  };
  function makeCoreConfig(browserConfig) {
    var _a, _b, _c, _d, _e;
    const transports = [];
    const internalLogger2 = createInternalLogger(browserConfig.unpatchedConsole, browserConfig.internalLoggerLevel);
    if (browserConfig.transports) {
      if (browserConfig.url || browserConfig.apiKey) {
        internalLogger2.error('if "transports" is defined, "url" and "apiKey" should not be defined');
      }
      transports.push(...browserConfig.transports);
    } else if (browserConfig.url) {
      transports.push(new FetchTransport({
        url: browserConfig.url,
        apiKey: browserConfig.apiKey,
        requestCompression: browserConfig.requestCompression
      }));
    } else {
      internalLogger2.error('either "url" or "transports" must be defined');
    }
    const {
      dedupe = true,
      eventDomain = defaultEventDomain,
      globalObjectKey = defaultGlobalObjectKey,
      instrumentations = getWebInstrumentations(),
      internalLoggerLevel = defaultInternalLoggerLevel,
      isolate = false,
      logArgsSerializer = defaultLogArgsSerializer,
      metas = createDefaultMetas(browserConfig),
      paused = false,
      preventGlobalExposure = false,
      unpatchedConsole: unpatchedConsole2 = defaultUnpatchedConsole,
      url: browserConfigUrl,
      experimental
    } = browserConfig, restProperties = __rest2(browserConfig, ["dedupe", "eventDomain", "globalObjectKey", "instrumentations", "internalLoggerLevel", "isolate", "logArgsSerializer", "metas", "paused", "preventGlobalExposure", "unpatchedConsole", "url", "experimental"]);
    const trackNavigation = (_a = experimental === null || experimental === undefined ? undefined : experimental.trackNavigation) !== null && _a !== undefined ? _a : false;
    const userActionsInstrumentation = {
      dataAttributeName: (_c = (_b = browserConfig.userActionsInstrumentation) === null || _b === undefined ? undefined : _b.dataAttributeName) !== null && _c !== undefined ? _c : userActionDataAttribute,
      excludeItem: (_d = browserConfig.userActionsInstrumentation) === null || _d === undefined ? undefined : _d.excludeItem
    };
    return Object.assign(Object.assign({}, restProperties), {
      batching: Object.assign(Object.assign({}, defaultBatchingConfig), browserConfig.batching),
      dedupe,
      globalObjectKey,
      instrumentations: getFilteredInstrumentations(instrumentations, browserConfig),
      internalLoggerLevel,
      isolate,
      logArgsSerializer,
      metas,
      parseStacktrace,
      paused,
      preventGlobalExposure,
      transports,
      unpatchedConsole: unpatchedConsole2,
      eventDomain,
      ignoreUrls: [
        ...(_e = browserConfig.ignoreUrls) !== null && _e !== undefined ? _e : [],
        ...browserConfigUrl ? [browserConfigUrl] : [],
        /\/collect(?:\/[\w]*)?$/
      ],
      sessionTracking: Object.assign(Object.assign(Object.assign({}, defaultSessionTrackingConfig), browserConfig.sessionTracking), crateSessionMeta({
        trackGeolocation: browserConfig.trackGeolocation,
        sessionTracking: browserConfig.sessionTracking
      })),
      userActionsInstrumentation,
      experimental: {
        trackNavigation
      }
    });
  }
  function getFilteredInstrumentations(instrumentations, { experimental }) {
    var _a;
    const trackNavigation = (_a = experimental === null || experimental === undefined ? undefined : experimental.trackNavigation) !== null && _a !== undefined ? _a : false;
    return instrumentations.filter((instr) => {
      if (instr.name === "@grafana/faro-web-sdk:instrumentation-navigation" && !trackNavigation) {
        return false;
      }
      return true;
    });
  }
  function createDefaultMetas(browserConfig) {
    var _a, _b;
    const { page, generatePageId } = (_a = browserConfig === null || browserConfig === undefined ? undefined : browserConfig.pageTracking) !== null && _a !== undefined ? _a : {};
    const initialMetas = [
      browserMeta,
      osMeta,
      createPageMeta({ generatePageId, initialPageMeta: page }),
      ...(_b = browserConfig.metas) !== null && _b !== undefined ? _b : [],
      sdkMeta
    ];
    const isK6BrowserSession = isObject(window === null || window === undefined ? undefined : window.k6);
    if (isK6BrowserSession) {
      return [...initialMetas, k6Meta];
    }
    return initialMetas;
  }
  function crateSessionMeta({ trackGeolocation, sessionTracking }) {
    var _a;
    const overrides = {};
    if (isBoolean(trackGeolocation)) {
      overrides.geoLocationTrackingEnabled = trackGeolocation;
    }
    if (isEmpty(overrides)) {
      return {};
    }
    return {
      session: Object.assign(Object.assign({}, (_a = sessionTracking === null || sessionTracking === undefined ? undefined : sessionTracking.session) !== null && _a !== undefined ? _a : {}), { overrides })
    };
  }
  // node_modules/@grafana/faro-web-sdk/dist/esm/initialize.js
  function initializeFaro2(config) {
    const coreConfig = makeCoreConfig(config);
    if (!coreConfig) {
      return;
    }
    return initializeFaro(coreConfig);
  }
  // src/replay-privacy.ts
  var REDACTED_TEXT = "[redacted]";
  var MAX_REPLAY_TEXT_BYTES = 1024 * 1024;
  var MAX_SAFE_INTEGER = Number.MAX_SAFE_INTEGER;
  var SAFE_REPLAY_ATTRIBUTES = new Set(`autofocus checked colspan controls dir disabled height hidden lang loop max maxlength min
   minlength multiple open readonly required reversed role rowspan selected size step type width`.split(/\s+/));
  var SAFE_REPLAY_CSS_PROPERTIES = new Set(`align-content align-items align-self alignment-baseline appearance aspect-ratio
   backface-visibility background-color border border-block border-block-color border-block-end
   border-block-end-color border-block-end-style border-block-end-width border-block-start
   border-block-start-color border-block-start-style border-block-start-width border-block-style
   border-block-width border-bottom border-bottom-color border-bottom-left-radius
   border-bottom-right-radius border-bottom-style border-bottom-width border-collapse border-color
   border-end-end-radius border-end-start-radius border-inline border-inline-color border-inline-end
   border-inline-end-color border-inline-end-style border-inline-end-width border-inline-start
   border-inline-start-color border-inline-start-style border-inline-start-width border-inline-style
   border-inline-width border-left border-left-color border-left-style border-left-width border-radius
   border-right border-right-color border-right-style border-right-width border-spacing
   border-start-end-radius border-start-start-radius border-style border-top border-top-color
   border-top-left-radius border-top-right-radius border-top-style border-top-width border-width bottom
   box-shadow box-sizing caption-side clear color color-scheme column-count column-fill column-gap
   column-rule column-rule-color column-rule-style column-rule-width column-span column-width columns
   direction display dominant-baseline empty-cells fill fill-opacity fill-rule flex flex-basis
   flex-direction flex-flow flex-grow flex-shrink flex-wrap float flood-color flood-opacity font
   font-family font-feature-settings font-kerning font-optical-sizing font-size font-size-adjust
   font-stretch font-style font-variant font-variant-caps font-weight gap grid grid-area
   grid-auto-columns grid-auto-flow grid-auto-rows grid-column grid-column-end grid-column-start grid-row
   grid-row-end grid-row-start grid-template grid-template-areas grid-template-columns
   grid-template-rows height hyphens inset inset-block inset-block-end inset-block-start inset-inline
   inset-inline-end inset-inline-start isolation justify-content justify-items justify-self left
   letter-spacing lighting-color line-height list-style-position list-style-type margin margin-block
   margin-block-end margin-block-start margin-bottom margin-inline margin-inline-end margin-inline-start
   margin-left margin-right margin-top max-block-size max-height max-inline-size max-width min-block-size
   min-height min-inline-size min-width object-fit object-position opacity order outline outline-color
   outline-offset outline-style outline-width overflow overflow-anchor overflow-block overflow-inline
   overflow-wrap overflow-x overflow-y padding padding-block padding-block-end padding-block-start
   padding-bottom padding-inline padding-inline-end padding-inline-start padding-left padding-right
   padding-top paint-order perspective perspective-origin place-content place-items place-self position
   right row-gap shape-rendering stop-color stop-opacity stroke stroke-dasharray stroke-dashoffset
   stroke-linecap stroke-linejoin stroke-miterlimit stroke-opacity stroke-width tab-size table-layout
   text-align text-align-last text-anchor text-decoration text-decoration-color text-decoration-line
   text-decoration-style text-decoration-thickness text-indent text-overflow text-shadow
   text-size-adjust text-transform text-underline-offset top transform transform-box transform-origin
   transform-style unicode-bidi vector-effect vertical-align visibility white-space width word-break
   word-spacing word-wrap writing-mode z-index -moz-osx-font-smoothing -webkit-appearance
   -webkit-font-smoothing -webkit-text-size-adjust -webkit-transform -webkit-transform-origin`.split(/\s+/));
  var SAFE_REPLAY_CSS_FUNCTIONS = new Set(`calc clamp color color-mix env fit-content hsl hsla hwb lab lch matrix matrix3d max min minmax
   oklab oklch perspective repeat rgb rgba rotate rotate3d rotatex rotatey rotatez scale scale3d
   scalex scaley scalez skew skewx skewy translate translate3d translatex translatey translatez var`.split(/\s+/));
  var SAFE_SVG_ATTRIBUTES = new Set(`alignment-baseline cx cy d dominant-baseline dx dy fill fill-opacity fill-rule font-family
   font-size font-style font-weight gradienttransform gradientunits height lengthadjust offset opacity
   paint-order pathlength points preserveaspectratio r rx ry shape-rendering spreadmethod stop-color
   stop-opacity stroke stroke-dasharray stroke-dashoffset stroke-linecap stroke-linejoin
   stroke-miterlimit stroke-opacity stroke-width text-anchor textlength transform transform-origin
   vector-effect viewbox visibility width x x1 x2 y y1 y2`.split(/\s+/));
  var FORBIDDEN_CSS = /(?:url\s*\(|@import\b|@font-face\b|expression\s*\(|image(?:-set)?\s*\(|cross-fade\s*\(|element\s*\(|paint\s*\(|-moz-binding\b|behavior\s*:|javascript\s*:|data\s*:|blob\s*:|https?\s*:|\/\*)/i;
  var SAFE_SELECTOR = /^[-A-Za-z0-9\s._:(),>+~*]+$/;
  var SAFE_AT_RULE_CONDITION = /^[-A-Za-z0-9\s._:(),/%+~*]+$/;
  function asObject(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value) ? value : undefined;
  }
  function finiteNumber(value) {
    return typeof value === "number" && Number.isFinite(value) ? value : undefined;
  }
  function integer(value, minimum = 0) {
    return typeof value === "number" && Number.isSafeInteger(value) && value >= minimum && value <= MAX_SAFE_INTEGER ? value : undefined;
  }
  function finiteFields(source, names) {
    const output = {};
    for (const name of names) {
      const value = finiteNumber(source[name]);
      if (value === undefined)
        return;
      output[name] = value;
    }
    return output;
  }
  function integerFields(source, names, minimum = 0) {
    const output = {};
    for (const name of names) {
      const value = integer(source[name], minimum);
      if (value === undefined)
        return;
      output[name] = value;
    }
    return output;
  }
  function redactText(value) {
    if (typeof value !== "string")
      return;
    return value.length === 0 ? "" : REDACTED_TEXT;
  }
  function readableText(value) {
    if (typeof value !== "string")
      return;
    return new TextEncoder().encode(value).byteLength <= MAX_REPLAY_TEXT_BYTES ? value : undefined;
  }
  function decodeCssEscapes(input) {
    let output = "";
    for (let index = 0;index < input.length; index += 1) {
      const character = input[index];
      if (character !== "\\") {
        output += character;
        continue;
      }
      index += 1;
      if (index >= input.length)
        return;
      const escaped = input[index];
      if (escaped === `
` || escaped === "\r" || escaped === "\f")
        return;
      if (!/[0-9a-f]/i.test(escaped)) {
        output += escaped;
        continue;
      }
      let hex = escaped;
      while (hex.length < 6 && index + 1 < input.length && /[0-9a-f]/i.test(input[index + 1])) {
        index += 1;
        hex += input[index];
      }
      const codePoint = Number.parseInt(hex, 16);
      if (codePoint === 0 || codePoint > 1114111)
        return;
      output += String.fromCodePoint(codePoint);
      if (index + 1 < input.length && /[\t\n\f\r ]/.test(input[index + 1]))
        index += 1;
    }
    return output;
  }
  function containsCssRequestSyntax(value) {
    const decoded = decodeCssEscapes(value);
    if (decoded === undefined)
      return true;
    return /(?:^|[;{])\s*@(import|font-face)\b|(?:url|image-set|cross-fade|element|paint)\s*\(/i.test(decoded);
  }
  function hasControlCharacter(value, allowCssWhitespace) {
    for (let index = 0;index < value.length; index += 1) {
      const code = value.charCodeAt(index);
      if (code === 127)
        return true;
      if (code >= 32)
        continue;
      if (allowCssWhitespace && (code === 9 || code === 10 || code === 13))
        continue;
      return true;
    }
    return false;
  }
  function safePrintableString(value, maximumBytes = 4096) {
    if (typeof value !== "string" || new TextEncoder().encode(value).byteLength > maximumBytes || hasControlCharacter(value, false)) {
      return;
    }
    return value;
  }
  function safeCssValue(value) {
    if (value.length > 16 * 1024 || hasControlCharacter(value, true) || FORBIDDEN_CSS.test(value)) {
      return false;
    }
    for (const match of value.matchAll(/(-?[A-Za-z][A-Za-z0-9-]*)\s*\(/g)) {
      if (!SAFE_REPLAY_CSS_FUNCTIONS.has(match[1].toLowerCase()))
        return false;
    }
    return true;
  }
  function sanitizeCssDeclaration(rawProperty, rawValue, rawPriority = "") {
    if (typeof rawProperty !== "string" || typeof rawValue !== "string")
      return;
    const property = rawProperty.trim().toLowerCase();
    const priority = rawPriority === "important" ? "important" : rawPriority === "" ? "" : undefined;
    if (!SAFE_REPLAY_CSS_PROPERTIES.has(property) || priority === undefined || !safeCssValue(rawValue)) {
      return;
    }
    if (typeof document === "undefined")
      return;
    const probe = document.createElement("span").style;
    probe.setProperty(property, rawValue, priority);
    const value = probe.getPropertyValue(property);
    if (!value || !safeCssValue(value))
      return;
    return { priority: probe.getPropertyPriority(property), property, value };
  }
  function sanitizeStyleDeclaration(style) {
    if (typeof document === "undefined")
      return "";
    const output = document.createElement("span").style;
    for (const property of Array.from(style)) {
      const sanitized = sanitizeCssDeclaration(property, style.getPropertyValue(property), style.getPropertyPriority(property));
      if (sanitized) {
        output.setProperty(sanitized.property, sanitized.value, sanitized.priority);
      }
    }
    return output.cssText;
  }
  function sanitizeInlineCss(value) {
    if (typeof value !== "string" || value.length > 64 * 1024 || typeof document === "undefined") {
      return;
    }
    const source = document.createElement("span").style;
    source.cssText = value;
    return sanitizeStyleDeclaration(source);
  }
  function sanitizeSelector(value) {
    const selector = value.trim();
    return selector.length > 0 && selector.length <= 4096 && SAFE_SELECTOR.test(selector) ? selector : undefined;
  }
  function sanitizeCssRuleList(rules) {
    const output = [];
    for (const rule of Array.from(rules)) {
      if (rule.type === 1) {
        const styleRule = rule;
        const selector = sanitizeSelector(styleRule.selectorText);
        const declarations = sanitizeStyleDeclaration(styleRule.style);
        if (selector && declarations)
          output.push(`${selector}{${declarations}}`);
        continue;
      }
      if (rule.type === 4 || rule.type === 12) {
        const group = rule;
        const condition = group.conditionText.trim();
        if (condition.length > 0 && condition.length <= 4096 && SAFE_AT_RULE_CONDITION.test(condition) && !FORBIDDEN_CSS.test(condition)) {
          const nested = sanitizeCssRuleList(group.cssRules);
          if (nested)
            output.push(`@${rule.type === 4 ? "media" : "supports"} ${condition}{${nested}}`);
        }
      }
    }
    return output.join("");
  }
  function sanitizeStylesheetCss(value) {
    if (typeof value !== "string" || value.length > 1024 * 1024 || typeof CSSStyleSheet === "undefined") {
      return;
    }
    try {
      const sheet = new CSSStyleSheet;
      sheet.replaceSync(value);
      return sanitizeCssRuleList(sheet.cssRules);
    } catch {
      return "";
    }
  }
  function sanitizeStyleAttribute(value) {
    if (typeof value === "string")
      return sanitizeInlineCss(value);
    const source = asObject(value);
    if (!source)
      return;
    const output = {};
    for (const [rawProperty, rawValue] of Object.entries(source)) {
      if (rawValue === false) {
        if (SAFE_REPLAY_CSS_PROPERTIES.has(rawProperty.toLowerCase()))
          output[rawProperty] = false;
        continue;
      }
      const tuple = Array.isArray(rawValue) ? rawValue : [rawValue, ""];
      if (tuple.length !== 2)
        continue;
      const sanitized = sanitizeCssDeclaration(rawProperty, tuple[0], tuple[1]);
      if (!sanitized)
        continue;
      output[sanitized.property] = Array.isArray(rawValue) ? [sanitized.value, sanitized.priority] : sanitized.value;
    }
    return output;
  }
  function sanitizeRrAttribute(name, value) {
    if (name === "rr_mediastate")
      return value === "played" || value === "paused" ? value : undefined;
    if (name === "rr_open_mode")
      return value === "modal" || value === "non-modal" ? value : undefined;
    if (name === "rr_mediamuted" || name === "rr_medialoop") {
      return typeof value === "boolean" ? value : undefined;
    }
    if (name === "rr_mediacurrenttime" || name === "rr_mediaplaybackrate" || name === "rr_mediavolume" || name === "rr_scrollleft" || name === "rr_scrolltop") {
      return finiteNumber(value);
    }
    if (name === "rr_width" || name === "rr_height") {
      return typeof value === "string" && /^[0-9]+(?:\.[0-9]+)?px$/.test(value) ? value : undefined;
    }
    return;
  }
  function sanitizeAttributes(value) {
    const source = asObject(value);
    if (!source)
      return;
    const output = {};
    for (const [rawName, rawValue] of Object.entries(source)) {
      const name = rawName.toLowerCase();
      if (name === "class") {
        const value3 = safePrintableString(rawValue, 2048)?.trim().split(/\s+/).slice(0, 64).join(" ");
        if (value3)
          output.class = value3;
        continue;
      }
      if (name === "style") {
        const value3 = sanitizeStyleAttribute(rawValue);
        if (value3 !== undefined)
          output.style = value3;
        continue;
      }
      if (name === "_csstext") {
        const value3 = sanitizeStylesheetCss(rawValue);
        if (value3 !== undefined)
          output._cssText = value3;
        continue;
      }
      if (name.startsWith("rr_")) {
        const value3 = sanitizeRrAttribute(name, rawValue);
        if (value3 !== undefined)
          output[rawName] = value3;
        continue;
      }
      if (SAFE_SVG_ATTRIBUTES.has(name)) {
        const value3 = safePrintableString(rawValue, 16 * 1024);
        if (value3 !== undefined && !FORBIDDEN_CSS.test(value3))
          output[rawName] = value3;
        continue;
      }
      if (!SAFE_REPLAY_ATTRIBUTES.has(name))
        continue;
      if (rawValue === null || typeof rawValue === "boolean" || typeof rawValue === "number") {
        output[rawName] = rawValue;
        continue;
      }
      const value2 = safePrintableString(rawValue);
      if (value2 !== undefined)
        output[rawName] = value2;
    }
    return output;
  }
  function sanitizeNode(value, depth = 0) {
    if (depth > 64)
      return;
    const source = asObject(value);
    const type = integer(source?.type);
    const id = integer(source?.id, 1);
    if (!source || type === undefined || id === undefined || type > 5)
      return;
    const output = { id, type };
    const rootId = integer(source.rootId, 1);
    if (rootId !== undefined)
      output.rootId = rootId;
    for (const name of ["isShadowHost", "isShadow"]) {
      if (typeof source[name] === "boolean")
        output[name] = source[name];
    }
    if (type === 0 || type === 2) {
      if (!Array.isArray(source.childNodes))
        return;
      const childNodes = [];
      for (const child of source.childNodes) {
        const sanitized = sanitizeNode(child, depth + 1);
        if (!sanitized)
          return;
        childNodes.push(sanitized);
      }
      output.childNodes = childNodes;
    }
    if (type === 0) {
      if (source.compatMode === "CSS1Compat" || source.compatMode === "BackCompat") {
        output.compatMode = source.compatMode;
      }
      return output;
    }
    if (type === 1) {
      const name = safePrintableString(source.name, 64);
      if (!name)
        return;
      output.name = name;
      output.publicId = "";
      output.systemId = "";
      return output;
    }
    if (type === 2) {
      const tagName = safePrintableString(source.tagName, 64);
      const attributes = sanitizeAttributes(source.attributes);
      if (!tagName || !attributes)
        return;
      output.tagName = tagName;
      output.attributes = attributes;
      for (const name of ["isSVG", "needBlock", "isCustom"]) {
        if (typeof source[name] === "boolean")
          output[name] = source[name];
      }
      return output;
    }
    const textContent = source.isStyle === true ? sanitizeStylesheetCss(source.textContent) : type === 3 ? readableText(source.textContent) : redactText(source.textContent);
    if (textContent === undefined)
      return;
    output.textContent = textContent;
    if (source.isStyle === true)
      output.isStyle = true;
    return output;
  }
  function sanitizeIndex(value) {
    const scalar = integer(value);
    if (scalar !== undefined)
      return scalar;
    if (!Array.isArray(value))
      return;
    const output = [];
    for (const item of value) {
      const parsed = integer(item);
      if (parsed === undefined)
        return;
      output.push(parsed);
    }
    return output;
  }
  function sanitizeMutationData(source) {
    if (!Array.isArray(source.texts) || !Array.isArray(source.attributes) || !Array.isArray(source.removes) || !Array.isArray(source.adds)) {
      return;
    }
    const texts = [];
    for (const entry of source.texts) {
      const item = asObject(entry);
      const id = integer(item?.id, 1);
      const readable = item?.value === null ? null : readableText(item?.value);
      const value = readable === null ? null : readable === undefined ? undefined : containsCssRequestSyntax(readable) ? REDACTED_TEXT : readable;
      if (!item || id === undefined || value === undefined)
        return;
      texts.push({ id, value });
    }
    const attributes = [];
    for (const entry of source.attributes) {
      const item = asObject(entry);
      const id = integer(item?.id, 1);
      const values = sanitizeAttributes(item?.attributes);
      if (!item || id === undefined || !values)
        return;
      attributes.push({ attributes: values, id });
    }
    const removes = [];
    for (const entry of source.removes) {
      const item = asObject(entry);
      const ids = item ? integerFields(item, ["parentId", "id"], 1) : undefined;
      if (!item || !ids)
        return;
      if (typeof item.isShadow === "boolean")
        ids.isShadow = item.isShadow;
      removes.push(ids);
    }
    const adds = [];
    for (const entry of source.adds) {
      const item = asObject(entry);
      const parentId = integer(item?.parentId, 1);
      const nextId = item?.nextId === null ? null : integer(item?.nextId, -1);
      const node = sanitizeNode(item?.node);
      if (!item || parentId === undefined || nextId === undefined || !node)
        return;
      const output2 = { nextId, node, parentId };
      if (item.previousId === null)
        output2.previousId = null;
      else {
        const previousId = integer(item.previousId, -1);
        if (previousId !== undefined)
          output2.previousId = previousId;
      }
      adds.push(output2);
    }
    const output = { adds, attributes, removes, source: 0, texts };
    if (typeof source.isAttachIframe === "boolean")
      output.isAttachIframe = source.isAttachIframe;
    return output;
  }
  function sanitizePositionData(source, incrementalSource) {
    if (!Array.isArray(source.positions))
      return;
    const positions = [];
    for (const entry of source.positions) {
      const item = asObject(entry);
      const values = item ? finiteFields(item, ["x", "y", "timeOffset"]) : undefined;
      const id = integer(item?.id, 1);
      if (!item || !values || id === undefined)
        return;
      positions.push({ ...values, id });
    }
    return { positions, source: incrementalSource };
  }
  function sanitizeStyleRuleData(source) {
    const output = { source: 8 };
    for (const name of ["id", "styleId"]) {
      const value = integer(source[name], 1);
      if (value !== undefined)
        output[name] = value;
    }
    if (source.removes !== undefined) {
      if (!Array.isArray(source.removes))
        return;
      const removes = [];
      for (const entry of source.removes) {
        const item = asObject(entry);
        const index = sanitizeIndex(item?.index);
        if (!item || index === undefined)
          return;
        removes.push({ index });
      }
      output.removes = removes;
    }
    if (source.adds !== undefined) {
      if (!Array.isArray(source.adds))
        return;
      const adds = [];
      for (const entry of source.adds) {
        const item = asObject(entry);
        const rule = sanitizeStylesheetCss(item?.rule);
        if (!item || rule === undefined)
          return;
        if (!rule)
          continue;
        const sanitized = { rule };
        const index = sanitizeIndex(item.index);
        if (index !== undefined)
          sanitized.index = index;
        adds.push(sanitized);
      }
      output.adds = adds;
    }
    for (const name of ["replace", "replaceSync"]) {
      if (source[name] === undefined)
        continue;
      const value = sanitizeStylesheetCss(source[name]);
      if (value === undefined)
        return;
      output[name] = value;
    }
    return output;
  }
  function sanitizeStyleDeclarationData(source) {
    const index = sanitizeIndex(source.index);
    if (index === undefined)
      return;
    const output = { index, source: 13 };
    for (const name of ["id", "styleId"]) {
      const value = integer(source[name], 1);
      if (value !== undefined)
        output[name] = value;
    }
    if (source.set !== undefined) {
      const set = asObject(source.set);
      if (!set)
        return;
      const value = set.value === null ? undefined : set.value;
      const sanitized = sanitizeCssDeclaration(set.property, value, set.priority ?? "");
      if (sanitized)
        output.set = sanitized;
    }
    if (source.remove !== undefined) {
      const remove = asObject(source.remove);
      const property = typeof remove?.property === "string" ? remove.property.toLowerCase() : "";
      if (SAFE_REPLAY_CSS_PROPERTIES.has(property))
        output.remove = { property };
    }
    return output;
  }
  function sanitizeAdoptedStyleData(source) {
    const id = integer(source.id, 1);
    if (id === undefined || !Array.isArray(source.styleIds))
      return;
    const styleIds = [];
    for (const value of source.styleIds) {
      const styleId = integer(value, 1);
      if (styleId === undefined)
        return;
      styleIds.push(styleId);
    }
    const output = { id, source: 15, styleIds };
    if (source.styles === undefined)
      return output;
    if (!Array.isArray(source.styles))
      return;
    const styles = [];
    for (const entry of source.styles) {
      const style = asObject(entry);
      const styleId = integer(style?.styleId, 1);
      if (!style || styleId === undefined || !Array.isArray(style.rules))
        return;
      const rules = [];
      for (const entry2 of style.rules) {
        const item = asObject(entry2);
        const rule = sanitizeStylesheetCss(item?.rule);
        if (!item || rule === undefined)
          return;
        if (!rule)
          continue;
        const sanitized = { rule };
        const index = sanitizeIndex(item.index);
        if (index !== undefined)
          sanitized.index = index;
        rules.push(sanitized);
      }
      styles.push({ rules, styleId });
    }
    output.styles = styles;
    return output;
  }
  function sanitizeIncrementalData(value) {
    const source = asObject(value);
    const incrementalSource = integer(source?.source);
    if (!source || incrementalSource === undefined || incrementalSource > 16)
      return;
    if (incrementalSource === 0)
      return sanitizeMutationData(source);
    if (incrementalSource === 1 || incrementalSource === 6 || incrementalSource === 12) {
      return sanitizePositionData(source, incrementalSource);
    }
    if (incrementalSource === 2) {
      const values = finiteFields(source, ["x", "y"]) ?? {};
      const identity = integerFields(source, ["type", "id"]);
      if (!identity)
        return;
      const output = { ...identity, ...values, source: 2 };
      const pointerType = integer(source.pointerType);
      if (pointerType !== undefined && pointerType <= 2)
        output.pointerType = pointerType;
      return output;
    }
    if (incrementalSource === 3) {
      const values = finiteFields(source, ["x", "y"]);
      const id = integer(source.id, 1);
      return values && id !== undefined ? { ...values, id, source: 3 } : undefined;
    }
    if (incrementalSource === 4) {
      const values = finiteFields(source, ["width", "height"]);
      return values ? { ...values, source: 4 } : undefined;
    }
    if (incrementalSource === 5) {
      const id = integer(source.id, 1);
      const text = redactText(source.text);
      if (id === undefined || text === undefined || typeof source.isChecked !== "boolean") {
        return;
      }
      const output = {
        id,
        isChecked: source.isChecked,
        source: 5,
        text
      };
      if (typeof source.userTriggered === "boolean")
        output.userTriggered = source.userTriggered;
      return output;
    }
    if (incrementalSource === 7) {
      const identity = integerFields(source, ["type", "id"]);
      if (!identity)
        return;
      const output = { ...identity, source: 7 };
      for (const name of ["currentTime", "volume", "playbackRate"]) {
        const value2 = finiteNumber(source[name]);
        if (value2 !== undefined)
          output[name] = value2;
      }
      for (const name of ["muted", "loop"]) {
        if (typeof source[name] === "boolean")
          output[name] = source[name];
      }
      return output;
    }
    if (incrementalSource === 8)
      return sanitizeStyleRuleData(source);
    if (incrementalSource === 9 || incrementalSource === 10 || incrementalSource === 11) {
      return;
    }
    if (incrementalSource === 13)
      return sanitizeStyleDeclarationData(source);
    if (incrementalSource === 14) {
      if (!Array.isArray(source.ranges))
        return;
      const ranges = [];
      for (const entry of source.ranges) {
        const range = asObject(entry);
        const values = range ? integerFields(range, ["start", "startOffset", "end", "endOffset"]) : undefined;
        if (!values)
          return;
        ranges.push(values);
      }
      return { ranges, source: 14 };
    }
    if (incrementalSource === 15)
      return sanitizeAdoptedStyleData(source);
    if (incrementalSource === 16) {
      const define2 = asObject(source.define);
      const name = safePrintableString(define2?.name, 64);
      return name && /^[a-z][a-z0-9._-]*-[a-z0-9._-]*$/.test(name) ? { define: { name }, source: 16 } : undefined;
    }
    return;
  }
  function sanitizeReplayEvent(event) {
    const source = asObject(event);
    const type = integer(source?.type);
    const timestamp = finiteNumber(source?.timestamp);
    if (!source || type === undefined || type > 7 || timestamp === undefined)
      return null;
    let data;
    if (type === 0 || type === 1) {
      data = {};
    } else if (type === 2) {
      const fullSnapshot = asObject(source.data);
      const initialOffset = asObject(fullSnapshot?.initialOffset);
      const offset = initialOffset ? finiteFields(initialOffset, ["top", "left"]) : undefined;
      const node = sanitizeNode(fullSnapshot?.node);
      if (offset && node)
        data = { initialOffset: offset, node };
    } else if (type === 3) {
      data = sanitizeIncrementalData(source.data);
    } else if (type === 4) {
      const meta = asObject(source.data);
      const dimensions = meta ? finiteFields(meta, ["width", "height"]) : undefined;
      if (dimensions)
        data = { ...dimensions, href: "about:blank" };
    } else {
      return null;
    }
    if (!data)
      return null;
    const output = { data, timestamp, type };
    if (source.delay !== undefined) {
      const delay = finiteNumber(source.delay);
      if (delay === undefined)
        return null;
      output.delay = delay;
    }
    return output;
  }

  // src/replay.ts
  var FARO_REPLAY_EVENT = "faro.session_recording.event";
  var FARO_REPLAY_PAUSED_EVENT = "faro.session_recording.paused";
  var FARO_REPLAY_STARTED_EVENT = "faro.session_recording.started";
  var FARO_REPLAY_RESUMED_EVENT = "faro.session_recording.resumed";
  var REPLAY_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
  function eventPayload(item) {
    if (item.type !== TransportItemType.EVENT)
      return;
    return item.payload;
  }
  function isReplayEvent(item) {
    const payload = eventPayload(item);
    if (payload?.name !== FARO_REPLAY_EVENT)
      return false;
    const serialized = payload.attributes?.event;
    if (!serialized)
      return false;
    try {
      const event = JSON.parse(serialized);
      return typeof event === "object" && event !== null && typeof event.timestamp === "number";
    } catch {
      return false;
    }
  }
  function isReplayReservedEvent(item) {
    const name = eventPayload(item)?.name;
    return typeof name === "string" && name.startsWith("faro.session_recording.");
  }
  function parseReplayItem(item) {
    if (!isReplayEvent(item)) {
      throw new TypeError("invalid Faro Replay event");
    }
    const payload = item.payload;
    const application = item.meta.app?.name?.trim();
    const sessionId = item.meta.session?.id?.trim();
    const userId = item.meta.user?.id?.trim();
    if (!application || !sessionId) {
      throw new TypeError("Replay requires non-empty app.name and session.id");
    }
    if (userId && !REPLAY_ID_PATTERN.test(userId)) {
      throw new TypeError("Replay user.id must be a safe pseudonymous identifier");
    }
    return {
      application,
      environment: item.meta.app?.environment,
      event: normalizeCanonical(JSON.parse(payload.attributes.event)),
      pageId: item.meta.page?.id,
      release: item.meta.app?.release ?? item.meta.app?.version,
      sessionId,
      userId: userId ?? ""
    };
  }
  var utf8Encoder = new TextEncoder;
  function normalizeUnicodeScalars(value) {
    const parts = [];
    let start = 0;
    for (let index = 0;index < value.length; index += 1) {
      const unit = value.charCodeAt(index);
      if (unit < 55296 || unit > 57343)
        continue;
      if (unit <= 56319) {
        const next = value.charCodeAt(index + 1);
        if (next >= 56320 && next <= 57343) {
          index += 1;
          continue;
        }
      }
      if (index > start)
        parts.push(value.slice(start, index));
      parts.push("�");
      start = index + 1;
    }
    if (parts.length === 0)
      return value;
    if (start < value.length)
      parts.push(value.slice(start));
    return parts.join("");
  }
  function compareUtf8(left, right) {
    const leftBytes = utf8Encoder.encode(left);
    const rightBytes = utf8Encoder.encode(right);
    const length = Math.min(leftBytes.length, rightBytes.length);
    for (let index = 0;index < length; index += 1) {
      const difference = leftBytes[index] - rightBytes[index];
      if (difference !== 0)
        return difference;
    }
    return leftBytes.length - rightBytes.length;
  }
  function encodeJsonString(value) {
    return JSON.stringify(normalizeUnicodeScalars(value)).replaceAll("\u2028", "\\u2028").replaceAll("\u2029", "\\u2029");
  }
  function normalizeCanonical(value) {
    if (typeof value === "string")
      return normalizeUnicodeScalars(value);
    if (Array.isArray(value)) {
      return value.map((entry) => normalizeCanonical(entry));
    }
    if (value && typeof value === "object") {
      const entries = Object.entries(value).filter(([, entry]) => entry !== undefined).map(([key, entry]) => [
        normalizeUnicodeScalars(key),
        normalizeCanonical(entry)
      ]).sort(([left], [right]) => compareUtf8(left, right));
      return Object.fromEntries(entries);
    }
    return value;
  }
  function canonicalStringify(value) {
    const normalized = normalizeCanonical(value);
    if (normalized === null)
      return "null";
    if (typeof normalized === "string")
      return encodeJsonString(normalized);
    if (typeof normalized === "number" || typeof normalized === "boolean") {
      return JSON.stringify(normalized);
    }
    if (Array.isArray(normalized)) {
      return `[${normalized.map((entry) => canonicalStringify(entry)).join(",")}]`;
    }
    if (typeof normalized === "object") {
      const entries = Object.entries(normalized).sort(([left], [right]) => compareUtf8(left, right));
      return `{${entries.map(([key, entry]) => `${encodeJsonString(key)}:${canonicalStringify(entry)}`).join(",")}}`;
    }
    throw new TypeError("canonical JSON only supports JSON values");
  }
  function encodeReplayEnvelope(material, checksum) {
    const entries = [
      ["schema_version", material.schema_version],
      ["application", material.application],
      ["environment", material.environment],
      ["release", material.release],
      ["session_id", material.session_id],
      ...material.user_id ? [["user_id", material.user_id]] : [],
      ["page_id", material.page_id],
      ["recording_id", material.recording_id],
      ["segment_id", material.segment_id],
      ["sequence", material.sequence],
      ["started_at", material.started_at],
      ["ended_at", material.ended_at],
      ["has_full_snapshot", material.has_full_snapshot],
      ["event_count", material.event_count],
      ...checksum ? [["checksum_sha256", checksum]] : [],
      ["events", material.events]
    ];
    return `{${entries.map(([key, value]) => `${encodeJsonString(key)}:${canonicalStringify(value)}`).join(",")}}`;
  }
  async function sha256Hex(value) {
    if (!globalThis.crypto?.subtle) {
      throw new Error("Web Crypto is required by bklite-rum-sdk");
    }
    const digest = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
    return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  }
  async function gzip(value) {
    if (typeof CompressionStream === "undefined") {
      throw new Error("CompressionStream is required for Faro Replay");
    }
    const bytes = new TextEncoder().encode(value);
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(bytes);
        controller.close();
      }
    }).pipeThrough(new CompressionStream("gzip"));
    return new Uint8Array(await new Response(stream).arrayBuffer());
  }
  function chunkReplayItems(items, firstSequence, maxEvents, targetDurationMs, targetUncompressedBytes, maxEventBytes, maxUncompressedBytes, onDrop) {
    const chunks = [];
    const accepted = [];
    for (const item of items) {
      const bytes = new TextEncoder().encode(canonicalStringify(item.event)).byteLength;
      if (bytes > maxEventBytes || bytes > maxUncompressedBytes) {
        onDrop?.("event-too-large");
        return;
      }
      accepted.push({ bytes, item });
    }
    let current = [];
    let currentBytes = 0;
    let currentStartMs = 0;
    let startIndex = 0;
    const startsWithCheckpoint = accepted[0]?.item.event.type === 4 && accepted[1]?.item.event.type === 2;
    if (firstSequence === 0 && !startsWithCheckpoint)
      return [];
    if (startsWithCheckpoint) {
      const checkpoint = accepted.slice(0, 2);
      current = checkpoint.map(({ item }) => item);
      currentBytes = checkpoint.reduce((total, { bytes }) => total + bytes, 0);
      if (currentBytes > maxUncompressedBytes) {
        onDrop?.("segment-too-large");
        return;
      }
      currentStartMs = Number(current[0]?.event.timestamp ?? 0);
      startIndex = 2;
    }
    for (let index = startIndex;index < accepted.length; index += 1) {
      const { bytes: eventBytes, item } = accepted[index];
      if (item.event.type === 4) {
        const fullSnapshot = accepted[index + 1];
        if (fullSnapshot?.item.event.type !== 2)
          return [];
        if (current.length > 0)
          chunks.push(current);
        current = [item, fullSnapshot.item];
        currentBytes = eventBytes + fullSnapshot.bytes;
        if (currentBytes > maxUncompressedBytes) {
          onDrop?.("segment-too-large");
          return;
        }
        currentStartMs = Number(item.event.timestamp);
        index += 1;
        continue;
      }
      if (item.event.type === 2)
        return [];
      const eventTimestamp = Number(item.event.timestamp);
      if (current.length > 0 && (current.length >= maxEvents || currentBytes + eventBytes > targetUncompressedBytes || eventTimestamp - currentStartMs >= targetDurationMs)) {
        chunks.push(current);
        current = [];
        currentBytes = 0;
      }
      if (current.length === 0)
        currentStartMs = eventTimestamp;
      current.push(item);
      currentBytes += eventBytes;
    }
    if (current.length > 0)
      chunks.push(current);
    return chunks;
  }
  async function buildReplaySegments(items, options) {
    if (items.length === 0)
      return [];
    if (!Number.isInteger(options.maxEvents) || options.maxEvents < 1) {
      throw new RangeError("maxEvents must be a positive integer");
    }
    const targetDurationMs = options.targetDurationMs ?? 5000;
    const maxCompressedBytes = options.maxCompressedBytes ?? 1024 * 1024;
    const maxEventBytes = options.maxEventBytes ?? 4 * 1024 * 1024;
    const maxUncompressedBytes = options.maxUncompressedBytes ?? 4 * 1024 * 1024;
    for (const [name, value] of Object.entries({
      targetDurationMs,
      targetUncompressedBytes: options.targetUncompressedBytes,
      maxCompressedBytes,
      maxEventBytes,
      maxUncompressedBytes
    })) {
      if (!Number.isInteger(value) || value < 1) {
        throw new RangeError(`${name} must be a positive integer`);
      }
    }
    if (options.targetUncompressedBytes > maxUncompressedBytes) {
      throw new RangeError("targetUncompressedBytes cannot exceed maxUncompressedBytes");
    }
    const parsed = items.map(parseReplayItem);
    const first = parsed[0];
    if (parsed.some((item) => item.application !== first.application || item.sessionId !== first.sessionId || item.userId !== first.userId)) {
      throw new TypeError("Replay segment cannot mix applications, sessions, or users");
    }
    const chunks = chunkReplayItems(parsed, options.firstSequence, options.maxEvents, targetDurationMs, options.targetUncompressedBytes, maxEventBytes, maxUncompressedBytes, options.onDrop);
    if (!chunks)
      return [];
    const segments = [];
    for (let index = 0;index < chunks.length; index += 1) {
      const chunk = chunks[index];
      const sequence = options.firstSequence + segments.length;
      const events = chunk.map((item) => item.event);
      const startMs = Math.min(...events.map((event) => Number(event.timestamp)));
      const endMs = Math.max(...events.map((event) => Number(event.timestamp)));
      const hasFullSnapshot = events.some((event) => event.type === 2);
      const eventDigest = await sha256Hex(canonicalStringify(events));
      const segmentId = await sha256Hex(canonicalStringify({
        application: first.application,
        eventDigest,
        recordingId: options.recordingId,
        sequence,
        sessionId: first.sessionId,
        userId: first.userId
      }));
      const material = {
        schema_version: 1,
        application: first.application,
        environment: first.environment ?? "",
        release: first.release ?? "",
        session_id: first.sessionId,
        user_id: first.userId,
        page_id: first.pageId?.trim() || options.recordingId,
        recording_id: options.recordingId,
        segment_id: segmentId,
        sequence,
        started_at: new Date(startMs).toISOString(),
        ended_at: new Date(endMs).toISOString(),
        has_full_snapshot: hasFullSnapshot,
        event_count: events.length,
        events
      };
      const checksum = await sha256Hex(encodeReplayEnvelope(material));
      const envelope = encodeReplayEnvelope(material, checksum);
      const uncompressedBytes = new TextEncoder().encode(envelope).byteLength;
      if (uncompressedBytes > maxUncompressedBytes) {
        options.onDrop?.("segment-too-large");
        return [];
      }
      const body = await gzip(envelope);
      if (body.byteLength > maxCompressedBytes) {
        options.onDrop?.("segment-too-large");
        return [];
      }
      segments.push({
        application: first.application,
        body,
        checksum,
        compressedBytes: body.byteLength,
        endMs,
        eventCount: events.length,
        hasFullSnapshot,
        recordingId: options.recordingId,
        segmentId,
        sequence,
        sessionId: first.sessionId,
        startMs,
        uncompressedBytes
      });
    }
    return segments;
  }

  // src/batches.ts
  function sanitizeMeta(meta) {
    let page = meta.page;
    if (page?.url) {
      try {
        const url = new URL(page.url);
        page = { ...page, url: `${url.origin}${url.pathname}` };
      } catch {
        page = { ...page, url: undefined };
      }
    }
    const userId = meta.user?.id?.trim();
    return {
      ...meta,
      page,
      user: userId ? { id: userId } : undefined
    };
  }
  function classifyItems(items) {
    const result = {
      collect: [],
      ordinary: [],
      replay: [],
      traces: []
    };
    for (const item of items) {
      if (isReplayReservedEvent(item)) {
        result.replay.push(item);
      } else if (item.type === TransportItemType.TRACE) {
        result.collect.push(item);
        result.traces.push(item);
      } else {
        result.collect.push(item);
        result.ordinary.push(item);
      }
    }
    return result;
  }
  function createCollectBatch(items) {
    if (items.length === 0) {
      throw new TypeError("collect batch cannot be empty");
    }
    const sanitized = items.map((item) => ({
      ...item,
      meta: sanitizeMeta(item.meta)
    }));
    const traces = sanitized.filter((item) => item.type === TransportItemType.TRACE);
    const ordinary = sanitized.filter((item) => item.type !== TransportItemType.TRACE);
    const body = getTransportBody(ordinary.length > 0 ? ordinary : traces.slice(0, 1));
    if (traces.length > 0) {
      body.traces = {
        resourceSpans: traces.flatMap((item) => item.payload.resourceSpans ?? [])
      };
    }
    return { body };
  }

  // src/queue.ts
  class TransportQueueFullError extends Error {
    constructor() {
      super("Faro transport queue is full");
      this.name = "TransportQueueFullError";
    }
  }

  class TransportQueueDroppedError extends Error {
    constructor() {
      super("Faro transport queue dropped replaceable work");
      this.name = "TransportQueueDroppedError";
    }
  }

  class BoundedConcurrentQueue {
    limits;
    onDrop;
    inFlight = 0;
    queuedBytes = 0;
    queuedItems = 0;
    waiting = [];
    constructor(limits, onDrop) {
      this.limits = limits;
      this.onDrop = onDrop;
      for (const [name, value] of Object.entries(limits)) {
        if (!Number.isInteger(value) || value < 1) {
          throw new RangeError(`${name} must be a positive integer`);
        }
      }
    }
    enqueue(task, weight) {
      if (!Number.isInteger(weight.items) || weight.items < 1 || !Number.isInteger(weight.bytes) || weight.bytes < 0) {
        return Promise.reject(new RangeError("queue weight is invalid"));
      }
      if (this.inFlight >= this.limits.maxInFlight) {
        if (!this.makeRoom(weight)) {
          return Promise.reject(new TransportQueueFullError);
        }
      }
      const result = new Promise((resolve, reject) => {
        const entry = {
          ...weight,
          droppable: weight.droppable ?? false,
          reject,
          resolve,
          task
        };
        if (this.inFlight < this.limits.maxInFlight) {
          this.start(entry);
          return;
        }
        this.waiting.push(entry);
        this.queuedItems += entry.items;
        this.queuedBytes += entry.bytes;
      });
      return result;
    }
    snapshot() {
      return {
        inFlight: this.inFlight,
        queuedBytes: this.queuedBytes,
        queuedItems: this.queuedItems
      };
    }
    start(entry) {
      this.inFlight += 1;
      let running;
      try {
        running = Promise.resolve(entry.task());
      } catch (error) {
        running = Promise.reject(error);
      }
      running.then(entry.resolve, entry.reject).finally(() => {
        this.inFlight -= 1;
        this.pump();
      });
    }
    makeRoom(weight) {
      const overLimit = () => this.queuedItems + weight.items > this.limits.maxQueuedItems || this.queuedBytes + weight.bytes > this.limits.maxQueuedBytes;
      while (overLimit()) {
        const index = this.waiting.findIndex((entry) => entry.droppable);
        if (index < 0)
          return false;
        const [dropped] = this.waiting.splice(index, 1);
        if (!dropped)
          return false;
        this.queuedItems -= dropped.items;
        this.queuedBytes -= dropped.bytes;
        dropped.reject(new TransportQueueDroppedError);
        this.onDrop?.();
      }
      return true;
    }
    pump() {
      while (this.inFlight < this.limits.maxInFlight) {
        const entry = this.waiting.shift();
        if (!entry)
          return;
        this.queuedItems -= entry.items;
        this.queuedBytes -= entry.bytes;
        this.start(entry);
      }
    }
  }

  // src/retry.ts
  class TransportRequestError extends Error {
    retryable;
    status;
    constructor(message, retryable, status, options) {
      super(message, options);
      this.retryable = retryable;
      this.status = status;
      this.name = "TransportRequestError";
    }
  }
  var defaultSleep = (delayMs) => new Promise((resolve) => {
    setTimeout(resolve, delayMs);
  });
  function retryAfterMs(response, now = Date.now()) {
    const value = response.headers.get("retry-after");
    if (!value)
      return;
    const seconds = Number(value);
    if (Number.isFinite(seconds) && seconds >= 0) {
      return seconds * 1000;
    }
    const timestamp = Date.parse(value);
    if (Number.isFinite(timestamp)) {
      return Math.max(0, timestamp - now);
    }
    return;
  }
  async function drainResponse(response) {
    const reader = response.body?.getReader();
    if (!reader)
      return;
    try {
      for (;; ) {
        const { done } = await reader.read();
        if (done)
          return;
      }
    } finally {
      reader.releaseLock();
    }
  }
  var MAX_TIMER_DELAY_MS = 2147483647;
  async function requestWithRetry(url, request, options = {}) {
    const fetcher = options.fetch ?? globalThis.fetch;
    if (!fetcher) {
      throw new TransportRequestError("fetch is not available", false);
    }
    const maxRetries = Math.max(0, options.maxRetries ?? 3);
    const baseDelayMs = Math.max(0, options.baseDelayMs ?? 500);
    const maxDelayMs = Math.max(baseDelayMs, options.maxDelayMs ?? 30000);
    const sleep = options.sleep ?? defaultSleep;
    const random = options.random ?? Math.random;
    const retryableStatuses = new Set([408, 429, 502, 503, 504]);
    let lastError;
    let currentRequest = request;
    for (let attempt = 0;attempt <= maxRetries; attempt += 1) {
      let response;
      try {
        response = await fetcher(url, currentRequest);
        if (response.status === 202) {
          await drainResponse(response);
          return response;
        }
      } catch (error) {
        lastError = error;
        if (currentRequest.keepalive === true) {
          currentRequest = { ...currentRequest, keepalive: false };
        }
        if (attempt < maxRetries) {
          const exponential2 = Math.min(maxDelayMs, baseDelayMs * 2 ** attempt);
          await sleep(Math.round(exponential2 * (0.5 + random() * 0.5)));
          continue;
        }
        break;
      }
      const retryable = retryableStatuses.has(response.status);
      if (!retryable || attempt >= maxRetries) {
        response.body?.cancel();
        throw new TransportRequestError(`Core RUM transport request failed with status ${response.status}`, retryable, response.status);
      }
      const delay = retryAfterMs(response);
      response.body?.cancel();
      const exponential = Math.min(maxDelayMs, baseDelayMs * 2 ** attempt);
      await sleep(delay === undefined ? Math.round(exponential * (0.5 + random() * 0.5)) : Math.min(delay, MAX_TIMER_DELAY_MS));
    }
    throw new TransportRequestError("Core RUM transport request failed", true, undefined, {
      cause: lastError
    });
  }

  // src/transport.ts
  var MAX_KEEPALIVE_BYTES = 60000;
  var MAX_KEEPALIVE_REQUESTS2 = 9;
  var MAX_REPLAY_META_BYTES = 16 * 1024;
  var MAX_COLLECT_BODY_BYTES = 1e6;
  var MEBIBYTE = 1024 * 1024;
  var ORDINARY_QUEUE_MAX_BYTES = 2 * MEBIBYTE;
  var ORDINARY_QUEUE_MAX_ITEMS = 1000;
  var REPLAY_QUEUE_MAX_BYTES = 8 * MEBIBYTE;
  var REPLAY_BOUNDARY_MAX_BYTES = 4 * MEBIBYTE + MAX_REPLAY_META_BYTES;
  var REPLAY_TARGET_BYTES = 256 * 1024;
  var REPLAY_TARGET_DURATION_MS = 5000;
  var REPLAY_MAX_SEGMENT_EVENTS = 1000;
  var TRANSPORT_VERSION = "0.1.0";
  var APPLICATION_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$/;
  var PROTOCOL_HEADERS = {
    apiKey: "X-API-Key",
    application: "X-RUM-Application",
    batchId: "X-RUM-Batch-Id",
    sessionId: "X-Faro-Session-Id"
  };
  var pendingKeepaliveBytes = 0;
  var pendingKeepaliveRequests2 = 0;
  var replayLifecycleFlushers = new Set;
  var replayLifecycleListenersInstalled = false;
  function installReplayLifecycleListeners() {
    if (replayLifecycleListenersInstalled || typeof window === "undefined")
      return;
    replayLifecycleListenersInstalled = true;
    const flushAll = () => {
      queueMicrotask(() => {
        for (const flush of [...replayLifecycleFlushers])
          flush();
      });
    };
    window.addEventListener("pagehide", flushAll);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden")
        flushAll();
    });
  }
  function defaultRandomId() {
    if (globalThis.crypto?.randomUUID)
      return globalThis.crypto.randomUUID();
    if (!globalThis.crypto?.getRandomValues) {
      throw new Error("Web Crypto is required by bklite-rum-sdk");
    }
    const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
    return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  }
  function byteLength(body) {
    if (typeof body === "string")
      return new TextEncoder().encode(body).byteLength;
    if (body instanceof Blob)
      return body.size;
    if (body instanceof ArrayBuffer)
      return body.byteLength;
    if (ArrayBuffer.isView(body))
      return body.byteLength;
    return MAX_KEEPALIVE_BYTES + 1;
  }
  function isDroppableOrdinaryItem(item) {
    if (item.type === TransportItemType.EXCEPTION)
      return false;
    if (item.type === TransportItemType.LOG) {
      const level = item.payload.level;
      return level !== LogLevel.ERROR;
    }
    return true;
  }
  function replayScope(item) {
    const sessionId = item.meta.session?.id?.trim();
    const application = item.meta.app?.name?.trim();
    if (!sessionId || !application)
      return;
    return { application, sessionId, userIdentity: replayUserIdentity(item) };
  }
  var replayItemInfoCache = new WeakMap;
  function replayItemInfo(item) {
    const cached = replayItemInfoCache.get(item);
    if (cached)
      return cached;
    const info = { bytes: 0 };
    const serialized = item.payload.attributes?.event ?? "";
    info.bytes = new TextEncoder().encode(serialized).byteLength;
    if (serialized) {
      try {
        const parsed = JSON.parse(serialized);
        if (Number.isInteger(parsed.type))
          info.type = parsed.type;
        if (typeof parsed.timestamp === "number" && Number.isFinite(parsed.timestamp)) {
          info.timestamp = parsed.timestamp;
        }
      } catch {}
    }
    replayItemInfoCache.set(item, info);
    return info;
  }
  function withReplayItemInfo(item, info) {
    replayItemInfoCache.set(item, info);
    return item;
  }
  function replayUserIdentity(item) {
    const userId = item.meta.user?.id?.trim();
    return userId ? `user:${userId}` : "anonymous";
  }
  function replayEventType(item) {
    return replayItemInfo(item).type;
  }
  function replayItemBytes(item) {
    return replayItemInfo(item).bytes;
  }
  function replayEventTimestamp(item) {
    return replayItemInfo(item).timestamp;
  }
  function scopesMatch(left, right) {
    return left !== undefined && right !== undefined && left.application === right.application && left.sessionId === right.sessionId && left.userIdentity === right.userIdentity;
  }
  function sameSessionAndApplication(left, right) {
    return left !== undefined && right !== undefined && left.application === right.application && left.sessionId === right.sessionId;
  }
  function eventName(item) {
    if (item.type !== TransportItemType.EVENT)
      return;
    return item.payload.name;
  }
  function cloneReplayMetaForSnapshot(metaItem, snapshotItem) {
    const clone = structuredClone(metaItem);
    const snapshotPayload = snapshotItem.payload;
    const payload = clone.payload;
    const serialized = payload.attributes?.event;
    if (!serialized)
      return clone;
    const event = JSON.parse(serialized);
    const snapshotSerialized = snapshotItem.payload.attributes?.event;
    if (snapshotSerialized) {
      const snapshotEvent = JSON.parse(snapshotSerialized);
      event.timestamp = snapshotEvent.timestamp;
    }
    clone.meta = structuredClone(snapshotItem.meta);
    payload.timestamp = snapshotPayload.timestamp;
    payload.attributes = { ...payload.attributes, event: JSON.stringify(event) };
    return clone;
  }
  function reserveKeepalive(bytes) {
    if (bytes > MAX_KEEPALIVE_BYTES || pendingKeepaliveBytes + bytes > MAX_KEEPALIVE_BYTES || pendingKeepaliveRequests2 >= MAX_KEEPALIVE_REQUESTS2) {
      return { keepalive: false, release: () => {} };
    }
    pendingKeepaliveBytes += bytes;
    pendingKeepaliveRequests2 += 1;
    let released = false;
    return {
      keepalive: true,
      release: () => {
        if (released)
          return;
        released = true;
        pendingKeepaliveBytes = Math.max(0, pendingKeepaliveBytes - bytes);
        pendingKeepaliveRequests2 = Math.max(0, pendingKeepaliveRequests2 - 1);
      }
    };
  }
  function requireApplication(items) {
    const applications = new Set(items.map((item) => {
      const application = item.meta.app?.name?.trim() ?? "";
      if (!APPLICATION_PATTERN.test(application)) {
        throw new TypeError("Faro app.name must be a 1-80 character application identifier");
      }
      return application;
    }));
    if (applications.size !== 1) {
      throw new TypeError("one transport request cannot mix applications");
    }
    return applications.values().next().value;
  }

  class CoreRumTransport extends BaseTransport {
    options;
    name = "bklite-rum-sdk";
    version = TRANSPORT_VERSION;
    ordinaryQueue;
    replayQueue;
    recordings = new Map;
    randomId;
    retryOptions;
    lastReplayMeta;
    lastActivatedReplay;
    pendingReplayBoundary;
    replayTimerFlush;
    restartExpected;
    flushOnPageLifecycle = () => {
      this.settle("replay", this.flushActiveReplay(true));
    };
    constructor(options) {
      super();
      this.options = options;
      if (!options.apiKey.trim())
        throw new TypeError("apiKey is required");
      if (!options.collectUrl.trim())
        throw new TypeError("collectUrl is required");
      if (!options.replayUrl.trim())
        throw new TypeError("replayUrl is required");
      const testRuntime = options;
      this.randomId = testRuntime.randomId ?? defaultRandomId;
      this.retryOptions = {
        fetch: testRuntime.fetch,
        sleep: testRuntime.sleep,
        random: testRuntime.random,
        maxRetries: testRuntime.maxRetries,
        baseDelayMs: testRuntime.baseDelayMs,
        maxDelayMs: testRuntime.maxDelayMs
      };
      installReplayLifecycleListeners();
      this.ordinaryQueue = new BoundedConcurrentQueue({
        maxInFlight: 2,
        maxQueuedBytes: ORDINARY_QUEUE_MAX_BYTES,
        maxQueuedItems: ORDINARY_QUEUE_MAX_ITEMS
      }, () => this.debug("ordinary", "queue-drop"));
      this.replayQueue = this.createReplayQueue();
    }
    getIgnoreUrls() {
      return [this.options.collectUrl, this.options.replayUrl];
    }
    isBatched() {
      return true;
    }
    async send(input) {
      const items = Array.isArray(input) ? input : [input];
      if (items.length === 0)
        return;
      try {
        requireApplication(items);
      } catch {
        this.debug("ordinary", "invalid-item");
        return;
      }
      const { collect, replay, traces } = classifyItems(items);
      const operations = [];
      if (collect.length > 0) {
        const channel = traces.length === collect.length ? "traces" : "ordinary";
        operations.push(this.settle(channel, this.enqueueCollect(collect, this.ordinaryQueue, channel)));
      }
      if (this.options.replay?.enabled === true) {
        operations.push(...this.prepareReplayOperations(replay).map((operation) => this.settle("replay", operation)));
      }
      await Promise.all(operations);
    }
    async flushReplay() {
      await Promise.all([
        this.replayTimerFlush ?? Promise.resolve(),
        this.settle("replay", this.flushActiveReplay())
      ]);
    }
    prepareReplayOperations(items) {
      const operations = [];
      let replay = [];
      const flush = (lifecycle = {}) => {
        const operation = this.prepareReplayOperation(replay, lifecycle);
        if (operation)
          operations.push(operation);
        replay = [];
      };
      for (const item of items) {
        if (isReplayEvent(item)) {
          const currentScope = replay[0] ? replayScope(replay[0]) : undefined;
          const nextScope = replayScope(item);
          if (replay.length > 0 && !scopesMatch(currentScope, nextScope))
            flush();
          replay.push(item);
          continue;
        }
        const name = eventName(item);
        if (name === FARO_REPLAY_PAUSED_EVENT) {
          flush();
          const operation = this.flushActiveReplay();
          operations.push(operation);
          this.observeReplayLifecycle([item]);
        } else if (name === FARO_REPLAY_STARTED_EVENT || name === FARO_REPLAY_RESUMED_EVENT) {
          const lifecycle = this.observeReplayLifecycle([item]);
          flush(lifecycle);
        } else {
          this.debug("replay", "invalid-item");
        }
      }
      flush();
      return operations;
    }
    observeReplayLifecycle(items) {
      let boundary;
      let boundaryName;
      for (const item of items) {
        const name = eventName(item);
        if (name !== FARO_REPLAY_PAUSED_EVENT && name !== FARO_REPLAY_STARTED_EVENT && name !== FARO_REPLAY_RESUMED_EVENT) {
          continue;
        }
        const scope = replayScope(item);
        if (!scope)
          continue;
        if (name === FARO_REPLAY_PAUSED_EVENT) {
          this.restartExpected = scope;
          this.pendingReplayBoundary = undefined;
          continue;
        }
        boundary = scope;
        boundaryName = name;
      }
      return { boundary, boundaryName };
    }
    prepareReplayOperation(replay, lifecycle) {
      const incomingScope = replay[0] ? replayScope(replay[0]) : undefined;
      if (incomingScope && sameSessionAndApplication(this.restartExpected, incomingScope) && !scopesMatch(this.restartExpected, incomingScope)) {
        this.restartExpected = incomingScope;
      }
      const pendingMatches = scopesMatch(this.pendingReplayBoundary, incomingScope);
      const restartMatches = scopesMatch(this.restartExpected, incomingScope);
      const boundaryMatches = scopesMatch(lifecycle.boundary, incomingScope);
      const isResume = lifecycle.boundaryName === FARO_REPLAY_RESUMED_EVENT;
      const forceBoundary = lifecycle.boundary !== undefined && (isResume || lifecycle.boundaryName === FARO_REPLAY_STARTED_EVENT) && (boundaryMatches || scopesMatch(this.pendingReplayBoundary, lifecycle.boundary) || scopesMatch(this.restartExpected, lifecycle.boundary));
      if (replay.length > 0 && incomingScope) {
        if (forceBoundary) {
          const combined = this.takePendingReplayBoundary(incomingScope, replay);
          this.restartExpected = undefined;
          return this.enqueueReplay(combined, true);
        }
        if (pendingMatches || restartMatches) {
          this.stageReplayBoundary(incomingScope, replay);
          return;
        }
        return this.enqueueReplay(replay);
      }
      if (lifecycle.boundary && (isResume || scopesMatch(this.pendingReplayBoundary, lifecycle.boundary) || scopesMatch(this.restartExpected, lifecycle.boundary))) {
        if (isResume && !scopesMatch(this.pendingReplayBoundary, lifecycle.boundary) && !scopesMatch(this.restartExpected, lifecycle.boundary) && scopesMatch(this.lastActivatedReplay, lifecycle.boundary)) {
          this.lastActivatedReplay = undefined;
          this.restartExpected = undefined;
          return;
        }
        const pending = this.takePendingReplayBoundary(lifecycle.boundary, []);
        this.restartExpected = undefined;
        return this.enqueueReplay(pending, true, lifecycle.boundary);
      }
      return;
    }
    stageReplayBoundary(scope, items) {
      const startsNewBoundary = items.some((item) => replayEventType(item) === 4);
      if (startsNewBoundary || !scopesMatch(this.pendingReplayBoundary, scope)) {
        this.pendingReplayBoundary = { ...scope, bytes: 0, items: [] };
      }
      const pending = this.pendingReplayBoundary;
      if (!pending)
        return;
      const bytes = items.reduce((total, item) => total + replayItemBytes(item), 0);
      if (pending.bytes + bytes > REPLAY_BOUNDARY_MAX_BYTES) {
        this.pendingReplayBoundary = undefined;
        this.debug("replay", "segment-too-large");
        return;
      }
      pending.bytes += bytes;
      pending.items.push(...items.map((item) => withReplayItemInfo(structuredClone(item), replayItemInfo(item))));
      this.rememberReplayMeta(items);
    }
    takePendingReplayBoundary(scope, incoming) {
      let items = incoming;
      if (scopesMatch(this.pendingReplayBoundary, scope)) {
        items = [...this.pendingReplayBoundary.items, ...incoming];
      }
      this.pendingReplayBoundary = undefined;
      return items;
    }
    enqueueCollect(items, queue, channel) {
      const chunks = [];
      let current = [];
      for (const item of items) {
        const candidate = [...current, item];
        let candidateBody;
        try {
          candidateBody = JSON.stringify(createCollectBatch(candidate).body);
        } catch {
          this.debug(channel, "invalid-item");
          continue;
        }
        if (byteLength(candidateBody) <= MAX_COLLECT_BODY_BYTES) {
          current = candidate;
          continue;
        }
        if (current.length > 0)
          chunks.push(current);
        current = [];
        let singleBody;
        try {
          singleBody = JSON.stringify(createCollectBatch([item]).body);
        } catch {
          this.debug(channel, "invalid-item");
          continue;
        }
        if (byteLength(singleBody) > MAX_COLLECT_BODY_BYTES) {
          this.debug(channel, "event-too-large");
          continue;
        }
        current = [item];
      }
      if (current.length > 0)
        chunks.push(current);
      return Promise.all(chunks.map((chunk) => this.enqueueCollectChunk(chunk, queue))).then(() => {
        return;
      });
    }
    enqueueCollectChunk(items, queue) {
      const batch = createCollectBatch(items);
      const application = requireApplication(items);
      const body = JSON.stringify(batch.body);
      const request = {
        method: "POST",
        credentials: "omit",
        referrerPolicy: "no-referrer",
        headers: {
          "Content-Type": "application/json",
          [PROTOCOL_HEADERS.apiKey]: this.options.apiKey,
          [PROTOCOL_HEADERS.application]: application,
          [PROTOCOL_HEADERS.batchId]: this.randomId()
        },
        body
      };
      return queue.enqueue(() => this.sendRequest(this.options.collectUrl, request, byteLength(body)), {
        bytes: byteLength(body),
        droppable: items.every(isDroppableOrdinaryItem),
        items: items.length
      });
    }
    enqueueReplay(items, forceRestart = false, fallbackScope) {
      const operations = [];
      const scope = items[0] ? replayScope(items[0]) : fallbackScope;
      if (!scope) {
        this.debug("replay", "snapshot-required");
        return Promise.resolve();
      }
      const { application, sessionId, userIdentity } = scope;
      this.rememberReplayMeta(items);
      const activeState = this.recordings.values().next().value;
      let state = this.recordings.get(sessionId);
      const stateMatchesIdentity = state?.application === application && state.userIdentity === userIdentity;
      const fullSnapshotIndex = items.findIndex((item) => replayEventType(item) === 2);
      const containsOnlyMeta = items.length > 0 && items.every((item) => replayEventType(item) === 4);
      if (forceRestart || !stateMatchesIdentity || state?.failed) {
        if (forceRestart || !stateMatchesIdentity) {
          if (activeState && !activeState.failed) {
            operations.push(this.flushReplayAccumulator(activeState));
          }
          this.recordings.clear();
          this.lastActivatedReplay = undefined;
          state = undefined;
        }
        const meta = scopesMatch(this.lastReplayMeta, scope) ? this.lastReplayMeta?.item : undefined;
        if (fullSnapshotIndex < 0 && containsOnlyMeta) {
          return Promise.all(operations).then(() => {
            return;
          });
        }
        if (fullSnapshotIndex < 0 || !meta) {
          this.debug("replay", "snapshot-required");
          return Promise.all(operations).then(() => {
            return;
          });
        }
        state = this.activateRecording(sessionId, application, userIdentity);
        const snapshot = items[fullSnapshotIndex];
        items = [
          cloneReplayMetaForSnapshot(meta, snapshot),
          ...items.slice(fullSnapshotIndex)
        ];
      }
      if (!state) {
        this.debug("replay", "snapshot-required");
        return Promise.resolve();
      }
      if (!forceRestart && stateMatchesIdentity)
        this.lastActivatedReplay = undefined;
      operations.push(...this.bufferReplayItems(items, state));
      return Promise.all(operations).then(() => {
        return;
      });
    }
    bufferReplayItems(items, state) {
      const operations = [];
      for (const item of items) {
        if (state.failed)
          break;
        const type = replayEventType(item);
        if (type === undefined) {
          this.quarantineRecording(state);
          this.debug("replay", "invalid-item");
          break;
        }
        if (type === 4) {
          if (state.accumulator.items.length > 0) {
            if (this.accumulatorAwaitsFullSnapshot(state)) {
              this.quarantineRecording(state);
              this.debug("replay", "snapshot-required");
              break;
            }
            operations.push(this.flushReplayAccumulator(state));
          }
          this.appendReplayItem(state, item);
          continue;
        }
        if (type === 2) {
          if (!this.accumulatorAwaitsFullSnapshot(state)) {
            this.quarantineRecording(state);
            this.debug("replay", "snapshot-required");
            break;
          }
          this.appendReplayItem(state, item);
          operations.push(this.flushReplayAccumulator(state));
          continue;
        }
        if (this.accumulatorAwaitsFullSnapshot(state)) {
          this.quarantineRecording(state);
          this.debug("replay", "snapshot-required");
          break;
        }
        if (this.shouldFlushBeforeReplayItem(state, item)) {
          operations.push(this.flushReplayAccumulator(state));
        }
        this.appendReplayItem(state, item);
        if (this.replayAccumulatorReachedHardTarget(state)) {
          operations.push(this.flushReplayAccumulator(state));
        }
      }
      return operations;
    }
    appendReplayItem(state, item) {
      const clone = withReplayItemInfo(structuredClone(item), replayItemInfo(item));
      state.accumulator.items.push(clone);
      state.accumulator.bytes += replayItemBytes(clone);
      state.accumulator.firstTimestamp ??= replayEventTimestamp(clone);
      if (!state.accumulator.timer) {
        state.accumulator.timer = setTimeout(() => {
          state.accumulator.timer = undefined;
          const operation = this.settle("replay", this.flushReplayAccumulator(state));
          this.replayTimerFlush = operation;
          operation.finally(() => {
            if (this.replayTimerFlush === operation)
              this.replayTimerFlush = undefined;
          });
        }, REPLAY_TARGET_DURATION_MS);
      }
      replayLifecycleFlushers.add(this.flushOnPageLifecycle);
    }
    accumulatorAwaitsFullSnapshot(state) {
      return state.accumulator.items.length === 1 && replayEventType(state.accumulator.items[0]) === 4;
    }
    shouldFlushBeforeReplayItem(state, item) {
      if (state.accumulator.items.length === 0)
        return false;
      const maxEvents = this.options.replay?.maxSegmentEvents ?? REPLAY_MAX_SEGMENT_EVENTS;
      if (state.accumulator.items.length >= maxEvents)
        return true;
      if (state.accumulator.bytes + replayItemBytes(item) > (this.options.replay?.targetSegmentBytes ?? REPLAY_TARGET_BYTES)) {
        return true;
      }
      const timestamp = replayEventTimestamp(item);
      return timestamp !== undefined && state.accumulator.firstTimestamp !== undefined && timestamp - state.accumulator.firstTimestamp >= REPLAY_TARGET_DURATION_MS;
    }
    replayAccumulatorReachedHardTarget(state) {
      return state.accumulator.items.length >= (this.options.replay?.maxSegmentEvents ?? REPLAY_MAX_SEGMENT_EVENTS) || state.accumulator.bytes >= (this.options.replay?.targetSegmentBytes ?? REPLAY_TARGET_BYTES);
    }
    flushActiveReplay(pageLifecycle = false) {
      const state = this.recordings.values().next().value;
      return state ? this.flushReplayAccumulator(state, pageLifecycle) : Promise.resolve();
    }
    flushReplayAccumulator(state, pageLifecycle = false) {
      if (state.accumulator.items.length === 0)
        return Promise.resolve();
      if (this.accumulatorAwaitsFullSnapshot(state)) {
        this.quarantineRecording(state);
        this.debug("replay", "snapshot-required");
        return Promise.resolve();
      }
      const items = state.accumulator.items;
      this.resetReplayAccumulator(state);
      const queuedBytes = items.reduce((total, item) => total + replayItemBytes(item), 0);
      return state.queue.enqueue(() => {
        if (state.failed) {
          this.debug("replay", "queue-drop");
          return Promise.resolve();
        }
        return this.sendReplay(items, state, pageLifecycle);
      }, {
        bytes: queuedBytes,
        droppable: false,
        items: items.length
      }).catch((error) => {
        this.quarantineRecording(state);
        this.debug("replay", "queue-drop");
        throw error;
      });
    }
    resetReplayAccumulator(state) {
      if (state.accumulator.timer)
        clearTimeout(state.accumulator.timer);
      state.accumulator = { bytes: 0, items: [] };
      if (![...this.recordings.values()].some((recording) => recording.accumulator.items.length > 0)) {
        replayLifecycleFlushers.delete(this.flushOnPageLifecycle);
      }
    }
    rememberReplayMeta(items) {
      for (const item of items) {
        if (replayEventType(item) !== 4 || replayItemBytes(item) > MAX_REPLAY_META_BYTES)
          continue;
        const scope = replayScope(item);
        if (!scope)
          continue;
        this.lastReplayMeta = {
          ...scope,
          item: withReplayItemInfo(structuredClone(item), replayItemInfo(item))
        };
      }
    }
    async sendReplay(items, state, pageLifecycle = false) {
      try {
        const segments = await buildReplaySegments(items, {
          recordingId: state.recordingId,
          firstSequence: state.nextSequence,
          maxEvents: this.options.replay?.maxSegmentEvents ?? REPLAY_MAX_SEGMENT_EVENTS,
          onDrop: (reason) => {
            this.quarantineRecording(state);
            this.debug("replay", reason);
          },
          targetDurationMs: 5000,
          targetUncompressedBytes: this.options.replay?.targetSegmentBytes ?? REPLAY_TARGET_BYTES
        });
        if (state.failed)
          return;
        for (const segment of segments) {
          await this.sendReplaySegment(segment, pageLifecycle);
          state.nextSequence = segment.sequence + 1;
        }
      } catch (error) {
        this.quarantineRecording(state);
        throw error;
      }
    }
    quarantineRecording(state) {
      state.failed = true;
      this.resetReplayAccumulator(state);
      if (this.recordings.get(state.sessionId) === state)
        this.lastReplayMeta = undefined;
    }
    activateRecording(sessionId, application, userIdentity) {
      this.recordings.clear();
      const state = {
        accumulator: { bytes: 0, items: [] },
        application,
        failed: false,
        nextSequence: 0,
        queue: this.replayQueue,
        recordingId: this.randomId(),
        sessionId,
        userIdentity
      };
      this.recordings.set(sessionId, state);
      this.lastActivatedReplay = { application, sessionId, userIdentity };
      return state;
    }
    async sendReplaySegment(segment, pageLifecycle) {
      const request = {
        method: "POST",
        credentials: "omit",
        referrerPolicy: "no-referrer",
        headers: {
          "Content-Encoding": "gzip",
          "Content-Type": "application/vnd.weops.rum-replay.v1+json",
          [PROTOCOL_HEADERS.apiKey]: this.options.apiKey,
          [PROTOCOL_HEADERS.sessionId]: segment.sessionId,
          [PROTOCOL_HEADERS.application]: segment.application,
          [PROTOCOL_HEADERS.batchId]: segment.segmentId
        },
        body: segment.body
      };
      await this.sendRequest(this.options.replayUrl, request, segment.compressedBytes, pageLifecycle);
    }
    async sendRequest(url, request, bytes, pageLifecycle = false) {
      const reservation = reserveKeepalive(bytes);
      if (pageLifecycle && !reservation.keepalive) {
        this.debug("replay", "pagehide-keepalive-unavailable");
      }
      try {
        await requestWithRetry(url, { ...request, keepalive: reservation.keepalive }, this.retryOptions);
      } finally {
        reservation.release();
      }
    }
    settle(channel, operation) {
      return operation.catch(() => {
        this.debug(channel, "request-failed");
      });
    }
    createReplayQueue() {
      return new BoundedConcurrentQueue({
        maxInFlight: 1,
        maxQueuedBytes: REPLAY_QUEUE_MAX_BYTES,
        maxQueuedItems: Number.MAX_SAFE_INTEGER
      }, () => this.debug("replay", "queue-drop"));
    }
    debug(channel, reason) {
      this.options.debug?.({ channel, reason });
    }
  }

  // src/cdn.ts
  var REPLAY_MASK_TEXT = ".faro-mask, [data-faro-mask], [contenteditable]";
  var REPLAY_BLOCK = "input[type='password'], [autocomplete='current-password'], [autocomplete='new-password'], [autocomplete='one-time-code'], form[action*='login' i], form[action*='signin' i], form[action*='checkout' i], form[action*='payment' i]";
  function initCoreRum(config) {
    const endpoint = config.endpoint.replace(/\/+$/, "");
    const replayEnabled = Boolean(config.replay);
    const samplingRate = replayEnabled ? config.replay && config.replay.samplingRate || 0.1 : 0;
    const instrumentations = [...getWebInstrumentations()];
    if (replayEnabled && window.__coreRumReplay) {
      const replay = window.__coreRumReplay;
      instrumentations.push(new replay.ReplayInstrumentation({
        samplingRate,
        beforeSend: sanitizeReplayEvent,
        maskAllInputs: true,
        maskTextSelector: REPLAY_MASK_TEXT,
        blockSelector: REPLAY_BLOCK,
        recordCanvas: false,
        collectFonts: false,
        inlineStylesheet: true,
        inlineImages: false,
        recordCrossOriginIframes: false
      }));
    }
    const faro2 = initializeFaro2({
      app: {
        name: config.app.name,
        environment: config.app.environment,
        release: config.app.release
      },
      sessionTracking: { enabled: true, samplingRate: 1 },
      pageTracking: { generatePageId: () => crypto.randomUUID() },
      transports: [
        new CoreRumTransport({
          apiKey: config.apiKey,
          collectUrl: `${endpoint}/collect`,
          replayUrl: `${endpoint}/replay`,
          replay: { enabled: replayEnabled }
        })
      ],
      instrumentations
    });
    function syncViewFromLocation() {
      faro2.api.setView({ name: window.location.pathname || "/" });
    }
    syncViewFromLocation();
    for (const method of ["pushState", "replaceState"]) {
      const original = history[method].bind(history);
      history[method] = (...args) => {
        const result = original(...args);
        syncViewFromLocation();
        return result;
      };
    }
    window.addEventListener("popstate", syncViewFromLocation);
    if (replayEnabled && window.__coreRumReplay) {
      const takeFullSnapshot = window.__coreRumReplay.takeFullSnapshot;
      let replayScope2 = "";
      faro2.metas.addListener((meta) => {
        const nextScope = `${meta.session?.id ?? ""}\x00${meta.user?.id ?? ""}`;
        if (nextScope === replayScope2)
          return;
        replayScope2 = nextScope;
        try {
          takeFullSnapshot(true);
        } catch {}
      });
    }
    return faro2;
  }

  // scripts/cdn-entry.ts
  var root = globalThis;
  root.initCoreRum = initCoreRum;
})();

//# debugId=AE4A9394EA9F258364756E2164756E21
