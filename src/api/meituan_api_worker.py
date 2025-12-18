import requests
import json
import time
import os
import subprocess
import itertools
# from setup import get_node_executable_path # Assuming this might be missing, handling gracefully

# 1. 将Pragma Token定义为列表，方便管理和轮询
PRAGMA_TOKENS = [
    "AgGoIpKltDaz2ibn-FGw-03jav9iL1UB8tsJPsUt7XtVN7kJAt5tCD_DL2IWrByjwT5P-_gFYW3ZmAAAAABtLwAAu7m9nw4XAoKTGEEnpiXnfuKIOciQXqXotVt4lGdBL922WXg76fuVQFUiOuPmwtb-",
    "AgGoIpKltDaz2ibn-FGw-03jav9iL1UB8tsJPsUt7XtVN7kJAt5tCD_DL2IWrByjwT5P-_gFYW3ZmAAAAABtLwAAu7m9nw4XAoKTGEEnpiXnfuKIOciQXqXotVt4lGdBL922WXg76fuVQFUiOuPmwtb-"
]

# 2. 使用itertools.cycle创建一个无限循环的Token迭代器，实现轮询功能
token_cycler = itertools.cycle(PRAGMA_TOKENS)

MEITUAN_API_URL_TEMPLATE = (
    "https://mapi.dianping.com/api/dzviewscene/productshelf/dzdealshelf?shopid={shop_id}"
    "&shopidEncrypt={shop_id_encrypt}&platform=201&sceneCode=mt_h5_default_deal_shelf"
    "&pagesource=&yodaReady=h5&csecplatform=4&csecversion=4.0.4"
)

def log_message(message):
    """打印带有时间戳的日志信息。"""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def get_node_executable_path():
    """尝试获取node路径，简单回退"""
    try:
        # 尝试直接运行 node -v
        subprocess.run(["node", "-v"], check=True, capture_output=True)
        return "node"
    except:
        return None

def get_raw_shop_data(shop_id, shop_id_encrypt):
    """
    获取单个店铺的原始商品数据。
    此函数现在会轮询使用PRAGMA_TOKENS列表中的Token。
    """
    node_executable = get_node_executable_path()
    if not node_executable:
        log_message("[致命错误] 无法找到本地的Node.js可执行文件。")
        return None

    url_to_sign = MEITUAN_API_URL_TEMPLATE.format(
        shop_id=shop_id,
        shop_id_encrypt=shop_id_encrypt
    )
    log_message(f"准备为店铺 {shop_id} 生成签名...")
    mtgsig_string = None
    try:
        # 检查 sign_generator.js 是否存在
        if not os.path.exists('sign_generator.js'):
             log_message("[错误] sign_generator.js 文件不存在，无法生成签名。")
             return None

        # 运行Node.js脚本以生成签名
        subprocess.run(
            [node_executable, 'sign_generator.js', url_to_sign],
            capture_output=True, text=True, encoding='utf-8', check=True
        )
        result_file = 'mtgsig_result.json'
        if os.path.exists(result_file):
            with open(result_file, 'r', encoding='utf-8') as f:
                mtgsig_string = f.read().strip()
            os.remove(result_file)
        else:
            log_message("[错误] 签名文件 (mtgsig_result.json) 未生成。")
            return None
    except subprocess.CalledProcessError as e:
        log_message(f"[致命错误] Node.js 签名脚本执行失败: {e.stderr}")
        return None
    except Exception as e:
        log_message(f"[致命错误] 在生成签名阶段出错: {e}")
        return None

    if not mtgsig_string:
        log_message("[错误] 未能获取到有效的签名字符串。")
        return None
    
    log_message(f"成功获取签名，准备为店铺 {shop_id} 发起API请求。")
    
    # 动态从轮询器中获取下一个Token
    current_pragma_token = next(token_cycler)
    # log_message(f"本次请求使用 Token (后10位): ...{current_pragma_token[-10:]}")
    
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://g.meituan.com",
        "Referer": "https://g.meituan.com/",
        "User-Agent": user_agent,
        "mtgsig": mtgsig_string,
        "pragma-token": current_pragma_token,  # 使用从轮询器中获取的Token
    }

    try:
        response = requests.get(url_to_sign, headers=headers, timeout=10)
        response.raise_for_status()
        log_message(f"店铺 {shop_id} 的API请求成功，状态码: {response.status_code}")
        
        response_data = response.json()
        return response_data
        
    except requests.exceptions.RequestException as e:
        log_message(f"[致命错误] 店铺 {shop_id} 的网络请求阶段出错: {e}")
    except json.JSONDecodeError:
        log_message(f"[致命错误] 店铺 {shop_id} 的API响应不是有效的JSON格式。")
    return None

