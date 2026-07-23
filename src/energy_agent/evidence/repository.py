from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from energy_agent.core.time import ensure_utc
from energy_agent.evidence.ports import EvidenceSourceDetail
from energy_agent.persistence.models import (
    DiagnosisCaseModel,
    MaintenanceTicketModel,
    ManualChunkModel,
)


class MySQLEvidenceRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def manual(self, source_id: str) -> EvidenceSourceDetail | None:
        async with self.sessions() as db:
            row = (
                await db.execute(
                    select(ManualChunkModel).where(ManualChunkModel.chunk_id == source_id)
                )
            ).scalar_one_or_none()
        if not row:
            return None
        excerpt = row.summary_or_content[:1200]
        return EvidenceSourceDetail(
            title=row.chapter_title,
            payload_name="manual_location",
            content_excerpt=excerpt,
            payload={
                "doc_id": row.doc_id,
                "version": row.version,
                "chapter_title": row.chapter_title,
                "page_no": row.page_no,
                "section_type": row.section_type,
                "content_excerpt": excerpt,
                "effective": row.effective,
                "verified": row.verified,
            },
        )

    async def ticket(self, source_id: str) -> EvidenceSourceDetail | None:
        async with self.sessions() as db:
            row = await db.get(MaintenanceTicketModel, source_id)
        if not row:
            return None
        return EvidenceSourceDetail(
            title=f"工单 {row.ticket_id}",
            payload_name="ticket_detail",
            payload={
                "ticket_id": row.ticket_id,
                "device_id": row.device_id,
                "device_model": row.device_model,
                "alarm_name": row.alarm_name,
                "fault_symptom": row.fault_symptom,
                "root_cause": row.root_cause,
                "action_taken": row.action_taken,
                "is_verified": row.is_verified,
                "close_time": ensure_utc(row.close_time).isoformat() if row.close_time else None,
            },
        )

    async def case(self, source_id: str) -> EvidenceSourceDetail | None:
        async with self.sessions() as db:
            row = await db.get(DiagnosisCaseModel, source_id)
        if not row:
            return None
        return EvidenceSourceDetail(
            title=f"案例 {row.case_id}",
            payload_name="case_detail",
            payload={
                "case_id": row.case_id,
                "case_version": row.case_version,
                "root_cause": row.root_cause,
                "resolution_steps": row.resolution_steps,
                "review_status": row.review_status,
                "reviewer": row.reviewer,
                "evidence_refs": row.evidence_refs,
            },
        )
