from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .catalog import SkillCatalog
from .loader import META_FILE, parse_skill_text, read_skill_package, safe_child, validate_name, validate_support_path
from .models import SkillConflictError, SkillError, SkillPermissionError, SkillSource


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

    def _write_meta(self, directory: Path, data: dict[str, Any]) -> None:
        target = directory / META_FILE
        temp = target.with_name(f".{META_FILE}.{uuid.uuid4().hex}.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, target)

    def _create_tree(
        self,
        directory: Path,
        *,
        name: str,
        content: str,
        source: SkillSource,
        support_files: dict[str, str] | None,
        enabled: bool,
    ) -> None:
        parse_skill_text(content, expected_name=name)
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "SKILL.md").write_text(content, encoding="utf-8")
        for relative, file_content in (support_files or {}).items():
            rel = validate_support_path(relative)
            target = safe_child(directory, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(file_content), encoding="utf-8")
        self._write_meta(directory, {
            "source": source.value,
            "enabled": enabled,
            "storage_version": 1,
            "updated_at": time.time(),
            "agentCreated": source is SkillSource.AGENT,
        })
        read_skill_package(directory, expected_name=name)

    def create(
        self,
        name: str,
        content: str,
        *,
        source: SkillSource = SkillSource.USER,
        support_files: dict[str, str] | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        name = validate_name(name)
        root = self._root(source)
        target = safe_child(root, name)
        with self._lock:
            if target.exists():
                raise SkillConflictError(f"Skill already exists: {name}")
            temp = safe_child(root, f".{name}.{uuid.uuid4().hex}.tmp")
            try:
                self._create_tree(temp, name=name, content=content, source=source, support_files=support_files, enabled=enabled)
                os.replace(temp, target)
            except Exception:
                shutil.rmtree(temp, ignore_errors=True)
                raise
            self.catalog.refresh()
            record = self.catalog.get(name)
            if record is None:
                raise SkillError("created Skill did not enter the catalog")
            return record.to_dict(include_path=True)

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
