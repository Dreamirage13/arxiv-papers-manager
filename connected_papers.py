# ArXiv Papers Manager - 相关论文获取模块
"""
相关论文获取模块：每次获取一篇相关论文
使用 Semantic Scholar API 获取引用和参考文献
"""
import re
import time
import random
import requests
import feedparser
from pathlib import Path
from typing import Optional, Dict, Any, List
from config import HEADERS, PAPERS_DIR


class RelatedPapersParser:
    """
    相关论文解析器：获取论文的相关论文信息

    获取策略：
    1. 从 Semantic Scholar Citations/References API 获取相关论文
    2. 从 externalIds 提取 ArXiv ID（优先）
    3. 通过 DOI 在 CrossRef 查找 ArXiv ID（其次）
    4. 通过论文标题在 ArXiv 搜索（兜底）
    5. ArXiv ID 保存到 related_ids.txt，支持增量获取
    """

    # Semantic Scholar API 速率限制配置
    SEMANTIC_SCHOLAR_MIN_INTERVAL = 1.0  # 每次请求最小间隔（秒）
    CROSSREF_MIN_INTERVAL = 1.0         # CrossRef API 最小间隔（秒）
    ARXIV_MIN_INTERVAL = 3.0            # ArXiv API 最小间隔（秒）

    def __init__(self):
        """初始化解析器"""
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.semantic_scholar_base_url = "https://api.semanticscholar.org/graph/v1"
        self.arxiv_api_url = "http://export.arxiv.org/api/query"
        self._last_semantic_request = 0
        self._last_crossref_request = 0
        self._last_arxiv_request = 0

    def _rate_limit(self, request_type: str) -> None:
        """
        通用速率限制方法，确保不同类型的API请求遵守各自的间隔限制
        
        Args:
            request_type: 请求类型，可选值:
                - 'semantic': Semantic Scholar API (默认间隔 1 秒)
                - 'crossref': CrossRef API (默认间隔 1 秒)
                - 'arxiv': ArXiv API (默认间隔 3 秒)
        """
        import time
        
        if request_type == 'semantic':
            min_interval = self.SEMANTIC_SCHOLAR_MIN_INTERVAL
            last_request = self._last_semantic_request
        elif request_type == 'crossref':
            min_interval = self.CROSSREF_MIN_INTERVAL
            last_request = self._last_crossref_request
        elif request_type == 'arxiv':
            min_interval = self.ARXIV_MIN_INTERVAL
            last_request = self._last_arxiv_request
        else:
            min_interval = 1.0
            last_request = 0
        
        current_time = time.time()
        elapsed = current_time - last_request
        if elapsed < min_interval:
            sleep_time = min_interval - elapsed
            time.sleep(sleep_time)
        
        # 更新最后请求时间
        if request_type == 'semantic':
            self._last_semantic_request = time.time()
        elif request_type == 'crossref':
            self._last_crossref_request = time.time()
        elif request_type == 'arxiv':
            self._last_arxiv_request = time.time()

    def _extract_arxiv_id(self, identifier: str) -> Optional[str]:
        """从各种格式提取 ArXiv ID（不含版本号）"""
        if 'arxiv.org' in identifier:
            match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d+\.\d+)', identifier)
            if match:
                return match.group(1)

        match = re.search(r'(\d+\.\d+)', identifier)
        if match:
            return match.group(1)

        return None

    def _get_ids_file_path(self, main_arxiv_id: str) -> Path:
        """获取主论文的 paperId 列表文件路径"""
        paper_dir = PAPERS_DIR / main_arxiv_id.replace('/', '_')
        return paper_dir / "related_ids.txt"

    def _load_ids_file(self, main_arxiv_id: str) -> Dict[str, List[str]]:
        """加载主论文的 ArXiv ID 列表文件"""
        ids_file = self._get_ids_file_path(main_arxiv_id)
        result = {
            'citation': [],                    # 从 Citations API 获取的 ArXiv ID（待获取）
            'reference': [],                  # 从 References API 获取的 ArXiv ID（待获取）
            'extracted_from_citation': [],    # 已提取的 citation ArXiv ID
            'extracted_from_reference': []    # 已提取的 reference ArXiv ID
        }

        if ids_file.exists():
            try:
                with open(ids_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                current_type = None
                for line in lines:
                    line = line.strip()
                    if line == '[citation]':
                        current_type = 'citation'
                    elif line == '[reference]':
                        current_type = 'reference'
                    elif line == '[extracted from citation]':
                        current_type = 'extracted_from_citation'
                    elif line == '[extracted from reference]':
                        current_type = 'extracted_from_reference'
                    elif line and current_type and not line.startswith('#'):
                        result[current_type].append(line)
            except:
                pass

        return result

    def _save_ids_file(self, main_arxiv_id: str, ids_data: Dict[str, List[str]]) -> None:
        """保存 ArXiv ID 列表到文件"""
        ids_file = self._get_ids_file_path(main_arxiv_id)

        with open(ids_file, 'w', encoding='utf-8') as f:
            f.write("# 相关论文 ArXiv ID 列表\n")
            f.write("# citation: 从Citations API获取的ArXiv ID（待获取，这些论文引用了主论文）\n")
            f.write("# reference: 从References API获取的ArXiv ID（待获取，主论文引用了这些论文）\n")
            f.write("# extracted from citation: 已提取的citation ArXiv ID\n")
            f.write("# extracted from reference: 已提取的reference ArXiv ID\n\n")

            f.write("[citation]\n")
            for arxiv_id in ids_data.get('citation', []):
                f.write(f"{arxiv_id}\n")

            f.write("\n[reference]\n")
            for arxiv_id in ids_data.get('reference', []):
                f.write(f"{arxiv_id}\n")

            f.write("\n[extracted from citation]\n")
            for arxiv_id in ids_data.get('extracted_from_citation', []):
                f.write(f"{arxiv_id}\n")

            f.write("\n[extracted from reference]\n")
            for arxiv_id in ids_data.get('extracted_from_reference', []):
                f.write(f"{arxiv_id}\n")

    def _find_arxiv_by_doi(self, doi: str) -> Optional[str]:
        """根据 DOI 在 ArXiv 上查找论文 ArXiv ID"""
        try:
            self._rate_limit('crossref')  # CrossRef API 速率限制
            # 使用 CrossRef API 将 DOI 转换为 ArXiv ID
            crossref_url = f"https://api.crossref.org/works/{doi}"
            print(f"查询CrossRef API: {crossref_url}")
            response = self.session.get(crossref_url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                # 尝试获取 ArXiv URL
                arxiv_url = None
                items = data.get('message', {}).get('link', [])
                for item in items:
                    if 'arxiv.org' in item.get('URL', ''):
                        arxiv_url = item.get('URL')
                        break
                
                # 也检查 resource 部分
                if not arxiv_url:
                    resources = data.get('message', {}).get('resource', {})
                    if resources.get('primary', {}).get('URL'):
                        url = resources['primary']['URL']
                        if 'arxiv.org' in url:
                            arxiv_url = url
                
                if arxiv_url:
                    arxiv_id = self._extract_arxiv_id(arxiv_url)
                    if arxiv_id:
                        return arxiv_id
        except Exception as e:
            print(f"CrossRef查询失败: {e}")
        
        return None

    def _get_paper_ids_from_api(self, main_arxiv_id: str) -> Dict[str, List[str]]:
        """
        从 Semantic Scholar API 获取相关论文的 ArXiv ID

        Returns:
            Dict: {'citation': [ArXiv IDs], 'reference': [ArXiv IDs]}
        """
        all_ids = {'citation': [], 'reference': []}
        
        # 去除版本号
        pure_id = main_arxiv_id.split('v')[0] if 'v' in main_arxiv_id else main_arxiv_id

        # 1. 获取 Citations（引用该论文的论文）-> 这些论文引用了主论文
        citation_ids = self._get_citation_papers(pure_id)
        print(f"从Citations获取到 {len(citation_ids)} 篇引用主论文的论文")
        all_ids['citation'] = citation_ids

        # 2. 获取 References（该论文引用的论文）-> 主论文引用了这些论文
        reference_ids = self._get_reference_papers(pure_id)
        print(f"从References获取到 {len(reference_ids)} 篇主论文引用的论文")
        all_ids['reference'] = reference_ids

        return all_ids

    def _get_citation_papers(self, arxiv_id: str) -> List[str]:
        """获取引用该论文的所有 ArXiv ID"""
        try:
            self._rate_limit('semantic')  # Semantic Scholar API 速率限制
            url = f"{self.semantic_scholar_base_url}/paper/arXiv:{arxiv_id}/citations"
            params = {"fields": "paperId,title,externalIds", "limit": 100}
            print(f"请求 Citations API... ({url})")

            response = self.session.get(url, params=params, timeout=60)
            if response.status_code != 200:
                print(f"Citations API 返回: {response.status_code}")
                return []

            data = response.json()
            arxiv_ids = []
            
            for item in data.get('data', []):
                paper = item.get('citingPaper', {})
                if not paper.get('paperId'):
                    continue
                    
                # 优先从 externalIds 获取 ArXiv ID
                external_ids = paper.get('externalIds', {}) or {}
                arxiv_id_from_ids = external_ids.get('ArXiv')
                if arxiv_id_from_ids:
                    # 去除版本号
                    pure_arxiv_id = arxiv_id_from_ids.split('v')[0] if 'v' in arxiv_id_from_ids else arxiv_id_from_ids
                    if pure_arxiv_id and pure_arxiv_id not in arxiv_ids:
                        arxiv_ids.append(pure_arxiv_id)
                        continue
                
                # 如果没有 ArXiv ID，但有 DOI，尝试通过 CrossRef 获取
                doi = external_ids.get('DOI')
                if doi:
                    arxiv_id_from_doi = self._find_arxiv_by_doi(doi)
                    if arxiv_id_from_doi and arxiv_id_from_doi not in arxiv_ids:
                        arxiv_ids.append(arxiv_id_from_doi)
                        continue
                
                # 如果以上都没有，尝试通过论文标题在 ArXiv 搜索
                title = paper.get('title')
                if title:
                    arxiv_id_from_title = self._search_arxiv_by_title(title)
                    if arxiv_id_from_title and arxiv_id_from_title not in arxiv_ids:
                        arxiv_ids.append(arxiv_id_from_title)
            
            return arxiv_ids

        except Exception as e:
            print(f"获取Citations失败: {e}")
            return []

    def _get_reference_papers(self, arxiv_id: str) -> List[str]:
        """获取该论文引用的所有 ArXiv ID"""
        try:
            self._rate_limit('semantic')  # Semantic Scholar API 速率限制
            url = f"{self.semantic_scholar_base_url}/paper/arXiv:{arxiv_id}/references"
            params = {"fields": "paperId,title,externalIds", "limit": 100}
            print(f"请求 References API... ({url})")

            response = self.session.get(url, params=params, timeout=60)
            if response.status_code != 200:
                print(f"References API 返回: {response.status_code}")
                return []

            data = response.json()
            arxiv_ids = []
            
            for item in data.get('data', []):
                paper = item.get('citedPaper', {})
                if not paper.get('paperId'):
                    continue
                    
                # 优先从 externalIds 获取 ArXiv ID
                external_ids = paper.get('externalIds', {}) or {}
                arxiv_id_from_ids = external_ids.get('ArXiv')
                if arxiv_id_from_ids:
                    # 去除版本号
                    pure_arxiv_id = arxiv_id_from_ids.split('v')[0] if 'v' in arxiv_id_from_ids else arxiv_id_from_ids
                    if pure_arxiv_id and pure_arxiv_id not in arxiv_ids:
                        arxiv_ids.append(pure_arxiv_id)
                        continue
                
                # 如果没有 ArXiv ID，但有 DOI，尝试通过 CrossRef 获取
                doi = external_ids.get('DOI')
                if doi:
                    arxiv_id_from_doi = self._find_arxiv_by_doi(doi)
                    if arxiv_id_from_doi and arxiv_id_from_doi not in arxiv_ids:
                        arxiv_ids.append(arxiv_id_from_doi)
                        continue
                
                # 如果以上都没有，尝试通过论文标题在 ArXiv 搜索
                title = paper.get('title')
                if title:
                    arxiv_id_from_title = self._search_arxiv_by_title(title)
                    if arxiv_id_from_title and arxiv_id_from_title not in arxiv_ids:
                        arxiv_ids.append(arxiv_id_from_title)
            
            return arxiv_ids

        except Exception as e:
            print(f"获取References失败: {e}")
            return []

    def _search_arxiv_by_title(self, title: str) -> Optional[str]:
        """通过论文标题在 ArXiv 搜索查找 ArXiv ID"""
        try:
            self._rate_limit('arxiv')  # ArXiv API 速率限制
            # 清理标题，移除特殊字符
            clean_title = re.sub(r'[^\w\s]', ' ', title)
            # URL 编码
            import urllib.parse
            query = urllib.parse.quote(clean_title[:200])  # 限制长度
            
            search_url = f"{self.arxiv_api_url}?search_query=ti:{query}&start=0&max_results=5"
            print(f"  通过标题搜索ArXiv: {clean_title[:50]}...")
            
            response = self.session.get(search_url, timeout=30)
            if response.status_code == 200:
                feed = feedparser.parse(response.text)
                if feed.entries:
                    # 返回第一个匹配结果
                    entry = feed.entries[0]
                    match = re.search(r'(\d+\.\d+)', entry.get('id', ''))
                    if match:
                        return match.group(1)
        except Exception as e:
            print(f"  ArXiv标题搜索失败: {e}")
        return None

    def get_one_related_paper(self, main_arxiv_id: str) -> Optional[Dict[str, Any]]:
        """
        获取一篇相关论文

        Args:
            main_arxiv_id: 主论文的 ArXiv ID

        Returns:
            Optional[Dict]: 相关论文信息，包含 relation_type 字段
        """
        print(f"正在获取论文 {main_arxiv_id} 的相关论文...")

        # 获取主论文信息用于日志
        main_info = self._get_paper_meta(main_arxiv_id)
        if main_info:
            print(f"主论文标题: {main_info.get('title', '')[:60]}...")

        # 获取文件路径
        ids_file = self._get_ids_file_path(main_arxiv_id)
        file_exists = ids_file.exists()

        # 加载已保存的 ID 列表
        saved_ids = self._load_ids_file(main_arxiv_id)

        # 检查 citation 和 reference section（待获取列表）
        pending_citation = saved_ids['citation']
        pending_reference = saved_ids['reference']

        # 如果待获取列表为空
        if not pending_citation and not pending_reference:
            # 如果文件不存在，说明是第一次获取，需要先从 API 获取
            if not file_exists:
                print("首次获取相关论文，从 API 获取...")
                # 从 API 获取相关论文 ID
                api_ids = self._get_paper_ids_from_api(main_arxiv_id)
                citation_count = len(api_ids.get('citation', []))
                reference_count = len(api_ids.get('reference', []))

                if not citation_count and not reference_count:
                    print("从 API 获取不到任何相关论文")
                    return None

                # 保存到文件
                saved_ids['citation'] = api_ids.get('citation', [])
                saved_ids['reference'] = api_ids.get('reference', [])
                self._save_ids_file(main_arxiv_id, saved_ids)
                print(f"已保存 {citation_count} 个 citation 和 {reference_count} 个 reference 到文件")

                # 更新待获取列表
                pending_citation = saved_ids['citation']
                pending_reference = saved_ids['reference']
            else:
                # 文件存在但列表为空，说明已经全部获取过或被删除了
                print("获取相关论文失败：citation 和 reference 列表都为空")
                return None

        # 合并待处理列表并打乱顺序
        all_pending_ids = pending_citation + pending_reference
        random.shuffle(all_pending_ids)

        for arxiv_id in all_pending_ids:
            # 确定来源 section
            if arxiv_id in pending_citation:
                source_section = 'citation'
            else:
                source_section = 'reference'

            print(f"\n尝试 ArXiv ID: {arxiv_id} (来自 {source_section})")

            # 排除主论文自身
            pure_main_id = main_arxiv_id.split('v')[0] if 'v' in main_arxiv_id else main_arxiv_id
            if arxiv_id == pure_main_id:
                print(f"  是主论文自身，从列表移除...")
                if arxiv_id in saved_ids['citation']:
                    saved_ids['citation'].remove(arxiv_id)
                else:
                    saved_ids['reference'].remove(arxiv_id)
                self._save_ids_file(main_arxiv_id, saved_ids)
                # 更新 pending 列表
                pending_citation = saved_ids['citation']
                pending_reference = saved_ids['reference']
                continue

            # 确定关系类型
            # citation section -> 这些论文引用了主论文 -> relation_type='reference'
            # reference section -> 主论文引用了这些论文 -> relation_type='citation'
            relation_type = 'reference' if source_section == 'citation' else 'citation'

            print(f"选中论文: {arxiv_id} (关系: {relation_type})")

            # 获取论文详细信息
            paper = self._get_paper_info(arxiv_id)
            if paper:
                # 从原始列表移除，添加到 extracted 列表（存储到与 source_section 对应的 extracted 列表）
                if source_section == 'citation':
                    saved_ids['citation'].remove(arxiv_id)
                    saved_ids['extracted_from_citation'].append(arxiv_id)
                else:
                    saved_ids['reference'].remove(arxiv_id)
                    saved_ids['extracted_from_reference'].append(arxiv_id)
                self._save_ids_file(main_arxiv_id, saved_ids)

                paper['relation_type'] = relation_type
                paper['source_section'] = source_section  # 用于恢复时确定目标列表
                return paper

            # 获取失败，从原始列表移除，添加到 extracted 列表
            if source_section == 'citation':
                saved_ids['citation'].remove(arxiv_id)
                saved_ids['extracted_from_citation'].append(arxiv_id)
            else:
                saved_ids['reference'].remove(arxiv_id)
                saved_ids['extracted_from_reference'].append(arxiv_id)
            self._save_ids_file(main_arxiv_id, saved_ids)
            # 更新 pending 列表
            pending_citation = saved_ids['citation']
            pending_reference = saved_ids['reference']

        print("所有 ArXiv ID 都已尝试，没有找到有效论文")
        return None

    def restore_arxiv_id(self, main_arxiv_id: str, arxiv_id: str, relation_type: str) -> bool:
        """
        恢复 ArXiv ID 到原始列表（用于"删除"操作）

        Args:
            main_arxiv_id: 主论文的 ArXiv ID
            arxiv_id: 要恢复的 ArXiv ID
            relation_type: 关系类型 ('citation' 或 'reference')

        Returns:
            bool: 是否成功恢复
        """
        saved_ids = self._load_ids_file(main_arxiv_id)

        # 根据 relation_type 确定源列表和目标列表
        # relation_type='reference' -> 来自 citation section -> 存于 extracted_from_citation -> 恢复到 citation
        # relation_type='citation' -> 来自 reference section -> 存于 extracted_from_reference -> 恢复到 reference
        if relation_type == 'reference':
            source_list = 'extracted_from_citation'
            target_list = 'citation'
        else:
            source_list = 'extracted_from_reference'
            target_list = 'reference'

        # 从 extracted 列表移除并添加到原始列表
        if arxiv_id in saved_ids[source_list]:
            saved_ids[source_list].remove(arxiv_id)
            if arxiv_id not in saved_ids[target_list]:
                saved_ids[target_list].append(arxiv_id)
            self._save_ids_file(main_arxiv_id, saved_ids)
            print(f"已恢复 ArXiv ID {arxiv_id} 到 {target_list} 列表")
            return True

        return False

    def permanently_remove_arxiv_id(self, main_arxiv_id: str, arxiv_id: str, relation_type: str) -> bool:
        """
        彻底删除 ArXiv ID（用于"彻底删除"操作）

        Args:
            main_arxiv_id: 主论文的 ArXiv ID
            arxiv_id: 要彻底删除的 ArXiv ID
            relation_type: 关系类型 ('citation' 或 'reference')

        Returns:
            bool: 是否成功删除
        """
        saved_ids = self._load_ids_file(main_arxiv_id)

        # 根据 relation_type 确定源列表
        # relation_type='reference' -> 存于 extracted_from_citation
        # relation_type='citation' -> 存于 extracted_from_reference
        if relation_type == 'reference':
            source_list = 'extracted_from_citation'
        else:
            source_list = 'extracted_from_reference'

        # 只从 extracted 列表移除
        if arxiv_id in saved_ids[source_list]:
            saved_ids[source_list].remove(arxiv_id)
            self._save_ids_file(main_arxiv_id, saved_ids)
            print(f"已彻底删除 ArXiv ID {arxiv_id}")
            return True

        return False

    def get_saved_ids_count(self, main_arxiv_id: str) -> Dict[str, int]:
        """获取已保存的 ArXiv ID 数量"""
        saved_ids = self._load_ids_file(main_arxiv_id)
        return {
            'citation': len(saved_ids['citation']),
            'reference': len(saved_ids['reference']),
            'extracted_citation': len(saved_ids['extracted_from_citation']),
            'extracted_reference': len(saved_ids['extracted_from_reference']),
            'total_pending': len(saved_ids['citation']) + len(saved_ids['reference']),
            'total': len(saved_ids['citation']) + len(saved_ids['reference']) + len(saved_ids['extracted_from_citation']) + len(saved_ids['extracted_from_reference'])
        }

    def _get_paper_meta(self, arxiv_id: str) -> Optional[Dict]:
        """获取论文基本信息"""
        pure_id = arxiv_id.split('v')[0] if 'v' in arxiv_id else arxiv_id
        try:
            self._rate_limit('semantic')  # Semantic Scholar API 速率限制
            url = f"{self.semantic_scholar_base_url}/paper/arXiv:{pure_id}"
            params = {"fields": "title,paperId"}
            response = self.session.get(url, params=params, timeout=30)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return None

    def _get_paper_info(self, arxiv_id: str) -> Optional[Dict[str, Any]]:
        """获取论文详细信息"""
        # 先尝试 Semantic Scholar
        pure_id = arxiv_id.split('v')[0] if 'v' in arxiv_id else arxiv_id
        try:
            self._rate_limit('semantic')  # Semantic Scholar API 速率限制
            url = f"{self.semantic_scholar_base_url}/paper/arXiv:{pure_id}"
            params = {
                "fields": "title,authors,year,abstract,externalIds,citationCount,referenceCount"
            }

            print(f"获取论文信息: {arxiv_id}")
            response = self.session.get(url, params=params, timeout=30)

            if response.status_code == 200:
                paper = response.json()

                authors = [a.get('name', '') for a in paper.get('authors', [])]
                authors_str = ', '.join(authors[:3])
                if len(authors) > 3:
                    authors_str += ' et al.'

                return {
                    'title': paper.get('title', ''),
                    'authors': authors,
                    'authors_display': authors_str,
                    'year': paper.get('year'),
                    'abstract': paper.get('abstract', ''),
                    'arxiv_id': arxiv_id,
                    'arxiv_url': f"https://arxiv.org/abs/{arxiv_id}",
                    'citationCount': paper.get('citationCount', 0),
                    'referenceCount': paper.get('referenceCount', 0)
                }
        except Exception as e:
            print(f"Semantic Scholar 获取失败: {e}")

        # 备用：使用 ArXiv API
        return self._get_paper_from_arxiv(arxiv_id)

    def _get_paper_from_arxiv(self, arxiv_id: str) -> Optional[Dict[str, Any]]:
        """从 ArXiv API 获取论文信息"""
        try:
            self._rate_limit('arxiv')  # ArXiv API 速率限制
            api_url = f"{self.arxiv_api_url}?id_list={arxiv_id}"
            print(f"从ArXiv API获取: {api_url}")
            response = self.session.get(api_url, timeout=30)

            if response.status_code != 200:
                return None

            feed = feedparser.parse(response.text)
            if not feed.entries:
                return None

            entry = feed.entries[0]

            authors = [a.get('name', '') for a in entry.get('authors', [])]
            authors_str = ', '.join(authors[:3])
            if len(authors) > 3:
                authors_str += ' et al.'

            summary = entry.get('summary', '').replace('\n', ' ').strip()
            published = entry.get('published', '')
            year = int(published[:4]) if published else None

            return {
                'title': entry.get('title', '').replace('\n', ' ').strip(),
                'authors': authors,
                'authors_display': authors_str,
                'year': year,
                'abstract': summary,
                'arxiv_id': arxiv_id,
                'arxiv_url': f"https://arxiv.org/abs/{arxiv_id}",
                'citationCount': 0,
                'referenceCount': 0,
                'doi': entry.get('arxiv_doi') or entry.get('doi'),
                'journal_ref': entry.get('arxiv_journal_ref') or entry.get('journal_ref'),
            }

        except Exception as e:
            print(f"ArXiv获取失败: {e}")
            return None


# 全局实例
related_parser = RelatedPapersParser()
