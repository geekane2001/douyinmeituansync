"""
美团API模块 - 处理美团套餐信息爬取
"""
import requests
import time
import re
from bs4 import BeautifulSoup
from src.api.meituan_api_worker import get_raw_shop_data, parse_and_format_data

def process_store_name_for_meituan(store_name, log_func):
    """处理店名用于美团搜索（移除'竞潮玩'）"""
    cleaned_name = store_name.replace("竞潮玩", "").strip()
    log_func(f"处理店名: '{store_name}' -> '{cleaned_name}'")
    return cleaned_name

def get_meituan_packages(store_name, city, log_func):
    """获取美团套餐信息"""
    url = f"https://i.meituan.com/s/{city}-{store_name}"
    log_func(f"--- 正在请求美团URL: {url} ---")
    
    # 美团Cookie模板
    current_timestamp_ms = int(time.time() * 1000)
    base_cookie = (
        f"__mta=176011805.1756208359328.{current_timestamp_ms-5000}.{current_timestamp_ms}.30; "
        "iuuid=BB0697D3630DED2F82ADB96105EC195EB173E4FFD90723B66428C9829840A7AA; "
        "_lxsdk_cuid=199985447cbc8-0682d08c20b0dd-4c657b58-1fa400-199985447cbc8; "
        "_lxsdk=BB0697D3630DED2F82ADB96105EC195EB173E4FFD90723B66428C9829840A7AA; "
        "uuid=15efb5c50ad74159b2cd.1759197288.1.0.0; "
        "webp=1; "
        "_hc.v=17500b8b-5eb7-fe17-d4e8-ffc997c5aeda.1762150863; "
        "token=AgE9Jw3iB0xS0K4Dvg5h7_SFKSHEFNG3l3ns5orAsvwiPjQSJEe4ONv8nXX8acfUcNWMJhCiWxrpXgAAAAD1LgAAJsMNtP1gv1zb-teZ_5_kWSrKWuemK26NdJ5W9PXcqThYpPwqaiFNJIXoQXyCW92I; "
        "userId=4976202507; "
        f"latlng=30.602421,104.09746,{current_timestamp_ms}; "
        f"_lxsdk_s=199869550cd-0fd-14f-716%7C%7C46"
    )
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Host': 'i.meituan.com',
        'Cookie': base_cookie
    }
    
    # proxies = {'http': 'http://127.0.0.1:10808', 'https': 'http://127.0.0.1:10808'}
    # 移除硬编码的代理，或者增加自动回退机制
    proxies = None # 默认不使用代理，或者可以从环境变量读取
    
    # 如果想保留本地开发的便利性，可以尝试检测是否本地环境，或者捕获异常回退
    local_proxy = {'http': 'http://127.0.0.1:10808', 'https': 'http://127.0.0.1:10808'}
    
    try:
        # 第一次尝试：尝试使用本地代理（如果是Windows且看起来像本地开发环境）
        # 为了兼容性，先尝试带代理请求
        try:
            response = requests.get(url, headers=headers, proxies=local_proxy, timeout=15)
            response.raise_for_status()
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError) as e:
            # 如果代理连接失败（如在服务器环境），则回退到无代理模式
            log_func(f"[Info] 本地代理连接失败，尝试直接连接... ({str(e)[:50]}...)")
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()

        response.encoding = 'utf-8'
        
        log_func(f"请求成功! 状态码: {response.status_code}")
        
        if "访问异常" in response.text:
            log_func("[Error] 美团页面访问异常，可能需要更新Cookie")
            return []
        
        soup = BeautifulSoup(response.text, 'lxml')
        
        # 提取店名用于确认
        shop_name_tag = soup.find('span', class_='poiname')
        shop_name = shop_name_tag.text.strip() if shop_name_tag else "未知店名"
        log_func(f"--- 成功提取到【{shop_name}】的美团套餐信息 ---")
        
        # 尝试提取 poiId 和 poiIdEncrypt 以使用新接口
        # 查找 data-com="redirect" ... poiIdEncrypt=...
        # 示例: <p data-com="redirect"  data-href="//i.meituan.com/poi/5262849?poiIdEncrypt=...">
        redirect_tag = soup.find('p', attrs={'data-com': 'redirect'})
        poi_id = None
        poi_id_encrypt = None
        
        if redirect_tag:
            href = redirect_tag.get('data-href', '')
            match = re.search(r'/poi/(\d+)\?poiIdEncrypt=([a-zA-Z0-9]+)', href)
            if match:
                poi_id = match.group(1)
                poi_id_encrypt = match.group(2)
                log_func(f"获取到新接口参数: shopId={poi_id}, encryptId={poi_id_encrypt[:10]}...")
        
        if not poi_id:
            # 尝试另一种方式查找，有时可能是直接的链接列表
            # 比如 dl.list dd a.react 链接中可能包含
            first_deal = soup.select_one('dl.bd-deal-list dd a.react')
            if first_deal:
                href = first_deal.get('href', '')
                # 尝试从链接中提取，但不一定有encryptId
                pass

        if poi_id and poi_id_encrypt:
            log_func(">>> 尝试使用高级接口获取完整套餐列表...")
            raw_data = get_raw_shop_data(poi_id, poi_id_encrypt)
            if raw_data:
                packages = parse_and_format_data(raw_data)
                if packages:
                    log_func(f"✅ 高级接口调用成功！获取到 {len(packages)} 个套餐")
                    for idx, p in enumerate(packages):
                        log_func(f"  [{idx+1}] {p['title']} (￥{p['price']})")
                    return packages
                else:
                    log_func("⚠️ 高级接口解析结果为空，回退到网页解析模式。")
            else:
                log_func("⚠️ 高级接口请求失败，回退到网页解析模式。")
        else:
            log_func("⚠️ 未能提取到 shopIdEncrypt，将使用网页解析模式（可能只能获取前10个）。")

        # --- 回退：原有网页解析逻辑 ---
        
        deal_items = soup.select('dl.bd-deal-list dd a.react')
        
        if not deal_items:
            log_func("[Warning] 未找到美团套餐信息")
            return []
        
        log_func(f"找到 {len(deal_items)} 个套餐项 (网页模式)")
        
        packages = []
        for idx, item in enumerate(deal_items):
            # 提取标题
            title_tag = item.find('div', class_='title')
            title = title_tag.text.strip() if title_tag else "无标题"
            
            # 提取现价
            price_tag = item.find('span', class_='strong')
            price_str = price_tag.text.strip() if price_tag else "0"
            
            # 提取原价
            original_price_tag = item.find('del')
            original_price_str = original_price_tag.text.strip() if original_price_tag else ""
            
            # 转换为数字
            try:
                price_clean = re.sub(r'[^\d.]', '', price_str)
                price = float(price_clean) if price_clean else 0.0
                
                if original_price_str:
                    original_price_clean = re.sub(r'[^\d.]', '', original_price_str)
                    original_price = float(original_price_clean) if original_price_clean else price
                else:
                    original_price = price
                
                log_func(f"提取美团套餐{idx+1}: {title} | 现价: {price}元 | 原价: {original_price}元")
            except (ValueError, AttributeError) as e:
                log_func(f"[Error] 套餐{idx+1}价格转换失败: {e}")
                price = 0.0
                original_price = 0.0
            
            packages.append({
                "title": title,
                "price": price,
                "original_price": original_price
            })
        
        log_func(f"成功获取 {len(packages)} 个美团套餐")
        return packages
        
    except Exception as e:
        log_func(f"[Error] 获取美团套餐失败: {e}")
        import traceback
        log_func(f"[Debug] 详细错误: {traceback.format_exc()}")
        return []
