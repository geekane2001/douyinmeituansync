"""
LLM API模块 - 处理AI智能分析相关功能
"""
import json
import re
import hashlib
import traceback
from openai import OpenAI
from ..config import MS_BASE_URL, MS_API_KEY, LLM_MODEL_ID

# 初始化LLM客户端
try:
    # llm_client = OpenAI(base_url=MS_BASE_URL, api_key=MS_API_KEY, timeout=30.0)
    # 硬编码配置 - ModelScope DeepSeek-V3.1
    llm_client = OpenAI(
        base_url='https://api-inference.modelscope.cn/v1',
        api_key='ms-871a8344-b18d-4fb5-b96e-d4123fbbb0f0', # ModelScope Token
        timeout=60.0
    )
    LLM_MODEL_ID = 'deepseek-ai/DeepSeek-V3.1' # Update Model ID here locally for this module
except Exception as e:
    llm_client = None
    print(f"初始化LLM客户端失败: {e}")

def get_llm_client():
    """获取LLM客户端实例"""
    return llm_client


def match_products_with_llm(douyin_products, excel_data, log_func, cache):
    """使用LLM智能匹配抖音商品与Excel商品"""
    if not llm_client: 
        return None
    log_func("--- 开始使用LLM智能匹配套餐 ---")
    
    # 准备更详细的数据给LLM，以提高匹配准确性
    douyin_product_details_for_llm = [
        {"name": p['name'], "price": p['price'], "origin_price": p.get('origin_price', '0.00')}
        for p in douyin_products
    ]
    excel_product_details_for_llm = [
        {"团购标题": p['团购标题'], "售价": p.get('售价', 0.0), "网费": p.get('网费', 0.0), "区域": p.get('可用区域', '')}
        for p in excel_data
    ]

    prompt = f"""
# 任务：智能匹配抖音商品与Excel商品

请为"抖音商品列表"中的每一个商品，在"Excel商品列表"中找到唯一且最精确的匹配项。

## 匹配原则 (极其重要):
1.  **核心匹配**: 首先必须根据商品的核心内容进行匹配。例如，抖音的"【新会员】108网费"应该匹配Excel中的"【新会员】108网费"。
2.  **价格验证**: 在核心内容匹配的基础上，必须严格比较价格。抖音商品的价格 (`price`) 必须与Excel中对应的"售价"**几乎完全相等**。
3.  **内容与价格结合**: 综合核心内容和价格进行双重验证。例如，一个抖音商品叫"【上午包】无烟区"，价格是10.5元，那么它应该匹配到Excel中"团购标题"为"【上午包】无烟区"且"售价"为10.5的那一行。
4.  **处理模糊情况**: 如果多个抖音商品（例如"【瞬影必杀券】100元网费（新会员）"和"【新鼠鼠券A】100元网费"）都能模糊匹配到同一个Excel项（例如"【新会员】108网费"），你需要根据**价格**来区分。如果价格也相似，则选择内容更接近的那个。如果无法区分，则可以将其中一个设为null。
5.  **找不到则为null**: 如果在Excel列表中找不到任何满足上述条件的匹配项，对应的值必须是 `null`。

## 数据列表:

### 抖音商品列表 (包含名称、现价、原价):
{json.dumps(douyin_product_details_for_llm, ensure_ascii=False, indent=2)}

### Excel商品列表 (包含团购标题、售价、网费、区域):
{json.dumps(excel_product_details_for_llm, ensure_ascii=False, indent=2)}

## 返回格式:
请严格按照以下JSON格式返回结果，键是抖音商品**完整的`name`**，值是匹配到的Excel商品**完整的`团购标题`**。不要包含任何额外的解释。

```json
{{
  "抖音商品名称1": "匹配到的Excel团购标题1",
  "抖音商品名称2": null,
  "抖音商品名称3": "匹配到的Excel团购标题3"
}}
```
"""
    
    cache_key = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
    if cache_key in cache:
        log_func(f"[Cache Hit] 发现相同请求的缓存结果，直接使用缓存。")
        return cache[cache_key]

    log_func("[Cache Miss] 未找到缓存，发起新的LLM请求。")
    try:
        log_func("正在调用LLM API...")
        log_func(f"--- [DEBUG] 发送给LLM的Prompt ---\n{prompt[:500]}...\n" + "-"*30)
        response = llm_client.chat.completions.create(
            model=LLM_MODEL_ID,
            messages=[{'role': 'user', 'content': prompt}],
            stream=True
        )
        full_response = ""
        full_reasoning = ""
        for chunk in response:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    full_reasoning += delta.reasoning_content
                if delta.content:
                    full_response += delta.content
                    
        if full_reasoning:
            log_func(f"--- [LLM Reasoning] ---\n{full_reasoning}\n" + "-"*30)
        log_func(f"--- [LLM Raw Response for Product Matching] ---\n{full_response}\n" + "-"*30)
        json_match = re.search(r'\{[\s\S]*\}', full_response)
        if json_match:
            cleaned_response = json_match.group(0)
            match_result = json.loads(cleaned_response)
        else:
            raise json.JSONDecodeError("在LLM响应中未找到JSON对象", full_response, 0)
        log_func("[Success] LLM智能匹配成功！")
        cache[cache_key] = match_result
        log_func(f"已将本次结果存入缓存，Key: {cache_key[:10]}...")
        return match_result
    except Exception as e:
        log_func(f"[Error] LLM智能匹配过程中出错: {e}")
    return None


