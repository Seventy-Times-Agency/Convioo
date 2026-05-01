"""User-uploaded knowledge files (sales deck, pricelist, brochure...).

The binary is parsed to plain text once on upload and stored in the
``user_knowledge_files.content_text`` column. Henry's prompts pull a
compact rendered block at draft-time so cold-emails can echo the user's
actual offering instead of paraphrasing their onboarding profile.
"""

from __future__ import annotations

import io
import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.db.models import UserKnowledgeFile

logger = logging.getLogger(__name__)


# Hard caps. Bumping these is a server-wide cost decision (more text
# in every prompt) — keep them tight by default.
MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB per upload
MAX_FILES_PER_USER = 10
MAX_PROMPT_BLOCK_CHARS = 5000  # combined across all files of one user

ACCEPTED_MIME = frozenset(
    {
        "application/pdf",
        "text/plain",
        "text/markdown",
    }
)


class KnowledgeFileError(ValueError):
    """Raised for invalid uploads (wrong type, too big, parse failure)."""


def extract_text(*, data: bytes, mime_type: str, filename: str) -> str:
    """Parse the uploaded blob to plain text. Raises on failure.

    PDFs go through pypdf with each page concatenated. Text-ish
    formats are decoded as UTF-8 with a tolerant fallback. The
    output is whitespace-collapsed so prompt budgets are predictable.
    """
    if mime_type not in ACCEPTED_MIME and not _looks_like_text(filename):
        raise KnowledgeFileError(
            f"Unsupported content type: {mime_type or filename}"
        )
    if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
        text = _extract_pdf(data)
    else:
        text = data.decode("utf-8", errors="replace")
    text = _collapse_whitespace(text)
    if not text.strip():
        raise KnowledgeFileError("file extracted to empty text")
    return text


def _looks_like_text(filename: str) -> bool:
    return filename.lower().endswith((".txt", ".md", ".markdown"))


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover — pypdf is a hard dep
        raise KnowledgeFileError(
            "pypdf is not installed on the server"
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001
                # Some PDFs have malformed pages; skip rather than fail.
                continue
        return "\n".join(pages)
    except Exception as exc:  # noqa: BLE001
        raise KnowledgeFileError(
            f"failed to parse PDF: {exc.__class__.__name__}"
        ) from exc


_WS_RE = re.compile(r"[ \t ]+")
_NL_RE = re.compile(r"\n{3,}")


def _collapse_whitespace(text: str) -> str:
    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n\n", text)
    return text.strip()


async def list_files(
    session: AsyncSession, *, user_id: int
) -> list[UserKnowledgeFile]:
    rows = (
        (
            await session.execute(
                select(UserKnowledgeFile)
                .where(UserKnowledgeFile.user_id == user_id)
                .order_by(UserKnowledgeFile.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def count_files(session: AsyncSession, *, user_id: int) -> int:
    rows = await list_files(session, user_id=user_id)
    return len(rows)


async def add_file(
    session: AsyncSession,
    *,
    user_id: int,
    filename: str,
    mime_type: str,
    data: bytes,
) -> UserKnowledgeFile:
    if len(data) > MAX_FILE_BYTES:
        raise KnowledgeFileError(
            f"file too big ({len(data)} bytes); max is {MAX_FILE_BYTES}"
        )
    existing = await count_files(session, user_id=user_id)
    if existing >= MAX_FILES_PER_USER:
        raise KnowledgeFileError(
            f"file limit reached ({MAX_FILES_PER_USER} per user); "
            "delete one before uploading more"
        )
    text = extract_text(data=data, mime_type=mime_type, filename=filename)
    row = UserKnowledgeFile(
        user_id=user_id,
        filename=filename[:255],
        mime_type=(mime_type or "application/octet-stream")[:120],
        byte_size=len(data),
        content_text=text,
    )
    session.add(row)
    await session.flush()
    return row


async def delete_file(
    session: AsyncSession, *, user_id: int, file_id
) -> bool:
    row = (
        await session.execute(
            select(UserKnowledgeFile)
            .where(UserKnowledgeFile.user_id == user_id)
            .where(UserKnowledgeFile.id == file_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True


async def render_knowledge_block(
    session: AsyncSession,
    *,
    user_id: int,
    char_budget: int = MAX_PROMPT_BLOCK_CHARS,
) -> str:
    """Compact prompt block describing the user's uploaded materials.

    Empty string when no files — keep prompts unchanged in that case.
    Files are concatenated newest-first until ``char_budget`` is hit;
    each file gets a short ``--- FILE: name`` separator so the model
    can attribute facts back if needed.
    """
    files = await list_files(session, user_id=user_id)
    if not files:
        return ""
    parts: list[str] = ["МАТЕРИАЛЫ ПОЛЬЗОВАТЕЛЯ (offering / pricelist / brochure):"]
    used = 0
    for f in files:
        header = f"\n--- FILE: {f.filename} ---\n"
        remaining = char_budget - used - len(header)
        if remaining <= 200:
            parts.append("\n[остальные файлы пропущены — лимит контекста]")
            break
        snippet = f.content_text[:remaining]
        parts.append(header + snippet)
        used += len(header) + len(snippet)
    parts.append(
        "\n--- END ---\n"
        "Учитывай это при скоринге и в cold-email — это реальное "
        "предложение продажника."
    )
    return "".join(parts)
