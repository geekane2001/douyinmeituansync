import gradio as gr
import pandas as pd
import threading
import time
import os
import logging
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pypinyin import pinyin, Style

from src.config import (
    DOUYIN_WEB_COOKIE, DOUYIN_WEB_CSRF_TOKEN,
    DOUYIN_ROOT_LIFE_ACCOUNT_ID
)
from src.api.douyin_api import (
    get_douyin_access_token,
    get_douyin_products_by_store,
    get_douyin_product_details
)
from src.api.feishu_api import (
    get_feishu_tenant_access_token,
    get_feishu_bitable_records
)
from src.api.meituan_api import (
    process_store_name_for_meituan,
    get_meituan_packages
)
from src.core.matching_engine import match_packages_smart
from src.core.product_manager import (
    operate_douyin_product,
    update_douyin_product,
    create_product_via_web
)

# --- 全局日志处理 ---
log_buffer = []
def log_func(message):
    timestamp = time.strftime('%H:%M:%S')
    formatted_msg = f"{timestamp} - {message}"
    log_buffer.append(formatted_msg)
    # 限制日志缓冲区大小
    if len(log_buffer) > 2000:
        log_buffer.pop(0)
    
    # 安全打印到控制台 (处理 Windows GBK 编码问题)
    try:
        print(formatted_msg)
    except UnicodeEncodeError:
        try:
            print(formatted_msg.encode('gbk', errors='ignore').decode('gbk'))
        except:
            print(f"{timestamp} - [Log message contains unprintable characters]")

def get_logs():
    return "\n".join(log_buffer)

# --- 业务逻辑 ---

