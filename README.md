# ArXiv Papers Manager

一个基于 Python 的网页端 ArXiv 论文管理应用，支持论文上传、ArXiv ID 解析、相关论文获取和智能翻译。该项目使用 vibe coding 创建和维护。

## 功能特性

- **多种添加方式**：支持输入 ArXiv ID、URL 或上传 PDF 文件
- **本地存储**：论文和元数据按 ArXiv ID 分类存储，包含 PDF 和元数据文件
- **相关论文获取**：从 Semantic Scholar API 获取主论文的引用文献和被引用论文
- **智能翻译**：一键将论文标题和摘要翻译为中文（支持 OpenAI 兼容 API）
- **数据库管理**：SQLite 数据库存储，支持多表查询
- **摘要展开/收起**：摘要默认显示 3 行，可点击展开查看全部
- **元数据丰富**：自动获取并保存 DOI 和期刊/会议引用信息

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 设置 OpenAI API 密钥（用于翻译功能）
set OPENAI_API_KEY=your-api-key-here

# 可选：自定义 API 地址和模型（支持 OpenAI 兼容接口）
set OPENAI_BASE_URL=https://api.openai.com/v1
set OPENAI_MODEL=gpt-3.5-turbo
```

### 3. 启动服务

```bash
python main.py
```

访问 http://127.0.0.1:5000 即可使用。

## 项目结构

```
arxiv-papers-manage/
├── config.py              # 配置文件
├── database.py           # 数据库操作模块（SQLite）
├── arxiv_parser.py       # ArXiv 论文解析模块
├── connected_papers.py   # 相关论文获取模块（Semantic Scholar API）
├── translator.py         # 大模型翻译模块
├── main.py              # 应用入口（FastAPI）
├── static/              # 静态资源目录
├── templates/
│   └── index.html       # 前端页面
└── papers/               # 论文存储目录（自动创建）
    └── [arxiv_id]/
        ├── xxx.pdf       # 主论文 PDF（带 original 标记）
        ├── xxx.pdf       # 相关论文 PDF
        ├── metadata.json # 元数据（包含主论文和相关论文信息）
        └── related_ids.txt # 相关论文 ArXiv ID 列表
```

## 使用说明

### 添加论文

**方式 1：输入 ArXiv ID 或 URL**
- 在输入框中输入 ArXiv ID（如 `2301.12345`）或完整 URL
- 点击"添加论文"按钮

**方式 2：上传 PDF 文件**
- 点击"上传 PDF 文件"按钮选择本地 PDF
- 点击"上传"按钮
- 系统会自动从 PDF 中提取 ArXiv ID 并获取论文信息

### 查看论文

- 论文卡片显示：标题、作者、年份、ArXiv 链接
- 摘要默认显示 3 行，点击"Expand"展开全部内容
- 点击"Collapse"收起摘要

### 获取相关论文

1. 点击论文卡片中的"获取相关论文"按钮
2. 系统从 Semantic Scholar API 获取相关论文：
   - **引用了主论文**：这些论文的参考文献列表中包含主论文
   - **被主论文引用**：主论文参考文献列表中的论文
3. 相关论文会显示在主论文下方，带有关系类型标签
4. 支持删除（可重新获取）和彻底删除操作

### 翻译功能

- 点击"译文"按钮将标题和摘要翻译为中文
- 再次点击"原文"按钮恢复为英文原文
- 如果没有配置OPENAI_API_KEY，则无法翻译，可以直接使用浏览器自带的翻译功能暂时替代

### 元数据字段

| 字段 | 说明 |
|-----|------|
| arxiv_id | ArXiv 论文 ID |
| title | 论文标题 |
| authors | 作者列表 |
| year | 出版年份 |
| abstract | 摘要 |
| doi | DOI 标识符 |
| journal_ref | 期刊/会议引用信息（如 NeurIPS 2017） |
| citationCount | 被引用次数 |
| referenceCount | 参考文献数量 |
| relation_type | 关系类型（citation: 被主论文引用, reference: 引用了主论文） |

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 首页 |
| `/api/papers` | GET | 获取所有主论文 |
| `/api/papers` | POST | 添加论文（ArXiv ID/URL） |
| `/api/papers/upload` | POST | 上传 PDF 添加论文 |
| `/api/papers/{arxiv_id}` | GET | 获取指定论文详情 |
| `/api/papers/{arxiv_id}` | DELETE | 删除主论文 |
| `/api/papers/{parent_id}/{arxiv_id}` | DELETE | 删除相关论文 |
| `/api/papers/{arxiv_id}/fetch-related` | POST | 获取一篇相关论文 |
| `/api/papers/{arxiv_id}/pending-count` | GET | 获取待获取论文数量 |
| `/api/papers/{arxiv_id}/restore` | POST | 恢复已删除的相关论文 |
| `/api/papers/{arxiv_id}/permanent` | POST | 彻底删除相关论文 |
| `/api/translate` | POST | 翻译标题和摘要 |

## 技术栈

- **后端**：FastAPI + SQLite
- **前端**：HTML5 + JavaScript + CSS
- **翻译**：OpenAI API (GPT-3.5/4) / 兼容接口
- **论文数据**：ArXiv API + Semantic Scholar API

## 外部 API 说明

本项目使用以下公开 API，无需注册即可使用：

| API | 用途 | 速率限制 |
|-----|------|---------|
| ArXiv API | 论文元数据和 PDF 下载 | 建议间隔 3 秒 |
| Semantic Scholar API | 相关论文查询 | 建议间隔 1 秒 |
| CrossRef API | DOI 查询 | 建议间隔 1 秒 |

> 注意：大量请求可能导致 IP 被限流，建议合理控制请求频率。

## LICENSE:  MIT