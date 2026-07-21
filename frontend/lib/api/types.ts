import type { components } from "./generated";

export type Capabilities = components["schemas"]["CapabilitiesResponse"];
export type SiteList = components["schemas"]["SiteListResponse"];
export type DeviceList = components["schemas"]["DeviceListResponse"];
export type AlarmList = components["schemas"]["AlarmListResponse"];
export type SessionList = components["schemas"]["DiagnosisSessionListResponse"];
export type DiagnosisResponse = components["schemas"]["DiagnosisResponse"];
export type TimelineResponse = components["schemas"]["TimelineResponse"];
export type EvidenceDetail = components["schemas"]["EvidenceDetail"];
export type TimeseriesResponse = components["schemas"]["SessionTimeseriesResponse"];
export type CaseListResponse = components["schemas"]["CaseListResponse"];
export type DiagnosisCase = components["schemas"]["DiagnosisCase"];
export type CaseHistory = components["schemas"]["CaseReviewEvent"][];
