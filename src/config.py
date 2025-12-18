"""
配置文件 - 集中管理所有配置项
"""
import os
import logging

# --- 日志配置 ---
LOG_FILE_PATH = 'update_products_log.txt'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, encoding='utf-8'),
    ]
)

# --- Cloudflare R2 配置 ---
CLOUDFLARE_ACCOUNT_ID = "67a7569d0cd89aafb7499f3cf3bc9f73"
CLOUDFLARE_R2_ACCESS_KEY_ID = "6684b2a5b8f947ba4f6f3ba943d22439"
CLOUDFLARE_R2_SECRET_ACCESS_KEY = "bd3dce5ac2df30ae34377c9ca5af26fd845abe5fa6ea179ec6810552856ca27f"
R2_BUCKET_NAME = "0926taocantoutu"
R2_ENDPOINT_URL = f"https://{CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com"
R2_PUBLIC_URL_PREFIX = "https://pub-c92931353257460eb0beccbf59ef2ad0.r2.dev"

# --- ModelScope LLM (DeepSeek) 配置 ---
MS_BASE_URL = 'https://api-inference.modelscope.cn/v1'
MS_API_KEY = 'ms-871a8344-b18d-4fb5-b96e-d4123fbbb0f0'
LLM_MODEL_ID = 'deepseek-ai/DeepSeek-V3.2-Exp'
VISION_MODEL_IDS = [
    'Qwen/Qwen3-VL-8B-Instruct',
    'Qwen/Qwen3-VL-235B-A22B-Instruct',
    'Qwen/Qwen3-VL-30B-A3B-Instruct'
]

# --- 抖音开放平台密钥 ---
CLIENT_KEY = "awbeykzyos7kbidv"
CLIENT_SECRET = "4575440b156ecbe144284e4f69d284a2"
DOUYIN_ACCOUNT_ID = "7241078611527075855"

# --- 抖音网页端配置（用于重创模式）---
DOUYIN_WEB_CSRF_TOKEN = "000100000001ae8a406b9344d0cc4e30ceaf542c505dbbabca5a3842c450a93e0787a4d2f8991880c8ea9d2d1372"
DOUYIN_ROOT_LIFE_ACCOUNT_ID = "7241078611527075855"

def load_cookie_from_file():
    """从cookie.txt文件读取Cookie"""
    cookie_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cookie.txt')
    try:
        with open(cookie_file, 'r', encoding='utf-8') as f:
            cookie = f.read().strip()
            if cookie:
                logging.info(f"成功从 {cookie_file} 加载Cookie")
                return cookie
    except FileNotFoundError:
        logging.warning(f"未找到Cookie文件: {cookie_file}")
    except Exception as e:
        logging.error(f"读取Cookie文件失败: {e}")
    return ""

DOUYIN_WEB_COOKIE = load_cookie_from_file()

# --- 飞书多维表格配置 ---
FEISHU_APP_ID = "cli_a6672cae343ad00e"
FEISHU_APP_SECRET = "0J4SpfBMeIxJEOXDJMNbofMipRgwkMpV"
FEISHU_APP_TOKEN = "MslRbdwPca7P6qsqbqgcvpBGnRh"
FEISHU_TABLE_ID = "tbluVbrXLRUmfouv"

# --- API URL 地址 ---
DOUYIN_TOKEN_URL = "https://open.douyin.com/oauth/client_token/"
DOUYIN_PRODUCT_QUERY_URL = "https://open.douyin.com/goodlife/v1/goods/product/online/query/"
DOUYIN_PRODUCT_GET_URL = "https://open.douyin.com/goodlife/v1/goods/product/online/get/"
DOUYIN_PRODUCT_SAVE_URL = "https://open.douyin.com/goodlife/v1/goods/product/save/"
DOUYIN_PRODUCT_OPERATE_URL = "https://open.douyin.com/goodlife/v1/goods/product/operate/"
FEISHU_TENANT_ACCESS_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/"
FEISHU_BITABLE_RECORDS_SEARCH_URL = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{FEISHU_APP_TOKEN}/tables/{FEISHU_TABLE_ID}/records/search"
