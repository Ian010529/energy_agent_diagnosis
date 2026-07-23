from typing import Annotated, cast

from fastapi import Depends, Request

from energy_agent.agent.service import DiagnosisService
from energy_agent.bootstrap.container import ApplicationContainer
from energy_agent.cases.service import CaseService
from energy_agent.catalog.service import CatalogService
from energy_agent.evidence.service import EvidenceService
from energy_agent.timeline.service import TimelineService


def get_container(request: Request) -> ApplicationContainer:
    return cast(ApplicationContainer, request.app.state.container)


def get_diagnosis_service(request: Request) -> DiagnosisService:
    return get_container(request).services.diagnosis


def get_case_service(request: Request) -> CaseService:
    return get_container(request).services.cases


def get_catalog_service(request: Request) -> CatalogService:
    return get_container(request).services.catalog


def get_timeline_service(request: Request) -> TimelineService:
    return get_container(request).services.timeline


def get_evidence_service(request: Request) -> EvidenceService:
    return get_container(request).services.evidence


DiagnosisServiceDependency = Annotated[DiagnosisService, Depends(get_diagnosis_service)]
CaseServiceDependency = Annotated[CaseService, Depends(get_case_service)]
CatalogServiceDependency = Annotated[CatalogService, Depends(get_catalog_service)]
TimelineServiceDependency = Annotated[TimelineService, Depends(get_timeline_service)]
EvidenceServiceDependency = Annotated[EvidenceService, Depends(get_evidence_service)]
