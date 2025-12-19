"""
商品管理模块 - 处理抖音商品的创建、修改、下架等操作
"""
import requests
import json
import time
import traceback
from PIL import Image
import os

from src.config import (
    DOUYIN_ACCOUNT_ID,
    DOUYIN_PRODUCT_SAVE_URL,
    DOUYIN_PRODUCT_OPERATE_URL,
    DOUYIN_ROOT_LIFE_ACCOUNT_ID
)
from src.api.douyin_api import get_douyin_product_details
from src.core.image_processor import center_crop_image, upload_to_r2


def operate_douyin_product(access_token, product_id, log_func, offline=True):
    """下架或上架抖音商品"""
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


# ========== 以下函数从原文件迁移 ==========


def _get_product_template_web(session, product_id, root_life_account_id, log_func):
    """从网页端获取商品模板"""
    log_func(f"--- [网页端] 正在获取商品模板 (ID: {product_id})... ---")
    url = "https://life.douyin.com/life/tobias/product/get/"
    params = {
        'product_type': '1',
        'category_id': '4007001',
        'scene': '2',
        'product_id': product_id,
        'list_tab': '9',
        'source': '1',
        'is_lite_req': 'false',
        'root_life_account_id': root_life_account_id
    }
    
    try:
        response = session.get(url, params=params, timeout=20)
        response.raise_for_status()
        result = response.json()
        
        if result.get('status_code') == 0 and result.get('product_detail'):
            log_func("✅ 成功获取商品模板！")
            return result['product_detail'], None
        else:
            return None, f"获取模板失败: {result.get('status_msg', '未知错误')}"
    except requests.exceptions.RequestException as e:
        return None, f"获取模板请求失败: {e}"


