import hashlib
import re
from dataclasses import dataclass

from energy_agent.retrieval.ingestion.parsers import ParsedBlock
from energy_agent.retrieval.tokenization import tokenize

CHUNKING_VERSION = "chunking.v1.0"


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    content: str
    content_hash: str
    chunk_order: int
    chapter_title: str
    section_type: str
    page_no: int | None
    keywords: list[str]


def _sections(block: ParsedBlock) -> list[tuple[str, str, str]]:
    if block.section_type == "表格":
        return [("表格", block.text, "表格")]
    output: list[tuple[str, str, str]] = []
    title = "正文"
    buffer: list[str] = []
    for line in block.text.splitlines():
        stripped = line.strip()
        if not stripped:
            if buffer:
                output.append((title, "\n".join(buffer), "正文"))
                buffer = []
            continue
        if re.match(
            r"^(#{1,6}\s+|第[一二三四五六七八九十\d]+[章节]\s*|"
            r"\d+(?:\.\d+)+\s+\S)",
            stripped,
        ):
            if buffer:
                output.append((title, "\n".join(buffer), "正文"))
                buffer = []
            if stripped.startswith("#") or len(stripped) <= 80:
                title = stripped.lstrip("# ").strip()
                continue
        section_type = (
            "注意事项"
            if re.search(r"注意|警告|危险", stripped)
            else "告警定义"
            if re.search(r"告警.*(?:定义|说明|含义)", stripped)
            else "维护步骤"
            if re.match(r"^\d+[.)、]", stripped)
            else "正文"
        )
        if section_type != "正文" and buffer:
            output.append((title, "\n".join(buffer), "正文"))
            buffer = []
        if section_type != "正文":
            output.append((title, stripped, section_type))
        else:
            buffer.append(stripped)
    if buffer:
        output.append((title, "\n".join(buffer), "正文"))
    return output


def _split_text(text: str, target: int, overlap: int) -> list[str]:
    if len(text) <= target:
        return [text] if text.strip() else []
    sentences = [item for item in re.split(r"(?<=[。！？.!?；;])", text) if item]
    if len(sentences) == 1:
        sentences = [text[index : index + target] for index in range(0, len(text), target)]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) > target:
            chunks.append(current.strip())
            prefix = current[-overlap:] if overlap else ""
            current = prefix + sentence
        else:
            current += sentence
    if current.strip():
        chunks.append(current.strip())
    return chunks


def chunk_blocks(
    doc_id: str,
    version: str,
    blocks: list[ParsedBlock],
    *,
    target: int = 500,
    overlap: int = 80,
) -> list[DocumentChunk]:
    output: list[DocumentChunk] = []
    order = 0
    for block in blocks:
        for title, text, section_type in _sections(block):
            limit = target if section_type == "正文" else max(target, len(text))
            for content in _split_text(text, limit, overlap):
                digest = hashlib.sha256(content.encode()).hexdigest()
                stable = hashlib.sha256(
                    f"{CHUNKING_VERSION}|{doc_id}|{version}|{order}|{digest}".encode()
                ).hexdigest()[:24]
                output.append(
                    DocumentChunk(
                        chunk_id=f"chunk_{stable}",
                        content=content,
                        content_hash=digest,
                        chunk_order=order,
                        chapter_title=title,
                        section_type=section_type,
                        page_no=block.page_no,
                        keywords=list(dict.fromkeys(tokenize(f"{title} {content}")))[:30],
                    )
                )
                order += 1
    return output
