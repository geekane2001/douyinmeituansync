"""
主窗口UI模块 - 应用程序主界面
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import threading
import time
import os
import json
import re
import base64
import logging
from PIL import Image

# 导入配置
from src.config import (
    DOUYIN_WEB_COOKIE, DOUYIN_WEB_CSRF_TOKEN,
    DOUYIN_ROOT_LIFE_ACCOUNT_ID, load_cookie_from_file,
    VISION_MODEL_IDS
)

# 导入API模块
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
from src.api.llm_api import (
    llm_client,
    match_products_with_llm,
    analyze_text_for_actions
)

# 导入核心模块
from src.core.matching_engine import match_packages_smart
from src.core.product_manager import (
    operate_douyin_product,
    update_douyin_product,
    create_product_via_web
)
from src.core.excel_processor import load_excel_data, parse_product_details
from src.core.image_processor import center_crop_image, upload_to_r2


class App(tk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.master = master
        self.master.title("抖音团购智能同步工具 v2.4")
        self.master.geometry("1350x800")
        self.pack(fill="both", expand=True)
        self.store_data, self.douyin_access_token, self.douyin_products, self.excel_data, self.excel_file_path, self.all_store_names, self.image_dir, self.current_poi_id = {}, None, [], [], "", [], None, None
        self.llm_cache = {}
        self.product_details_cache = {}
        self.hide_live_only_var = tk.BooleanVar(value=False)
        self.multi_match_mode_var = tk.BooleanVar(value=False)
        self.edit_entry = None
        self.create_widgets()
        self.init_backend()

    def log(self, message): self.master.after(0, lambda: self._log_thread_safe(message))
    def _log_thread_safe(self, message):
        # GUI日志
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        # 文件日志
        logging.info(message)

    def create_widgets(self):
        top_frame = ttk.Frame(self); top_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(top_frame, text="选择门店:").pack(side="left", padx=(0, 5))
        self.store_name_combobox = ttk.Combobox(top_frame, width=35); self.store_name_combobox.pack(side="left", padx=5)
        self.store_name_combobox.bind('<KeyRelease>', self.filter_combobox_list)
        
        ttk.Label(top_frame, text="排除关键词:").pack(side="left", padx=(10, 5))
        self.exclude_keyword_var = tk.StringVar()
        self.exclude_keyword_entry = ttk.Entry(top_frame, textvariable=self.exclude_keyword_var, width=20); self.exclude_keyword_entry.pack(side="left")

        self.query_douyin_btn = ttk.Button(top_frame, text="1. 查询抖音商品", command=self.start_query_douyin); self.query_douyin_btn.pack(side="left", padx=5)
        self.hide_live_only_check = ttk.Checkbutton(top_frame, text="隐藏仅直播间商品", variable=self.hide_live_only_var, command=self.filter_and_populate_products); self.hide_live_only_check.pack(side="left", padx=10)
        self.web_config_btn = ttk.Button(top_frame, text="⚙️ 网页端配置", command=self.open_web_config); self.web_config_btn.pack(side="left", padx=5)

        excel_frame = ttk.LabelFrame(self, text="Excel 数据源"); excel_frame.pack(fill="x", padx=10, pady=5)
        self.load_excel_btn = ttk.Button(excel_frame, text="2. 加载Excel文件", command=self.start_load_excel); self.load_excel_btn.pack(side="left", padx=5, pady=5)
        self.excel_path_label = ttk.Label(excel_frame, text="未加载文件"); self.excel_path_label.pack(side="left", padx=5)

        image_source_frame = ttk.LabelFrame(self, text="图片源 (用于新增套餐)"); image_source_frame.pack(fill="x", padx=10, pady=5)
        self.select_image_dir_btn = ttk.Button(image_source_frame, text="选择图片文件夹", command=self.select_image_dir); self.select_image_dir_btn.pack(side="left", padx=5, pady=5)
        self.image_dir_label = ttk.Label(image_source_frame, text="未选择文件夹"); self.image_dir_label.pack(side="left", padx=5)
        self.auto_match_image_btn = ttk.Button(image_source_frame, text="自动匹配图片", command=self.start_auto_match_images, state="disabled"); self.auto_match_image_btn.pack(side="left", padx=10)
        self.multi_match_check = ttk.Checkbutton(image_source_frame, text="图片匹配多套餐模式", variable=self.multi_match_mode_var); self.multi_match_check.pack(side="left", padx=10)

        analysis_frame = ttk.LabelFrame(self, text="智能分析 (文本/图片/美团同步)"); analysis_frame.pack(fill="x", padx=10, pady=5)
        self.analysis_text = tk.Text(analysis_frame, height=8, width=80); self.analysis_text.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        analysis_btn_frame = ttk.Frame(analysis_frame); analysis_btn_frame.pack(side="left", fill="y", padx=5)
        self.analyze_text_btn = ttk.Button(analysis_btn_frame, text="分析文本", command=self.start_text_analysis); self.analyze_text_btn.pack(pady=5, fill="x")
        self.sync_meituan_btn = ttk.Button(analysis_btn_frame, text="同步美团套餐", command=self.start_sync_meituan); self.sync_meituan_btn.pack(pady=5, fill="x")
        # 美团同步选项
        self.meituan_skip_update_var = tk.BooleanVar(value=False)
        self.meituan_skip_update_check = ttk.Checkbutton(analysis_btn_frame, text="仅新增/下架\n(跳过价格更新)", variable=self.meituan_skip_update_var); self.meituan_skip_update_check.pack(pady=2, fill="x")
        self.analyze_image_btn = ttk.Button(analysis_btn_frame, text="分析图片 (暂未实现)", state="disabled"); self.analyze_image_btn.pack(pady=5, fill="x")

        main_frame = ttk.Frame(self); main_frame.pack(fill="both", expand=True, padx=10, pady=5)
        columns = ("douyin_name", "douyin_price", "douyin_origin_price", "match_status", "action_mode", "matched_image", "excel_title", "excel_price", "excel_origin_price", "commodity_type", "applicable_location", "excel_area", "excel_limit", "excel_validity", "id")
        self.product_tree = ttk.Treeview(main_frame, columns=columns, show="headings"); self.product_tree.pack(side="left", fill="both", expand=True)
        headings = {
            "douyin_name": "抖音商品名", "douyin_price": "抖音价", "douyin_origin_price": "抖音原价",
            "match_status": "匹配状态", "action_mode": "操作模式", "matched_image": "匹配图片",
            "excel_title": "匹配Excel商品", "excel_price": "Excel价", "excel_origin_price": "Excel原价",
            "commodity_type": "套餐类型", "applicable_location": "适用位置", "excel_area": "可用区域", "excel_limit": "限购", "excel_validity": "有效期",
            "id": "Product ID"
        }
        widths = {
            "douyin_name": 220, "douyin_price": 60, "douyin_origin_price": 60,
            "match_status": 80, "action_mode": 80, "matched_image": 120,
            "excel_title": 220, "excel_price": 60, "excel_origin_price": 60,
            "commodity_type": 80, "applicable_location": 100, "excel_area": 100, "excel_limit": 80, "excel_validity": 60
        }
        for col, text in headings.items(): self.product_tree.heading(col, text=text)
        for col, width in widths.items(): self.product_tree.column(col, width=width, anchor="center" if "price" in col or "status" in col or "validity" in col or "mode" in col else "w")
        self.product_tree["displaycolumns"] = [col for col in columns if col != "id"]
        self.product_tree.bind("<Double-1>", self.edit_cell)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=self.product_tree.yview); self.product_tree.configure(yscroll=scrollbar.set); scrollbar.pack(side="right", fill="y")
        
        bottom_frame = ttk.Frame(self); bottom_frame.pack(fill="both", expand=True, padx=10, pady=5)
        action_frame = ttk.Frame(bottom_frame); action_frame.pack(fill="x", pady=5)
        self.match_btn = ttk.Button(action_frame, text="3. 开始智能匹配", command=self.start_match_products, state="disabled"); self.match_btn.pack(side="left", fill="x", expand=True, padx=5)
        self.delete_btn = ttk.Button(action_frame, text="删除选中行", command=self.delete_selected_rows); self.delete_btn.pack(side="left", fill="x", expand=True, padx=5)
        self.update_btn = ttk.Button(action_frame, text="4. 一键批量操作", command=self.start_batch_update, state="disabled"); self.update_btn.pack(side="left", fill="x", expand=True, padx=5)
        log_frame = ttk.LabelFrame(bottom_frame, text="日志"); log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_frame, wrap="word", state="disabled", height=10); self.log_text.pack(fill="both", expand=True)

    def set_ui_state(self, is_busy):
        state = "disabled" if is_busy else "normal"
        for btn in (self.query_douyin_btn, self.load_excel_btn, self.delete_btn, self.analyze_text_btn, self.select_image_dir_btn, self.auto_match_image_btn): btn.config(state=state)
        self.store_name_combobox.config(state="disabled" if is_busy else "normal")
        self.exclude_keyword_entry.config(state="disabled" if is_busy else "normal")
        self.match_btn.config(state="disabled" if is_busy or not (self.douyin_products and self.excel_data) else "normal")
        self.update_btn.config(state="disabled" if is_busy or not any(self.product_tree.set(item, "match_status") == "匹配成功" for item in self.product_tree.get_children()) else "normal")
        self.auto_match_image_btn.config(state="disabled" if is_busy or not self.image_dir else "normal")

    def open_web_config(self):
        """打开网页端配置对话框"""
        config_window = tk.Toplevel(self.master)
        config_window.title("网页端配置（用于重创模式）")
        config_window.geometry("750x500")
        
        # 标题
        ttk.Label(config_window, text="重创模式 - 网页端API配置", font=("", 12, "bold")).pack(pady=10)
        
        # 配置状态
        status_frame = ttk.LabelFrame(config_window, text="当前配置状态")
        status_frame.pack(fill="x", padx=20, pady=10)
        
        cookie_status = "✅ 已配置" if DOUYIN_WEB_COOKIE else "❌ 未配置"
        csrf_status = "✅ 已配置" if DOUYIN_WEB_CSRF_TOKEN else "❌ 未配置"
        
        ttk.Label(status_frame, text=f"Cookie: {cookie_status}", font=("", 10)).pack(anchor="w", padx=10, pady=5)
        ttk.Label(status_frame, text=f"CSRF Token: {csrf_status}", font=("", 10)).pack(anchor="w", padx=10, pady=5)
        ttk.Label(status_frame, text=f"Cookie来源: cookie.txt 文件", font=("", 9), foreground="gray").pack(anchor="w", padx=10, pady=2)
        ttk.Label(status_frame, text=f"CSRF Token: 硬编码", font=("", 9), foreground="gray").pack(anchor="w", padx=10, pady=2)
        
        # 说明文字
        info_frame = ttk.LabelFrame(config_window, text="配置说明")
        info_frame.pack(fill="x", padx=20, pady=10)
        
        help_text = """
