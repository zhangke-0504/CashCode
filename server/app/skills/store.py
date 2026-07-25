from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .archive import extract_skill_zip
from .catalog import SkillCatalog
from .loader import META_FILE, SKILL_FILE, parse_skill_text, read_skill_package, safe_child, validate_name, validate_support_path
from .models import SkillConflictError, SkillError, SkillNotFoundError, SkillPermissionError, SkillPublicationError, SkillSource


class SkillStore:
    def __init__(self, catalog: SkillCatalog, snapshots_root: Path) -> None:
        self.catalog = catalog
        self.snapshots_root = snapshots_root.resolve()
        self.snapshots_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _root(self, source: SkillSource) -> Path:
        if source is SkillSource.BUILTIN:
            raise SkillPermissionError("built-in Skills are read-only")
        return self.catalog.roots[source]

    def physical_name_conflicts(self, name: str) -> tuple[SkillSource, ...]:
        normalized = validate_name(name)
        return tuple(
            source
            for source, root in self.catalog.roots.items()
            if safe_child(root, normalized).exists()
        )

    def _ensure_name_available(self, name: str) -> None:
        conflicts = self.physical_name_conflicts(name)
        if conflicts:
            sources = ", ".join(source.value for source in conflicts)
            raise SkillConflictError(f"Skill already exists in {sources}: {name}")

    def _write_meta(self, directory: Path, data: dict[str, Any]) -> None:
        target = directory / META_FILE
        temp = target.with_name(f".{META_FILE}.{uuid.uuid4().hex}.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, target)

    @staticmethod
    def _runtime_meta(
        source: SkillSource,
        *,
        enabled: bool,
        audit_reason: str | None = None,
    ) -> dict[str, Any]:
        """生成只由服务端控制的 Skill 运行时元数据。"""

        metadata = {
            "source": source.value,
            "enabled": enabled,
            "storage_version": 1,
            "updated_at": time.time(),
            "agentCreated": source is SkillSource.AGENT,
        }
        if audit_reason:
            metadata["creation_reason"] = audit_reason
        return metadata

    def _create_tree(
        self,
        directory: Path,
        *,
        name: str,
        content: str,
        source: SkillSource,
        support_files: dict[str, str] | None,
        enabled: bool,
        audit_reason: str | None = None,
    ) -> None:
        parse_skill_text(content, expected_name=name)
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "SKILL.md").write_text(content, encoding="utf-8")
        for relative, file_content in (support_files or {}).items():
            rel = validate_support_path(relative)
            target = safe_child(directory, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(file_content), encoding="utf-8")
        self._write_meta(
            directory,
            self._runtime_meta(
                source, enabled=enabled, audit_reason=audit_reason
            ),
        )
        read_skill_package(directory, expected_name=name)

    def import_zip(self, data: bytes) -> dict[str, Any]:
        """校验并原子安装一个用户上传的 Skill ZIP。"""

        root = self._root(SkillSource.USER)
        temp = safe_child(root, f".skill-import.{uuid.uuid4().hex}.tmp")
        target: Path | None = None
        published = False
        try:
            name = extract_skill_zip(data, temp)
            target = safe_child(root, name)
            with self._lock:
                self._ensure_name_available(name)
                self._write_meta(
                    temp,
                    self._runtime_meta(SkillSource.USER, enabled=True),
                )
                read_skill_package(temp, expected_name=name)
                os.replace(temp, target)
                published = True
                self.catalog.refresh()
                record = self.catalog.get(name)
                if record is None or record.source is not SkillSource.USER:
                    raise SkillError("imported Skill did not enter the catalog")
                return record.to_dict()
        except Exception:
            if published and target is not None:
                shutil.rmtree(target, ignore_errors=True)
                self.catalog.refresh()
            raise
        finally:
            shutil.rmtree(temp, ignore_errors=True)

    def read_content(self, name: str) -> dict[str, Any]:
        """读取用于编辑的完整 SKILL.md，并同步可能发生的外部变更。"""

        normalized = validate_name(name)
        record = self.catalog.get(normalized)
        if record is None:
            raise SkillError(f"Skill not found: {normalized}")
        manifest, _, digest, _ = read_skill_package(record.path, expected_name=normalized)
        if manifest.name != record.name or digest != record.content_hash:
            self.catalog.refresh()
            record = self.catalog.get(normalized)
            if record is None:
                raise SkillError(f"Skill not found: {normalized}")
            _, _, digest, _ = read_skill_package(record.path, expected_name=normalized)
        content = (record.path / SKILL_FILE).read_text(encoding="utf-8")
        return {
            "name": record.name,
            "display_name": record.display_name,
            "content": content,
            "hash": digest,
            "source": record.source.value,
            "mutable": record.source is not SkillSource.BUILTIN,
        }

    def create(
        self,
        name: str,
        content: str,
        *,
        source: SkillSource = SkillSource.USER,
        support_files: dict[str, str] | None = None,
        enabled: bool = True,
        audit_reason: str | None = None,
    ) -> dict[str, Any]:
        name = validate_name(name)
        _, _, expected_hash = parse_skill_text(content, expected_name=name)
        root = self._root(source)
        target = safe_child(root, name)
        temp = safe_child(root, f".{name}.{uuid.uuid4().hex}.tmp")
        published = False
        with self._lock:
            try:
                self._ensure_name_available(name)
                self._create_tree(
                    temp,
                    name=name,
                    content=content,
                    source=source,
                    support_files=support_files,
                    enabled=enabled,
                    audit_reason=audit_reason,
                )
                os.replace(temp, target)
                published = True
                self.catalog.refresh()
                record = self.catalog.get(name)
                if (
                    record is None
                    or record.source is not source
                    or record.content_hash != expected_hash
                ):
                    raise SkillPublicationError("created Skill did not enter the catalog")
                return record.to_dict(include_path=True)
            except Exception:
                if published:
                    shutil.rmtree(target, ignore_errors=True)
                    self.catalog.refresh()
                raise
            finally:
                shutil.rmtree(temp, ignore_errors=True)

    def _snapshot(self, source: SkillSource, name: str, target: Path) -> str:
        root = self.snapshots_root / source.value / name
        root.mkdir(parents=True, exist_ok=True)
        version = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
        shutil.copytree(target, root / version)
        return version

    def replace(
        self,
        name: str,
        content: str,
        *,
        support_files: dict[str, str] | None = None,
        expected_hash: str | None = None,
        evolution: bool = False,
    ) -> dict[str, Any]:
        record = self.catalog.get(validate_name(name))
        if record is None:
            raise SkillError(f"Skill not found: {name}")
        if record.source is SkillSource.BUILTIN:
            raise SkillPermissionError("built-in Skills are read-only")
        if evolution and record.source is not SkillSource.AGENT:
            raise SkillPermissionError("evolution can modify only agent Skills")
        if expected_hash and expected_hash != record.content_hash:
            raise SkillConflictError("Skill content changed since it was read")
        source = record.source
        root = self._root(source)
        target = safe_child(root, name)
        with self._lock:
            version = self._snapshot(source, name, target)
            temp = safe_child(root, f".{name}.{uuid.uuid4().hex}.tmp")
            backup = safe_child(root, f".{name}.{uuid.uuid4().hex}.bak")
            try:
                if support_files is None:
                    parse_skill_text(content, expected_name=name)
                    shutil.copytree(target, temp)
                    (temp / "SKILL.md").write_text(content, encoding="utf-8")
                    read_skill_package(temp, expected_name=name)
                else:
                    self._create_tree(
                        temp,
                        name=name,
                        content=content,
                        source=source,
                        support_files=support_files,
                        enabled=record.enabled,
                        audit_reason=None,
                    )
                os.replace(target, backup)
                os.replace(temp, target)
                shutil.rmtree(backup, ignore_errors=True)
            except Exception:
                shutil.rmtree(temp, ignore_errors=True)
                if backup.exists() and not target.exists():
                    os.replace(backup, target)
                raise
            self.catalog.refresh()
            updated = self.catalog.get(name)
            if updated is None:
                raise SkillError("updated Skill did not enter the catalog")
            result = updated.to_dict(include_path=True)
            result["snapshot"] = version
            return result

    def set_enabled(self, name: str, enabled: bool) -> dict[str, Any]:
        record = self.catalog.get(validate_name(name))
        if record is None:
            raise SkillError(f"Skill not found: {name}")
        if record.source is SkillSource.BUILTIN:
            raise SkillPermissionError("built-in Skills are read-only")
        with self._lock:
            meta_path = record.path / META_FILE
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            meta["enabled"] = bool(enabled)
            meta["updated_at"] = time.time()
            self._write_meta(record.path, meta)
            self.catalog.refresh()
            return self.catalog.get(name).to_dict(include_path=True)  # type: ignore[union-attr]

    def delete(self, name: str) -> None:
        record = self.catalog.get(validate_name(name))
        if record is None:
            raise SkillError(f"Skill not found: {name}")
        if record.source is SkillSource.BUILTIN:
            raise SkillPermissionError("built-in Skills are read-only")
        with self._lock:
            self._snapshot(record.source, name, record.path)
            shutil.rmtree(record.path)
            self.catalog.refresh()

    def delete_invalid(
        self, source: str | SkillSource, directory: str
    ) -> dict[str, str]:
        """将用户确认的无效包移入可恢复快照，并刷新共享目录。"""

        try:
            skill_source = source if isinstance(source, SkillSource) else SkillSource(source)
        except ValueError as exc:
            raise SkillError("invalid Skill source") from exc
        if skill_source is SkillSource.BUILTIN:
            raise SkillPermissionError("built-in Skills are read-only")
        selector = str(directory or "").strip()
        if (
            not selector
            or selector in {".", ".."}
            or "/" in selector
            or "\\" in selector
        ):
            raise SkillError("invalid Skill directory selector")

        with self._lock:
            target = self.catalog.invalid_target(skill_source, selector)
            if target is None:
                raise SkillNotFoundError("invalid Skill package not found")
            root = self._root(skill_source)
            if target.parent.resolve() != root or not target.exists():
                raise SkillNotFoundError("invalid Skill package not found")
            try:
                read_skill_package(target, expected_name=target.name)
            except (SkillError, OSError, UnicodeError):
                pass
            else:
                raise SkillConflictError(
                    "Skill package is valid and cannot be deleted as invalid"
                )

            package_id = hashlib.sha256(
                f"{skill_source.value}:{target.name}".encode("utf-8")
            ).hexdigest()[:16]
            version = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
            snapshot_root = (
                self.snapshots_root / "invalid" / skill_source.value / package_id
            )
            snapshot_root.mkdir(parents=True, exist_ok=True)
            snapshot = snapshot_root / version
            moved = False
            try:
                os.replace(target, snapshot)
                moved = True
                self.catalog.refresh()
            except Exception:
                if moved and snapshot.exists() and not target.exists():
                    os.replace(snapshot, target)
                    self.catalog.refresh()
                raise
            return {
                "source": skill_source.value,
                "directory": selector,
                "snapshot": f"invalid/{skill_source.value}/{package_id}/{version}",
            }

    def versions(self, name: str) -> list[str]:
        record = self.catalog.get(validate_name(name))
        if record is None or record.source is SkillSource.BUILTIN:
            return []
        root = self.snapshots_root / record.source.value / name
        return sorted((child.name for child in root.iterdir() if child.is_dir()), reverse=True) if root.exists() else []

    def rollback(self, name: str, version: str) -> dict[str, Any]:
        record = self.catalog.get(validate_name(name))
        if record is None:
            raise SkillError(f"Skill not found: {name}")
        if record.source is SkillSource.BUILTIN:
            raise SkillPermissionError("built-in Skills are read-only")
        snapshot = safe_child(self.snapshots_root / record.source.value / name, version)
        if not snapshot.is_dir():
            raise SkillError(f"snapshot not found: {version}")
        with self._lock:
            self._snapshot(record.source, name, record.path)
            temp = record.path.with_name(f".{name}.{uuid.uuid4().hex}.tmp")
            backup = record.path.with_name(f".{name}.{uuid.uuid4().hex}.bak")
            shutil.copytree(snapshot, temp)
            try:
                os.replace(record.path, backup)
                os.replace(temp, record.path)
                shutil.rmtree(backup, ignore_errors=True)
            except Exception:
                shutil.rmtree(temp, ignore_errors=True)
                if backup.exists() and not record.path.exists():
                    os.replace(backup, record.path)
                raise
            self.catalog.refresh()
            return self.catalog.get(name).to_dict(include_path=True)  # type: ignore[union-attr]