class AppLogic:
    def __init__(self):
        self.douyin_access_token = None
        self.store_data = {} # name -> {'id': 'xxx', 'city': 'xxx'}
        self.douyin_products = [] # List of dicts
        self.llm_cache = {}
        self.current_poi_id = None
        self.product_details_cache = {}
        self.full_product_df = pd.DataFrame() # 存储完整数据以便过滤
        
        # 初始化后台
        self.init_backend()

    def init_backend(self):
        log_func("正在初始化后台...")
        threading.Thread(target=self._init_thread, daemon=True).start()

    def _init_thread(self):
        self.douyin_access_token = get_douyin_access_token(log_func)
        if not self.douyin_access_token:
            log_func("[Error] 获取抖音Access Token失败")
        
        feishu_token = get_feishu_tenant_access_token(log_func)
        if feishu_token:
            self.store_data = get_feishu_bitable_records(feishu_token, log_func)
            if self.store_data:
                log_func(f"成功加载 {len(self.store_data)} 家门店数据")
        else:
            log_func("[Error] 获取飞书 Token 失败")

    def get_store_names(self):
        if not self.store_data:
            return []
        return sorted(list(self.store_data.keys()))

    def get_store_city_pinyin(self, store_name):
        """获取门店城市的拼音"""
        if not store_name or store_name not in self.store_data:
            return ""
        
        city_cn = self.store_data[store_name].get('city', '')
        if not city_cn:
            return ""
        
        # 去掉 "市"
        city_cn = city_cn.replace("市", "")
        
        # 转拼音
        try:
            # pinyin 返回的是 list of list, e.g., [['wu'], ['xi']]
            pinyin_list = pinyin(city_cn, style=Style.NORMAL)
            city_pinyin = "".join([item[0] for item in pinyin_list])
            log_func(f"城市自动识别: {city_cn} -> {city_pinyin}")
            return city_pinyin
        except Exception as e:
            log_func(f"[Warning] 城市转拼音失败: {e}")
            return ""

    def query_douyin_products(self, store_name, hide_live_only):
        if not store_name:
            log_func("请先选择门店")
            return []
        
        store_info = self.store_data.get(store_name)
        if not store_info:
            log_func(f"未找到门店 {store_name} 的信息")
            return []
            
        poi_id = store_info.get('id')
        if not poi_id:
            log_func(f"未找到门店 {store_name} 的 POI ID")
            return []
        
        self.current_poi_id = poi_id
        self.douyin_products = get_douyin_products_by_store(self.douyin_access_token, poi_id, log_func)
        
        # 过滤仅直播间商品 (并发处理)
        if hide_live_only:
            log_func("正在并发获取详情以过滤直播间商品...")
            filtered_products = []
            
            def fetch_detail(p):
                pid = p['id']
                if pid in self.product_details_cache:
                    return pid, self.product_details_cache[pid]
                try:
                    # 使用空日志函数避免刷屏
                    d = get_douyin_product_details(self.douyin_access_token, pid, lambda x: None)
                    return pid, d
                except:
                    return pid, None

            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {executor.submit(fetch_detail, p): p for p in self.douyin_products}
                for i, future in enumerate(as_completed(futures)):
                    try:
                        pid, details = future.result()
                        if details:
                            self.product_details_cache[pid] = details
                            attr_map = details.get('product', {}).get('attr_key_value_map', {})
                            if str(attr_map.get('show_channel', '1')) == '2':
                                log_func(f"-> 隐藏仅直播间商品: {futures[future]['name']}")
                                continue
                            filtered_products.append(futures[future])
                        else:
                            # 获取失败也保留，以免误删
                            filtered_products.append(futures[future])
                    except Exception as e:
                        log_func(f"处理商品出错: {e}")
                        filtered_products.append(futures[future])
                    
                    if (i+1) % 5 == 0:
                        log_func(f"过滤进度: {i+1}/{len(self.douyin_products)}")
            
            self.douyin_products = filtered_products
            log_func(f"过滤完成，剩余 {len(self.douyin_products)} 个商品")

        df = self.format_products_for_df(self.douyin_products)
        self.full_product_df = df
        return df

    def filter_table(self, filter_mode):
        if self.full_product_df.empty:
            return self.full_product_df
        
        if filter_mode == "全部":
            return self.full_product_df
        elif filter_mode == "仅修改":
            return self.full_product_df[self.full_product_df['操作模式'] == "修改"]
        elif filter_mode == "仅重创":
            return self.full_product_df[self.full_product_df['操作模式'] == "重创"]
        elif filter_mode == "仅保持/下架":
            # 这里的逻辑可能需要根据实际需求调整，比如包括 "保持", "无操作", "下架"
            return self.full_product_df[self.full_product_df['操作模式'].isin(["保持", "无操作", "下架"])]
        return self.full_product_df

    def format_products_for_df(self, products, match_results=None):
        data = []
        for p in products:
            row = {
                "Product ID": p['id'],
                "抖音名称": p['name'],
                "抖音现价": p['price'],
                "抖音原价": p['origin_price'],
                "匹配状态": "未匹配",
                "操作模式": "无操作", # 默认
                "目标名称": "",
                "目标现价": "",
                "目标原价": "",
                "Hidden Data": "{}" # Hidden field for internal data
            }
            if match_results:
                # 查找匹配结果 (这里需要更复杂的逻辑来关联)
                # 暂时简化，直接由 sync_meituan 返回完整的 DF 数据
                pass
            data.append(row)
        return pd.DataFrame(data)

    def sync_meituan(self, store_name, city, skip_price_update):
        if not self.douyin_products:
            log_func("请先查询抖音商品")
            return None

        log_func(f"开始同步美团套餐: {city} - {store_name}")
        cleaned_store_name = process_store_name_for_meituan(store_name, log_func)
        mt_packages = get_meituan_packages(cleaned_store_name, city, log_func)
        
        if not mt_packages:
            log_func("未获取到美团套餐")
            return None

        # 智能匹配
        match_result = match_packages_smart(self.douyin_products, mt_packages, log_func, self.llm_cache)
        
        # 构建 DataFrame 数据
        rows = []
        
        # 1. 匹配上的 (Keep / Update)
        for match in match_result["matches"]:
            dy = match["douyin"]
            mt = match["meituan"]
            action = match["action"]
            
            op_mode = "无操作"
            if action == "keep":
                op_mode = "保持"
            elif action == "update":
                op_mode = "修改"
                if skip_price_update:
                    op_mode = "跳过(用户设置)"

            rows.append({
                "Product ID": dy['id'],
                "抖音名称": dy['name'],
                "抖音现价": dy['price'],
                "抖音原价": dy.get('origin_price', ''),
                "匹配状态": "匹配成功",
                "操作模式": op_mode,
                "目标名称": mt['title'],
                "目标现价": mt['price'],
                "目标原价": mt['original_price'],
                "Hidden Data": json.dumps({
                    "团购标题": mt['title'],
                    "售价": mt['price'],
                    "原价": mt['original_price']
                }, ensure_ascii=False)
            })

        # 2. 美团独有 (Create)
        for mt in match_result["meituan_only"]:
            rows.append({
                "Product ID": "",
                "抖音名称": "<待创建>",
                "抖音现价": "",
                "抖音原价": "",
                "匹配状态": "需新建",
                "操作模式": "重创",
                "目标名称": mt['title'],
                "目标现价": mt['price'],
                "目标原价": mt['original_price'],
                "Hidden Data": json.dumps({
                    "团购标题": mt['title'],
                    "售价": mt['price'],
                    "原价": mt['original_price'],
                    "commodity_type": "网费" if "网费" in mt['title'] else "包时", # 简单推断
                    "applicable_location": "大厅" # 默认
                }, ensure_ascii=False)
            })

        # 3. 抖音独有 (Keep/Delete) - 根据最新逻辑是保留
        matched_dy_ids = {str(m["douyin"]['id']) for m in match_result["matches"]}
        for dy in self.douyin_products:
            if str(dy['id']) not in matched_dy_ids:
                rows.append({
                    "Product ID": dy['id'],
                    "抖音名称": dy['name'],
                    "抖音现价": dy['price'],
                    "抖音原价": dy.get('origin_price', ''),
                    "匹配状态": "未匹配",
                    "操作模式": "保持", # 默认保留
                    "目标名称": "",
                    "目标现价": "",
                    "目标原价": "",
                    "Hidden Data": "{}"
                })

        df = pd.DataFrame(rows)
        self.full_product_df = df
        return df

    def execute_batch_update(self, df):
        if df is None or df.empty:
            log_func("表格为空，无法操作")
            return
        
        # 转换 DataFrame 为 list of dict
        records = df.to_dict('records')
        
        success_count = 0
        fail_count = 0
        
        # 查找模板ID (用于重创)
        template_id = None
        for item in records:
            if item['Product ID'] and item['操作模式'] == "修改":
                template_id = item['Product ID']
                break
        if not template_id and self.douyin_products:
             template_id = self.douyin_products[0]['id']

        log_func(f"开始批量操作 {len(records)} 条记录...")
        
        for item in records:
            mode = item['操作模式']
            pid = item['Product ID']
            new_data = json.loads(item['Hidden Data']) if item['Hidden Data'] else {}
            
            if mode in ["无操作", "保持", "跳过(用户设置)"]:
                continue
                
            success = False
            reason = ""
            
            if mode == "下架": # 虽然目前逻辑是保留，但保留下架功能以防万一
                success, reason = operate_douyin_product(self.douyin_access_token, pid, log_func, offline=True)
            elif mode == "修改":
                # new_data 需要包含更多字段，这里简化了，实际可能需要完善 new_data 的构建
                success, reason = update_douyin_product(self.douyin_access_token, pid, new_data, log_func, mode, target_poi_id=self.current_poi_id)
            elif mode == "重创":
                if not template_id:
                    log_func(f"[Skip] 无法创建 {new_data.get('团购标题')}，缺少模板ID")
                    continue
                # 需要 cookie
                pid_new, reason = create_product_via_web(
                    DOUYIN_WEB_COOKIE, DOUYIN_WEB_CSRF_TOKEN, DOUYIN_ROOT_LIFE_ACCOUNT_ID,
                    template_id, new_data, self.current_poi_id, self.douyin_access_token, log_func
                )
                success = pid_new is not None
            
            if success:
                success_count += 1
            else:
                fail_count += 1
                log_func(f"[Fail] 操作失败: {reason}")
            
            time.sleep(1) # 避免速率限制

        log_func(f"批量操作结束。成功: {success_count}, 失败: {fail_count}")