Cookie配置：
• Cookie已从程序根目录的 cookie.txt 文件自动加载
• 如需更新Cookie，请编辑 cookie.txt 文件，然后点击下方"重新加载Cookie"按钮

CSRF Token配置：
• CSRF Token已硬编码在程序中
• 当前值: 000100000001ae8a406b9344d0cc4e30ceaf542c505dbbabca5a3842c450a93e0787a4d2f8991880c8ea9d2d1372

如何获取新的Cookie：
1. 打开浏览器，登录 https://life.douyin.com
2. 按F12打开开发者工具，切换到Network标签
3. 刷新页面，找到任意请求
4. 在Request Headers中复制完整的Cookie值
5. 将Cookie粘贴到程序根目录的 cookie.txt 文件中
        """
        ttk.Label(info_frame, text=help_text, justify="left", foreground="#333").pack(anchor="w", padx=10, pady=10)
        
        # 按钮区域
        button_frame = ttk.Frame(config_window)
        button_frame.pack(pady=10)
        
        def reload_cookie():
            global DOUYIN_WEB_COOKIE
            DOUYIN_WEB_COOKIE = load_cookie_from_file()
            if DOUYIN_WEB_COOKIE:
                messagebox.showinfo("重新加载成功", "Cookie已从 cookie.txt 文件重新加载！")
                config_window.destroy()
                self.open_web_config()  # 重新打开窗口显示新状态
            else:
                messagebox.showerror("加载失败", "无法从 cookie.txt 文件加载Cookie，请检查文件是否存在。")
        
        def open_cookie_file():
            cookie_file = os.path.join(os.path.dirname(__file__), 'cookie.txt')
            if os.path.exists(cookie_file):
                os.startfile(cookie_file)
            else:
                messagebox.showwarning("文件不存在", f"Cookie文件不存在: {cookie_file}\n\n请创建该文件并粘贴Cookie内容。")
        
        ttk.Button(button_frame, text="🔄 重新加载Cookie", command=reload_cookie).pack(side="left", padx=5)
        ttk.Button(button_frame, text="📝 打开cookie.txt", command=open_cookie_file).pack(side="left", padx=5)
        ttk.Button(button_frame, text="关闭", command=config_window.destroy).pack(side="left", padx=5)

    def init_backend(self):
        self.set_ui_state(True)
        threading.Thread(target=self._init_backend_thread, daemon=True).start()

    def _init_backend_thread(self):
        self.douyin_access_token = get_douyin_access_token(self.log)
        if not self.douyin_access_token: messagebox.showerror("错误", "获取抖音Access Token失败。")
        feishu_token = get_feishu_tenant_access_token(self.log)
        if feishu_token:
            self.store_data = get_feishu_bitable_records(feishu_token, self.log)
            if self.store_data: self.master.after(0, self.update_store_combobox)
        self.master.after(0, lambda: self.set_ui_state(False))

    def select_image_dir(self):
        dir_path = filedialog.askdirectory(title="选择包含头图的文件夹")
        if dir_path:
            self.image_dir = dir_path
            self.image_dir_label.config(text=f"已选: {os.path.basename(dir_path)}")
            self.log(f"新增套餐的图片源文件夹已设置为: {dir_path}")

    def update_store_combobox(self):
        self.all_store_names = sorted(list(self.store_data.keys()))
        self.store_name_combobox['values'] = self.all_store_names
        if self.all_store_names: self.store_name_combobox.set(self.all_store_names[0])
        self.log("门店下拉列表已更新。")

    def filter_combobox_list(self, event):
        typed_text = self.store_name_combobox.get().lower()
        self.store_name_combobox['values'] = [name for name in self.all_store_names if typed_text in name.lower()] if typed_text else self.all_store_names

    def start_query_douyin(self):
        store_name = self.store_name_combobox.get().strip()
        if not store_name: return messagebox.showerror("错误", "请选择一个门店。")
        poi_id = self.store_data.get(store_name)
        if not poi_id: return messagebox.showerror("错误", f"未找到门店 '{store_name}' 的ID。")
        self.set_ui_state(True)
        threading.Thread(target=self._query_douyin_thread, args=(poi_id,), daemon=True).start()
    
    def _query_douyin_thread(self, poi_id):
        self.current_poi_id = poi_id
        self.product_details_cache.clear()
        all_products = get_douyin_products_by_store(self.douyin_access_token, poi_id, self.log)
        
        exclude_string = self.exclude_keyword_var.get().strip()
        if exclude_string:
            # Use regex to split by spaces, commas (English/Chinese), and semicolons
            exclude_keywords = [kw for kw in re.split(r'[ ,;，；]+', exclude_string) if kw]
            if exclude_keywords:
                self.log(f"开始根据排除关键词 {exclude_keywords} 过滤商品...")
                # Filter products: exclude if ANY keyword is present in the name
                self.douyin_products = [
                    p for p in all_products
                    if not any(keyword in p['name'] for keyword in exclude_keywords)
                ]
                self.log(f"过滤后剩余 {len(self.douyin_products)} 个商品。")
            else:
                self.douyin_products = all_products
        else:
            self.douyin_products = all_products

        self.master.after(0, self.filter_and_populate_products)
        self.master.after(0, lambda: self.set_ui_state(False))

    def populate_product_list(self, products_to_show):
        self.product_tree.delete(*self.product_tree.get_children())
        for pkg in products_to_show:
            # columns = ("douyin_name", "douyin_price", "douyin_origin_price", "match_status", "action_mode", "excel_title", "excel_price", "excel_origin_price", "excel_area", "excel_limit", "excel_validity", "id")
            values = (
                pkg['name'], pkg['price'], pkg.get('origin_price', '0.00'),
                "未匹配", "修改", "",
                "", "", "", "", "", "",
                pkg['id']
            )
            self.product_tree.insert("", "end", values=values)
        self.log(f"抖音商品列表已更新，共 {len(products_to_show)} 项。")
    
    def filter_and_populate_products(self):
        self.set_ui_state(True)
        self.log("正在应用筛选条件...")
        threading.Thread(target=self._filter_worker_thread, daemon=True).start()

    def _filter_worker_thread(self):
        hide_live_only = self.hide_live_only_var.get()
        
        # 如果不需要过滤，直接显示所有商品
        # 但为了保证数据完整性（如果用户希望获取更详细信息），这里保持原来的逻辑：不勾选就不获取详情
        # 用户的反馈 "无论是否勾选...都应该并发处理" 可能是指在执行获取详情这个动作时要并发。
        # 如果不勾选，根本不执行获取详情，所以也就没有并发的问题。
        # 除非用户意图是：无论是否勾选，都要获取详情（为了其他目的？），且要并发。
        # 鉴于目前架构，如果不勾选，列表显示的是 query 接口返回的基础信息，已经包含了价格，基本够用。
        # 这里仅对 "勾选过滤" 的情况进行并发优化。
        
        if not hide_live_only:
            self.master.after(0, lambda: self.populate_product_list(self.douyin_products))
            self.master.after(0, lambda: self.set_ui_state(False))
            return

        self.log("筛选开启：隐藏仅直播间可见商品。正在并发获取详情...")
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        filtered_products = []
        total = len(self.douyin_products)
        
        # 准备任务
        tasks = []
        # 使用锁来保护共享资源（虽然这里主要是在主线程汇总，但log可能需要）
        # 实际上 product_details_cache 是共享的
        
        def fetch_detail_task(index, product):
            product_id = product['id']
            if product_id in self.product_details_cache:
                return product_id, self.product_details_cache[product_id]
            
            # self.log 是线程安全的吗？_log_thread_safe 使用了 master.after，是安全的。
            # 减少日志输出频率，避免界面卡顿
            # self.log(f"正在获取 ({index+1}/{total}): {product['name'][:10]}...")
            details = get_douyin_product_details(self.douyin_access_token, product_id, lambda x: None) # 传入空log函数减少刷屏
            return product_id, details

        # 并发执行，最大线程数设为 5
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_product = {executor.submit(fetch_detail_task, i, p): p for i, p in enumerate(self.douyin_products)}
            
            completed_count = 0
            for future in as_completed(future_to_product):
                p = future_to_product[future]
                completed_count += 1
                try:
                    pid, details = future.result()
                    if details:
                        self.product_details_cache[pid] = details
                        
                        # 检查过滤条件
                        if 'product' in details:
                            attr_map = details.get('product', {}).get('attr_key_value_map', {})
                            show_channel = str(attr_map.get('show_channel', '1'))
                            if show_channel == '2':
                                self.log(f" -> 已隐藏 (仅直播间): {p['name']}")
                                continue
                        
                        filtered_products.append(p)
                    else:
                        self.log(f"[Warning] 获取详情失败: {p['name']}")
                except Exception as e:
                    self.log(f"[Error] 处理商品 {p['name']} 时出错: {e}")
                
                # 简单的进度提示
                if completed_count % 5 == 0 or completed_count == total:
                    self.log(f"进度: {completed_count}/{total}")

        # 保持原有顺序（可选，如果需要）
        # filtered_products.sort(key=lambda x: self.douyin_products.index(x))

        self.master.after(0, lambda: self.populate_product_list(filtered_products))
        self.master.after(0, lambda: self.set_ui_state(False))

    def start_load_excel(self):
        file_path = filedialog.askopenfilename(title="选择Excel文件", filetypes=(("Excel files", "*.xlsx"), ("All files", "*.*")))
        if not file_path: return
        self.excel_file_path = file_path; self.set_ui_state(True)
        threading.Thread(target=self._load_excel_thread, args=(file_path,), daemon=True).start()

    def _load_excel_thread(self, file_path):
        self.excel_data = load_excel_data(file_path, self.log)
        if self.excel_data is not None: self.master.after(0, lambda: self.excel_path_label.config(text=os.path.basename(file_path)))
        else: messagebox.showerror("错误", "加载Excel文件失败。")
        self.master.after(0, lambda: self.set_ui_state(False))

    def select_image_dir(self):
        dir_path = filedialog.askdirectory(title="选择包含头图的文件夹")
        if dir_path:
            self.image_dir = dir_path
            self.image_dir_label.config(text=f"已选: {os.path.basename(dir_path)}")
            self.log(f"新增套餐的图片源文件夹已设置为: {dir_path}")

    def start_match_products(self):
        if not self.excel_data:
            messagebox.showinfo("提示", "请先加载Excel文件。")
            return

        current_products_in_tree = []
        for item_id in self.product_tree.get_children():
            douyin_name = self.product_tree.set(item_id, "douyin_name")
            # 只对实际的抖音商品进行匹配，忽略待创建的行
            if douyin_name and douyin_name != "<待创建>":
                current_products_in_tree.append({
                    "name": douyin_name,
                    "price": self.product_tree.set(item_id, "douyin_price"),
                    "origin_price": self.product_tree.set(item_id, "douyin_origin_price"),
                    "id": self.product_tree.set(item_id, "id")
                })
        
        if not current_products_in_tree:
            messagebox.showinfo("提示", "抖音商品列表为空，无法进行匹配。")
            return

        self.set_ui_state(True)
        threading.Thread(target=self._match_products_thread, args=(current_products_in_tree,), daemon=True).start()

    def _match_products_thread(self, current_douyin_products):
        match_result = match_products_with_llm(current_douyin_products, self.excel_data, self.log, self.llm_cache)
        if match_result: self.master.after(0, lambda: self.update_matches_in_tree(match_result))
        self.master.after(0, lambda: self.set_ui_state(False))

    def update_matches_in_tree(self, match_result):
        excel_map = {item['团购标题']: item for item in self.excel_data}
        for item_id in self.product_tree.get_children():
            douyin_name = self.product_tree.set(item_id, "douyin_name")
            matched_excel_title = match_result.get(douyin_name)
            if matched_excel_title in excel_map:
                excel_item = excel_map[matched_excel_title]
                self.product_tree.set(item_id, "match_status", "匹配成功")
                self.product_tree.set(item_id, "excel_title", matched_excel_title)
                self.product_tree.set(item_id, "excel_price", excel_item.get('售价', ''))
                self.product_tree.set(item_id, "excel_area", excel_item.get('可用区域', ''))
                self.product_tree.set(item_id, "excel_limit", excel_item.get('限购', ''))
                self.product_tree.set(item_id, "excel_validity", excel_item.get('有效期', ''))
                self.product_tree.set(item_id, "action_mode", "重创" if "重置次数" in str(excel_item.get('可用区域', '')) else "修改")
            else:
                self.product_tree.set(item_id, "match_status", "匹配失败")
                self.product_tree.set(item_id, "action_mode", "-")
                for col in ("excel_title", "excel_price", "excel_area", "excel_limit", "excel_validity"): self.product_tree.set(item_id, col, "")
        self.log("LLM匹配结果已更新到界面。")

    def edit_cell(self, event):
        if hasattr(self, 'edit_entry') and self.edit_entry:
            self.edit_entry.destroy()

        item_id = self.product_tree.focus()
        if not item_id: return

        column_id = self.product_tree.identify_column(event.x)
        column_name = self.product_tree.column(column_id, "id")

        if column_name == "action_mode":
            current_mode = self.product_tree.set(item_id, "action_mode")
            modes = ["修改", "重创", "下架", "-"]
            try:
                new_mode = modes[(modes.index(current_mode) + 1) % len(modes)]
            except ValueError:
                new_mode = "修改"
            self.product_tree.set(item_id, "action_mode", new_mode)
            return

        editable_columns = ["excel_title", "excel_price", "excel_origin_price", "commodity_type", "applicable_location", "excel_area", "excel_limit", "excel_validity", "matched_image"]
        if column_name not in editable_columns:
            return

        x, y, width, height = self.product_tree.bbox(item_id, column_id)
        value = self.product_tree.set(item_id, column_name)
        
        entry_var = tk.StringVar(value=value)
        self.edit_entry = ttk.Entry(self.product_tree, textvariable=entry_var)
        self.edit_entry.place(x=x, y=y, width=width, height=height)
        self.edit_entry.focus_force()
        self.edit_entry.selection_range(0, tk.END)

        def on_edit_done(event=None):
            new_value = entry_var.get()
            self.product_tree.set(item_id, column_name, new_value)
            if hasattr(self, 'edit_entry') and self.edit_entry:
                self.edit_entry.destroy()
                self.edit_entry = None
        
        self.edit_entry.bind("<Return>", on_edit_done)
        self.edit_entry.bind("<FocusOut>", on_edit_done)
        self.edit_entry.bind("<Escape>", lambda e: self.edit_entry.destroy() if hasattr(self, 'edit_entry') and self.edit_entry else None)

    def delete_selected_rows(self):
        selected_items = self.product_tree.selection()
        if not selected_items: return messagebox.showinfo("提示", "请先选择要删除的行。")
        if messagebox.askyesno("确认删除", f"确定要删除选中的 {len(selected_items)} 行吗？此操作仅在界面上移除，不影响线上商品。"):
            for item in selected_items: self.product_tree.delete(item)
            self.log(f"已从界面删除 {len(selected_items)} 行。")

    def start_sync_meituan(self):
        """开始美团同步"""
        if not self.douyin_products:
            messagebox.showerror("错误", "请先查询抖音商品列表")
            return
        
        store_name = self.store_name_combobox.get().strip()
        if not store_name:
            messagebox.showerror("错误", "请选择门店")
            return
        
        # 使用simpledialog询问城市拼音
        from tkinter import simpledialog
        city = simpledialog.askstring(
            "输入城市信息",
            "请输入城市拼音（如：taiyuan）:",
            initialvalue="taiyuan",
            parent=self.master
        )
        
        if not city or not city.strip():
            return
        
        self.set_ui_state(True)
        threading.Thread(target=self._sync_meituan_thread, args=(store_name, city.strip()), daemon=True).start()
    
    def _sync_meituan_thread(self, store_name, city):
        """美团同步线程"""
        self.log("========== 开始美团同步 ==========")
        
        # 1. 处理店名
        cleaned_store_name = process_store_name_for_meituan(store_name, self.log)
        
        # 2. 获取美团套餐
        meituan_packages = get_meituan_packages(cleaned_store_name, city, self.log)
        
        if not meituan_packages:
            self.log("[Error] 未能获取美团套餐，同步终止")
            self.master.after(0, lambda: messagebox.showerror("错误", "未能获取美团套餐，请检查网络和代理设置"))
            self.master.after(0, lambda: self.set_ui_state(False))
            return
        
        # 3. 智能匹配
        match_result = match_packages_smart(self.douyin_products, meituan_packages, self.log, self.llm_cache)
        
        # 获取用户选项：是否跳过价格更新
        skip_price_update = self.meituan_skip_update_var.get()
        if skip_price_update:
            self.log("\n[用户选项] 已启用'仅新增/下架'模式，将跳过所有价格更新操作")
        
        # 4. 构建操作列表
        operations = []
        
        # 4.1 匹配的套餐 - 根据action和用户选项决定是否更新
        for match in match_result["matches"]:
            dy_pkg = match["douyin"]
            mt_pkg = match["meituan"]
            action = match["action"]
            
            if action == "update":
                if skip_price_update:
                    # 用户选择跳过价格更新
                    self.log(f"跳过价格更新: {dy_pkg['name']} (用户选择仅新增/下架)")
                else:
                    # 价格不同，需要更新
                    operations.append({
                        "action": "update",
                        "product_id": dy_pkg['id'],
                        "douyin_name": dy_pkg['name'],
                        "new_data": {
                            "团购标题": mt_pkg['title'],  # 更新为美团名称，保持一致
                            "售价": mt_pkg['price'],
                            "原价": mt_pkg['original_price'],
                            "可用区域": "",
                            "限购": "",
                            "有效期": "",
                            "团单备注": ""
                        }
                    })
            elif action == "keep":
                # 价格相同，保持原样，但也添加到操作列表以便在UI显示
                self.log(f"保持原样: {dy_pkg['name']} (价格已同步)")
                operations.append({
                    "action": "keep",
                    "product_id": dy_pkg['id'],
                    "douyin_name": dy_pkg['name'],
                    "new_data": {
                        "团购标题": mt_pkg['title'],  # 显示美团名称
                        "售价": mt_pkg['price'],
                        "原价": mt_pkg['original_price'],
                        "可用区域": "",
                        "限购": "",
                        "有效期": "",
                        "团单备注": ""
                    }
                })
        
        # 4.2 美团独有 - 新建
        for mt_pkg in match_result["meituan_only"]:
            operations.append({
                "action": "add",
                "product_id": None,
                "douyin_name": "<待创建>",
                "new_data": {
                    "团购标题": mt_pkg['title'],
                    "售价": mt_pkg['price'],
                    "原价": mt_pkg['original_price'],
                    "member_type": "不限制",
                    "commodity_type": "网费" if "网费" in mt_pkg['title'] else "包时",
                    "applicable_location": "大厅",
                    "可用区域": "",
                    "限购": "",
                    "有效期": "30",
                    "团单备注": ""
                }
            })
        
        # 4.3 抖音独有 - 下架
        for dy_pkg in match_result["douyin_only"]:
            operations.append({
                "action": "delete",
                "product_id": dy_pkg['id'],
                "douyin_name": dy_pkg['name'],
                "new_data": {"团购标题": f"下架-{dy_pkg['name']}"}
            })
        
        # 5. 统计操作类型
        update_count = sum(1 for op in operations if op["action"] == "update")
        add_count = sum(1 for op in operations if op["action"] == "add")
        delete_count = sum(1 for op in operations if op["action"] == "delete")
        
        # 6. 更新UI显示
        self.master.after(0, lambda: self._populate_meituan_sync_result(operations))
        self.master.after(0, lambda: self.set_ui_state(False))
        
        # 7. 输出汇总信息
        self.log(f"\n========== 美团同步分析完成 ==========")
        self.log(f"总操作数: {len(operations)} 个")
        self.log(f"  - 价格更新: {update_count} 个")
        self.log(f"  - 新增套餐: {add_count} 个")
        self.log(f"  - 下架套餐: {delete_count} 个")
        if skip_price_update and update_count == 0:
            skipped_updates = sum(1 for m in match_result["matches"] if m["action"] == "update")
            if skipped_updates > 0:
                self.log(f"  - 已跳过价格更新: {skipped_updates} 个（用户选择）")
        self.log(f"========================================\n")
    
    def _populate_meituan_sync_result(self, operations):
        """将美团同步结果填充到表格"""
        self.product_tree.delete(*self.product_tree.get_children())
        self.excel_data = []
        
        for op in operations:
            action = op["action"]
            product_id = op.get("product_id", "")
            douyin_name = op.get("douyin_name", "")
            new_data = op["new_data"]
            
            self.excel_data.append(new_data)
            
            if action == "update":
                action_mode = "修改"
                douyin_price = next((p['price'] for p in self.douyin_products if p['id'] == product_id), "")
                douyin_origin_price = next((p['origin_price'] for p in self.douyin_products if p['id'] == product_id), "")
            elif action == "keep":
                action_mode = "无操作" # 或者 "保持"
                douyin_price = next((p['price'] for p in self.douyin_products if p['id'] == product_id), "")
                douyin_origin_price = next((p['origin_price'] for p in self.douyin_products if p['id'] == product_id), "")
            elif action == "add":
                action_mode = "重创"
                douyin_price = ""
                douyin_origin_price = ""
            else:  # delete
                action_mode = "下架"
                douyin_price = next((p['price'] for p in self.douyin_products if p['id'] == product_id), "")
                douyin_origin_price = next((p['origin_price'] for p in self.douyin_products if p['id'] == product_id), "")
            
            values = (
                douyin_name, douyin_price, douyin_origin_price,
                "匹配成功", action_mode, "",
                new_data.get('团购标题'), new_data.get('售价'), new_data.get('原价'),
                new_data.get('commodity_type', ''), new_data.get('applicable_location', ''),
                new_data.get('可用区域'), new_data.get('限购'), new_data.get('有效期'),
                product_id
            )
            
            if action == "keep":
                tag = 'keep'
            else:
                tag = 'update' if action == "update" else ('add' if action == "add" else 'delete')
            self.product_tree.insert("", "end", values=values, tags=(tag,))
        
        self.product_tree.tag_configure('add', background='#D4EDDA')
        self.product_tree.tag_configure('update', background='#FFF3CD')
        self.product_tree.tag_configure('delete', background='#F8D7DA')
        self.product_tree.tag_configure('keep', background='#FFFFFF') # 白色背景表示保持
        
        self.log("美团同步结果已更新到界面，请检查后执行'一键批量操作'")
        self.update_btn.config(state="normal")

    def start_text_analysis(self):
        if not self.douyin_products:
            if not messagebox.askyesno("确认操作", "当前门店没有线上商品或未查询。\n\n这会导致AI无法进行'修改'或'下架'的判断。\n\n是否继续，只执行纯'新增'操作？"):
                return
        
        text_to_analyze = self.analysis_text.get("1.0", tk.END).strip()
        if not text_to_analyze:
            messagebox.showerror("错误", "请输入需要分析的文本内容。")
            return
            
        if not messagebox.askyesno("确认操作", "这将使用LLM分析文本并覆盖当前表格内容，确定要继续吗？"):
            return

        self.set_ui_state(True)
        threading.Thread(target=self._text_analysis_thread, args=(text_to_analyze,), daemon=True).start()

    def _text_analysis_thread(self, text_to_analyze):
        self.log("--- 开始使用LLM进行文本智能分析 ---")
        
        # 直接使用已有的简略商品列表，无需重新获取详情
        simple_product_list = self.douyin_products
        self.log(f"已加载 {len(simple_product_list)} 个线上商品用于分析。")

        analysis_result = analyze_text_for_actions(text_to_analyze, simple_product_list, self.log, self.llm_cache)
        
        if analysis_result:
            self.master.after(0, lambda: self.populate_tree_from_analysis(analysis_result))
        else:
            self.log("[Error] 文本分析失败，未能获取有效结果。")
            
        self.master.after(0, lambda: self.set_ui_state(False))

    def populate_tree_from_analysis(self, analysis_result):
        self.log("--- 正在根据文本分析结果更新列表 ---")
        self.product_tree.delete(*self.product_tree.get_children())
        
        douyin_products_map = {p['name']: p for p in self.douyin_products}
        self.excel_data = []
        processed_douyin_products = set()

        # columns = ("douyin_name", "douyin_price", "douyin_origin_price", "match_status", "action_mode", "excel_title", "excel_price", "excel_origin_price", "excel_area", "excel_limit", "excel_validity", "id")
        for new_data in analysis_result.get('add', []):
            self.excel_data.append(new_data)
            values = (
                "<待创建>", "", "",
                "匹配成功", "重创", "",
                new_data.get('团购标题'), new_data.get('售价'), new_data.get('原价'),
                new_data.get('commodity_type'), new_data.get('applicable_location', '大厅'), new_data.get('可用区域'), new_data.get('限购'), new_data.get('有效期'), ""
            )
            self.product_tree.insert("", "end", values=values, tags=('add',))

        for update_item in analysis_result.get('update', []):
            from_name = update_item.get('from_name')
            new_data = update_item.get('new_data')
            if from_name in douyin_products_map and new_data:
                product = douyin_products_map[from_name]
                self.excel_data.append(new_data)
                values = (
                    product['name'], product['price'], product.get('origin_price', '0.00'),
                    "匹配成功", "修改", "",
                    new_data.get('团购标题'), new_data.get('售价'), new_data.get('原价'),
                    new_data.get('commodity_type', ''), new_data.get('applicable_location', ''),
                    new_data.get('可用区域'), new_data.get('限购'), new_data.get('有效期'), product['id']
                )
                self.product_tree.insert("", "end", values=values, tags=('update',))
                processed_douyin_products.add(from_name)

        for delete_item in analysis_result.get('delete', []):
            name = delete_item.get('name')
            if name in douyin_products_map:
                product = douyin_products_map[name]
                new_data = {"团购标题": f"下架-{name}"}
                self.excel_data.append(new_data)
                values = (
                    product['name'], product['price'], product.get('origin_price', '0.00'),
                    "匹配成功", "下架", "",
                    f"下架-{name}", "", "", "", "", "", product['id']
                )
                self.product_tree.insert("", "end", values=values, tags=('delete',))
                processed_douyin_products.add(name)

        for name, product in douyin_products_map.items():
            if name not in processed_douyin_products:
                values = (
                    product['name'], product['price'], product.get('origin_price', '0.00'),
                    "无操作", "-", "", "", "", "", "", "", "", product['id']
                )
                self.product_tree.insert("", "end", values=values, tags=('keep',))
        
        self.product_tree.tag_configure('add', background='#D4EDDA')
        self.product_tree.tag_configure('update', background='#FFF3CD')
        self.product_tree.tag_configure('delete', background='#F8D7DA')

        self.log("列表已根据分析结果更新。请检查并执行“一键批量操作”。")
        self.update_btn.config(state="normal")

    def start_batch_update(self):
        if hasattr(self, 'edit_entry') and self.edit_entry:
            self.edit_entry.destroy()
            self.edit_entry = None
            
        items_to_process = []
        for item_id in self.product_tree.get_children():
            action_mode = self.product_tree.set(item_id, "action_mode")
            if action_mode == "-" or action_mode == "无操作":
                continue

            try:
                # 从Treeview中直接读取最终确认的数据
                excel_title_from_tree = self.product_tree.set(item_id, "excel_title")
                full_data_from_excel = next((d for d in self.excel_data if d.get("团购标题") == excel_title_from_tree), {})

                new_data = {
                    "团购标题": excel_title_from_tree,
                    "售价": float(self.product_tree.set(item_id, "excel_price") or 0),
                    "原价": float(self.product_tree.set(item_id, "excel_origin_price") or 0),
                    "可用区域": self.product_tree.set(item_id, "excel_area"),
                    "限购": self.product_tree.set(item_id, "excel_limit"),
                    "有效期": self.product_tree.set(item_id, "excel_validity"),
                    "团单备注": "", # 备注字段目前不在表格中，默认为空
                    "matched_image": self.product_tree.set(item_id, "matched_image"),
                    "member_type": full_data_from_excel.get("member_type"),
                    "commodity_type": self.product_tree.set(item_id, "commodity_type"),
                    "applicable_location": self.product_tree.set(item_id, "applicable_location")
                }
                
                # 对“下架”操作进行特殊处理
                if action_mode == "下架":
                    original_name = self.product_tree.set(item_id, "douyin_name")
                    new_data["团购标题"] = f"下架-{original_name}"

                item_to_add = {
                    "product_id": self.product_tree.set(item_id, "id"),
                    "new_data": new_data,
                    "action_mode": action_mode
                }
                items_to_process.append(item_to_add)
            except ValueError:
                messagebox.showerror("数据错误", f"商品 '{self.product_tree.set(item_id, 'excel_title')}' 的价格格式不正确，请确保为数字。")
                return
            except Exception as e:
                messagebox.showerror("未知错误", f"处理行数据时发生错误: {e}")
                return

        if not items_to_process: return messagebox.showinfo("提示", "没有找到任何需要操作的商品（操作模式不为'-'或'无操作'）。")
        if not messagebox.askyesno("确认操作", f"即将处理 {len(items_to_process)} 个商品。此操作不可逆，是否继续？"): return
        self.set_ui_state(True)
        threading.Thread(target=self._batch_process_thread, args=(items_to_process,), daemon=True).start()

    def start_auto_match_images(self):
        if not self.image_dir:
            messagebox.showerror("错误", "请先选择一个图片文件夹。")
            return
        
        add_items = []
        for item_id in self.product_tree.get_children():
            if self.product_tree.set(item_id, "action_mode") == "重创":
                add_items.append(self.product_tree.set(item_id, "excel_title"))

        if not add_items:
            messagebox.showinfo("提示", "表格中没有找到需要'重创'的新增套餐。")
            return

        self.set_ui_state(True)
        threading.Thread(target=self._auto_match_images_thread, args=(add_items,), daemon=True).start()

    def _auto_match_images_thread(self, add_items):
        self.log("--- 开始智能匹配套餐和图片 ---")
        if not llm_client:
            self.log("[Error] LLM客户端未初始化，无法进行智能匹配。")
            self.master.after(0, lambda: self.set_ui_state(False))
            return
        
        # 1. AI分析图片文件夹中的图片
        self.log("步骤 1/2: 正在使用AI分析图片内容...")
        image_summaries = []
        supported_formats = (".jpg", ".jpeg", ".png", ".bmp")
        model_index = 0
        try:
            image_files = [f for f in os.listdir(self.image_dir) if f.lower().endswith(supported_formats)]
            for filename in image_files:
                try:
                    full_path = os.path.join(self.image_dir, filename)
                    with open(full_path, "rb") as image_file:
                        base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                    
                    image_url = f"data:image/jpeg;base64,{base64_image}"
                    
                    selected_vision_model = VISION_MODEL_IDS[model_index % len(VISION_MODEL_IDS)]
                    self.log(f"使用视觉模型: {selected_vision_model}")
                    model_index += 1
                    
                    response = llm_client.chat.completions.create(
                        model=selected_vision_model,
                        messages=[{
                            'role': 'user',
                            'content': [{
                                'type': 'text',
                                'text': '根据图片内容，为其生成一个简短且描述性的中文名（不要带扩展名）。例如，如果图片是关于500元网费套餐，就返回"500元网费"。',
                            }, {
                                'type': 'image_url',
                                'image_url': { 'url': image_url },
                            }],
                        }]
                    )
                    summary = response.choices[0].message.content.strip()
                    self.log(f"--- [Vision LLM Raw Response for Image Summary] ---\n{summary}\n" + "-"*30)
                    image_summaries.append({"original_filename": filename, "summary": summary})
                    self.log(f"分析图片 '{filename}' -> AI摘要: '{summary}'")
                except Exception as e:
                    self.log(f"[Error] 分析图片 {filename} 时出错: {e}")
        except Exception as e:
            self.log(f"[Error] 遍历图片文件夹时出错: {e}")
            self.master.after(0, lambda: self.set_ui_state(False))
            return

        if not image_summaries:
            self.log("[Error] 未能成功分析任何图片。")
            self.master.after(0, lambda: self.set_ui_state(False))
            return

        # 2. AI匹配文本
        self.log("步骤 2/2: 正在使用AI匹配图片摘要和套餐标题...")
        image_summary_list = [item['summary'] for item in image_summaries]
        
        multi_mode = self.multi_match_mode_var.get()
        if multi_mode:
            self.log("--- 当前为 [图片匹配多套餐] 模式 ---")
            prompt = f"""
            现有以下需要创建的套餐列表：
            {json.dumps(add_items, ensure_ascii=False)}

            以及以下从图片中分析出的摘要列表：
            {json.dumps(image_summary_list, ensure_ascii=False)}

            任务：对于每一个“图片摘要”，判断它可以匹配到哪些“套餐列表”中的项目。匹配应该是基于核心关键词的包含关系。
            例如，摘要“网费”可以匹配所有标题中包含“网费”的套餐。
            
            返回一个严格的JSON对象，其中键是图片摘要，值是一个包含所有匹配的套餐标题的**列表**。如果一个摘要找不到任何匹配项，值应为空列表 `[]`。
            例如: {{ "通用网费图": ["【新客】50元网费", "【老客】100元网费"], "包时套餐图": [] }}
            """
        else:
            self.log("--- 当前为 [一对一精准匹配] 模式 ---")
            prompt = f"""
            现有以下需要创建的套餐列表：
            {json.dumps(add_items, ensure_ascii=False)}

            以及以下从图片中分析出的摘要列表：
            {json.dumps(image_summary_list, ensure_ascii=False)}

            请为每个“套餐列表”中的项目，在“图片摘要列表”中找到**最匹配**的一项。
            返回一个严格的JSON对象，其中键是套餐标题，值是匹配上的图片摘要。如果找不到匹配项，请将值设为 null。
            例如: {{ "【新客】50元网费": "50元网费", "【专享】300元包时": null }}
            """

        try:
            response = llm_client.chat.completions.create(
                model=LLM_MODEL_ID, # 使用文本模型
                messages=[
                    {'role': 'system', 'content': 'You are a helpful assistant that only returns JSON.'},
                    {'role': 'user', 'content': prompt}
                ]
            )
            
            match_result_str = response.choices[0].message.content
            log_func(f"--- [LLM Raw Response for Image-Text Matching] ---\n{match_result_str}\n" + "-"*30)
            json_match = re.search(r'\{[\s\S]*\}', match_result_str)
            if json_match:
                cleaned_response = json_match.group(0)
                match_result = json.loads(cleaned_response)
            else:
                raise json.JSONDecodeError("在LLM响应中未找到JSON对象", match_result_str, 0)

            self.log("智能匹配API调用成功，正在更新UI...")

            summary_to_filename = {item['summary']: item['original_filename'] for item in image_summaries}

            # 在UI线程中更新Treeview
            def _update_ui():
                title_to_image_map = {}
                if multi_mode:
                    self.log("[Debug] 进入多对多匹配UI更新逻辑。")
                    # "一对多"逻辑: 反转字典
                    for summary, titles in match_result.items():
                        if summary in summary_to_filename:
                            filename = summary_to_filename[summary]
                            for title in titles:
                                title_to_image_map[title] = filename
                else:
                    self.log("[Debug] 进入一对一匹配UI更新逻辑。")
                    # "一对一"逻辑
                    for title, summary in match_result.items():
                        if summary in summary_to_filename:
                            title_to_image_map[title] = summary_to_filename[summary]
                
                self.log(f"[Debug] 最终构建的 '套餐标题 -> 图片' 映射: {json.dumps(title_to_image_map, ensure_ascii=False, indent=2)}")

                for item_id in self.product_tree.get_children():
                    if self.product_tree.set(item_id, "action_mode") == "重创":
                        title = self.product_tree.set(item_id, "excel_title")
                        if title in title_to_image_map:
                            filename = title_to_image_map[title]
                            self.product_tree.set(item_id, "matched_image", filename)
                            self.log(f"UI更新: 套餐 '{title}' -> 图片 '{filename}'")
                        else:
                            self.log(f"[Debug] 套餐 '{title}' 在映射中未找到匹配图片。")
                
                self.log("--- 智能匹配完成 ---")
                self.set_ui_state(False)

            self.master.after(0, _update_ui)

        except json.JSONDecodeError:
            self.log(f"[Error] 解析LLM返回的JSON失败。返回内容: {match_result_str}")
            self.master.after(0, lambda: messagebox.showerror("AI匹配错误", "AI服务返回了无效的数据格式。"))
            self.master.after(0, lambda: self.set_ui_state(False))
        except Exception as e:
            self.log(f"[Error] 智能匹配过程中出错: {e}")
            self.master.after(0, lambda: messagebox.showerror("AI匹配错误", f"请求AI服务时出错: {e}"))
            self.master.after(0, lambda: self.set_ui_state(False))

    def _batch_process_thread(self, items_to_process):
        success_count, failed_items = 0, []
        items_to_process.sort(key=lambda x: 1 if x["action_mode"] != "修改" else 0)
        
        # 为"重创"模式准备模板ID：
        # 1. 优先使用第一个"修改"操作的商品ID
        # 2. 否则使用当前门店商品列表中的第一个（self.douyin_products是当前门店的套餐列表）
        template_id_for_recreate = next(
            (item['product_id'] for item in items_to_process if item['action_mode'] == "修改"), 
            self.douyin_products[0]['id'] if self.douyin_products else None
        )
        
        if not template_id_for_recreate and any(item['action_mode'] == "重创" for item in items_to_process):
            self.log("[Error] 重创模式需要模板商品，但当前门店没有可用的商品。")
            self.master.after(0, lambda: messagebox.showerror("错误", "重创模式需要模板商品，但当前门店没有可用的商品。\n请先查询门店商品列表。"))
            self.master.after(0, lambda: self.set_ui_state(False))
            return

        # 记录模板商品信息（用于重创模式）
        if template_id_for_recreate and any(item['action_mode'] == "重创" for item in items_to_process):
            template_product = next((p for p in self.douyin_products if p['id'] == template_id_for_recreate), None)
            if template_product:
                self.log(f"--- 重创模式将使用模板商品: {template_product['name']} (ID: {template_id_for_recreate}) ---")
            else:
                self.log(f"--- 重创模式将使用模板商品ID: {template_id_for_recreate} ---")

        for item in items_to_process:
            mode = item["action_mode"]
            product_id = item["product_id"]
            if mode == "下架":
                success, reason = operate_douyin_product(self.douyin_access_token, product_id, self.log, offline=True)
            elif mode == "修改":
                # 修改模式：使用当前商品自己的ID作为模板
                success, reason = update_douyin_product(self.douyin_access_token, product_id, item["new_data"], self.log, mode, image_dir=self.image_dir, target_poi_id=self.current_poi_id)
            else:  # 重创模式 - 使用网页端API
                # 使用网页端API创建商品（复用模板图片，创建后自动修改POI ID）
                # 模板来源：当前门店的商品列表中的第一个
                product_id_created, reason = create_product_via_web(
                    DOUYIN_WEB_COOKIE,
                    DOUYIN_WEB_CSRF_TOKEN,
                    DOUYIN_ROOT_LIFE_ACCOUNT_ID,
                    template_id_for_recreate,  # 模板商品ID（来自当前门店）
                    item["new_data"],
                    self.current_poi_id,  # 目标门店POI ID
                    self.douyin_access_token,  # 用于后续修改POI ID
                    self.log
                )
                success = product_id_created is not None
            
            if success: success_count += 1
            else: failed_items.append(f"ID {product_id}: {reason}")
            time.sleep(1)

        summary_message = f"批量操作完成！\n\n成功: {success_count} 个\n失败: {len(failed_items)} 个"
        if failed_items:
            self.log("--- 操作失败详情 ---"); [self.log(f) for f in failed_items]
            summary_message += "\n\n失败详情请查看日志。"
        self.master.after(0, lambda: messagebox.showinfo("操作完成", summary_message))
        self.master.after(0, self.start_query_douyin)