def match_packages_douyin_meituan_llm(douyin_packages, meituan_packages, log_func, cache):
    """使用LLM智能匹配抖音和美团套餐"""
    if not llm_client:
        log_func("[Error] LLM客户端未初始化。")
        return None
        
    log_func("--- 开始使用LLM智能匹配抖音与美团套餐 ---")
    
    # 简化数据结构以减少Token消耗
    dy_list = []
    for p in douyin_packages:
        dy_list.append({
            "id": p['id'],
            "name": p['name'],
            "price": float(p['price']),
            "origin_price": float(p.get('origin_price', 0) or 0)
        })
        
    mt_list = []
    for i, p in enumerate(meituan_packages):
        mt_list.append({
            "index": i,
            "title": p['title'],
            "price": p['price'],
            "original_price": p['original_price']
        })

    prompt = f"""
你是一个专业的团购运营专家。任务是将"美团套餐"(目标)与"抖音套餐"(现有)进行智能匹配，以便我们将抖音套餐更新为与美团一致。

# 核心原则：
1.  **高度相似匹配（优先）**：
    -   对于每一个美团套餐，请在抖音列表中寻找一个**名称和现价都高度相似**的套餐。
    -   **判定标准**：如果两者看起来就是同一个商品（例如名称非常接近，且价格也接近或相同），则应判定为匹配。
    -   **目的**：我们将把匹配到的抖音套餐的名称和价格更新为与美团完全一致。
2.  **严格的内容类型匹配（禁止乱配）**：
    -   **"网费/充值"类** 绝不能与 **"包时/包房/包段"类** 匹配！这是两条平行线。
    -   **"包房/包间"类** 绝不能与 **"大厅"类** 匹配！
    -   如果相似度不高，或者类型不匹配，请不要强行匹配。
3.  **新建判定**：
    -   如果一个美团套餐在抖音列表中找不到**高度相似**的对应项，则视为需要"新建"。不要为了匹配而匹配。
4.  **一对一匹配**：一个美团套餐只能匹配一个抖音套餐。

# 输入数据：

## 美团套餐列表 (目标标准):
{json.dumps(mt_list, ensure_ascii=False, indent=2)}

## 抖音套餐列表 (现有库存):
{json.dumps(dy_list, ensure_ascii=False, indent=2)}

# 输出要求：
请返回一个 JSON 对象，包含 `matches` 列表。
- `matches`: 列表，每个元素包含 `meituan_index` (对应美团列表的index) 和 `douyin_id` (对应抖音列表的id)。
- 只有确信是同类产品（可以经过修改变成一样）时才匹配。

格式示例：
```json
{{
  "matches": [
    {{ "meituan_index": 0, "douyin_id": "123456", "reason": "同为100元网费，仅价格不同" }},
    {{ "meituan_index": 2, "douyin_id": "789012", "reason": "同为通宵包段" }}
  ]
}}
```
"""
    
    cache_key = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
    if cache_key in cache:
        log_func("[Cache Hit] 发现相同匹配请求的缓存结果，直接使用。")
        return cache[cache_key]

    try:
        log_func(f"--- [DEBUG] 发送给LLM的Prompt (前500字符) ---\n{prompt[:500]}...\n" + "-"*30)
        response = llm_client.chat.completions.create(
            model=LLM_MODEL_ID,
            messages=[{'role': 'user', 'content': prompt}],
            stream=True
        )
        
        full_response = ""
        full_reasoning = ""
        
        for chunk in response:
            if chunk.choices:
                delta = chunk.choices[0].delta
                # Handle reasoning content if available (DeepSeek R1/V3 features)
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    full_reasoning += delta.reasoning_content
                
                if delta.content:
                    full_response += delta.content
                    
        if full_reasoning:
            log_func(f"--- [LLM Reasoning] ---\n{full_reasoning}\n" + "-"*30)
            
        log_func(f"--- [LLM Raw Response] ---\n{full_response}\n" + "-"*30)
        
        json_match = re.search(r'\{[\s\S]*\}', full_response)
        if json_match:
            result = json.loads(json_match.group(0))
            log_func(f"[Success] LLM匹配成功，找到 {len(result.get('matches', []))} 对匹配。")
            cache[cache_key] = result
            return result
        else:
            raise json.JSONDecodeError("未找到JSON对象", full_response, 0)
            
    except Exception as e:
        log_func(f"[Error] LLM匹配过程中出错: {e}")
        return None