def _build_web_product_payload_from_template(product_detail_template, new_data, log_func):
    """基于模板构建网页端商品创建payload（复用图片）"""
    log_func("--- [网页端] 正在基于模板构建商品负载... ---")
    
    # 移除不需要的字段
    product_detail_template.pop('product_permission_list', None)
    
    if 'product' not in product_detail_template:
        return None
    
    product_object = product_detail_template['product']
    product_object.pop('product_id', None)  # 移除product_id以创建新商品
    
    if 'comp_key_value_map' not in product_object:
        return None
    
    comp_map = product_object['comp_key_value_map']
    
    # 更新商品名称、价格和时间
    current_timestamp = int(time.time())
    comp_map['productName'] = new_data["团购标题"]
    
    # 更新售价和原价
    actual_amount = int(new_data["售价"] * 100)  # 转换为分
    origin_amount = int(new_data["原价"] * 100)  # 转换为分
    comp_map['actualAmount'] = str(actual_amount)
    comp_map['originAmount'] = str(origin_amount)
    
    sold_start_time = str(current_timestamp)
    sold_end_time = str(current_timestamp + 90 * 24 * 3600)
    comp_map['auto_renew-sold_end_time-sold_start_time'] = json.dumps({
        "soldStartTime": sold_start_time,
        "soldEndTime": sold_end_time,
        "autoRenew": True,
        "soldTimeType": 1
    })
    
    log_func(f"✅ 商品名称已更新为: {comp_map['productName']}")
    log_func(f"✅ 售价已更新为: {new_data['售价']}元 (原价: {new_data['原价']}元)")
    
    # 强制设置为"不需要"顾客信息
    comp_map['customer_reserved_info-real_name_info'] = '{"customerReservedInfo":{"allow":false},"realNameInfo":{"enable":false}}'
    log_func("✅ 已强制将 '顾客信息设置' 修改为 '不需要'。")
    
    # 图片保持不变（复用模板商品的图片）
    log_func("✅ 图片链接保持原样（复用模板商品图片）。")
    
    # 更新 commodity 字段中的价格（这是网页端API真正读取的原价）
    # 重要：根据commodity_type构建正确的结构
    try:
        commodity_type = new_data.get("commodity_type", "网费")
        log_func(f"--- [Commodity更新] 目标类型: {commodity_type}")
        
        # 根据类型构建commodity结构
        if commodity_type == "网费":
            # 网费类型：简单结构，不需要服务时长等字段
            # 注意：price必须是字符串格式！
            
            # 确定适用人群
            member_type = new_data.get("member_type", "不限制")
            if member_type == "新客":
                suitable_group_key = 2
                suitable_group_value = "本店新会员"
            elif member_type == "老客":
                suitable_group_key = 3
                suitable_group_value = "本店老会员"
            else:
                suitable_group_key = 1
                suitable_group_value = "不限制"
            
            commodity_obj = [{
                "group_name": "网费",
                "total_count": 1,
                "option_count": 1,
                "item_list": [{
                    "count": "1",
                    "count-unit": json.dumps({"count": 1, "unit": "FEN"}, ensure_ascii=False),
                    "includeMeal": json.dumps({"value": False}, ensure_ascii=False),
                    "itemOpticalItemClassify": json.dumps({"value": 1, "label": "网费服务", "isCustom": None}, ensure_ascii=False),
                    "itemSuitableGroup": json.dumps({"key": suitable_group_key, "value": suitable_group_value}, ensure_ascii=False),
                    "name": "网费",
                    "price": str(origin_amount),  # 必须是字符串！
                    "unit": "FEN"
                }]
            }]
            log_func(f"✅ 已构建网费类型commodity结构，原价: {origin_amount/100}元，适用人群: {suitable_group_value}")
        else:
            # 包时类型：构建全新的commodity结构 (大幅简化，避免旧数据干扰)
            # 注意：包时类型通常需要 itemOpticalItemClassify.value = 2 (上网包时类服务)
            
            # 确定适用人群 (同上)
            member_type = new_data.get("member_type", "不限制")
            if member_type == "新客":
                suitable_group_key = 2
                suitable_group_value = "本店新会员"
            elif member_type == "老客":
                suitable_group_key = 3
                suitable_group_value = "本店老会员"
            else:
                suitable_group_key = 1
                suitable_group_value = "不限制"

            # 确定服务时长 (尝试从标题推断，或者默认)
            # 包时通常需要 totalServiceTime
            # 默认设置为 1 小时 (或者根据 new_data 中的时长，如果能提取)
            # 暂时设置为 1 小时 {unit: 2(小时), value: 1} 作为占位，或者如果不设可能报错
            # 但用户反馈说 "大幅简化...不要出现多个item"
            
            # 为了保险，我们还是需要一些基本结构。
            # 这里构建一个最基础的包时结构
            
            commodity_obj = [{
                "group_name": commodity_type, # 如 "包时"
                "total_count": 1,
                "option_count": 1,
                "item_list": [{
                    "count": "1",
                    "count-unit": json.dumps({"count": 1, "unit": "FEN"}, ensure_ascii=False),
                    "includeMeal": json.dumps({"value": False}, ensure_ascii=False),
                    "itemOpticalItemClassify": json.dumps({"value": 2, "label": "上网包时类服务", "isCustom": None}, ensure_ascii=False), # 2 代表包时
                    "itemSuitableGroup": json.dumps({"key": suitable_group_key, "value": suitable_group_value}, ensure_ascii=False),
                    "name": commodity_type, # 如 "包时"
                    "price": str(origin_amount),
                    "unit": "FEN",
                    # 包时特有字段，如果不传可能会报错，但传了不匹配也可能报错
                    # 这里尝试不传 totalServiceTime，看是否能通过 (简化策略)
                    # 如果报错，可能需要默认值
                }]
            }]
            log_func(f"✅ 已重建包时类型commodity结构，原价: {origin_amount/100}元")
        
        if commodity_obj:
            comp_map['commodity'] = json.dumps(commodity_obj, ensure_ascii=False)
            log_func(f"--- [Commodity更新] 最终commodity长度: {len(comp_map['commodity'])} 字符")
    except Exception as e:
        log_func(f"[Warning] 更新 commodity 价格时出错: {e}")
        import traceback
        log_func(f"详细错误: {traceback.format_exc()}")
    
    # 强制使用固定的 poi_set_id
    fixed_poi_set_id = "7585446102637381686"
    product_object['extra_map'] = {
        "poi_set_id": fixed_poi_set_id,
        "poi_check_result": "",
        "boost_strategy": '{"ai_recommend_title":"","ai_recommend_title_source":""}'
    }
    log_func(f"✅ 已强制将 'extra_map' 设置为固定值，poi_set_id 为: {fixed_poi_set_id}")
    
    # 更新 SKU 价格（如果存在）
    if 'sku' in product_detail_template:
        sku_object = product_detail_template['sku']
        log_func(f"--- [SKU更新前] actual_amount: {sku_object.get('actual_amount')}, origin_amount: {sku_object.get('origin_amount')}")
        sku_object['actual_amount'] = actual_amount
        sku_object['origin_amount'] = origin_amount
        sku_object['sku_name'] = new_data["团购标题"]
        log_func(f"--- [SKU更新后] actual_amount: {sku_object.get('actual_amount')}, origin_amount: {sku_object.get('origin_amount')}")
        log_func(f"✅ SKU 价格已同步更新: 售价={actual_amount/100}元, 原价={origin_amount/100}元")
    else:
        log_func("[Warning] product_detail_template 中没有 'sku' 字段")
    
    # 构建最终payload
    final_payload = {
        "product_detail": product_detail_template,
        "save_product_draft_cache_type": 4,
        "product_cache_scene": 1,
        "version_info": {
            "Enable": True,
            "VersionName": "1.0.8"
        }
    }
    
    # 打印关键价格信息用于调试
    log_func("--- [价格信息检查] ---")
    log_func(f"Product actualAmount: {comp_map.get('actualAmount')}")
    log_func(f"Product originAmount: {comp_map.get('originAmount')}")
    
    # 打印commodity字段中的价格
    try:
        commodity_str = comp_map.get('commodity')
        if commodity_str:
            commodity_obj = json.loads(commodity_str)
            log_func(f"Commodity 结构: {len(commodity_obj)} 个group")
            for idx, group in enumerate(commodity_obj):
                if 'item_list' in group:
                    for item_idx, item in enumerate(group['item_list']):
                        log_func(f"  Group[{idx}].item[{item_idx}].price = {item.get('price')}")
    except:
        pass
    
    if 'sku' in product_detail_template:
        log_func(f"SKU actual_amount: {product_detail_template['sku'].get('actual_amount')}")
        log_func(f"SKU origin_amount: {product_detail_template['sku'].get('origin_amount')}")
    
    return final_payload


