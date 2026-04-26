# ArXiv Papers Manager - 应用入口
"""
主应用模块：FastAPI Web服务器
提供RESTful API接口，处理论文上传、获取和翻译请求
"""
import os
import json
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

# 导入项目模块
import config
from database import db, PaperDatabase
from arxiv_parser import parser as arxiv_parser
from connected_papers import related_parser
from translator import translator
from config import PAPERS_DIR


# ==================== FastAPI应用初始化 ====================
app = FastAPI(
    title="ArXiv Papers Manager",
    description="ArXiv论文管理网页应用 - 获取相关论文并翻译",
    version="1.0.0"
)

# 启动时打印所有注册的路由（调试用）
@app.on_event("startup")
async def startup_event():
    print("\n[DEBUG] 已注册的路由:")
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            print(f"  {route.methods} {route.path}")
    print("[DEBUG] 路由列表结束\n")

# 配置模板引擎（前端HTML渲染）
templates = Jinja2Templates(directory="templates")

# 确保静态文件目录存在
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)


# ==================== 静态文件服务 ====================
# 挂载静态文件目录（用于CSS、JS等资源）
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ==================== 辅助函数 ====================

def paper_to_display(paper: Dict[str, Any]) -> Dict[str, Any]:
    """
    将论文数据转换为前端显示格式
    
    Args:
        paper: 原始论文数据
        
    Returns:
        Dict: 处理后的显示数据
    """
    # 格式化作者列表
    authors = paper.get('authors', [])
    if isinstance(authors, str):
        authors = [authors]
    
    # 截断长摘要用于预览（3行约150字符）
    abstract = paper.get('abstract', '')
    if len(abstract) > 200:
        abstract_preview = abstract[:200] + '...'
    else:
        abstract_preview = abstract
    
    return {
        'arxiv_id': paper.get('arxiv_id', ''),
        'title': paper.get('title', ''),
        'authors': authors,
        'authors_display': ', '.join(authors[:5]) + (' et al.' if len(authors) > 5 else ''),
        'year': paper.get('year', ''),
        'abstract': abstract,
        'abstract_preview': abstract_preview,
        'arxiv_url': paper.get('arxiv_url', ''),
        'pdf_path': paper.get('pdf_path', ''),
        'created_at': paper.get('created_at', ''),
        'parent_arxiv_id': paper.get('parent_arxiv_id'),
        'is_main_paper': paper.get('parent_arxiv_id') is None,
        'relation_type': paper.get('relation_type'),  # 关系类型：citation 或 reference
    }


