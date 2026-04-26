# ArXiv Papers Manager - 论文管理网页应用
"""
配置文件：管理应用的所有配置参数
"""
import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent
PAPERS_DIR = BASE_DIR / "papers"  # 论文存储目录（按DOI命名子文件夹）

# 数据库配置
DATABASE_PATH = BASE_DIR / "arxiv_papers.db"

# ArXiv API 配置
ARXIV_API_URL = "http://export.arxiv.org/api/query"

# Connected Papers 配置
CONNECTED_PAPERS_URL = "https://www.connectedpapers.com"

# 大模型翻译配置（支持 OpenAI 兼容 API）
LLM_CONFIG = {
    "api_key": os.getenv("OPENAI_API_KEY", ""),  # 从环境变量读取API密钥
    "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),  # API地址
    "model": os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),  # 使用的模型
    "timeout": 60,  # 请求超时时间（秒）
}

# Flask/服务器配置
SERVER_CONFIG = {
    "host": os.getenv("HOST", "127.0.0.1"),
    "port": int(os.getenv("PORT", 5000)),
    "debug": os.getenv("DEBUG", "True").lower() == "true",
}

# 请求头配置（模拟浏览器访问）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 确保必要目录存在
PAPERS_DIR.mkdir(exist_ok=True)
