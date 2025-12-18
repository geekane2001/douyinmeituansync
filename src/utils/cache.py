"""
缓存管理模块 - 管理LLM请求缓存
"""
import hashlib
import json


class LLMCache:
    """LLM请求缓存管理器"""
    
    def __init__(self):
        self.cache = {}
    
    def get_cache_key(self, prompt):
        """生成缓存键"""
        return hashlib.sha256(prompt.encode('utf-8')).hexdigest()
    
    def get(self, prompt):
        """获取缓存"""
        cache_key = self.get_cache_key(prompt)
        return self.cache.get(cache_key)
    
    def set(self, prompt, result):
        """设置缓存"""
        cache_key = self.get_cache_key(prompt)
        self.cache[cache_key] = result
    
    def has(self, prompt):
        """检查是否有缓存"""
        cache_key = self.get_cache_key(prompt)
        return cache_key in self.cache
    
    def clear(self):
        """清空缓存"""
        self.cache.clear()
    
    def size(self):
        """获取缓存大小"""
        return len(self.cache)
