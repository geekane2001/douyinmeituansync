// sign_generator.js (最终修复版 - 添加 webdriver 伪造)

const fs = require('fs');
const path = require('path');
const { URL } = require('url');

let envConfig;
try {
    const envData = fs.readFileSync(path.join(__dirname, 'env.json'), 'utf-8');
    envConfig = JSON.parse(envData);
} catch (e) {
    console.error("错误: 无法读取或解析 env.json 文件。", e);
    process.exit(1);
}

// ==============================================================================
// 步骤3: 手动创建并注入一个更完备的模拟浏览器环境
// ==============================================================================
function setupMockBrowserEnvironment(env) {
    global.window = global;

    // --- 基础对象模拟 ---
    Object.defineProperty(global, 'navigator', { value: env.navigator, configurable: true, writable: true });
    Object.defineProperty(global, 'screen', { value: env.screen, configurable: true, writable: true });
    global.location = env.location;
    global.history = env.history;

    // --- 窗口尺寸模拟 ---
    global.innerWidth = env.window.innerWidth;
    global.innerHeight = env.window.innerHeight;
    global.outerWidth = env.window.outerWidth;
    global.outerHeight = env.window.outerHeight;
    global.devicePixelRatio = env.window.devicePixelRatio;

    // --- document 对象模拟 (增强版) ---
    global.document = {
        createElement: function(tagName) {
            tagName = String(tagName).toLowerCase();
            if (tagName === 'canvas') {
                return {
                    getContext: function() { return { fillText: function() {}, stroke: function() {}, closePath: function() {} }; },
                    toDataURL: function() { return "data:image/png;base64,mock_canvas_data"; },
                    style: {},
                    appendChild: function() {},
                    remove: function() {},
                };
            }
            return { style: {}, appendChild: function() {}, remove: function() {} };
        },
        body: { appendChild: function() {} },
        documentElement: { style: {}, clientWidth: env.window.innerWidth },
        _cookie: "",
        get cookie() { return this._cookie; },
        set cookie(val) { this._cookie = val; }
    };

    // --- XMLHttpRequest 模拟 ---
    global.XMLHttpRequest = function () {};
    global.XMLHttpRequest.prototype = new global.XMLHttpRequest();

    // ================= [ !! 关键修复区域 !! ] =================
    // 补充原生函数和对象
    
    global.setTimeout = setTimeout;
    global.setInterval = setInterval;
    global.clearTimeout = clearTimeout;
    global.clearInterval = clearInterval;
    global.Promise = Promise;
    global.addEventListener = function() {};
    global.removeEventListener = function() {};
    global.requestAnimationFrame = function(callback) { return setTimeout(callback, 16); };
    global.cancelAnimationFrame = function(id) { clearTimeout(id); };
    global.Image = function() {};
    global.Storage = function() {};
    global.localStorage = new Storage();
    global.sessionStorage = new Storage();
    if (typeof global.performance === 'undefined') {
        global.performance = { now: () => Date.now(), timing: { navigationStart: Date.now() - 1000 } };
    }
    if (typeof global.Element === 'undefined') {
        global.Element = function() {};
        global.Element.prototype.appendChild = function() {};
        global.Element.prototype.remove = function() {};
        global.Element.prototype.getBoundingClientRect = function() {
            return { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 };
        };
    }
    
    // 【新增】根据视频思路，彻底伪造 navigator.webdriver 属性
    Object.defineProperty(global.navigator, 'webdriver', {
        get: () => false, // 始终返回 false
        configurable: true // 允许再次修改
    });
    // ========================================================
}

// 在 require H5guard.js 之前就执行环境设置
setupMockBrowserEnvironment(envConfig);

// (后续代码与上一版完全相同，保持不变)
// ...
try {
    require('./H5guard.js');
} catch(e) {
    console.error("加载 H5guard.js 时出错:", e.stack || e);
    process.exit(1);
}
const H5guard = window.H5guard;
async function get_mtgsig(url) {
    try {
        if (!H5guard || typeof H5guard.sign !== 'function') {
             throw new Error('在全局 window 对象上未找到 H5guard 或其 sign 方法。');
        }
        const urlObject = new URL(url);
        global.location = {
            ...envConfig.location,
            href: url,
            protocol: urlObject.protocol,
            host: urlObject.host,
            hostname: urlObject.hostname,
            port: urlObject.port,
            pathname: urlObject.pathname,
            search: urlObject.search,
            hash: urlObject.hash,
        };
        if (typeof H5guard.init === 'function') {
            await H5guard.init({});
        }
        const settings = { url: url, data: null, method: 'GET', headers: {} };
        const result = await H5guard.sign(settings);
        const resultFile = path.join(__dirname, 'mtgsig_result.json');
        fs.writeFileSync(resultFile, result.headers.mtgsig);
        process.exit(0);
    } catch (e) {
        console.error("生成签名时出错:", e.stack || e);
        process.exit(1);
    }
}
const url_to_sign = process.argv[2];
if (url_to_sign) {
    get_mtgsig(url_to_sign);
} else {
    console.error("错误: 未提供URL作为命令行参数。");
    process.exit(1);
}