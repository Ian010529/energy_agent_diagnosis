from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from energy_agent.persistence.mysql import Base


class DiagnosisSessionModel(Base):
    __tablename__ = "diagnosis_session"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    site_id: Mapped[str | None] = mapped_column(String(128))
    device_id: Mapped[str | None] = mapped_column(String(128))
    alarm_id: Mapped[str | None] = mapped_column(String(128))
    alarm_name: Mapped[str | None] = mapped_column(String(255))
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    final_summary: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class DiagnosisStepLogModel(Base):
    __tablename__ = "diagnosis_step_log"
    __table_args__ = (Index("ix_step_log_session_id", "session_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("diagnosis_session.id"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    step_name: Mapped[str] = mapped_column(String(128), nullable=False)
    step_status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
