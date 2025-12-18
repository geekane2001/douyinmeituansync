import requests
import json
import time
import os
import subprocess
import itertools
from setup import get_node_executable_path

# 1. 将Pragma Token定义为列表，方便管理和轮询
PRAGMA_TOKENS = [
    "AgF9I_8fdoZh5oMm8ELWA3iJythauv2jpzVnYFrako1vowuWDl45gJuki8JzDMCcHa3IwPyGp3ExEAAAAAAELgAAlkhqO_a3y8EYlVnTdNhEVD7OArnAvraWGsTKMXbeYX2aakITtG6KfzabpQqg9VH-",
    "AgF9I_8fdoZh5oMm8ELWA3iJythauv2jpzVnYFrako1vowuWDl45gJuki8JzDMCcHa3IwPyGp3ExEAAAAAAELgAAlkhqO_a3y8EYlVnTdNhEVD7OArnAvraWGsTKMXbeYX2aakITtG6KfzabpQqg9VH-"
]

# 2. 使用itertools.cycle创建一个无限循环的Token迭代器，实现轮询功能
# 这是一个更优雅、更高效的轮询实现方式
token_cycler = itertools.cycle(PRAGMA_TOKENS)

MEITUAN_API_URL_TEMPLATE = (
    "https://mapi.dianping.com/api/dzviewscene/productshelf/dzdealshelf?shopid={shop_id}"
    "&shopidEncrypt={shop_id_encrypt}&platform=201&sceneCode=mt_h5_default_deal_shelf"
    "&pagesource=&yodaReady=h5&csecplatform=4&csecversion=4.0.4"
)

def log_message(message):
    """打印带有时间戳的日志信息。"""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def get_raw_shop_data(shop_id, shop_id_encrypt):
    """
    获取单个店铺的原始商品数据。
    此函数现在会轮询使用PRAGMA_TOKENS列表中的Token。
    """
    node_executable = get_node_executable_path()
    if not node_executable:
        log_message("[致命错误] 无法找到本地的Node.js可执行文件。请先运行 setup.py。")
        return None

    url_to_sign = MEITUAN_API_URL_TEMPLATE.format(
        shop_id=shop_id,
        shop_id_encrypt=shop_id_encrypt
    )
    log_message(f"准备为店铺 {shop_id} 生成签名...")
    mtgsig_string = None
    try:
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
    log_message(f"本次请求使用 Token (后10位): ...{current_pragma_token[-10:]}")
    
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    try:
        with open('env.json', 'r', encoding='utf-8') as f:
            env_data = json.load(f)
            user_agent = env_data.get('navigator', {}).get('userAgent', user_agent)
    except Exception:
        log_message("警告: 读取 env.json 中的 User-Agent 失败，将使用默认值。")

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
        # 调试信息，可以按需注释掉
        # print("--- [API Worker] Raw JSON Response ---")
        # print(json.dumps(response_data, indent=4, ensure_ascii=False))
        # print("-------------------------------------")
        return response_data
        
    except requests.exceptions.RequestException as e:
        log_message(f"[致命错误] 店铺 {shop_id} 的网络请求阶段出错: {e}")
    except json.JSONDecodeError:
        log_message(f"[致命错误] 店铺 {shop_id} 的API响应不是有效的JSON格式。")
    return None

def parse_and_format_data(raw_data):
    """解析API返回的原始数据并格式化为所需的套餐列表。"""
    if not raw_data or raw_data.get('code') != 200:
        log_message("传入的原始数据无效或请求未成功，无法解析。")
        return []
    
    formatted_packages = []
    try:
        # 使用.get()方法来安全地访问嵌套的字典键
        shelf_component = raw_data.get('msg', {}).get('shelfComponent', {})
        product_areas_list = shelf_component.get('filterIdAndProductAreas', [])
        
        if not product_areas_list:
            log_message("解析警告: 'filterIdAndProductAreas' 字段为空，该店铺可能没有套餐。")
            return []
            
        product_areas = product_areas_list[0].get('productAreas', [])
        for area in product_areas:
            product_items = area.get('itemArea', {}).get('productItems', [])
            for item in product_items:
                package = {
                    "title": item.get('title', "无标题"),
                    "price": item.get('salePrice', ""),
                    "original_price": item.get('marketPrice', ""),
                    "sale": item.get('sale', ""),
                    "item_id": item.get('itemId'),
                    "jump_url": item.get('jumpUrl'),
                    "pic_url": item.get('pic', {}).get('pic', {}).get('picUrl')
                }
                formatted_packages.append(package)
        log_message(f"成功解析并格式化了 {len(formatted_packages)} 个商品套餐。")
        return formatted_packages
    except (AttributeError, KeyError, IndexError) as e:
        # 捕获潜在的解析错误
        log_message(f"解析JSON数据时发生错误: {e}。")
        return []