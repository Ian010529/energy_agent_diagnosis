from energy_agent.agent.templates.contracts import DiagnosisTemplate
from energy_agent.agent.templates.definitions import TEMPLATES
from energy_agent.agent.templates.registry import TemplateRegistry

DEFAULT_TEMPLATE_REGISTRY = TemplateRegistry(TEMPLATES)


def route_template(
    *,
    device_type: str | None,
    alarm_name: str | None,
    alarm_category: str | None = None,
    user_text: str | None = None,
) -> tuple[DiagnosisTemplate, str]:
    return DEFAULT_TEMPLATE_REGISTRY.route(
        device_type=device_type,
        alarm_name=alarm_name,
        alarm_category=alarm_category,
        user_text=user_text,
    )