def parse_and_format_data(raw_data):
    """解析API返回的原始数据并格式化为所需的套餐列表 (修复价格为0的问题)。"""
    if not raw_data or raw_data.get('code') != 200:
        log_message("传入的原始数据无效或请求未成功，无法解析。")
        # 调试: 如果code不是200，打印code和msg
        if raw_data:
            log_message(f"API响应码: {raw_data.get('code')}, 消息: {raw_data.get('msg')}")
        return []
    
    formatted_packages = []

    def safe_float(value):
        """安全地将各种类型转换为浮点数"""
        if value is None:
            return 0.0
        try:
            # 处理字符串中的空白字符
            str_val = str(value).strip()
            if not str_val:
                return 0.0
            return float(str_val)
        except (ValueError, TypeError):
            return 0.0

    try:
        # 安全路径获取 productItems
        msg = raw_data.get('msg', {})
        if not msg:
            return []
            
        shelf_component = msg.get('shelfComponent', {})
        product_areas_list = shelf_component.get('filterIdAndProductAreas', [])
        
        if not product_areas_list:
            log_message("解析警告: 'filterIdAndProductAreas' 字段为空。")
            return []
            
        # 遍历所有区域查找商品
        product_areas = product_areas_list[0].get('productAreas', [])
        for area in product_areas:
            product_items = area.get('itemArea', {}).get('productItems', [])
            
            for item in product_items:
                # 1. 解析 labs 字段 (很多核心数据藏在这里面)
                labs_data = {}
                labs_str = item.get('labs')
                if isinstance(labs_str, str):
                    try:
                        labs_data = json.loads(labs_str)
                    except:
                        pass
                
                # 2. 获取现价 (Priority: salePrice -> price -> labs.price)
                price = 0.0
                # 尝试字段 A: salePrice (最常见)
                price = safe_float(item.get('salePrice'))
                # 尝试字段 B: price
                if price == 0:
                    price = safe_float(item.get('price'))
                # 尝试字段 C: labs['price']
                if price == 0:
                    price = safe_float(labs_data.get('price'))
                
                # 3. 获取原价 (Priority: marketPrice -> originalPrice -> labs.originalPrice -> labs.marketPrice)
                original_price = 0.0
                # 尝试字段 A: marketPrice
                original_price = safe_float(item.get('marketPrice'))
                # 尝试字段 B: originalPrice
                if original_price == 0:
                    original_price = safe_float(item.get('originalPrice'))
                # 尝试字段 C: labs['marketPrice']
                if original_price == 0:
                    original_price = safe_float(labs_data.get('marketPrice'))
                # 尝试字段 D: labs['originalPrice']
                if original_price == 0:
                    original_price = safe_float(labs_data.get('originalPrice'))

                # 4. 兜底逻辑：如果原价没取到，或者原价小于现价（异常数据），则强制原价=现价
                if original_price == 0 or original_price < price:
                    original_price = price

                # 5. 过滤无效数据（价格为0的通常是脏数据）
                if price > 0:
                    package = {
                        "title": item.get('title', "无标题"),
                        "price": price,
                        "original_price": original_price,
                    }
                    formatted_packages.append(package)

        log_message(f"成功解析并格式化了 {len(formatted_packages)} 个商品套餐。")
        return formatted_packages

    except Exception as e:
        log_message(f"解析JSON数据时发生未预期的错误: {e}")
        # 为了调试，打印一下堆栈信息
        import traceback
        traceback.print_exc()
        return []