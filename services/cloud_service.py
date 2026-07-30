import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Mapping


class CloudUploadError(RuntimeError):
    """Raised when configured Cloudinary storage rejects a backup."""


@dataclass(frozen=True)
class CloudOperationResult:
    operation: str
    status: str
    message: str
    reference: str = ""
    artifact_path: str = ""
    secure_url: str = ""
    readable_artifact_path: str = ""
    readable_url: str = ""


class CloudService:
    """Cloudinary backup adapter with an offline-safe local simulation.

    Every backup first uses SQLite's online backup API for a consistent snapshot.
    If CLOUDINARY_URL is configured, that snapshot is uploaded as a raw asset.
    Without credentials, it remains a clearly labelled local simulation.
    """

    def __init__(
        self,
        enabled: bool = False,
        provider: str = "cloudinary",
        simulation_directory: str | Path = "instance/cloud_backups",
        cloudinary_url: str = "",
    ):
        self.enabled = enabled
        self.provider = provider
        self.simulation_directory = Path(simulation_directory)
        self.cloudinary_url = cloudinary_url

    @classmethod
    def from_config(
        cls,
        config: Mapping[str, object],
        simulation_directory: str | Path = "instance/cloud_backups",
    ) -> "CloudService":
        return cls(
            enabled=bool(config.get("CLOUD_SERVICE_ENABLED", False)),
            provider=str(config.get("CLOUD_SERVICE_PROVIDER", "cloudinary")),
            simulation_directory=simulation_directory,
            cloudinary_url=str(config.get("CLOUDINARY_URL", "")),
        )

    def health_check(self) -> CloudOperationResult:
        configured = self.cloudinary_url.startswith("cloudinary://")
        invalid = bool(self.cloudinary_url) and not configured
        return CloudOperationResult(
            operation="health_check",
            status="configured" if configured else ("invalid" if invalid else "simulated"),
            message=(
                "Cloudinary raw-asset backup is configured."
                if configured
                else (
                    "CLOUDINARY_URL has an invalid format."
                    if invalid
                    else "Offline cloud backup simulation is ready."
                )
            ),
            reference=self.provider,
        )

    def emit_log(
        self, event: str, payload: Mapping[str, object]
    ) -> CloudOperationResult:
        if not event.strip():
            raise ValueError("Cloud log event is required.")
        self.simulation_directory.mkdir(parents=True, exist_ok=True)
        log_path = self.simulation_directory / "remote_events.jsonl"
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event.strip(),
            "payload": dict(payload),
            "provider": self.provider if self.enabled else "simulation",
        }
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(record, default=str) + "\n")
        return CloudOperationResult(
            operation="emit_log",
            status="simulated",
            message="Remote logging hook accepted the event.",
            reference=record["timestamp"],
            artifact_path=str(log_path),
        )

    def backup_database(self, database_path: str | Path) -> CloudOperationResult:
        path = Path(database_path)
        if not path.is_file():
            raise FileNotFoundError(f"Local database does not exist: {path}")
        snapshot, timestamp, digest = self._create_snapshot(path)
        readable_snapshot = self._create_readable_snapshot(snapshot, timestamp)
        if not self.cloudinary_url:
            return self._simulation_result(
                path, snapshot, readable_snapshot, timestamp, digest
            )
        return self._upload_to_cloudinary(
            path, snapshot, readable_snapshot, timestamp, digest
        )

    def _create_snapshot(self, source_path: Path) -> tuple[Path, str, str]:
        self.simulation_directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destination = self.simulation_directory / f"fitness_studio_{timestamp}.db"

        source = sqlite3.connect(source_path)
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()

        digest = hashlib.sha256(destination.read_bytes()).hexdigest()[:12]
        return destination, timestamp, digest

    def _create_readable_snapshot(
        self, database_snapshot: Path, timestamp: str
    ) -> Path:
        """Export selected normalized tables to a styled, sanitized HTML report."""

        table_names = (
            "users",
            "members",
            "membership_plans",
            "membership_subscriptions",
            "membership_purchases",
            "membership_renewals",
            "workout_sessions",
            "bookings",
        )
        connection = sqlite3.connect(database_snapshot)
        connection.row_factory = sqlite3.Row
        try:
            available_tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            table_data = []
            for table_name in table_names:
                if table_name not in available_tables:
                    continue
                rows = [
                    self._sanitize_row(table_name, dict(row))
                    for row in connection.execute(f'SELECT * FROM "{table_name}"')
                ]
                table_data.append((table_name, rows))
        finally:
            connection.close()

        report_path = (
            self.simulation_directory / f"database_snapshot_{timestamp}.html"
        )
        report_path.write_text(
            self._render_html_report(table_data, timestamp), encoding="utf-8"
        )
        return report_path

    @staticmethod
    def _sanitize_row(table_name: str, row: dict[str, object]) -> dict[str, object]:
        if table_name == "users" and "password_hash" in row:
            row["password_hash"] = "[REDACTED]"
        return row

    @staticmethod
    def _render_html_report(
        table_data: list[tuple[str, list[dict[str, object]]]], timestamp: str
    ) -> str:
        total_rows = sum(len(rows) for _, rows in table_data)
        sections = []
        for table_name, rows in table_data:
            columns = list(rows[0]) if rows else []
            headers = "".join(f"<th>{escape(column)}</th>" for column in columns)
            body = "".join(
                "<tr>"
                + "".join(
                    f"<td>{escape(str(row.get(column, '')))}</td>"
                    for column in columns
                )
                + "</tr>"
                for row in rows
            )
            if not rows:
                body = '<tr><td class="empty">No rows</td></tr>'
            sections.append(
                f'<section class="table-card"><div class="table-title">'
                f"<h2>{escape(table_name)}</h2><span>{len(rows)} rows</span></div>"
                f'<div class="table-scroll"><table><thead><tr>{headers}</tr></thead>'
                f"<tbody>{body}</tbody></table></div></section>"
            )

        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fitness Studio Database Snapshot</title>
