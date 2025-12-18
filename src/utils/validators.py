"""
数据验证模块 - 验证商品数据的完整性和正确性
"""


def validate_product_data(product_data):
    """验证商品数据"""
    required_fields = ['团购标题', '售价']
    
    for field in required_fields:
        if field not in product_data or not product_data[field]:
            return False, f"缺少必填字段: {field}"
    
    # 验证价格格式
    try:
        price = float(product_data['售价'])
        if price <= 0:
            return False, "售价必须大于0"
    except (ValueError, TypeError):
        return False, "售价格式不正确"
    
    return True, ""


def validate_poi_id(poi_id):
    """验证POI ID格式"""
    if not poi_id or not str(poi_id).strip():
        return False, "POI ID不能为空"
    
    return True, ""


def validate_access_token(access_token):
    """验证Access Token"""
    if not access_token or not str(access_token).strip():
        return False, "Access Token不能为空"
    
    return True, ""
