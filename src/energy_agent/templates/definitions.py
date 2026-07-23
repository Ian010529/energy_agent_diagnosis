from energy_agent.templates.contracts import (
    CandidateRule,
    DiagnosisTemplate,
    TemplateGraphRelation,
)

SAFETY = ["涉及停机、断电或回路切换时，必须由授权人员人工确认并执行。"]


def _rules(rows: list[tuple[str, list[str], str]]) -> list[CandidateRule]:
    return [
        CandidateRule(cause=cause, evidence_terms=terms, missing_information=[missing])
        for cause, terms, missing in rows
    ]


TEMPLATES = [
    DiagnosisTemplate(
        template_id="pcs_temperature_abnormal_v1",
        template_version="1.1.0",
        device_type="PCS",
        device_aliases=["储能变流器", "储能柜"],
        alarm_category="temperature",
        alarm_patterns=["机柜温度异常", "温度持续升高", "温度高"],
        alarm_aliases=["pcs温度异常", "柜温告警"],
        measurements=["pcs_metrics", "fan_metrics", "environment_metrics"],
        metrics=[
            "cabinet_temperature",
            "ambient_temperature",
            "fan_speed",
            "fan_status",
            "output_power",
            "dc_current",
        ],
        plan_steps=["核验设备与告警", "分析温度和散热时序", "检索手册与案例", "现场确认"],
        candidate_rules=_rules(
            [
                ("散热风扇失效或转速异常", ["风扇", "fan_speed", "不转"], "确认风扇供电与机械状态"),
                ("滤网或风道堵塞", ["滤网", "风道", "堵塞"], "检查滤网压差与积尘"),
                ("环境温度或负荷过高", ["环境温度", "负荷", "output_power"], "核对环境温度与负荷"),
                ("温度传感器漂移", ["传感器", "漂移"], "使用独立测温仪交叉校验"),
            ]
        ),
        clarification_rules=["确认风扇是否运转", "补充独立测温值"],
        inspection_steps=["核对独立测温值", "检查风扇与供电", "检查滤网和风道", "核对环境与负荷"],
        safety_notes=SAFETY,
        graph_relations=[
            TemplateGraphRelation(
                fault_cause="散热风扇失效或转速异常",
                component="散热风扇",
                actions=["检查供电与转速"],
            ),
            TemplateGraphRelation(
                fault_cause="滤网或风道堵塞",
                component="风道与滤网",
                actions=["清洁滤网并检查风道"],
            ),
            TemplateGraphRelation(
                fault_cause="环境温度或负荷过高",
                component="设备通用部件",
                actions=["核对环境温度与设备负荷"],
            ),
            TemplateGraphRelation(
                fault_cause="温度传感器漂移",
                component="温度传感器",
                actions=["使用独立测温仪交叉校验"],
            ),
        ],
    ),
    DiagnosisTemplate(
        template_id="pcs_fan_abnormal_v1",
        template_version="1.1.0",
        device_type="PCS",
        device_aliases=["储能变流器", "储能柜"],
        alarm_category="fan",
        alarm_patterns=["风扇异常", "风扇故障", "风扇告警"],
        alarm_aliases=["fan abnormal", "风机异常"],
        measurements=["fan_metrics", "pcs_metrics"],
        metrics=["fan_speed", "fan_status", "fan_current", "cabinet_temperature", "control_signal"],
        plan_steps=["核验风扇告警", "对比指令与反馈", "检索历史案例", "现场检查"],
        candidate_rules=_rules(
            [
                ("风扇供电异常", ["fan_current", "供电", "电流"], "测量风扇供电"),
                ("风扇机械卡滞", ["卡滞", "异响", "不转"], "断电后检查叶轮"),
                ("控制信号异常", ["control_signal", "控制信号"], "核对控制指令"),
                (
                    "状态反馈或转速传感器异常",
                    ["反馈", "fan_speed", "转速传感器"],
                    "交叉校验实际转速",
                ),
            ]
        ),
        clarification_rules=["风扇是否实际转动", "是否存在异响"],
        inspection_steps=["检查风扇供电", "检查机械卡滞", "核对控制信号", "交叉校验转速反馈"],
        safety_notes=SAFETY,
        graph_relations=[
            TemplateGraphRelation(
                fault_cause="风扇机械卡滞", component="散热风扇", actions=["检查叶轮和轴承"]
            ),
            TemplateGraphRelation(
                fault_cause="风扇供电异常", component="散热风扇", actions=["测量风扇供电"]
            ),
            TemplateGraphRelation(
                fault_cause="控制信号异常", component="散热风扇", actions=["核对控制指令"]
            ),
            TemplateGraphRelation(
                fault_cause="状态反馈或转速传感器异常",
                component="散热风扇",
                actions=["交叉校验实际转速"],
            ),
        ],
    ),
    DiagnosisTemplate(
        template_id="pcs_temperature_sensor_abnormal_v1",
        template_version="1.0.0",
        device_type="PCS",
        device_aliases=["储能变流器", "储能柜"],
        alarm_category="sensor",
        alarm_patterns=["温度传感器异常", "温度传感器故障", "测温异常"],
        alarm_aliases=["sensor abnormal", "温度探头异常"],
        measurements=["pcs_metrics", "environment_metrics"],
        metrics=[
            "cabinet_temperature",
            "redundant_temperature",
            "ambient_temperature",
            "sensor_quality",
            "sensor_status",
        ],
        plan_steps=["核验传感器告警", "比较冗余测点", "检查数据质量", "现场交叉测温"],
        candidate_rules=_rules(
            [
                ("温度传感器漂移", ["漂移", "redundant_temperature"], "使用独立测温仪校验"),
                ("线路或接触异常", ["线路", "接触", "sensor_status"], "检查端子与线束"),
                ("数据质量或通讯异常", ["sensor_quality", "质量", "通讯"], "核对采集质量码"),
                ("真实温升而非传感器故障", ["真实温升", "ambient_temperature"], "核对多个测点趋势"),
            ]
        ),
        clarification_rules=["补充独立测温值", "确认端子和线束状态"],
        inspection_steps=["比较冗余测点", "检查质量码", "检查端子线束", "独立测温"],
        safety_notes=SAFETY,
        graph_relations=[
            TemplateGraphRelation(
                fault_cause="线路或接触异常", component="温度传感器", actions=["检查端子与线束"]
            )
        ],
    ),
    DiagnosisTemplate(
        template_id="pv_inverter_communication_abnormal_v1",
        template_version="1.0.0",
        device_type="PV_INVERTER",
        device_aliases=["光伏逆变器", "逆变器"],
        alarm_category="communication",
        alarm_patterns=["通讯异常", "通信异常", "离线"],
        alarm_aliases=["communication abnormal", "通讯中断"],
        measurements=["inverter_metrics"],
        metrics=[
            "communication_status",
            "heartbeat_age",
            "packet_loss",
            "auxiliary_power",
            "dc_voltage",
        ],
        plan_steps=["核验通讯告警", "分析心跳与丢包", "核查供电", "检查网关和参数"],
        candidate_rules=_rules(
            [
                ("网络链路中断", ["packet_loss", "链路", "心跳"], "检查交换机与链路"),
                ("通讯参数或协议配置异常", ["协议", "参数", "配置"], "核对地址、波特率与协议"),
                ("辅助供电异常", ["auxiliary_power", "辅助供电"], "测量辅助电源"),
                ("网关、采集器或 EMS 异常", ["网关", "采集器", "ems"], "检查上游采集链路"),
            ]
        ),
        clarification_rules=["确认本地面板是否在线", "同网段设备是否同时离线"],
        inspection_steps=["检查链路和交换机", "核对通讯参数", "检查辅助电源", "检查网关与采集器"],
        safety_notes=SAFETY,
        graph_relations=[
            TemplateGraphRelation(
                fault_cause="网络链路中断", component="通讯链路", actions=["检查交换机、网线和光纤"]
            )
        ],
    ),
    DiagnosisTemplate(
        template_id="pv_inverter_power_abnormal_v1",
        template_version="1.0.0",
        device_type="PV_INVERTER",
        device_aliases=["光伏逆变器", "逆变器"],
        alarm_category="power",
        alarm_patterns=["功率异常", "功率偏低", "无功率"],
        alarm_aliases=["power abnormal", "出力异常"],
        measurements=["inverter_metrics", "environment_metrics"],
        metrics=[
            "active_power",
            "dc_voltage",
            "dc_current",
            "ac_voltage",
            "ac_current",
            "irradiance",
            "grid_frequency",
            "cabinet_temperature",
        ],
        plan_steps=["核验功率告警", "比较辐照与直流输入", "检查电网侧", "核查降额与测量"],
        candidate_rules=_rules(
            [
                (
                    "辐照度或直流输入不足",
                    ["irradiance", "dc_voltage", "直流输入"],
                    "核对辐照和直流输入",
                ),
                ("直流侧组串异常", ["组串", "dc_current"], "检查组串电流一致性"),
                (
                    "电网侧限发或电压频率异常",
                    ["限发", "ac_voltage", "grid_frequency"],
                    "核对调度与电网参数",
                ),
                ("热降额", ["cabinet_temperature", "热降额", "温度"], "核对温度与降额状态"),
                ("功率测量异常", ["测量", "active_power"], "交叉校验电表"),
            ]
        ),
        clarification_rules=["确认是否存在调度限发", "补充同阵列逆变器出力"],
        inspection_steps=["核对辐照与直流输入", "检查组串", "核对电网与限发", "检查温度和电表"],
        safety_notes=SAFETY,
        graph_relations=[
            TemplateGraphRelation(
                fault_cause="直流侧组串异常", component="光伏组串", actions=["检查组串电流与连接"]
            )
        ],
    ),
]