def analyze_text_for_actions(text_input, douyin_products, log_func, cache):
    """使用LLM分析文本指令，识别新增、修改、下架操作"""
    if not llm_client:
        log_func("[Error] LLM客户端未初始化。")
        return None
        
    log_func("--- 开始使用LLM分析文本指令 ---")
    
    # 转换价格为数字，以便AI更好地处理
    simple_product_list_for_llm = []
    for p in douyin_products:
        try:
            price = float(p.get('price', 0))
            origin_price = float(p.get('origin_price', 0))
        except (ValueError, TypeError):
            price = 0.0
            origin_price = 0.0
        simple_product_list_for_llm.append({
            "name": p.get('name'),
            "price": price,
            "origin_price": origin_price
        })

    prompt = f"""
你是一个专业的抖音团购运营助理。请根据用户提供的文本指令和当前的抖音线上商品列表，分析出需要执行的新增、修改、下架操作。

# 当前线上商品列表 (包含名称、现价和原价):
{json.dumps(simple_product_list_for_llm, ensure_ascii=False, indent=2)}

# 用户指令:
---
{text_input}
---

# 任务要求:
1.  **分析指令**: 仔细阅读用户指令，识别出三种操作：`add` (新增), `update` (修改), `delete` (下架)。
    *   **特别注意：如果用户指令中明确包含"新建"或"新增"关键词，则应将所有内容都解析为 `add` 操作，不要尝试进行 `update` 或 `delete` 匹配。**

2.  **智能匹配商品 (核心任务)**:
    *   对于 `update` 和 `delete` 操作（**仅在指令不含"新建"或"新增"时执行**），你必须在"当前线上商品列表"中找到最相关的商品。匹配不应是简单的文本相等，而应是基于核心内容、现价 (`price`) 和原价 (`origin_price`) 的**智能模糊匹配**。
    *   **匹配示例**: 用户指令 `【9.9得60】换成【19.9得100】` 应该能准确匹配到线上商品 `{{"name": "【开业新会员】9.9得60网费", "price": 9.9, "origin_price": 60.0}}`，因为它的核心部分 `9.9得60` 与价格 `9.9` 和 `60.0` 高度相关。
    *   对于 `delete` 操作，如果指令只有价格（如 `59.9下架`），应根据 `price` 字段进行匹配。
    *   对于 `add` 操作，是全新的商品，不需要匹配。

3.  **提取并构建信息**:
    *   对于 `add` 操作，根据指令提取并构建一个完整商品信息对象。
        *   **售价提取**: 必须从指令中提取出明确的"售价"。
        *   **套餐类型提取**: 从指令中识别套餐的核心类型，例如"网费"或"包时"。将结果放入 `commodity_type` 字段。
        *   **原价计算规则**:
            *   如果 `commodity_type` 是 "**网费**"，则从指令中直接提取"原价"。例如，指令"19.9得50网费"中，"原价"是50。
            *   如果 `commodity_type` 是 "**包时**"，则"原价"应根据"售价"**估算**，规则为 **售价的3倍**。例如，指令"3小时包时，价格9.8"，`售价`是9.8，那么`原价`就应该是 9.8 * 3 = 29.4。**绝对不要**将"3小时"这个时长错误地识别为原价。
        *   **用户类型提取**: 从指令中识别用户类型，如"新客"、"新会员"应提取为 "新客"；如"老客"、"会员"应提取为 "老客"；如果未提及，则为 "不限制"。将结果放入 `member_type` 字段。
        *   **适用位置提取**: 详细分析指令中描述套餐的关键词，例如"单人双人包"、"豪华电竞包间"、"大厅"等。如果指令中明确提到了房间类型或位置，就提取它。如果未提及任何具体位置，则默认为"大厅"。将结果放入 `applicable_location` 字段。
        *   **标题生成**: 你需要根据提取出的信息，为"团购标题"生成一个清晰、规范的名称。
            *   **网费标题格式**: 保持 `【用户类型】售价得原价内容` 格式。例如：`【新客专享】42.9得100元网费`。
            *   **包时标题格式**: 简化为 `时长 + 更详细的套餐描述`。例如，指令 "包时 单人双人包套餐 5 小时，价格 39.9"，标题应生成为 `5小时单人双人包套餐`。
        *   **其他字段**: 如果指令中包含，也请提取 "可用区域", "限购", "有效期", "团单备注"。
    *   对于 `update` 操作，首先通过智能匹配找到要修改的商品。在返回结果中，`from_name` 必须使用"当前线上商品列表"中被匹配到的那个商品**完整的 `name`**。`new_data` 则是根据用户指令生成的、包含所有字段的完整新商品信息对象，其中必须包含`售价`和`原价`。
    *   对于 `delete` 操作，只需提取并返回要下架的商品的**完整的 `name`**。
4.  **格式化输出**: 必须严格按照以下JSON格式返回结果，不要添加任何额外的解释或说明文字。

```json
{{
  "add": [
    {{
      "团购标题": "...",
      "售价": 0.0,
      "原价": 0.0,
      "member_type": "新客",
      "commodity_type": "网费",
      "applicable_location": "大厅",
      "可用区域": "...",
      "限购": "...",
      "有效期": "...",
      "团单备注": "..."
    }}
  ],
  "update": [
    {{
      "from_name": "要修改的线上商品原名称",
      "new_data": {{
          "团购标题": "修改后的新名称",
          "售价": 19.9,
          "原价": 100.0,
          "可用区域": "...",
          "限购": "...",
          "有效期": "...",
          "团单备注": "..."
      }}
    }}
  ],
  "delete": [
    {{
      "name": "要下架的线上商品名称"
    }}
  ]
}}
```

**注意事项**:
-   如果找不到完全匹配的商品进行修改或下架，请不要凭空创造，在结果中忽略该项操作。
-   价格必须是数字（浮点数）。
-   返回的结果必须是纯粹的JSON字符串。
"""

    cache_key = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
    if cache_key in cache:
        log_func("[Cache Hit] 发现相同分析请求的缓存结果，直接使用。")
        return cache[cache_key]

    log_func("[Cache Miss] 未找到缓存，发起新的LLM请求。")
    try:
        log_func(f"--- [DEBUG] 发送给LLM的Prompt ---\n{prompt[:800]}...\n" + "-"*30)
        response = llm_client.chat.completions.create(
            model=LLM_MODEL_ID,
            messages=[{'role': 'user', 'content': prompt}],
            stream=True
        )
        full_response = ""
        full_reasoning = ""
        for chunk in response:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    full_reasoning += delta.reasoning_content
                if delta.content:
                    full_response += delta.content

        if full_reasoning:
            log_func(f"--- [LLM Reasoning] ---\n{full_reasoning}\n" + "-"*30)
        log_func(f"--- [LLM Raw Response for Text Analysis] ---\n{full_response}\n" + "-"*30)
        
        json_match = re.search(r'\{[\s\S]*\}', full_response)
        if json_match:
            cleaned_response = json_match.group(0)
            analysis_result = json.loads(cleaned_response)
        else:
            raise json.JSONDecodeError("在LLM响应中未找到JSON对象", full_response, 0)
        
        log_func("[Success] LLM文本指令分析成功！")
        cache[cache_key] = analysis_result
        log_func(f"已将本次结果存入缓存，Key: {cache_key[:10]}...")
        return analysis_result
    except Exception as e:
        log_func(f"[Error] LLM文本指令分析过程中出错: {e}\n{traceback.format_exc()}")
    return None
