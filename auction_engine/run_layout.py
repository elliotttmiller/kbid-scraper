from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")
CST = timezone(timedelta(hours=-6), name="CST")


def cst_now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def rfc2822_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(CST)
    return timestamp.strftime("%a, %d %b %Y %I:%M:%S %p %z")


def filesystem_rfc2822(value: datetime) -> str:
    return value.strftime("%a_%d_%b_%Y_%I-%M-%S_%z")


def cst_log_formatter(fmt: str) -> logging.Formatter:
    formatter = logging.Formatter(fmt)
    formatter.converter = lambda timestamp: datetime.fromtimestamp(timestamp, CST).timetuple()
    return formatter


def safe_name(value: str, fallback: str) -> str:
    cleaned = SAFE_NAME.sub("-", str(value or "").strip()).strip("-._").lower()
    return cleaned[:80] or fallback


def atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, path)


@dataclass(frozen=True)
class RunLayout:
    root: Path
    run_id: str
    run_name: str
    raw_dir: Path
    outputs_dir: Path
    reports_dir: Path
    state_dir: Path
    logs_dir: Path
    metadata_dir: Path
    shared_cache_dir: Path

    @classmethod
    def create(
        cls,
        results_root: str | Path = "results",
        run_name: str | None = None,
        run_dir: str | Path | None = None,
    ) -> "RunLayout":
        results = Path(results_root).resolve()
        label = safe_name(run_name or "auction-run", "auction-run")
        if run_dir:
            root = Path(run_dir).resolve()
            run_id = root.name
        else:
            now = datetime.now(CST)
            run_id = f"run_{filesystem_rfc2822(now)}_{uuid.uuid4().hex[:8]}"
            root = results / "runs" / f"{now:%Y}" / f"{now:%m}" / run_id
        layout = cls(
            root=root,
            run_id=run_id,
            run_name=label,
            raw_dir=root / "raw",
            outputs_dir=root / "outputs",
            reports_dir=root / "reports",
            state_dir=root / "state",
            logs_dir=root / "logs",
            metadata_dir=root / "metadata",
            shared_cache_dir=results / "shared" / "cache",
        )
        for directory in (
            layout.raw_dir,
            layout.outputs_dir,
            layout.reports_dir,
            layout.state_dir,
            layout.logs_dir,
            layout.metadata_dir,
            layout.shared_cache_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        atomic_json_write(
            results / "latest.json",
            {
                "run_id": run_id,
                "run_name": label,
                "run_dir": str(root),
                "timezone": "CST (UTC-06:00)",
                "run_timestamp_rfc2822": rfc2822_timestamp(now) if not run_dir else rfc2822_timestamp(),
                "updated_at": cst_now_iso(),
            },
        )
        return layout

    @property
    def manifest_path(self) -> Path:
        return self.metadata_dir / "manifest.json"

    @property
    def log_path(self) -> Path:
        return self.logs_dir / "run.log"

    @property
    def error_log_path(self) -> Path:
        return self.logs_dir / "errors.log"

    @property
    def checkpoint_path(self) -> Path:
        return self.state_dir / "scrape-checkpoint.json"

    @property
    def cache_path(self) -> Path:
        return self.shared_cache_dir / "auction-engine.sqlite3"

    def artifact(self, group: str, filename: str) -> Path:
        directories = {
            "raw": self.raw_dir,
            "outputs": self.outputs_dir,
            "reports": self.reports_dir,
            "state": self.state_dir,
            "logs": self.logs_dir,
        }
        if group not in directories:
            raise ValueError(f"unknown artifact group: {group}")
        return directories[group] / Path(filename).name

    def write_manifest(self, **updates: Any) -> dict[str, Any]:
        current: dict[str, Any] = {}
        if self.manifest_path.exists():
            with self.manifest_path.open("r", encoding="utf-8") as handle:
                current = json.load(handle)
        current.update(updates)
        current.setdefault("schema_version", 1)
        current.setdefault("run_id", self.run_id)
        current.setdefault("run_name", self.run_name)
        current.setdefault("run_dir", str(self.root))
        current.setdefault("timezone", "CST (UTC-06:00)")
        current.setdefault("run_timestamp_rfc2822", rfc2822_timestamp())
        current["updated_at"] = cst_now_iso()
        atomic_json_write(self.manifest_path, current)
        return current

    def relative_artifacts(self, artifacts: dict[str, str | Path]) -> dict[str, str]:
        mapped: dict[str, str] = {}
        for name, value in artifacts.items():
            path = Path(value).resolve()
            try:
                mapped[name] = str(path.relative_to(self.root))
            except ValueError:
                mapped[name] = str(path)
        return mapped
