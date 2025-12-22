"""
飞书API模块 - 处理飞书多维表格数据获取
"""
import requests
from ..config import *

def get_feishu_tenant_access_token(log_func):
    """获取飞书Access Token"""
    log_func("--- 正在获取飞书 Access Token ---")
    try:
        response = requests.post(
            FEISHU_TENANT_ACCESS_TOKEN_URL,
            json={
                "app_id": FEISHU_APP_ID,
                "app_secret": FEISHU_APP_SECRET
            },
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        if data.get("code") == 0:
            log_func("[Success] 飞书 Token 获取成功!")
            return data.get("tenant_access_token")
    except Exception as e:
        log_func(f"[Error] 获取飞书 Token 失败: {e}")
    return None

def get_feishu_bitable_records(feishu_token, log_func):
    """从飞书多维表格获取门店列表"""
    log_func("--- 正在从飞书获取门店列表 ---")
    headers = {"Authorization": f"Bearer {feishu_token}"}
    all_records = {}
    page_token = ""
    
    while True:
        params = {"page_size": 500, "page_token": page_token}
        try:
            response = requests.post(
                FEISHU_BITABLE_RECORDS_SEARCH_URL,
                headers=headers,
                params=params,
                json={"field_names": ["门店名称", "门店ID", "所在城市"]},
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") != 0:
                log_func(f"[Error] 查询飞书记录失败: {data.get('msg')}")
                return {}
            
            items = data.get("data", {}).get("items", [])
            for item in items:
                fields = item.get("fields", {})
                store_name = fields.get("门店名称", [{}])[0].get('text')
                store_id = fields.get("门店ID", [{}])[0].get('text')
                city = fields.get("所在城市", [{}])[0].get('text', '')
                
                if store_name and store_id:
                    # 返回结构: {'门店名': {'id': 'xxx', 'city': 'xxx'}}
                    all_records[store_name] = {
                        'id': store_id,
                        'city': city
                    }
            
            page_token = data.get("data", {}).get("page_token")
            if not data.get("data", {}).get("has_more", False):
                break
        except Exception as e:
            log_func(f"[Error] 查询飞书记录时发生错误: {e}")
            return {}
    
    log_func(f"[Success] 成功从飞书获取到 {len(all_records)} 个门店。")
    return all_records