# --- Gradio 界面构建 ---

logic = AppLogic()

def create_ui():
    with gr.Blocks(title="抖音团购智能同步工具 (Gradio版)") as demo:
        gr.Markdown("## 抖音团购智能同步工具 v3.0")
        
        with gr.Row():
            with gr.Column(scale=1):
                store_dropdown = gr.Dropdown(label="选择门店", choices=[], interactive=True)
                refresh_store_btn = gr.Button("刷新门店列表")
                hide_live_chk = gr.Checkbox(label="隐藏仅直播间商品", value=False)
                query_btn = gr.Button("1. 查询抖音商品", variant="primary")
                
                gr.Markdown("### 美团同步设置")
                # 隐藏城市输入框，由程序自动处理
                city_input = gr.Textbox(label="城市拼音", value="taiyuan", visible=False)
                skip_price_chk = gr.Checkbox(label="仅新增/下架(跳过价格更新)", value=False)
                sync_btn = gr.Button("2. 同步美团套餐", variant="primary")
                
                gr.Markdown("### 筛选视图")
                filter_radio = gr.Radio(["全部", "仅修改", "仅重创", "仅保持/下架"], label="筛选显示", value="全部")
                
                execute_btn = gr.Button("3. 执行批量操作", variant="stop")

            with gr.Column(scale=3):
                # Dataframe to display products
                # 使用 Dataframe 组件，设置为可交互以便查看，但主要通过逻辑更新
                product_table = gr.Dataframe(
                    headers=["Product ID", "抖音名称", "抖音现价", "抖音原价", "匹配状态", "操作模式", "目标名称", "目标现价", "目标原价", "Hidden Data"],
                    datatype=["str", "str", "str", "str", "str", "str", "str", "str", "str", "str"],
                    interactive=True, # 允许用户手动修改 "操作模式" 等
                    label="商品列表"
                )
                
                log_output = gr.TextArea(label="运行日志", lines=15, max_lines=20, autoscroll=True)

        # --- Event Handlers ---
        
        def refresh_stores():
            logic.init_backend() # Re-init to get fresh data
            return gr.Dropdown(choices=logic.get_store_names())

        refresh_store_btn.click(refresh_stores, outputs=store_dropdown)
        
        # 门店选择变化时，自动更新城市拼音
        def on_store_select(store_name):
            city_pinyin = logic.get_store_city_pinyin(store_name)
            return city_pinyin

        store_dropdown.change(on_store_select, inputs=store_dropdown, outputs=city_input)

        # 页面加载时自动获取门店 (需要 trick: 用 load 事件)
        def on_load():
            # 等待后台初始化完成 (简单的 sleep 不太好，但 demo 足够)
            # 实际逻辑已经在 logic.__init__ 启动了线程
            # 我们只需要返回列表
            return gr.Dropdown(choices=logic.get_store_names())
            
        demo.load(on_load, outputs=store_dropdown)

        # 查询抖音
        query_btn.click(
            fn=logic.query_douyin_products,
            inputs=[store_dropdown, hide_live_chk],
            outputs=product_table
        )

        # 同步美团
        sync_btn.click(
            fn=logic.sync_meituan,
            inputs=[store_dropdown, city_input, skip_price_chk],
            outputs=product_table
        )

        # 筛选
        filter_radio.change(
            fn=logic.filter_table,
            inputs=[filter_radio],
            outputs=product_table
        )

        # 执行操作
        execute_btn.click(
            fn=logic.execute_batch_update,
            inputs=[product_table],
            outputs=None # Log output handled by timer
        )

        # 日志自动刷新
        log_timer = gr.Timer(1)
        log_timer.tick(get_logs, outputs=log_output)

    return demo

if __name__ == "__main__":
    ui = create_ui()
    ui.launch(inbrowser=True)