# ==================== API路由 ====================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    首页路由：渲染主页面
    
    Returns:
        HTMLResponse: 渲染后的HTML页面
    """
    # 获取所有主论文
    main_papers = db.get_root_papers()
    
    # 转换为显示格式
    papers_display = [paper_to_display(p) for p in main_papers]
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "papers": papers_display,
            "translator_configured": translator.is_configured()
        }
    )


@app.get("/api/papers")
async def get_papers():
    """
    获取所有主论文列表API
    
    Returns:
        JSON: 所有主论文数据
    """
    papers = db.get_root_papers()
    return JSONResponse({
        "success": True,
        "papers": [paper_to_display(p) for p in papers]
    })


@app.get("/api/papers/{arxiv_id}")
async def get_paper(arxiv_id: str):
    """
    获取指定论文详情API
    
    Args:
        arxiv_id: ArXiv论文ID
        
    Returns:
        JSON: 论文详情
    """
    paper = db.get_paper(arxiv_id)
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")
    
    # 获取相关论文
    related_papers = db.get_all_papers(parent_arxiv_id=arxiv_id)
    
    return JSONResponse({
        "success": True,
        "paper": paper_to_display(paper),
        "related_papers": [paper_to_display(p) for p in related_papers]
    })


@app.post("/api/papers")
async def add_paper(identifier: str = Form(...)):
    """
    添加论文API（通过ArXiv ID或URL）
    
    Args:
        identifier: ArXiv论文ID或URL
        
    Returns:
        JSON: 添加结果
    """
    try:
        # 解析ArXiv论文
        paper_data = arxiv_parser.fetch_paper(identifier)
        
        if not paper_data:
            return JSONResponse({
                "success": False,
                "error": "无法获取论文信息，请检查ArXiv ID或URL是否正确"
            }, status_code=400)
        
        arxiv_id = paper_data.get('arxiv_id')
        
        # 检查是否已存在
        if db.paper_exists(arxiv_id):
            return JSONResponse({
                "success": False,
                "error": "论文已存在",
                "arxiv_id": arxiv_id
            }, status_code=409)
        
        # 保存PDF和元数据
        paths = arxiv_parser.save_paper_files(paper_data)
        paper_data['pdf_path'] = paths.get('pdf', '')
        
        # 添加到数据库
        success = db.add_paper(paper_data)
        
        if not success:
            return JSONResponse({
                "success": False,
                "error": "数据库保存失败"
            }, status_code=500)
        
        return JSONResponse({
            "success": True,
            "paper": paper_to_display(paper_data)
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)


@app.post("/api/papers/upload")
async def upload_paper(file: UploadFile = File(...)):
    """
    上传PDF文件API - 从PDF中提取ArXiv ID并获取论文信息
    
    Args:
        file: 上传的PDF文件
        
    Returns:
        JSON: 上传结果
    """
    try:
        # 检查文件类型
        if not file.filename.endswith('.pdf'):
            return JSONResponse({
                "success": False,
                "error": "仅支持PDF文件"
            }, status_code=400)
        
        # 读取PDF内容
        content = await file.read()
        
        # 从PDF中提取ArXiv ID并获取论文信息
        paper_data = arxiv_parser.fetch_paper_from_pdf(content)
        
        if not paper_data:
            return JSONResponse({
                "success": False,
                "error": "无法从PDF中提取ArXiv ID，请确保PDF包含正确的ArXiv链接或ID"
            }, status_code=400)
        
        arxiv_id = paper_data.get('arxiv_id')
        
        # 检查是否已存在
        if db.paper_exists(arxiv_id):
            return JSONResponse({
                "success": False,
                "error": "论文已存在",
                "arxiv_id": arxiv_id
            }, status_code=409)
        
        # 保存PDF和元数据（传入上传的PDF内容）
        paths = arxiv_parser.save_paper_files(paper_data, uploaded_pdf=content)
        paper_data['pdf_path'] = paths.get('pdf', '')
        
        # 添加到数据库
        success = db.add_paper(paper_data)
        
        if not success:
            return JSONResponse({
                "success": False,
                "error": "数据库保存失败"
            }, status_code=500)
        
        return JSONResponse({
            "success": True,
            "paper": paper_to_display(paper_data)
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)


@app.get("/api/papers/{arxiv_id}/related")
async def get_related_papers(arxiv_id: str):
    """
    获取论文的相关论文列表API
    
    Args:
        arxiv_id: 主论文ArXiv ID
        
    Returns:
        JSON: 相关论文列表
    """
    # 从主论文的metadata.json中读取相关论文
    paper_dir = PAPERS_DIR / arxiv_id.replace('/', '_')
    metadata_path = paper_dir / "metadata.json"
    
    related_papers = []
    if metadata_path.exists():
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            related_papers = metadata.get('related_papers', [])
        except:
            pass
    
    return JSONResponse({
        "success": True,
        "related_papers": [paper_to_display(p) for p in related_papers]
    })


@app.post("/api/papers/{arxiv_id}/fetch-related")
async def fetch_related_paper(arxiv_id: str):
    """
    获取一篇相关论文

    Args:
        arxiv_id: 主论文ArXiv ID

    Returns:
        JSON: 获取结果
    """
    print(f"[DEBUG] 收到获取相关论文请求，arxiv_id: {arxiv_id}")

    try:
        # 获取主论文信息
        main_paper = db.get_paper(arxiv_id)
        if not main_paper:
            print(f"[DEBUG] 主论文不存在: {arxiv_id}")
            raise HTTPException(status_code=404, detail="主论文不存在")

        # 获取一篇相关论文（传入主论文的 arxiv_id）
        related_data = related_parser.get_one_related_paper(arxiv_id)

        if not related_data:
            return JSONResponse({
                "success": False,
                "error": "无法获取相关论文"
            }, status_code=404)

        related_id = related_data.get('arxiv_id')

        # 检查是否已存在（通过metadata.json检查）
        from config import PAPERS_DIR
        paper_dir = PAPERS_DIR / arxiv_id.replace('/', '_')
        metadata_path = paper_dir / "metadata.json"

        if metadata_path.exists():
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                existing_ids = [p.get('arxiv_id') for p in metadata.get('related_papers', [])]
                if related_id in existing_ids:
                    return JSONResponse({
                        "success": False,
                        "error": "该相关论文已存在",
                        "arxiv_id": related_id
                    }, status_code=409)
            except:
                pass

        # 保存PDF到主论文目录下
        paths = arxiv_parser.save_paper_files(related_data, parent_arxiv_id=arxiv_id)
        pdf_path = paths.get('pdf', '')

        # 更新主论文目录下的metadata.json
        arxiv_parser.update_parent_metadata(arxiv_id, related_data, pdf_path)

        # 保存相关论文信息用于返回（不添加到独立数据库）
        related_data['pdf_path'] = pdf_path
        related_data['parent_arxiv_id'] = arxiv_id

        return JSONResponse({
            "success": True,
            "paper": paper_to_display(related_data)
        })

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)


@app.post("/api/translate")
async def translate_paper_content(title: str = Form(...), abstract: str = Form(...)):
    """
    翻译论文标题和摘要API
    
    Args:
        title: 论文标题
        abstract: 论文摘要
        
    Returns:
        JSON: 翻译结果
    """
    try:
        result = translator.translate_paper(title, abstract)
        
        return JSONResponse({
            "success": True,
            "translation": result
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)


@app.delete("/api/papers/{arxiv_id}")
async def delete_paper(arxiv_id: str, related_to: str = None, permanent: bool = False):
    """
    删除论文API

    Args:
        arxiv_id: 论文ArXiv ID
        related_to: 如果删除的是相关论文，传入主论文的arxiv_id
        permanent: 是否彻底删除（默认False，会恢复ArXiv ID到原列表）

    Returns:
        JSON: 删除结果
    """
    # 如果有 related_to 参数，说明删除的是主论文下的相关论文
    if related_to:
        return await _delete_related_paper(arxiv_id, related_to, permanent)

    # 检查是否是主论文
    paper = db.get_paper(arxiv_id)

    if paper:
        # 数据库中存在，可能是主论文或旧数据
        parent_id = paper.get('parent_arxiv_id')

        if parent_id:
            # 相关论文：删除PDF并从metadata.json移除
            return await _delete_related_paper(arxiv_id, parent_id, permanent)
        else:
            # 主论文：删除整个文件夹和数据库记录
            return await _delete_main_paper(arxiv_id)
    else:
        # 数据库中不存在，可能是相关论文（只在metadata.json中）
        # 搜索所有主论文的metadata.json来找到相关论文
        return await _find_and_delete_related_paper(arxiv_id, permanent)


async def _delete_related_paper(arxiv_id: str, parent_arxiv_id: str, permanent: bool = False):
    """删除相关论文"""
    try:
        paper_dir = PAPERS_DIR / parent_arxiv_id.replace('/', '_')
        metadata_path = paper_dir / "metadata.json"

        # 获取该论文的 relation_type
        relation_type = None
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            for p in metadata.get('related_papers', []):
                if p.get('arxiv_id') == arxiv_id:
                    relation_type = p.get('relation_type', 'citation')
                    break

            metadata['related_papers'] = [
                p for p in metadata.get('related_papers', [])
                if p.get('arxiv_id') != arxiv_id
            ]

            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

        # 删除PDF文件
        pdf_path = paper_dir / f"{arxiv_id}.pdf"
        if pdf_path.exists():
            pdf_path.unlink()
            print(f"[DEBUG] 删除PDF: {pdf_path}")

        # 根据 permanent 参数决定是恢复还是彻底删除
        if not permanent and relation_type:
            # 恢复 ArXiv ID 到原列表
            related_parser.restore_arxiv_id(parent_arxiv_id, arxiv_id, relation_type)
        elif permanent and relation_type:
            # 彻底删除 ArXiv ID
            related_parser.permanently_remove_arxiv_id(parent_arxiv_id, arxiv_id, relation_type)

        return JSONResponse({"success": True})

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


async def _find_and_delete_related_paper(arxiv_id: str, permanent: bool = False):
    """在所有主论文的metadata.json中查找并删除相关论文"""
    try:
        # 遍历所有主论文文件夹
        for paper_dir in PAPERS_DIR.iterdir():
            if not paper_dir.is_dir():
                continue

            metadata_path = paper_dir / "metadata.json"
            if not metadata_path.exists():
                continue

            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            except:
                continue

            related_papers = metadata.get('related_papers', [])

            # 查找是否有这个相关论文
            relation_type = None
            for related in related_papers:
                if related.get('arxiv_id') == arxiv_id:
                    # 找到相关论文，获取 relation_type
                    relation_type = related.get('relation_type', 'citation')
                    parent_arxiv_id = paper_dir.name

                    # 删除PDF
                    pdf_path = paper_dir / f"{arxiv_id}.pdf"
                    if pdf_path.exists():
                        pdf_path.unlink()
                        print(f"[DEBUG] 删除PDF: {pdf_path}")

                    # 从metadata中移除
                    metadata['related_papers'] = [
                        p for p in related_papers
                        if p.get('arxiv_id') != arxiv_id
                    ]

                    with open(metadata_path, 'w', encoding='utf-8') as f:
                        json.dump(metadata, f, ensure_ascii=False, indent=2)

                    # 根据 permanent 参数决定是恢复还是彻底删除
                    if not permanent and relation_type:
                        # 恢复 ArXiv ID 到原列表
                        related_parser.restore_arxiv_id(parent_arxiv_id, arxiv_id, relation_type)
                    elif permanent and relation_type:
                        # 彻底删除 ArXiv ID
                        related_parser.permanently_remove_arxiv_id(parent_arxiv_id, arxiv_id, relation_type)

                    return JSONResponse({"success": True})

        # 没找到
        raise HTTPException(status_code=404, detail="论文不存在")

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


async def _delete_main_paper(arxiv_id: str):
    """删除主论文及其所有相关论文"""
    try:
        # 删除论文文件夹
        paper_dir = PAPERS_DIR / arxiv_id.replace('/', '_')
        if paper_dir.exists():
            import shutil
            shutil.rmtree(paper_dir)
            print(f"[DEBUG] 删除论文文件夹: {paper_dir}")
        
        # 删除数据库记录
        db.delete_paper(arxiv_id)
        
        return JSONResponse({"success": True})
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/papers/{arxiv_id}/pdf")
async def get_paper_pdf(arxiv_id: str, parent_id: str = None):
    """
    下载论文PDF API
    
    Args:
        arxiv_id: 论文ArXiv ID
        parent_id: 如果是相关论文，传入主论文的arxiv_id
        
    Returns:
        FileResponse: PDF文件
    """
    # 确定PDF路径
    if parent_id:
        # 相关论文：从主论文目录下获取
        pdf_path = PAPERS_DIR / parent_id.replace('/', '_') / f"{arxiv_id}.pdf"
    else:
        # 尝试从数据库获取
        paper = db.get_paper(arxiv_id)
        if paper:
            pdf_path = paper.get('pdf_path')
        else:
            # 可能是相关论文但没传parent_id，尝试搜索
            pdf_path = None
    
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF文件不存在")
    
    return FileResponse(
        path=pdf_path,
        filename=f"{arxiv_id}.pdf",
        media_type="application/pdf"
    )


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return JSONResponse({
        "status": "healthy",
        "translator_configured": translator.is_configured()
    })


# ==================== 启动函数 ====================

def main():
    """启动应用"""
    print("=" * 50)
    print("ArXiv Papers Manager 启动中...")
    print("=" * 50)
    
    # 检查翻译器配置
    if not translator.is_configured():
        print("\n⚠️  翻译功能未配置（缺少OPENAI_API_KEY）")
        print("   如需使用翻译功能，请设置环境变量：")
        print("   export OPENAI_API_KEY='your-api-key'\n")
    
    # 启动服务器
    host = config.SERVER_CONFIG['host']
    port = config.SERVER_CONFIG['port']
    debug = config.SERVER_CONFIG['debug']
    
    print(f"访问地址: http://{host}:{port}")
    print("按 Ctrl+C 停止服务")
    print("=" * 50)
    
    # 使用导入字符串方式启动（解决reload模式警告）
    uvicorn.run(
        "main:app",  # 使用模块导入路径而非直接传入app对象
        host=host,
        port=port,
        reload=debug
    )


if __name__ == "__main__":
    main()
