from energy_agent.agent.templates.contracts import DiagnosisTemplate


class TemplateNotFoundError(LookupError):
    pass


class TemplateAmbiguousError(LookupError):
    pass


class TemplateRegistry:
    def __init__(self, templates: list[DiagnosisTemplate]) -> None:
        self._templates = {item.template_id: item for item in templates}
        if len(self._templates) != len(templates):
            raise ValueError("template_id must be unique")

    @property
    def templates(self) -> tuple[DiagnosisTemplate, ...]:
        return tuple(self._templates.values())

    def get(self, template_id: str) -> DiagnosisTemplate:
        try:
            return self._templates[template_id]
        except KeyError as exc:
            raise TemplateNotFoundError(template_id) from exc

    def route(
        self,
        *,
        device_type: str | None,
        alarm_name: str | None,
        alarm_category: str | None = None,
        user_text: str | None = None,
    ) -> tuple[DiagnosisTemplate, str]:
        device = (device_type or "").strip().lower()
        alarm = (alarm_name or "").strip().lower()
        category = (alarm_category or "").strip().lower()
        text = (user_text or "").strip().lower()
        candidates: list[tuple[int, DiagnosisTemplate, str]] = []
        for template in self._templates.values():
            aliases = {
                template.device_type.lower(),
                *(item.lower() for item in template.device_aliases),
            }
            if device and device not in aliases:
                continue
            score = 4 if device else 0
            basis = ["device_type"] if device else []
            alarm_terms = [
                *(item.lower() for item in template.alarm_patterns),
                *(item.lower() for item in template.alarm_aliases),
            ]
            if alarm and any(term in alarm for term in alarm_terms):
                score += 3
                basis.append("alarm_name")
            if category and category == template.alarm_category.lower():
                score += 2
                basis.append("alarm_category")
            if text and any(term in text for term in alarm_terms):
                score += 1
                basis.append("controlled_term")
            if score and (
                not alarm and not category and not text or len(basis) > int(bool(device))
            ):
                candidates.append((score, template, "+".join(basis)))
        if not candidates:
            raise TemplateNotFoundError("TEMPLATE_UNSUPPORTED_DEVICE_OR_ALARM")
        best_score = max(item[0] for item in candidates)
        best = [item for item in candidates if item[0] == best_score]
        if len(best) != 1:
            raise TemplateAmbiguousError("TEMPLATE_AMBIGUOUS")
        return best[0][1], best[0][2]
