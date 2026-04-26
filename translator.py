# ArXiv Papers Manager - 大模型翻译模块
"""
翻译模块：调用大语言模型API将论文标题和摘要翻译为中文
支持OpenAI兼容API，包括GPT-3.5、GPT-4等模型
"""
import json
import requests
from typing import Dict, Any, Optional
from config import LLM_CONFIG


class Translator:
    """
    翻译器类：封装大模型翻译功能
    
    使用大语言模型将英文论文标题和摘要翻译为中文，
    支持中英文切换显示
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化翻译器
        
        Args:
            config: 配置字典，包含api_key、base_url、model等
        """
        self.config = config or LLM_CONFIG
        self.api_key = self.config.get('api_key', '')
        self.base_url = self.config.get('base_url', 'https://api.openai.com/v1')
        self.model = self.config.get('model', 'gpt-3.5-turbo')
        self.timeout = self.config.get('timeout', 60)
    
    def is_configured(self) -> bool:
        """
        检查翻译器是否已正确配置
        
        Returns:
            bool: 是否配置了API密钥
        """
        return bool(self.api_key)
    
    def translate(self, text: str, target_lang: str = "Chinese") -> Optional[str]:
        """
        翻译文本到目标语言
        
        Args:
            text: 待翻译文本
            target_lang: 目标语言，默认中文
            
        Returns:
            Optional[str]: 翻译后的文本，失败返回None
        """
        if not text:
            return None
        
        if not self.is_configured():
            return "[翻译功能未配置 - 请设置OPENAI_API_KEY环境变量]"
        
        try:
            # 构建提示词
            prompt = self._build_translation_prompt(text, target_lang)
            
            # 调用API
            response = self._call_api(prompt)
            
            return response
            
        except Exception as e:
            print(f"翻译失败: {e}")
            return f"[翻译失败: {str(e)}]"
    
    def _build_translation_prompt(self, text: str, target_lang: str) -> str:
        """
        构建翻译提示词
        
        Args:
            text: 待翻译文本
            target_lang: 目标语言
            
        Returns:
            str: 格式化的提示词
        """
        return f"""请将以下论文内容翻译成{target_lang}。
要求：
1. 保持学术论文的专业性和准确性
2. 保留专业术语的原文（如有常见译法请保留中文）
3. 只返回翻译结果，不要添加任何解释或说明

原文内容：
{text}

{target_lang}翻译："""
    
    def _call_api(self, prompt: str) -> Optional[str]:
        """
        调用大模型API
        
        Args:
            prompt: 提示词
            
        Returns:
            Optional[str]: API返回的翻译结果
        """
        url = f"{self.base_url}/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a professional academic translator."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,  # 较低温度保证翻译一致性
            "max_tokens": 2000
        }
        
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=self.timeout
        )
        response.raise_for_status()
        
        result = response.json()
        
        if 'choices' in result and len(result['choices']) > 0:
            return result['choices'][0]['message']['content'].strip()
        
        return None
    
    def translate_paper(self, title: str, abstract: str) -> Dict[str, str]:
        """
        翻译论文的标题和摘要
        
        Args:
            title: 论文标题
            abstract: 论文摘要
            
        Returns:
            Dict[str, str]: 包含翻译结果的字典
                - translated_title: 翻译后的标题
                - translated_abstract: 翻译后的摘要
        """
        result = {}
        
        # 翻译标题
        if title:
            result['translated_title'] = self.translate(title)
        
        # 翻译摘要
        if abstract:
            result['translated_abstract'] = self.translate(abstract)
        
        return result
    
    def batch_translate(self, items: list) -> list:
        """
        批量翻译多个文本
        
        Args:
            items: 文本列表
            
        Returns:
            list: 翻译结果列表
        """
        return [self.translate(item) for item in items if item]


# 全局翻译器实例
translator = Translator()


def translate_text(text: str, target_lang: str = "Chinese") -> Optional[str]:
    """
    便捷翻译函数
    
    Args:
        text: 待翻译文本
        target_lang: 目标语言
        
    Returns:
        Optional[str]: 翻译结果
    """
    return translator.translate(text, target_lang)


def translate_paper(title: str, abstract: str) -> Dict[str, str]:
    """
    便捷论文翻译函数
    
    Args:
        title: 论文标题
        abstract: 论文摘要
        
    Returns:
        Dict[str, str]: 翻译结果
    """
    return translator.translate_paper(title, abstract)
