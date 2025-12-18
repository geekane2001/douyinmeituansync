"""
匹配引擎 - 处理抖音和美团套餐的智能匹配
"""
from src.config import (
    DOUYIN_ACCOUNT_ID,
    DOUYIN_PRODUCT_SAVE_URL,
    DOUYIN_PRODUCT_OPERATE_URL,
    DOUYIN_ROOT_LIFE_ACCOUNT_ID
)
from src.api.douyin_api import get_douyin_product_details
from src.core.image_processor import center_crop_image, upload_to_r2
from src.api.llm_api import match_packages_douyin_meituan_llm


def match_packages_smart(douyin_packages, meituan_packages, log_func, cache={}):
    """
    智能匹配抖音和美团套餐 (优先使用LLM智能匹配)
    """
    log_func("\n" + "="*80)
    log_func("开始智能匹配抖音和美团套餐 (LLM Mode)")
    log_func("="*80)
    
    # 打印输入数据概览
    log_func(f"\n[输入数据] 抖音套餐数量: {len(douyin_packages)}")
    log_func(f"[输入数据] 美团套餐数量: {len(meituan_packages)}")
    
    matches = []
    meituan_only = []
    douyin_only = []
    matched_douyin_ids = set()
    matched_meituan_indices = set()
    
    # 特殊套餐列表（不下架）
    special_packages = ["【新老会员】28得30网费", "28得30网费"]
    
    # 调用LLM进行匹配
    llm_result = match_packages_douyin_meituan_llm(douyin_packages, meituan_packages, log_func, cache)
    
    if llm_result and 'matches' in llm_result:
        # 预处理匹配结果，解决多对一冲突（多个美团套餐匹配同一个抖音套餐）
        # 策略：优先保留现价差异最小的匹配
        unique_matches = {} # douyin_id -> {match_data, price_diff}
        
        for m in llm_result['matches']:
            mt_idx = m.get('meituan_index')
            dy_id = m.get('douyin_id')
            
            if mt_idx is not None and dy_id:
                if 0 <= mt_idx < len(meituan_packages):
                    mt_pkg = meituan_packages[mt_idx]
                    dy_pkg = next((p for p in douyin_packages if str(p['id']) == str(dy_id)), None)
                    
                    if dy_pkg:
                        try:
                            dy_price = float(dy_pkg['price'])
                            mt_price = mt_pkg['price']
                            price_diff = abs(dy_price - mt_price)
                        except:
                            price_diff = 9999.0
                            
                        # 如果该抖音ID未被匹配，或者当前匹配的价格差异更小，则更新
                        if str(dy_id) not in unique_matches or price_diff < unique_matches[str(dy_id)]['price_diff']:
                            unique_matches[str(dy_id)] = {
                                'raw_match': m,
                                'mt_pkg': mt_pkg,
                                'dy_pkg': dy_pkg,
                                'price_diff': price_diff
                            }

        # 处理最终的唯一匹配
        for dy_id, match_info in unique_matches.items():
            m = match_info['raw_match']
            mt_pkg = match_info['mt_pkg']
            dy_pkg = match_info['dy_pkg']
            mt_idx = m.get('meituan_index')
            
            # 确定操作类型
            if match_info['price_diff'] < 0.01:
                action = "keep"
            else:
                action = "update"
                
            matches.append({
                "douyin": dy_pkg,
                "meituan": mt_pkg,
                "action": action,
                "reason": m.get('reason', 'LLM Match')
            })
            matched_douyin_ids.add(str(dy_pkg['id']))
            matched_meituan_indices.add(mt_idx)
            
            icon = "✅" if action == "keep" else "🔄"
            log_func(f"  {icon} 匹配: [抖音] {dy_pkg['name']} <==> [美团] {mt_pkg['title']} ({action})")
    
    # 找出美团独有的（需要新建）
    for idx, mt_pkg in enumerate(meituan_packages):
        if idx not in matched_meituan_indices:
            meituan_only.append(mt_pkg)
            log_func(f"  ➕ 新建: [美团] {mt_pkg['title']}")
            
    # 找出抖音独有的（改为保留，不下架）
    for dy_pkg in douyin_packages:
        if str(dy_pkg['id']) not in matched_douyin_ids:
            if dy_pkg['name'] in special_packages:
                log_func(f"  🔒 保留: [抖音] {dy_pkg['name']} (特殊套餐)")
            else:
                # douyin_only.append(dy_pkg) # 不再自动下架
                log_func(f"  🔒 保留: [抖音] {dy_pkg['name']} (无美团对应，保持原样)")

    log_func("\n" + "="*80)
    log_func("匹配结果汇总")
    log_func("="*80)
    log_func(f"✅ 成功匹配: {len(matches)} 个")
    log_func(f"➕ 需要新建: {len(meituan_only)} 个")
    log_func(f"🔒 保持原样: {len(douyin_packages) - len(matched_douyin_ids)} 个 (未匹配到美团套餐)")
    log_func("="*80 + "\n")
    
    return {
        "matches": matches,
        "meituan_only": meituan_only,
        "douyin_only": douyin_only
    }
