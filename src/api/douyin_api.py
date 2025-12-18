"""
抖音API模块 - 处理抖音开放平台和网页端API调用
"""
import requests
import json
import time
from ..config import *

def get_douyin_access_token(log_func):
    """获取抖音Access Token"""
    log_func("--- 正在获取抖音 Access Token ---")
    try:
        response = requests.post(
            DOUYIN_TOKEN_URL,
            json={
                "grant_type": "client_credential",
                "client_key": CLIENT_KEY,
                "client_secret": CLIENT_SECRET
            },
            timeout=10
        )
        response.raise_for_status()
        data = response.json().get("data", {})
        if data.get("error_code") == 0 and data.get("access_token"):
            log_func("[Success] 抖音 Token 获取成功!")
            return data["access_token"]
    except Exception as e:
        log_func(f"[Error] 获取抖音 Token 失败: {e}")
    return None

def get_douyin_products_by_store(access_token, poi_id, log_func):
    """查询指定门店的抖音商品列表"""
    log_func(f"--- 正在使用 POI ID: {poi_id} 查询抖音商品列表 ---")
    headers = {"Content-Type": "application/json", "access-token": access_token}
    params = {
        "account_id": str(DOUYIN_ACCOUNT_ID),
        "poi_ids": f'[{poi_id}]',
        "count": 50,
        "status": 1
    }
    try:
        response = requests.get(DOUYIN_PRODUCT_QUERY_URL, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("data", {}).get("error_code") != 0:
            return []
        
        product_list = data.get("data", {}).get("products", [])
        detailed_products = []
        for p in product_list:
            product_info = p.get("product", {})
            sku_info = p.get("sku", {})
            if product_info and sku_info:
                detailed_products.append({
                    "id": product_info.get('product_id'),
                    "name": product_info.get('product_name'),
                    "price": f"{sku_info.get('actual_amount', 0) / 100:.2f}",
                    "origin_price": f"{sku_info.get('origin_amount', 0) / 100:.2f}"
                })
        log_func(f"[Success] 查询到 {len(detailed_products)} 个在线商品。")
        return detailed_products
    except Exception as e:
        log_func(f"[Error] 查询抖音商品时发生错误: {e}")
    return []

def get_douyin_product_details(access_token, product_id, log_func):
    """获取商品详细信息"""
    log_func(f"--- 正在获取商品 '{product_id}' 的详细信息 ---")
    headers = {"Content-Type": "application/json", "access-token": access_token}
    params = {"account_id": DOUYIN_ACCOUNT_ID, "product_ids": [product_id]}
    try:
        response = requests.get(DOUYIN_PRODUCT_GET_URL, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        response_data = response.json()
        if response_data.get("data", {}).get("error_code") == 0:
            product_details = response_data.get("data", {}).get("product_onlines", [])
            if product_details:
                log_func(f"[Success] 商品 '{product_id}' 详情获取成功。")
                return product_details[0]
    except Exception as e:
        log_func(f"[Error] 获取商品 '{product_id}' 详情时发生意外错误: {e}")
    return None

def operate_douyin_product(access_token, product_id, log_func, offline=True):
    """上架/下架商品"""
    op_type = 2 if offline else 1
    action_text = "下架" if offline else "上架"
    log_func(f"========== 开始 {action_text} 商品 ID: {product_id} ==========")
    headers = {"Content-Type": "application/json", "access-token": access_token}
    payload = {
        "account_id": DOUYIN_ACCOUNT_ID,
        "product_id": product_id,
        "op_type": op_type
    }
    try:
        response = requests.post(DOUYIN_PRODUCT_OPERATE_URL, headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        response_data = response.json()
        if response_data.get('data', {}).get('error_code') == 0:
            log_func(f"[SUCCESS] 商品 {product_id} {action_text}成功!")
            return True, ""
        else:
            reason = response_data.get('data', {}).get('description', 'API返回未知错误')
            log_func(f"[FAILURE] 商品 {product_id} {action_text}失败: {reason}")
            return False, reason
    except Exception as e:
        log_func(f"商品 {product_id} {action_text}时发生意外错误: {e}")
        return False, str(e)