<style>
:root{{--ink:#0f172a;--teal:#0f766e;--orange:#f97316;--line:#dbe4ee}}
*{{box-sizing:border-box}} body{{margin:0;background:#f1f5f9;color:var(--ink);
font:14px/1.5 Arial,sans-serif}} header{{padding:38px;color:white;
background:linear-gradient(120deg,#0f172a,#0f766e)}} main{{max-width:1400px;
margin:auto;padding:28px}} h1{{margin:0 0 8px;font-size:32px}} .summary{{display:flex;
gap:12px;flex-wrap:wrap;margin-top:20px}} .metric{{padding:12px 18px;border-radius:10px;
background:rgba(255,255,255,.12)}} .metric strong{{display:block;font-size:22px}}
.table-card{{margin-bottom:24px;border:1px solid var(--line);border-radius:14px;
background:white;box-shadow:0 8px 24px rgba(15,23,42,.06);overflow:hidden}}
.table-title{{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;
border-bottom:1px solid var(--line)}} .table-title h2{{margin:0;color:var(--teal);
font-size:19px}} .table-title span{{padding:4px 9px;border-radius:99px;background:#ffedd5;
color:#9a3412;font-weight:bold}} .table-scroll{{overflow:auto}} table{{width:100%;
border-collapse:collapse}} th,td{{padding:10px 12px;border-bottom:1px solid #e8eef4;
text-align:left;white-space:nowrap}} th{{background:#f8fafc;color:#475569;
font-size:11px;text-transform:uppercase;letter-spacing:.04em}} tr:hover td{{background:#f8fafc}}
.empty{{color:#64748b;text-align:center}} footer{{padding:0 28px 28px;color:#64748b;
text-align:center}} code{{font-family:Consolas,monospace}}
</style>
</head>
<body>
<header><h1>Fitness Studio Database Snapshot</h1>
<p>Readable cloud export of normalized application data</p>
<div class="summary"><div class="metric"><strong>{len(table_data)}</strong>tables</div>
<div class="metric"><strong>{total_rows}</strong>rows</div>
<div class="metric"><strong>{escape(timestamp)}</strong>backup reference</div></div></header>
<main>{''.join(sections)}</main>
<footer>Password hashes are intentionally redacted. Generated from a consistent SQLite backup.</footer>
</body></html>"""

    def _simulation_result(
        self,
        source_path: Path,
        destination: Path,
        readable_snapshot: Path,
        timestamp: str,
        digest: str,
    ) -> CloudOperationResult:
        reference = f"cloud-sim-{timestamp}-{digest}"
        self.emit_log(
            "database_backup",
            {
                "reference": reference,
                "source": source_path.name,
                "artifact": destination.name,
                "readable_snapshot": readable_snapshot.name,
                "sha256_prefix": digest,
            },
        )
        return CloudOperationResult(
            operation="backup_database",
            status="simulated",
            message="Database snapshot stored by the cloud backup adapter.",
            reference=reference,
            artifact_path=str(destination),
            readable_artifact_path=str(readable_snapshot),
        )

    def _upload_to_cloudinary(
        self,
        source_path: Path,
        snapshot: Path,
        readable_snapshot: Path,
        timestamp: str,
        digest: str,
    ) -> CloudOperationResult:
        if not self.cloudinary_url.startswith("cloudinary://"):
            raise CloudUploadError(
                "CLOUDINARY_URL must start with 'cloudinary://'."
            )
        database_public_id = f"fitness_studio_{timestamp}.db"
        report_public_id = f"database_snapshot_{timestamp}.html"
        try:
            database_response = self._cloudinary_upload(
                snapshot, database_public_id
            )
            report_response = self._cloudinary_upload(
                readable_snapshot, report_public_id
            )
        except Exception as exc:
            if isinstance(exc, CloudUploadError):
                raise
            raise CloudUploadError(f"Cloudinary upload failed: {exc}") from exc

        secure_url = str(database_response.get("secure_url", ""))
        readable_url = str(report_response.get("secure_url", ""))
        uploaded_public_id = str(
            database_response.get("public_id", database_public_id)
        )
        report_uploaded_public_id = str(
            report_response.get("public_id", report_public_id)
        )
        if not secure_url or not readable_url:
            raise CloudUploadError(
                "Cloudinary did not return both required secure URLs."
            )

        self.emit_log(
            "cloudinary_database_backup",
            {
                "public_id": uploaded_public_id,
                "secure_url": secure_url,
                "readable_public_id": report_uploaded_public_id,
                "readable_url": readable_url,
                "source": source_path.name,
                "sha256_prefix": digest,
            },
        )
        return CloudOperationResult(
            operation="backup_database",
            status="uploaded",
            message="Database and readable table snapshot uploaded to Cloudinary.",
            reference=uploaded_public_id,
            artifact_path=str(snapshot),
            secure_url=secure_url,
            readable_artifact_path=str(readable_snapshot),
            readable_url=readable_url,
        )

    def _cloudinary_upload(
        self, snapshot: Path, public_id: str
    ) -> Mapping[str, object]:
        """Lazy-load the SDK so invalid environment values cannot crash startup."""

        import cloudinary
        import cloudinary.uploader

        cloudinary.config(cloudinary_url=self.cloudinary_url, secure=True)
        return cloudinary.uploader.upload(
            str(snapshot),
            resource_type="raw",
            type="upload",
            folder="fitness_studio_backups",
            public_id=public_id,
            overwrite=False,
        )