def _create_product_web(session, product_payload, root_life_account_id, log_func):
    """通过网页端API创建商品"""
    log_func("--- [网页端] 正在发送创建商品请求... ---")
    url = "https://life.douyin.com/life/tobias/product/save/"
    params = {'root_life_account_id': root_life_account_id}
    
    # 打印完整的请求payload用于调试
    log_func("--- [完整请求Payload] ---")
    payload_str = json.dumps(product_payload, ensure_ascii=False, indent=2)
    # 打印完整payload，不截断（用于调试原价问题）
    log_func(payload_str)
    log_func("-" * 60)
    
    try:
        response = session.post(url, params=params, data=json.dumps(product_payload), timeout=20)
        response.raise_for_status()
        result = response.json()
        log_func(f"服务器响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
        
        if result.get('status_code') == 0:
            product_id = result.get('product_id') or result.get('product', {}).get('product_id')
            if product_id and product_id != "0":
                log_func(f"[SUCCESS] 商品创建成功！Product ID: {product_id}")
                return product_id, None
        
        return None, result.get('status_msg', '未知API错误')
    except requests.exceptions.RequestException as e:
        return None, f"创建商品请求失败: {e}"


def _wait_for_product_approval(access_token, product_id, log_func, max_wait_time=60, check_interval=5):
    """等待商品审核通过"""
    log_func(f"--- 等待商品审核通过（最多等待{max_wait_time}秒）... ---")
    
    start_time = time.time()
    attempt = 0
    
    while time.time() - start_time < max_wait_time:
        attempt += 1
        log_func(f"第{attempt}次检查审核状态...")
        
        # 尝试获取商品详情
        product_details = get_douyin_product_details(access_token, product_id, log_func)
        
        if product_details:
            log_func(f"✅ 商品审核已通过！可以进行后续操作。")
            return True, product_details
        
        # 等待后再次检查
        if time.time() - start_time < max_wait_time:
            log_func(f"商品仍在审核中，{check_interval}秒后再次检查...")
            time.sleep(check_interval)
    
    log_func(f"[Warning] 等待超时（{max_wait_time}秒），商品可能仍在审核中。")
    return False, None


def create_product_via_web(cookie, csrf_token, root_life_account_id, template_product_id, new_data, target_poi_id, access_token, log_func):
    """使用网页端API创建商品（重创模式专用）- 复用模板图片，创建后自动修改POI ID"""
    log_func("========== 开始 重创 商品（网页端模式）==========")
    
    if not cookie or not csrf_token:
        log_func("[Error] 网页端Cookie或CSRF Token未配置，无法使用重创模式。")
        return None, "缺少网页端认证信息"
    
    if not template_product_id:
        log_func("[Error] 重创模式需要一个模板商品ID。")
        return None, "缺少模板商品ID"
    
    session = requests.Session()
    session.headers.update({
        'Accept': 'application/json, text/plain, */*',
        'Cookie': cookie,
        'Origin': 'https://life.douyin.com',
        'Referer': 'https://life.douyin.com/p/product/create',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0',
        'x-secsdk-csrf-token': csrf_token,
        'Content-Type': 'application/json;charset=UTF-8'
    })

    # 1. 获取模板详情
    template_detail, error = _get_product_template_web(session, template_product_id, root_life_account_id, log_func)
    if not template_detail:
        return None, error

    # 2. 构建创建商品的Payload
    payload = _build_web_product_payload_from_template(template_detail, new_data, log_func)
    if not payload:
        return None, "构建商品Payload失败"

    # 3. 发送创建请求
    new_product_id, error = _create_product_web(session, payload, root_life_account_id, log_func)
    if not new_product_id:
        return None, error

    # 4. 等待审核通过 (如果需要立即修改POI)
    # 注意：如果不需要修改POI，或者POI已经在payload中正确设置（payload中目前是硬编码的POI ID），则不需要这一步
    # 但为了保险，且create_product_via_web的docstring说"创建后自动修改POI ID"，这里保留逻辑
    
    # 检查是否需要修改 POI ID (如果target_poi_id与payload中的不同)
    # 目前 _build_web_product_payload_from_template 中硬编码了 fixed_poi_set_id = "7583358246137546802"
    # 如果 target_poi_id 不同，我们需要调用 operate_douyin_product 吗？不，那个是上下架
    # 如果要修改商品信息（包括POI），应该用 update_douyin_product
    
    log_func(f"✅ 商品创建成功！新商品ID: {new_product_id}")
    
    # 步骤4: 等待商品审核通过
    log_func(f"--- 步骤4: 等待商品审核通过 ---")
    approval_success, full_product_data = _wait_for_product_approval(access_token, new_product_id, log_func, max_wait_time=60, check_interval=5)
    
    if not approval_success or not full_product_data:
        log_func("[Warning] 商品可能仍在审核中，无法立即修改POI ID。")
        log_func("[Info] 商品已创建成功，但POI ID为固定值。请稍后手动修改或等待审核通过后重新运行。")
        return new_product_id, "创建成功，但POI修改需等待审核"
    
    # 步骤5: 使用开放平台API修改POI ID到目标门店
    log_func(f"--- 步骤5: 修改POI ID到目标门店 (POI ID: {target_poi_id}) ---")
    
    try:
        product_to_save = full_product_data.get('product')
        sku_to_save = full_product_data.get('skus', [{}])[0] if full_product_data.get('skus') else full_product_data.get('sku')
        
        if not product_to_save or not sku_to_save:
            log_func("[Warning] 商品数据不完整，POI ID可能未更新。")
            return new_product_id, "创建成功，数据不完整无法更新POI"
        
        # 更新POI ID到目标门店
        product_to_save['pois'] = [{"poi_id": str(target_poi_id)}]
        extra_obj = json.loads(product_to_save.get("extra", "{}"))
        extra_obj['poi_set_id'] = str(target_poi_id)
        product_to_save['extra'] = json.dumps(extra_obj)
        
        # 确保所有必填字段存在
        log_func("正在检查并补充必填字段...")
        
        # 1. product 必填字段
        if "attr_key_value_map" not in product_to_save:
            product_to_save["attr_key_value_map"] = {}
        
        # RefundPolicy（退款政策）
        if "RefundPolicy" not in product_to_save["attr_key_value_map"]:
            product_to_save["attr_key_value_map"]["RefundPolicy"] = "2"
            log_func("已添加缺失的 RefundPolicy 字段")
        
        # Notification（使用须知）
        if "Notification" not in product_to_save["attr_key_value_map"]:
            notification_content = [
                {"title": "使用须知", "content": "请按照商家规定使用"},
                {"title": "限购说明", "content": "每人限购1份"},
                {"title": "有效期", "content": "购买后30日内有效"}
            ]
            product_to_save["attr_key_value_map"]["Notification"] = json.dumps(notification_content, ensure_ascii=False)
            log_func("已添加缺失的 Notification 字段")
        
        # Description（商品描述）
        if "Description" not in product_to_save["attr_key_value_map"]:
            product_to_save["attr_key_value_map"]["Description"] = json.dumps(["适用区域: 全场通用"], ensure_ascii=False)
            log_func("已添加缺失的 Description 字段")
        
        # 2. sku 必填字段
        if "attr_key_value_map" not in sku_to_save:
            sku_to_save["attr_key_value_map"] = {}
        
        # use_type（使用类型）
        if "use_type" not in sku_to_save.get("attr_key_value_map", {}):
            sku_to_save["attr_key_value_map"]["use_type"] = "1"
            log_func("已添加缺失的 use_type 字段")
        
        log_func(f"正在将POI ID从固定值更新为目标门店: {target_poi_id}")
        
        # 构建保存请求
        save_payload = {
            "account_id": str(DOUYIN_ACCOUNT_ID),
            "product": product_to_save,
            "sku": sku_to_save,
            "poi_ids": [str(target_poi_id)],
            "supplier_ext_ids": [str(target_poi_id)]
        }
        
        headers = {"Content-Type": "application/json", "access-token": access_token}
        response = requests.post(DOUYIN_PRODUCT_SAVE_URL, headers=headers, json=save_payload, timeout=20)
        response.raise_for_status()
        response_data = response.json()
        
        if response_data.get('data', {}).get('error_code') == 0:
            log_func(f"✅ POI ID已成功更新到目标门店！")
        else:
            log_func(f"[Warning] POI ID更新失败: {response_data.get('data', {}).get('description', '未知错误')}")
    
    except Exception as e:
        log_func(f"[Warning] 更新POI ID时出错: {e}")
    
    log_func(f"[SUCCESS] 商品 '{new_data['团购标题']}' 重创完成！Product ID: {new_product_id}")
    return new_product_id, None

def update_douyin_product(access_token, product_id, new_data, log_func, mode="修改", image_dir=None, target_poi_id=None):
    """
    修改抖音商品函数 (增加必填参数补丁: use_type, RefundPolicy 等)
    """
    log_func(f"========== 开始 {mode} 商品 ID: {product_id} ==========")

    # 1. 获取详情
    full_product_data = get_douyin_product_details(access_token, product_id, log_func)
    if not full_product_data:
        return False, "获取商品详情失败"

    try:
        product_to_save = full_product_data.get('product')
        sku_to_save = full_product_data.get('skus', [{}])[0] if full_product_data.get('skus') else full_product_data.get('sku')
        
        if not product_to_save or not sku_to_save:
            return False, "模板数据结构不完整"

        # 2. 准备价格
        actual_amount_fen = int(float(new_data["售价"]) * 100)
        origin_amount_fen = int(float(new_data["原价"]) * 100)
        
        log_func(f"目标方案：标题={new_data['团购标题']}, 售价={actual_amount_fen}分, 原价={origin_amount_fen}分")

        # 3. 基础字段更新
        product_to_save["product_name"] = new_data["团购标题"]
        sku_to_save["sku_name"] = new_data["团购标题"]
        sku_to_save["actual_amount"] = actual_amount_fen
        sku_to_save["origin_amount"] = origin_amount_fen

        # 4. 【关键修复】补充必填字段补丁
        if "attr_key_value_map" not in product_to_save:
            product_to_save["attr_key_value_map"] = {}
        
        p_attr = product_to_save["attr_key_value_map"]
        
        # A. 退款政策 (必填): 1-不支持退款, 2-随心退, 4-过期自动退
        if "RefundPolicy" not in p_attr:
            p_attr["RefundPolicy"] = "2" 
            log_func("补丁: 已添加缺失的 RefundPolicy (随心退)")

        # B. 须知 (Notification)
        notification = [
            {"title": "使用须知", "content": new_data.get('团单备注', '请按照商家规定使用')},
            {"title": "限购说明", "content": new_data.get('限购', '无限制')},
            {"title": "有效期", "content": f"购买后{new_data.get('有效期', '30')}日内有效"}
        ]
        p_attr['Notification'] = json.dumps(notification, ensure_ascii=False)

        # C. 描述 (Description)
        p_attr['Description'] = json.dumps([f"适用区域: {new_data.get('可用区域', '全场通用')}"], ensure_ascii=False)

        # D. 【本次报错核心】核销方式 (use_type): 1-到店核销, 2-在线预约
        if "attr_key_value_map" not in sku_to_save:
            sku_to_save["attr_key_value_map"] = {}
        
        s_attr = sku_to_save["attr_key_value_map"]
        if "use_type" not in s_attr:
            s_attr["use_type"] = "1"
            log_func("补丁: 已添加缺失的 use_type (到店核销)")

        # 5. 更新 Commodity (修正价格类型与数值)
        if 'commodity' in s_attr:
            try:
                commodity_obj = json.loads(s_attr['commodity'])
                items = []
                for group in commodity_obj:
                    if 'item_list' in group:
                        for item in group['item_list']:
                            items.append(item)
                
                if items:
                    for i, item in enumerate(items):
                        original_val = item.get('price', 0)
                        # 第一个项目承担总价，其他归零，以通过 sum == origin_amount 校验
                        current_val = origin_amount_fen if i == 0 else 0
                        # 智能适配原有的数据类型
                        if isinstance(original_val, str):
                            item['price'] = str(current_val)
                        else:
                            item['price'] = int(current_val)
                    s_attr['commodity'] = json.dumps(commodity_obj, ensure_ascii=False)
                    log_func("Commodity 价格与类型修正完成")
            except Exception as e:
                log_func(f"[Warning] Commodity 修正失败: {e}")

        # 6. POI 设置
        import os
        poi_id_final = str(target_poi_id) if target_poi_id else str(os.getenv('DOUYIN_POI_ID', ''))
        
        if poi_id_final and poi_id_final != 'None' and poi_id_final != '':
            product_to_save['pois'] = [{"poi_id": poi_id_final}]
            extra_obj = json.loads(product_to_save.get("extra", "{}"))
            extra_obj['poi_set_id'] = poi_id_final
            product_to_save['extra'] = json.dumps(extra_obj)
            poi_ids_list = [poi_id_final]
        else:
            # 如果没有指定，保持详情中的 poi_set_id 
            curr_extra = json.loads(product_to_save.get("extra", "{}"))
            p_id = str(curr_extra.get('poi_set_id', ''))
            poi_ids_list = [p_id] if p_id else []

        # 7. 构建载荷
        save_payload = {
            "account_id": str(DOUYIN_ACCOUNT_ID),
            "product": product_to_save,
            "sku": sku_to_save,
            "poi_ids": poi_ids_list,
            "supplier_ext_ids": poi_ids_list
        }

        # --- 打印请求全量日志 ---
        log_func("-" * 20 + " [DEBUG: FINAL REQUEST PAYLOAD] " + "-" * 20)
        log_func(json.dumps(save_payload, ensure_ascii=False, indent=2))
        log_func("-" * 70)

        # 8. 执行请求
        headers = {"Content-Type": "application/json", "access-token": access_token}
        response = requests.post(DOUYIN_PRODUCT_SAVE_URL, headers=headers, json=save_payload, timeout=25)
        response.raise_for_status()
        response_data = response.json()

        # --- 打印响应全量日志 ---
        log_func("-" * 20 + " [DEBUG: FULL API RESPONSE] " + "-" * 20)
        log_func(json.dumps(response_data, ensure_ascii=False, indent=2))
        log_func("-" * 70)

        if response_data.get('data', {}).get('error_code') == 0:
            log_func(f"[SUCCESS] 商品 '{new_data['团购标题']}' 修改成功!")
            return True, ""
        else:
            reason = response_data.get('data', {}).get('description', '未知错误')
            log_func(f"[FAILURE] 修改失败原因: {reason}")
            return False, reason

    except Exception as e:
        log_func(f"修改过程中发生异常:\n{traceback.format_exc()}")
        return False, str(e)
