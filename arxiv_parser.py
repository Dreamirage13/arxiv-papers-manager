# ArXiv Papers Manager - ArXiv论文解析模块
"""
ArXiv论文信息获取模块：负责从ArXiv获取论文元数据和PDF下载
支持通过ArXiv ID、完整URL或上传PDF获取论文
"""
import re
import os
import json
import time
import requests
import feedparser
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse, parse_qs, quote
from config import ARXIV_API_URL, HEADERS, PAPERS_DIR


class ArxivParser:
    """
    ArXiv论文解析器：封装所有与ArXiv API交互的功能
    """
    
    def __init__(self):
        """初始化解析器"""
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
    
    def extract_arxiv_id(self, identifier: str) -> Optional[str]:
        """
        从各种格式的标识符中提取ArXiv ID
        
        支持的格式：
        - 完整URL: https://arxiv.org/abs/2301.12345
        - 纯ID: 2301.12345 或 arXiv:2301.12345
        
        Args:
            identifier: 论文标识符（URL或ID）
            
        Returns:
            Optional[str]: 提取的ArXiv ID，失败返回None
        """
        identifier = identifier.strip()
        
        # 1. 处理完整URL
        if 'arxiv.org' in identifier.lower():
            # 提取URL中的ID
            patterns = [
                r'arxiv\.org/abs/([0-9]+\.[0-9]+)',
                r'arxiv\.org/pdf/([0-9]+\.[0-9]+)',
                r'arxiv\.org/abs/([0-9]+\.[0-9]+v[0-9]+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, identifier.lower())
                if match:
                    return match.group(1)
        
        # 2. 处理纯ArXiv ID（带或不带前缀）
        id_match = re.search(r'([0-9]+\.[0-9]+v?[0-9]*)', identifier)
        if id_match:
            return id_match.group(1)
        
        return None
    
    def fetch_paper_by_id(self, arxiv_id: str) -> Optional[Dict[str, Any]]:
        """
        通过ArXiv API获取论文元数据
        
        Args:
            arxiv_id: ArXiv论文ID
            
        Returns:
            Optional[Dict]: 论文数据字典，获取失败返回None
        """
        try:
            # 构建API查询URL
            query = f"id_list={arxiv_id}"
            url = f"{ARXIV_API_URL}?{query}"
            
            # 发送请求
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # 解析Atom feed
            feed = feedparser.parse(response.content)
            
            if not feed.entries:
                print(f"未找到论文: {arxiv_id}")
                return None
            
            entry = feed.entries[0]
            return self._parse_entry(entry)
            
        except requests.RequestException as e:
            print(f"API请求失败: {e}")
            return None
    
    def _parse_entry(self, entry) -> Dict[str, Any]:
        """
        解析ArXiv API返回的条目数据
        
        Args:
            entry: feedparser条目对象
            
        Returns:
            Dict: 解析后的论文数据字典
        """
        # 提取ArXiv ID
        arxiv_id = entry.id.split('/')[-1]
        
        # 提取作者列表
        authors = [author.name for author in entry.authors]
        
        # 提取年份
        published = entry.get('published', '')
        year = int(published[:4]) if published else None
        
        # 提取摘要（移除LaTeX格式）
        abstract = entry.get('summary', '')
        abstract = self._clean_latex(abstract)
        
        # 提取DOI（可能在arxiv_doi或doi字段中）
        doi = None
        if hasattr(entry, 'arxiv_doi'):
            doi = entry.arxiv_doi
        elif hasattr(entry, 'doi'):
            doi = entry.doi
        
        # 提取期刊引用信息
        journal_ref = entry.get('arxiv_journal_ref') or entry.get('journal_ref')
        
        # 构建ArXiv URL
        arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"
        
        return {
            'arxiv_id': arxiv_id,
            'title': entry.get('title', '').replace('\n', ' ').strip(),
            'authors': authors,
            'year': year,
            'abstract': abstract,
            'arxiv_url': arxiv_url,
            'published': published,
            'doi': doi,
            'journal_ref': journal_ref,
        }
    
    def _clean_latex(self, text: str) -> str:
        """
        清理LaTeX格式标记
        
        Args:
            text: 原始文本
            
        Returns:
            str: 清理后的文本
        """
        # 移除常见的LaTeX标记
        replacements = [
            ('\\(', ''), ('\\)', ''),
            ('\\[', ''), ('\\]', ''),
            ('\\{', '{'), ('\\}', '}'),
            ('$', ''),
        ]
        for old, new in replacements:
            text = text.replace(old, new)
        return text.strip()
    
    def download_pdf(self, arxiv_id: str, save_dir: Path, is_original: bool = False) -> Tuple[bool, str]:
        """
        下载论文PDF文件
        
        Args:
            arxiv_id: ArXiv论文ID
            save_dir: 保存目录
            is_original: 是否为主论文（主论文文件名添加original标记）
            
        Returns:
            Tuple[bool, str]: (是否成功, 文件路径或错误信息)
        """
        try:
            # 创建目录
            save_dir = Path(save_dir)
            save_dir.mkdir(parents=True, exist_ok=True)
            
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            # 主论文文件名添加(original)标记
            if is_original:
                pdf_path = save_dir / f"{arxiv_id}(original).pdf"
            else:
                pdf_path = save_dir / f"{arxiv_id}.pdf"
            
            # 下载PDF
            response = self.session.get(pdf_url, timeout=60, stream=True)
            response.raise_for_status()
            
            # 检查是否为有效PDF
            content_type = response.headers.get('Content-Type', '')
            if 'pdf' not in content_type.lower() and not pdf_path.exists():
                return False, "下载的不是有效的PDF文件"
            
            # 保存文件
            with open(pdf_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return True, str(pdf_path)
            
        except requests.RequestException as e:
            return False, f"下载失败: {str(e)}"
    
    def extract_arxiv_id_from_pdf(self, pdf_content: bytes) -> Optional[str]:
        """
        从PDF文件中提取ArXiv ID
        
        优先查找：
        1. 带有版本号的arxiv id（如1706.03762v7）- 主论文特征
        2. PDF开头部分的arxiv id - 通常在第一页侧边
        3. 带有"arXiv:"前缀的id
        
        Args:
            pdf_content: PDF文件的字节内容
            
        Returns:
            Optional[str]: 提取的ArXiv ID，失败返回None
        """
        try:
            # 尝试使用PyMuPDF提取文本（更精确）
            try:
                import fitz  # PyMuPDF
                text = self._extract_text_with_pymupdf(pdf_content)
                if text:
                    arxiv_id = self._find_arxiv_id_from_text(text)
                    if arxiv_id:
                        return arxiv_id
            except ImportError:
                pass
            
            # 备用：直接搜索PDF字节内容
            content = pdf_content.decode('utf-8', errors='ignore')
            
            # 优先级1：查找带有版本号的arxiv id（如1706.03762v7）
            # 这种格式通常是主论文的特征
            patterns_with_version = [
                r'arxiv\.org/abs/(\d+\.\d+v\d+)',
                r'arXiv[:\s]+(\d+\.\d+v\d+)',
                r'(\d{4}\.\d{4}v\d+)',
            ]
            
            for pattern in patterns_with_version:
                matches = re.findall(pattern, content)
                if matches:
                    return matches[0]
            
            # 优先级2：查找PDF开头（前20000字符）的arxiv id
            # 主论文的arxiv id通常在第一页侧边
            front_content = content[:20000]
            
            patterns_front = [
                r'arxiv\.org/abs/(\d+\.\d+)',
                r'arXiv[:\s]+(\d+\.\d+)',
            ]
            
            for pattern in patterns_front:
                matches = re.findall(pattern, front_content)
                if matches:
                    return matches[0]
            
            # 优先级3：查找所有arxiv id
            patterns_all = [
                r'(\d{4}\.\d{4})',
            ]
            
            for pattern in patterns_all:
                matches = re.findall(pattern, content)
                if matches:
                    # 返回第一个4位数年份开头的匹配（更可能是主论文）
                    for match in matches:
                        if len(match) >= 7:  # 至少是YYYY.XXXX格式
                            return match
            
            return None
            
        except Exception as e:
            print(f"从PDF提取ArXiv ID失败: {e}")
            return None
    
    def _extract_text_with_pymupdf(self, pdf_content: bytes) -> Optional[str]:
        """
        使用PyMuPDF提取PDF文本
        
        Args:
            pdf_content: PDF字节内容
            
        Returns:
            Optional[str]: 提取的文本
        """
        try:
            import fitz
            import io
            
            doc = fitz.open(stream=pdf_content, filetype="pdf")
            text_parts = []
            
            # 只提取前5页（主论文信息通常在前面）
            max_pages = min(5, len(doc))
            for page_num in range(max_pages):
                page = doc[page_num]
                text = page.get_text()
                text_parts.append(text)
            
            doc.close()
            return '\n'.join(text_parts)
            
        except Exception as e:
            print(f"PyMuPDF提取文本失败: {e}")
            return None
    
    def _find_arxiv_id_from_text(self, text: str) -> Optional[str]:
        """
        从文本中查找ArXiv ID
        
        Args:
            text: PDF文本内容
            
        Returns:
            Optional[str]: ArXiv ID
        """
        # 优先级1：带有版本号的arxiv id
        patterns_version = [
            r'arxiv\.org/abs/(\d+\.\d+v\d+)',
            r'arXiv[:\s]+(\d+\.\d+v\d+)',
            r'(\d{4}\.\d{4}v\d+)',
        ]
        
        for pattern in patterns_version:
            matches = re.findall(pattern, text)
            if matches:
                return matches[0]
        
        # 优先级2：普通的arxiv id（但要避免引用文献）
        # 查找"arXiv:"前缀，这在主论文中更常见
        patterns_prefix = [
            r'arXiv[:\s]+(\d+\.\d+)',
            r'arxiv\.org/abs/(\d+\.\d+)',
        ]
        
        for pattern in patterns_prefix:
            matches = re.findall(pattern, text)
            if matches:
                # 返回第一个匹配
                return matches[0]
        
        return None
    
    def fetch_paper(self, identifier: str) -> Optional[Dict[str, Any]]:
        """
        统一的论文获取接口
        
        Args:
            identifier: 论文标识符（URL或ID）
            
        Returns:
            Optional[Dict]: 论文数据字典
        """
        # 提取ArXiv ID
        arxiv_id = self.extract_arxiv_id(identifier)
        if not arxiv_id:
            return None
        
        # 获取元数据
        paper_data = self.fetch_paper_by_id(arxiv_id)
        if not paper_data:
            return None
        
        return paper_data
    
    def fetch_paper_from_pdf(self, pdf_content: bytes) -> Optional[Dict[str, Any]]:
        """
        从上传的PDF文件获取论文信息
        
        Args:
            pdf_content: PDF文件的字节内容
            
        Returns:
            Optional[Dict]: 论文数据字典
        """
        # 从PDF中提取ArXiv ID
        arxiv_id = self.extract_arxiv_id_from_pdf(pdf_content)
        if not arxiv_id:
            return None
        
        # 获取论文元数据
        return self.fetch_paper_by_id(arxiv_id)
    
    def get_references(self, arxiv_id: str) -> list:
        """
        从ArXiv获取论文的参考文献列表
        
        注意：ArXiv API不直接提供参考文献列表，此方法返回空列表
        参考文献可从Connected Papers获取
        
        Args:
            arxiv_id: ArXiv论文ID
            
        Returns:
            list: 参考文献列表
        """
        # ArXiv API v1 不支持获取参考文献
        # 参考文献将通过Connected Papers获取
        return []
    
    def get_paper_dir(self, arxiv_id: str, base_dir: Path = None) -> Optional[str]:
        """
        获取论文文件夹路径
        
        Args:
            arxiv_id: ArXiv论文ID
            base_dir: 基础目录，默认使用配置目录
            
        Returns:
            Optional[str]: 论文文件夹路径，不存在则返回None
        """
        if base_dir is None:
            base_dir = PAPERS_DIR
        
        paper_dir = base_dir / arxiv_id.replace('/', '_')
        
        if paper_dir.exists():
            return str(paper_dir)
        
        return None
    
    def save_paper_files(self, paper_data: Dict[str, Any], base_dir: Path = None, 
                         uploaded_pdf: bytes = None, parent_arxiv_id: str = None) -> Dict[str, str]:
        """
        保存论文文件和元数据
        
        Args:
            paper_data: 论文数据字典
            base_dir: 保存基础目录，默认使用配置目录
            uploaded_pdf: 上传的PDF文件内容（如果有）
            parent_arxiv_id: 父论文arxiv_id（如果相关论文则传入主论文ID）
            
        Returns:
            Dict[str, str]: 保存的文件路径信息
        """
        if base_dir is None:
            base_dir = PAPERS_DIR
        
        arxiv_id = paper_data.get('arxiv_id', 'unknown')
        
        if parent_arxiv_id:
            # 相关论文：保存到主论文目录下
            paper_dir = base_dir / parent_arxiv_id.replace('/', '_')
            paper_dir.mkdir(parents=True, exist_ok=True)
        else:
            # 主论文：保存到自己的文件夹
            paper_dir = base_dir / arxiv_id.replace('/', '_')
            paper_dir.mkdir(parents=True, exist_ok=True)
        
        paths = {'dir': str(paper_dir)}
        
        # 判断是否为主论文
        is_original = not parent_arxiv_id
        
        # 如果有上传的PDF文件，直接保存
        if uploaded_pdf:
            # 主论文文件名添加(original)标记
            if is_original:
                pdf_path = paper_dir / f"{arxiv_id}(original).pdf"
            else:
                pdf_path = paper_dir / f"{arxiv_id}.pdf"
            with open(pdf_path, 'wb') as f:
                f.write(uploaded_pdf)
            paths['pdf'] = str(pdf_path)
        else:
            # 否则从ArXiv下载PDF
            success, result = self.download_pdf(arxiv_id, paper_dir, is_original=is_original)
            if success:
                paths['pdf'] = result
            else:
                paths['pdf_error'] = result
        
        # 保存主论文信息到metadata.json
        if not parent_arxiv_id:
            self._save_main_paper_metadata(paper_data, str(paper_dir))
        
        paths['metadata'] = str(paper_dir / "metadata.json")
        return paths
    
    def _save_main_paper_metadata(self, paper_data: Dict[str, Any], paper_dir: str) -> bool:
        """
        保存主论文信息到metadata.json
        
        Args:
            paper_data: 主论文数据字典
            paper_dir: 论文目录路径
            
        Returns:
            bool: 是否保存成功
        """
        try:
            metadata_path = Path(paper_dir) / "metadata.json"
            
            metadata = {
                "main_paper": {
                    'arxiv_id': paper_data.get('arxiv_id'),
                    'title': paper_data.get('title'),
                    'authors': paper_data.get('authors', []),
                    'year': paper_data.get('year'),
                    'abstract': paper_data.get('abstract', ''),
                    'arxiv_url': paper_data.get('arxiv_url'),
                    'pdf_path': paper_data.get('pdf_path', ''),
                    'citationCount': paper_data.get('citationCount', 0),
                    'referenceCount': paper_data.get('referenceCount', 0),
                    'doi': paper_data.get('doi'),
                    'journal_ref': paper_data.get('journal_ref'),
                },
                "related_papers": []
            }
            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            return True
            
        except Exception as e:
            print(f"保存主论文metadata.json失败: {e}")
            return False
    
    def update_parent_metadata(self, parent_arxiv_id: str, related_paper: Dict[str, Any], 
                                pdf_path: str = None, base_dir: Path = None) -> bool:
        """
        更新主论文目录下的metadata.json，添加相关论文信息
        
        Args:
            parent_arxiv_id: 主论文的arxiv_id
            related_paper: 相关论文数据字典
            pdf_path: 相关论文PDF路径
            base_dir: 基础目录
            
        Returns:
            bool: 是否更新成功
        """
        if base_dir is None:
            base_dir = PAPERS_DIR
        
        try:
            # 主论文目录
            paper_dir = base_dir / parent_arxiv_id.replace('/', '_')
            metadata_path = paper_dir / "metadata.json"
            
            # 读取现有metadata.json或创建新的
            if metadata_path.exists():
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            else:
                metadata = {"related_papers": []}
            
            # 确保related_papers字段存在
            if 'related_papers' not in metadata:
                metadata['related_papers'] = []
            
            # 添加相关论文信息
            related_info = {
                'arxiv_id': related_paper.get('arxiv_id'),
                'title': related_paper.get('title'),
                'authors': related_paper.get('authors', []),
                'year': related_paper.get('year'),
                'abstract': related_paper.get('abstract', ''),
                'arxiv_url': related_paper.get('arxiv_url'),
                'pdf_path': pdf_path,
                'citationCount': related_paper.get('citationCount', 0),
                'referenceCount': related_paper.get('referenceCount', 0),
                'relation_type': related_paper.get('relation_type'),  # citation: 被主论文引用, reference: 引用了主论文
                'paper_id': related_paper.get('_paper_id'),  # Semantic Scholar paperId，用于删除时恢复
                'doi': related_paper.get('doi'),
                'journal_ref': related_paper.get('journal_ref'),
            }
            
            # 检查是否已存在（避免重复添加）
            existing_ids = [p.get('arxiv_id') for p in metadata['related_papers']]
            if related_info['arxiv_id'] not in existing_ids:
                metadata['related_papers'].append(related_info)
                
                # 保存更新后的metadata.json
                with open(metadata_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)
                
                return True
            
            return False  # 已存在
            
        except Exception as e:
            print(f"更新metadata.json失败: {e}")
            return False


# 全局解析器实例
parser = ArxivParser()
