"""附件文件内容提取工具。

工作台 / 灵寻对话里用户上传的附件，模型只能拿到一个签名 URL，无法真正"读懂"文件。
这里负责把附件从对象存储下载下来，复用知识库的文档解析器（doc_parser）提取成纯文本，
再拼进提示词，让模型可以直接阅读附件内容。
"""
import os
import re
from typing import List
from urllib.parse import urlparse, unquote
from uuid import uuid4

from loguru import logger

from agentchat.services.storage import storage_client
from agentchat.settings import app_settings
from agentchat.services.rag.parser import doc_parser
from agentchat.utils.file_utils import get_save_tempfile

# 附件文本注入提示词的上限，避免超长附件撑爆上下文
MAX_ATTACHMENT_CHARS = 20000


def _object_key_from_url(file_url: str) -> str:
    """从签名 URL 中解析出对象存储的 object name（去掉 bucket 前缀）。"""
    parsed = urlparse(file_url)
    object_key = unquote(parsed.path).lstrip('/')
    bucket = app_settings.storage.active.bucket_name
    if object_key.startswith(bucket + "/"):
        object_key = object_key[len(bucket) + 1:]
    return object_key


def _display_name(file_url: str) -> str:
    """从 URL 路径中提取可读文件名，去掉上传时追加的随机后缀。"""
    name = os.path.basename(unquote(urlparse(file_url).path))
    # reset_file_name 生成形如「xxx_76ad0acd70.pdf」，去掉 _<8~10位hex> 后缀
    return re.sub(r"_[a-f0-9]{8,10}(?=\.)", "", name)


async def extract_attachment_text(file_url: str) -> str:
    """下载单个附件并解析为纯文本；失败返回空字符串。"""
    try:
        object_key = _object_key_from_url(file_url)
        local_file_path = get_save_tempfile(os.path.basename(unquote(urlparse(file_url).path)))
        storage_client.download_file(object_key, local_file_path)

        if not os.path.exists(local_file_path):
            logger.warning(f"附件下载失败：{file_url}")
            return ""

        chunks = await doc_parser.parse_doc_into_chunks(uuid4().hex, local_file_path, "attachment")
        text = "\n".join(c.content for c in chunks if c.content).strip()

        if len(text) > MAX_ATTACHMENT_CHARS:
            text = text[:MAX_ATTACHMENT_CHARS] + "\n……(附件内容过长，已截断)……"
        return text
    except Exception as err:
        logger.error(f"解析附件失败：{err}")
        return ""


async def build_query_with_attachments(query: str, file_urls: List[str]) -> str:
    """把附件内容拼进用户问题里，供模型直接阅读。

    未传附件、或附件全部解析失败时，原样返回 query。
    """
    if not file_urls:
        return query

    parts = []
    for file_url in file_urls:
        text = await extract_attachment_text(file_url)
        if text:
            parts.append(f"【附件《{_display_name(file_url)}》内容】\n{text}")

    if not parts:
        return query

    return "\n\n".join(parts) + f"\n\n【用户问题】\n{query}"
