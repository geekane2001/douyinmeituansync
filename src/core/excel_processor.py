"""
Excel处理模块 - 处理Excel数据的加载和解析
"""
import pandas as pd
import json
import re
from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell


def load_excel_data(file_path, log_func):
    """加载Excel数据（简化版）"""
    try:
        df = pd.read_excel(file_path, engine='openpyxl', header=1)
        
        # 简单的列名映射
        expected_columns = {
            df.columns[4]: '团购标题',
            df.columns[5]: '售价',
            df.columns[6]: '可用区域',
            df.columns[7]: '限购',
            df.columns[8]: '有效期',
            df.columns[9]: '团单备注'
        }
        
        df.rename(columns=expected_columns, inplace=True)
        df.fillna('', inplace=True)
        
        data = df.to_dict('records')
        log_func(f"[Success] 成功加载 {len(data)} 条Excel数据。")
        return data
    except Exception as e:
        log_func(f"[Error] 加载Excel文件失败: {e}")
        return None


def intelligent_load_excel_data(file_path, log_func, cache):
    """智能加载Excel数据（使用LLM）- 待实现"""
    # 当前使用简化版本
    return load_excel_data(file_path, log_func)


def extract_cells_with_formatting(file_path, log_func):
    """提取Excel单元格内容和格式化信息 - 待实现"""
    log_func("[Info] extract_cells_with_formatting 功能待实现")
    return None


def parse_product_details(details):
    """解析商品详情"""
    if not details or 'product' not in details:
        raise ValueError("无效的商品详情数据")

    product = details.get('product', {})
    sku = details.get('skus', [{}])[0]
    attr_map = product.get('attr_key_value_map', {})

    name = product.get('product_name')
    price = sku.get('actual_amount', 0) / 100
    product_id = product.get('product_id')

    # 默认值
    area, limit, validity, notes = "未知", "未知", "未知", ""

    try:
        notification = json.loads(attr_map.get('Notification', '[]'))
        title_map = {item['title']: item['content'] for item in notification}
        
        validity_text = title_map.get('有效期', '购买后30日内有效')
        validity = validity_text.replace("购买后", "").replace("内有效", "")
        
        limit = title_map.get('限购说明', '无')
        notes = title_map.get('使用须知', '')
        
        desc = json.loads(attr_map.get('Description', '[]'))
        if desc:
            area = desc[0].replace("适用区域: ", "")
    except (json.JSONDecodeError, IndexError, KeyError):
        pass

    return {
        "id": product_id,
        "团购标题": name,
        "售价": price,
        "可用区域": area,
        "限购": limit,
        "有效期": validity,
        "团单备注": notes
    }
