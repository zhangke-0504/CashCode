from __future__ import annotations

import io
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .loader import (
    ALLOWED_ROOT_ENTRIES,
    ALLOWED_SUPPORT_DIRS,
    MAX_SKILL_ARCHIVE_ENTRIES,
    MAX_SKILL_ARCHIVE_EXPANDED_BYTES,
    MAX_SKILL_BYTES,
    MAX_SKILL_ZIP_BYTES,
    MAX_SUPPORT_BYTES,
    META_FILE,
    SKILL_FILE,
    parse_skill_text,
    read_skill_package,
    safe_child,
)
from .models import SkillError

_WINDOWS_DRIVE_RE = re.compile(r"^[a-zA-Z]:")


@dataclass(frozen=True, slots=True)
class _ArchiveMember:
    """保存已经过路径与类型校验的 ZIP 成员。"""

    info: zipfile.ZipInfo
    parts: tuple[str, ...]
    is_dir: bool


def _normalize_member(info: zipfile.ZipInfo) -> _ArchiveMember:
    """规范化 ZIP 路径，并拒绝可能逃逸或覆盖其他文件的名称。"""

    raw = info.filename.replace("\\", "/")
    if not raw or "\x00" in raw or raw.startswith("/") or _WINDOWS_DRIVE_RE.match(raw):
        raise SkillError("archive contains an illegal path")
    normalized = raw.rstrip("/")
    parts = tuple(normalized.split("/"))
    if not normalized or any(part in {"", ".", ".."} for part in parts):
        raise SkillError("archive contains an illegal path")

    mode = (info.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(mode)
    is_dir = info.is_dir()
    if is_dir:
        if file_type not in {0, stat.S_IFDIR}:
            raise SkillError("archive contains an unsupported member type")
    elif file_type not in {0, stat.S_IFREG}:
        raise SkillError("archive contains a symlink or special file")
    if info.flag_bits & 0x1:
        raise SkillError("encrypted archive entries are not supported")
    return _ArchiveMember(info=info, parts=parts, is_dir=is_dir)


def _inspect_members(zf: zipfile.ZipFile) -> list[_ArchiveMember]:
    """检查成员数量、解压体积、重复路径和文件树冲突。"""

    infos = zf.infolist()
    if not infos:
        raise SkillError("archive is empty")
    if len(infos) > MAX_SKILL_ARCHIVE_ENTRIES:
        raise SkillError("archive contains too many entries")

    members: list[_ArchiveMember] = []
    seen: set[str] = set()
    file_keys: set[str] = set()
    expanded = 0
    for info in infos:
        member = _normalize_member(info)
        key = "/".join(member.parts).casefold()
        if key in seen:
            raise SkillError("archive contains duplicate paths")
        seen.add(key)
        if not member.is_dir:
            if info.file_size < 0 or info.file_size > MAX_SUPPORT_BYTES:
                raise SkillError("archive member is too large")
            expanded += info.file_size
            if expanded > MAX_SKILL_ARCHIVE_EXPANDED_BYTES:
                raise SkillError("archive expands beyond the allowed size")
            file_keys.add(key)
        members.append(member)

    for member in members:
        key_parts = [part.casefold() for part in member.parts]
        for index in range(1, len(key_parts)):
            if "/".join(key_parts[:index]) in file_keys:
                raise SkillError("archive contains a file and directory path conflict")
    return members


def _package_prefix(members: list[_ArchiveMember]) -> tuple[str, ...]:
    """定位平铺包或唯一的单层包装目录。"""

    files = [member for member in members if not member.is_dir]
    if any(member.parts == (SKILL_FILE,) for member in files):
        return ()
    candidates = {
        member.parts[0]
        for member in files
        if len(member.parts) == 2 and member.parts[1] == SKILL_FILE
    }
    if len(candidates) != 1:
        raise SkillError(
            "archive must contain SKILL.md at its root or in exactly one top-level directory"
        )
    prefix = (next(iter(candidates)),)
    if any(member.parts[:1] != prefix for member in members):
        raise SkillError("archive contains entries outside the Skill package")
    return prefix


def _relative_parts(member: _ArchiveMember, prefix: tuple[str, ...]) -> tuple[str, ...]:
    if prefix and member.parts == prefix:
        return ()
    return member.parts[len(prefix):]


def _validate_package_layout(
    members: list[_ArchiveMember], prefix: tuple[str, ...]
) -> None:
    """在写盘前校验包根目录结构和单文件体积。"""

    for member in members:
        relative = _relative_parts(member, prefix)
        if not relative:
            continue
        root_entry = relative[0]
        if root_entry not in ALLOWED_ROOT_ENTRIES:
            raise SkillError(f"unsupported package entry: {root_entry}")
        if root_entry in {SKILL_FILE, META_FILE} and len(relative) != 1:
            raise SkillError(f"invalid package path: {'/'.join(relative)}")
        if root_entry in ALLOWED_SUPPORT_DIRS and len(relative) == 1 and not member.is_dir:
            raise SkillError(f"{root_entry} must be a directory")
        if not member.is_dir:
            limit = MAX_SKILL_BYTES if relative == (SKILL_FILE,) else MAX_SUPPORT_BYTES
            if member.info.file_size > limit:
                raise SkillError(f"package file is too large: {'/'.join(relative)}")


def _write_member(
    zf: zipfile.ZipFile,
    member: _ArchiveMember,
    destination: Path,
    relative: tuple[str, ...],
) -> None:
    """按固定上限流式写入单个成员，避免信任 ZIP 中声明的体积。"""

    target = safe_child(destination, Path(*relative))
    if member.is_dir:
        target.mkdir(parents=True, exist_ok=True)
        return
    if relative == (META_FILE,):
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    limit = MAX_SKILL_BYTES if relative == (SKILL_FILE,) else MAX_SUPPORT_BYTES
    written = 0
    with zf.open(member.info, "r") as source, target.open("xb") as output:
        while chunk := source.read(64 * 1024):
            written += len(chunk)
            if written > limit:
                raise SkillError(f"package file is too large: {'/'.join(relative)}")
            output.write(chunk)


def extract_skill_zip(data: bytes, destination: Path) -> str:
    """安全解包一个 Skill ZIP，并返回 frontmatter 中的规范名称。"""

    if not isinstance(data, bytes) or len(data) < 4 or len(data) > MAX_SKILL_ZIP_BYTES:
        raise SkillError("invalid or oversized ZIP archive")
    buffer = io.BytesIO(data)
    if data[:2] != b"PK" or not zipfile.is_zipfile(buffer):
        raise SkillError("invalid ZIP archive")
    if destination.exists():
        raise SkillError("temporary extraction directory already exists")

    destination.mkdir(parents=True, exist_ok=False)
    try:
        with zipfile.ZipFile(buffer) as zf:
            members = _inspect_members(zf)
            prefix = _package_prefix(members)
            _validate_package_layout(members, prefix)
            for member in members:
                relative = _relative_parts(member, prefix)
                if relative:
                    _write_member(zf, member, destination, relative)
    except zipfile.BadZipFile as exc:
        raise SkillError("invalid ZIP archive") from exc
    except OSError as exc:
        raise SkillError(f"failed to extract Skill archive: {exc}") from exc

    skill_path = destination / SKILL_FILE
    try:
        content = skill_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SkillError("SKILL.md not found") from exc
    except UnicodeDecodeError as exc:
        raise SkillError("SKILL.md must be UTF-8") from exc
    manifest, _, _ = parse_skill_text(content)
    read_skill_package(destination, expected_name=manifest.name)
    return manifest.name
