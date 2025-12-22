# 抖音团购智能同步工具 (Douyin-Meituan-Sync)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Gradio](https://img.shields.io/badge/UI-Gradio-orange.svg)](https://gradio.app/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## 📖 项目简介

本项目是一个基于 Python 和 Gradio 开发的智能自动化工具，旨在帮助商家将 **美团** 的团购套餐自动同步到 **抖音** 平台。它通过爬取美团套餐信息，利用 LLM (大型语言模型) 进行智能匹配和分析，自动识别需要新增、修改或保留的商品，并调用抖音开放平台接口进行批量更新。

**核心解决痛点：**
*   手动维护双平台商品费时费力。
*   价格和库存更新不及时导致客诉。
*   商品名称和描述不一致影响用户体验。

## ✨ 主要功能

1.  **多门店管理**：支持从飞书多维表格读取门店列表，自动识别城市和 POI ID。
2.  **抖音商品查询**：一键查询指定门店的抖音线上在售商品，支持过滤直播间专享商品。
3.  **美团同步 (智能核心)**：
    *   **自动搜索**：根据门店名称（自动清洗无关后缀）或自定义关键词在美团搜索对应门店。
    *   **智能抓取**：爬取美团门店的套餐列表（包括标题、现价、原价）。
    *   **LLM 智能匹配**：使用 DeepSeek 模型分析抖音与美团商品的语义相似度，自动建立映射关系。
    *   **全量新建支持**：即使抖音侧无商品，也能通过模板复用机制，实现从美团到抖音的全量自动新建。
4.  **批量操作执行**：
    *   **修改**：更新现有商品的标题、价格、使用须知等信息。
    *   **重创**：基于模板商品，创建全新的抖音团购商品（复用图片和资质信息）。
    *   **下架/保持**：自动识别无对应关系的商品并提供处理选项。
5.  **可视化界面**：基于 Gradio 的 Web 界面，提供表格预览、日志实时输出和操作干预。

## 🛠️ 技术架构

*   **开发语言**: Python 3.10+
*   **UI 框架**: Gradio
*   **数据处理**: Pandas, BeautifulSoup4 (BS4)
*   **大模型**: OpenAI SDK (对接 ModelScope / DeepSeek)
*   **外部接口**:
    *   抖音生活服务开放平台 API
    *   飞书开放平台 API
    *   Cloudflare R2 (图片存储)

## 🚀 快速开始

### 1. 环境准备

确保已安装 Python 3.10 或更高版本。

```bash
# 克隆项目
git clone [repository-url]
cd douyinmeituansync

# 创建虚拟环境 (推荐)
python -m venv venv
# Windows 激活
venv\Scripts\activate
# Linux/Mac 激活
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置文件

项目核心配置位于 `src/config.py`。您需要准备以下敏感信息：

*   **抖音开放平台**: `CLIENT_KEY`, `CLIENT_SECRET`, `DOUYIN_ACCOUNT_ID`
*   **飞书开放平台**: `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_TABLE_ID`
*   **ModelScope (LLM)**: `MS_API_KEY` (用于调用 DeepSeek 模型)
*   **Cloudflare R2**: 相关 Key 和 Endpoint (用于图片上传，可选)
*   **抖音网页端 Cookie**:
    *   在项目根目录创建一个 `cookie.txt` 文件。
    *   登录 [抖音来客电脑版](https://life.douyin.com/)，按 F12 打开控制台。
    *   复制请求头中的 `Cookie` 字段内容，粘贴到 `cookie.txt` 中。
    *   同时需要更新 `src/config.py` 中的 `DOUYIN_WEB_CSRF_TOKEN`。

### 3. 运行项目

```bash
# 启动 Gradio 界面
python src/ui/gradio_ui.py
```

启动后，浏览器将自动打开 `http://127.0.0.1:7860`。

## 📖 使用指南

### 第一步：选择门店
1.  在界面左上角下拉框选择需要同步的门店。
2.  系统会自动识别该门店所在的城市（转为拼音）和默认的美团搜索名称。

### 第二步：查询抖音商品
1.  点击 **"1. 查询抖音商品"**。
2.  右侧表格将展示当前抖音门店的在售商品列表。
3.  勾选 "隐藏仅直播间商品" 可过滤掉不需要同步的特殊商品。

### 第三步：同步美团套餐
1.  确认 **"美团搜索名称"** 是否正确。如果不准确（例如搜不到店），可手动修改。
2.  点击 **"2. 同步美团套餐"**。
3.  **智能匹配过程**：
    *   系统爬取美团数据。
    *   调用 LLM 分析匹配关系。
    *   表格将更新，显示 "匹配状态"（匹配成功/需新建/未匹配）。
    *   **全量新建**：如果抖音列表为空，系统将自动把所有美团套餐标记为 "重创"。

### 第四步：执行批量操作
1.  检查表格中的 "操作模式" 列（修改/重创/保持）。您可以手动修改此列以覆盖系统决定。
2.  **模板 ID (重要)**：
    *   如果是全量新建（当前门店无商品），请在 **"高级设置"** 中填入一个可用的模板商品 ID（任意已有商品 ID 即可）。
    *   如果有现有商品，系统会自动选择一个作为模板。
3.  点击 **"3. 执行批量操作"**，观察下方日志输出。

## 📂 项目结构

```text
douyinmeituansync/
├── .gitignore              # Git 忽略规则
├── requirements.txt        # 依赖列表
├── main.py                 # (旧入口，建议使用 src/ui/gradio_ui.py)
├── cookie.txt              # (需手动创建) 抖音网页端 Cookie
├── src/
│   ├── api/
│   │   ├── douyin_api.py       # 抖音开放平台 API 封装
│   │   ├── meituan_api.py      # 美团爬虫与解析逻辑
│   │   ├── llm_api.py          # LLM 调用与 Prompt 管理
│   │   └── feishu_api.py       # 飞书多维表格接口
│   ├── core/
│   │   ├── matching_engine.py  # 核心匹配引擎 (LLM 逻辑)
│   │   ├── product_manager.py  # 商品增删改查实现 (含网页端 API)
│   │   └── image_processor.py  # 图片处理与上传
│   ├── ui/
│   │   └── gradio_ui.py        # Gradio 主界面逻辑
│   ├── utils/                  # 通用工具函数
│   └── config.py               # 全局配置文件
```

## ⚠️ 常见问题与排查

1.  **美团同步搜不到店？**
    *   检查门店名称是否包含特殊字符。尝试在 UI 的 "美团搜索名称" 输入框中简化名称（例如去掉分店名）。
    *   检查 `src/api/meituan_api.py` 中的 Cookie 是否过期。美团反爬较严，可能需要更新 `base_cookie`。

2.  **重创商品失败？**
    *   确保 `cookie.txt` 内容是最新的。
    *   确保 `src/config.py` 中的 `DOUYIN_WEB_CSRF_TOKEN` 与 Cookie 匹配。
    *   如果是全量新建，必须在高级设置中填写模板 ID。

3.  **价格更新不生效？**
    *   抖音限制最低价为 5 元，如果同步过来的价格低于 5 元，系统会自动上调。
    *   检查日志中是否有 "Skipping price update" 的提示。

## 🤝 参与贡献

欢迎提交 Issue 和 Pull Request。在开发前请先阅读 `src/core/product_manager.py` 理解商品操作的复杂性（涉及开放平台 API 和网页端逆向 API 的混合使用）。

## 📄 版权说明

本项目仅供学习和内部工具使用，请勿用于商业分发或违反平台规则的用途。