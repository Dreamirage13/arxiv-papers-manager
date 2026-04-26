# ArXiv Papers Manager - 数据库模块
"""
数据库操作模块：负责论文元数据的存储、查询和管理
使用SQLite数据库，支持多表关联查询
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from config import DATABASE_PATH, PAPERS_DIR


class PaperDatabase:
    """
    论文数据库类：封装所有数据库操作
    
    数据库表结构：
    - papers: 主论文表
      - arxiv_id: ArXiv论文ID（主键）
      - title: 标题
      - authors: 作者列表（JSON格式存储）
      - year: 出版年份
      - abstract: 摘要
      - arxiv_url: ArXiv链接
      - pdf_path: PDF文件本地路径
      - created_at: 创建时间
      - parent_arxiv_id: 父论文ArXiv ID（如果是相关论文）
    """
    
    def __init__(self, db_path: str = str(DATABASE_PATH)):
        """
        初始化数据库连接
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._init_database()
    
    def _get_connection(self) -> sqlite3.Connection:
        """
        获取数据库连接（每次操作创建新连接，保证线程安全）
        
        Returns:
            sqlite3.Connection: 数据库连接对象
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 支持列名访问
        return conn
    
    def _init_database(self):
        """初始化数据库表结构"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 创建主论文表（使用ArXiv ID作为主键）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                arxiv_id TEXT PRIMARY KEY,           -- ArXiv ID作为主键
                title TEXT NOT NULL,                -- 论文标题
                authors TEXT,                       -- 作者列表（JSON格式）
                year INTEGER,                       -- 出版年份
                abstract TEXT,                      -- 摘要
                arxiv_url TEXT,                     -- ArXiv链接
                pdf_path TEXT,                      -- PDF本地路径
                created_at TEXT,                    -- 创建时间
                parent_arxiv_id TEXT,               -- 父论文ArXiv ID（NULL表示主论文）
                doi TEXT,                           -- DOI标识符
                journal_ref TEXT,                   -- 期刊/会议引用信息
                FOREIGN KEY (parent_arxiv_id) REFERENCES papers(arxiv_id)
            )
        """)
        
        # 创建参考文献表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS refs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_arxiv_id TEXT,               -- 所属论文ArXiv ID
                ref_arxiv_id TEXT,                  -- 参考文献ArXiv ID
                ref_title TEXT,                      -- 参考文献标题
                ref_arxiv_url TEXT,                 -- 参考文献ArXiv链接
                FOREIGN KEY (paper_arxiv_id) REFERENCES papers(arxiv_id),
                FOREIGN KEY (ref_arxiv_id) REFERENCES papers(arxiv_id)
            )
        """)
        
        # 创建索引提升查询性能
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_parent ON papers(parent_arxiv_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_year ON papers(year)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ref_paper ON refs(paper_arxiv_id)")
        
        # 迁移：检查并添加新的字段（支持已有数据库）
        self._migrate_add_columns(conn)
        
        conn.commit()
        conn.close()
    
    def _migrate_add_columns(self, conn: sqlite3.Connection):
        """
        迁移数据库，添加新字段（支持已有数据库）
        
        Args:
            conn: 数据库连接
        """
        cursor = conn.cursor()
        
        # 检查并添加 doi 字段
        cursor.execute("PRAGMA table_info(papers)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'doi' not in columns:
            cursor.execute("ALTER TABLE papers ADD COLUMN doi TEXT")
            print("数据库迁移：添加 doi 字段")
        
        if 'journal_ref' not in columns:
            cursor.execute("ALTER TABLE papers ADD COLUMN journal_ref TEXT")
            print("数据库迁移：添加 journal_ref 字段")
    
    def add_paper(self, paper_data: Dict[str, Any]) -> bool:
        """
        添加论文到数据库
        
        Args:
            paper_data: 论文数据字典，必须包含arxiv_id字段
            
        Returns:
            bool: 添加是否成功
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # ArXiv ID为必填字段
            arxiv_id = paper_data.get('arxiv_id')
            if not arxiv_id:
                print("错误：论文必须包含arxiv_id")
                return False
            
            # 将作者列表转换为JSON字符串存储
            authors_json = json.dumps(paper_data.get('authors', []), ensure_ascii=False)
            
            cursor.execute("""
                INSERT OR REPLACE INTO papers 
                (arxiv_id, title, authors, year, abstract, arxiv_url, pdf_path, created_at, parent_arxiv_id, doi, journal_ref)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                arxiv_id,
                paper_data.get('title', ''),
                authors_json,
                paper_data.get('year'),
                paper_data.get('abstract', ''),
                paper_data.get('arxiv_url', ''),
                paper_data.get('pdf_path', ''),
                datetime.now().isoformat(),
                paper_data.get('parent_arxiv_id'),  # NULL表示主论文
                paper_data.get('doi'),
                paper_data.get('journal_ref'),
            ))
            
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"数据库错误: {e}")
            return False
        finally:
            conn.close()
    
    def add_reference(self, paper_arxiv_id: str, ref_data: Dict[str, Any]) -> bool:
        """
        添加论文参考文献
        
        Args:
            paper_arxiv_id: 论文ArXiv ID
            ref_data: 参考文献数据
            
        Returns:
            bool: 添加是否成功
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO refs 
                (paper_arxiv_id, ref_arxiv_id, ref_title, ref_arxiv_url)
                VALUES (?, ?, ?, ?)
            """, (
                paper_arxiv_id,
                ref_data.get('arxiv_id', ''),
                ref_data.get('title', ''),
                ref_data.get('arxiv_url', '')
            ))
            
            conn.commit()
            return True
        except sqlite3.Error:
            return False
        finally:
            conn.close()
    
    def get_paper(self, arxiv_id: str) -> Optional[Dict[str, Any]]:
        """
        根据ArXiv ID获取论文详情
        
        Args:
            arxiv_id: ArXiv论文ID
            
        Returns:
            Optional[Dict]: 论文数据字典，不存在则返回None
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self._row_to_dict(row)
        return None
    
    def get_all_papers(self, parent_arxiv_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取所有主论文或指定论文的相关论文
        
        Args:
            parent_arxiv_id: 父论文ArXiv ID，None表示获取所有主论文
            
        Returns:
            List[Dict]: 论文列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if parent_arxiv_id is None:
            # 获取所有主论文
            cursor.execute("SELECT * FROM papers WHERE parent_arxiv_id IS NULL ORDER BY created_at DESC")
        else:
            # 获取指定主论文的相关论文
            cursor.execute("SELECT * FROM papers WHERE parent_arxiv_id = ? ORDER BY created_at", (parent_arxiv_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_dict(row) for row in rows]
    
    def get_paper_references(self, arxiv_id: str) -> List[Dict[str, Any]]:
        """
        获取论文的参考文献列表
        
        Args:
            arxiv_id: 论文ArXiv ID
            
        Returns:
            List[Dict]: 参考文献列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM refs WHERE paper_arxiv_id = ?", (arxiv_id,))
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_root_papers(self) -> List[Dict[str, Any]]:
        """
        获取所有主论文（根论文，即parent_arxiv_id为NULL的论文）
        
        Returns:
            List[Dict]: 主论文列表
        """
        return self.get_all_papers(parent_arxiv_id=None)
    
    def delete_paper(self, arxiv_id: str) -> bool:
        """
        删除论文（同时删除其相关论文和参考文献）
        
        Args:
            arxiv_id: 论文ArXiv ID
            
        Returns:
            bool: 删除是否成功
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 删除参考文献
            cursor.execute("DELETE FROM refs WHERE paper_arxiv_id = ? OR ref_arxiv_id = ?", (arxiv_id, arxiv_id))
            # 删除相关论文
            cursor.execute("DELETE FROM papers WHERE parent_arxiv_id = ?", (arxiv_id,))
            # 删除主论文
            cursor.execute("DELETE FROM papers WHERE arxiv_id = ?", (arxiv_id,))
            
            conn.commit()
            return True
        except sqlite3.Error:
            return False
        finally:
            conn.close()
    
    def paper_exists(self, arxiv_id: str) -> bool:
        """
        检查论文是否已存在
        
        Args:
            arxiv_id: ArXiv ID
            
        Returns:
            bool: 是否存在
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1 FROM papers WHERE arxiv_id = ?", (arxiv_id,))
        exists = cursor.fetchone() is not None
        conn.close()
        
        return exists
    
    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """
        将数据库行转换为字典
        
        Args:
            row: 数据库行
            
        Returns:
            Dict: 转换后的字典
        """
        data = dict(row)
        # 解析作者JSON字符串
        if 'authors' in data and data['authors']:
            try:
                data['authors'] = json.loads(data['authors'])
            except json.JSONDecodeError:
                data['authors'] = []
        return data
    
    def search_papers(self, keyword: str) -> List[Dict[str, Any]]:
        """
        搜索论文（按标题或摘要关键词）
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            List[Dict]: 匹配的论文列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        search_pattern = f"%{keyword}%"
        cursor.execute("""
            SELECT * FROM papers 
            WHERE title LIKE ? OR abstract LIKE ?
            ORDER BY created_at DESC
        """, (search_pattern, search_pattern))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_dict(row) for row in rows]


# 全局数据库实例
db = PaperDatabase()
