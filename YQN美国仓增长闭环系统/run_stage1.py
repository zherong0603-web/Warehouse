#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 1 本地离线闭环 MVP。

读取 00_输入收件箱 中的 txt/md/csv，生成事实提取、MQL 复盘、
组织缺口、内容实验和双日报。只使用 Python 标准库。
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
SUPPORTED_EXTS = {".txt", ".md", ".csv"}
CONSTITUTION_PATH = ROOT / "07_项目宪法" / "项目宪法.md"
LOG_DIR = ROOT / "logs"
RUN_HISTORY_DIR = ROOT / "08_验收包" / "阶段1运行记录"

FACT_FIELDS = [
    "信息ID",
    "来源文件",
    "来源类型",
    "来源内容摘要",
    "证据片段",
    "客户/线索ID",
    "素材/渠道ID",
    "平台",
    "市场",
    "品类",
    "货量/单量",
    "当前履约方式",
    "当前供应商",
    "核心痛点",
    "对应YQN能力",
    "待确认字段",
    "是否可转内容选题",
]


@dataclass
class Record:
    info_id: str
    source_file: str
    source_type: str
    text: str
    summary: str
    evidence: str
    lead_id: str
    channel_id: str
    platform: str
    market: str
    category: str
    volume: str
    fulfillment: str
    supplier: str
    pain: str
    yqn_ability: str
    missing_fields: str
    can_be_content: str


@dataclass
class LeadReview:
    lead_id: str
    status: str
    reason: str
    evidence: list[str]
    customer_profile: str
    yqn_ability: str
    missing_fields: list[str]
    next_owner: str
    next_questions: list[str]
    next_action: str
    low_quality_reason: str = ""
    no_resource_reason: str = ""
    missing_evidence: str = ""
    records: list[Record] = field(default_factory=list)


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def today_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def log_error(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"stage1_{today_stamp()}.log"
    with path.open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {message}\n")


def read_text_file(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, "无法用 utf-8/gb18030 读取")


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[ \t]+", " ", text).strip()


def first_match(patterns: Iterable[str], text: str, default: str = "待确认") -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            value = match.group(1).strip()
            return re.sub(r"[，。；;、\s]+$", "", value) or default
    return default


def contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(keyword.lower() in text.lower() for keyword in keywords)


def split_sentences(text: str) -> list[str]:
    chunks = re.split(r"[。！？!?\n]+", clean_text(text))
    return [chunk.strip(" -:：") for chunk in chunks if chunk.strip(" -:：")]


def content_only_text(text: str) -> str:
    skip_prefixes = (
        "信息ID",
        "来源类型",
        "线索ID",
        "客户/线索ID",
        "素材/渠道ID",
        "渠道ID",
    )
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(stripped.startswith(prefix + ":") or stripped.startswith(prefix + "：") for prefix in skip_prefixes):
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("内容:") or stripped.startswith("内容："):
            stripped = stripped.split(":", 1)[-1].strip() if ":" in stripped else stripped.split("：", 1)[-1].strip()
        lines.append(stripped)
    return "\n".join(lines) if lines else text


def clip(text: str, limit: int = 120) -> str:
    text = clean_text(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def known(value: str) -> bool:
    return bool(value) and value != "待确认" and "待确认" not in value


def detect_source_type(text: str, file_name: str) -> str:
    explicit = first_match([r"来源类型[:：]\s*([^\n]+)"], text)
    if explicit != "待确认":
        return explicit
    name = file_name.lower()
    checks = [
        ("销售反馈", ["销售", "电话", "跟进"]),
        ("私域 MQL 下发记录", ["私域", "mql", "下发"]),
        ("小红书素材记录", ["小红书", "素材", "投放"]),
        ("仓库/运营能力边界", ["仓库", "运营", "能力"]),
        ("报价/费用客户问题", ["报价", "费用", "价格", "收费"]),
        ("客户原话", ["客户原话", "选题", "痛点"]),
    ]
    for source_type, words in checks:
        if any(word.lower() in name for word in words) or contains_any(text, words):
            return source_type
    return "输入资料"


def detect_info_id(text: str, fallback: str) -> str:
    return first_match(
        [
            r"信息ID[:：]\s*([A-Za-z0-9_\-]+)",
            r"\b((?:IN|S1|INFO)-[A-Za-z0-9_\-]+)\b",
        ],
        text,
        fallback,
    )


def detect_lead_id(text: str) -> str:
    return first_match(
        [
            r"线索ID[:：]\s*([A-Za-z0-9_\-]+)",
            r"客户/线索ID[:：]\s*([A-Za-z0-9_\-]+)",
            r"\b(MQL-[A-Za-z0-9_\-]+)\b",
        ],
        text,
    )


def detect_channel_id(text: str) -> str:
    return first_match(
        [
            r"素材/渠道ID[:：]\s*([A-Za-z0-9_\-]+)",
            r"渠道ID[:：]\s*([A-Za-z0-9_\-]+)",
            r"\b(XHS-[A-Za-z0-9_\-]+)\b",
        ],
        text,
    )


def detect_platform(text: str) -> str:
    platforms = []
    terms = ["TikTok Shop", "Shopify", "Amazon", "Walmart", "eBay", "Temu", "Wayfair"]
    for term in terms:
        if term.lower() in text.lower():
            platforms.append(term)
    if "亚马逊" in text and "Amazon" not in platforms:
        platforms.append("Amazon")
    return " + ".join(platforms) if platforms else "待确认"


def detect_market(text: str) -> str:
    if contains_any(text, ["美国", "北美", "美西", "美东", "LA", "洛杉矶", "新泽西", "海外仓"]):
        return "美国 / 北美"
    if "墨西哥" in text:
        return "墨西哥（非阶段1重点，不展开）"
    return "待确认"


def detect_category(text: str) -> str:
    explicit = first_match([r"品类[:：]\s*([^\n]+)"], text)
    if explicit != "待确认":
        return explicit
    category_terms = [
        ("手机壳/数据线", ["手机壳", "数据线", "3C", "带电"]),
        ("家居收纳", ["家居", "收纳"]),
        ("服饰", ["服饰", "衣服", "鞋"]),
        ("美妆", ["美妆", "护肤"]),
        ("宠物用品", ["宠物"]),
        ("小件标品", ["小件", "标品"]),
    ]
    for label, words in category_terms:
        if contains_any(text, words):
            return label
    return "待确认"


def detect_volume(text: str) -> str:
    explicit = first_match([r"(?:货量/单量|货量|单量|订单量)[:：]\s*([^\n]+)"], text)
    if explicit != "待确认":
        return explicit
    patterns = [
        r"((?:日均|每天|每日)\s*(?:约|大约)?\s*\d+\s*(?:[-~到至]\s*\d+)?\s*单)",
        r"((?:月均|每月|月)\s*(?:约|大约)?\s*\d+\s*(?:[-~到至]\s*\d+)?\s*单)",
        r"((?:旺季)\s*(?:预计|约|大约)?\s*\d+\s*(?:[-~到至]\s*\d+)?\s*单)",
        r"((?:每月|月)\s*(?:约|大约)?\s*\d+\s*(?:[-~到至]\s*\d+)?\s*(?:个)?托盘)",
        r"((?:每周|周)\D{0,6}\d+\s*(?:[-~到至]\s*\d+)?\s*件)",
        r"((?:SKU|sku)\s*\d+\s*(?:[-~到至]\s*\d+)?)",
    ]
    matches = [m.group(1).strip() for pattern in patterns for m in re.finditer(pattern, text, re.I)]
    return "；".join(dict.fromkeys(matches[:3])) if matches else "待确认"


def detect_fulfillment(text: str) -> str:
    explicit = first_match([r"当前履约方式[:：]\s*([^\n]+)"], text)
    if explicit != "待确认":
        return explicit
    if contains_any(text, ["LA 小仓", "洛杉矶小仓", "洛杉矶一个小仓"]):
        return "LA/洛杉矶小仓"
    if contains_any(text, ["国内直发", "深圳发货"]):
        return "国内直发 / 深圳发货"
    if contains_any(text, ["FBA"]):
        return "FBA 相关"
    return "待确认"


def detect_supplier(text: str) -> str:
    explicit = first_match([r"当前供应商[:：]\s*([^\n]+)"], text)
    if explicit != "待确认":
        return explicit
    if contains_any(text, ["现有服务商", "以前服务商", "外包尾程", "第三方仓"]):
        return "现有服务商/外包服务商"
    return "待确认"


def detect_pain(text: str) -> str:
    rules = [
        ("库存可视化不足", ["库存看不清", "库存不准", "可售库存", "库存可视化", "库存就乱"]),
        ("尾程费用/账单不清", ["尾程账单", "尾程费用", "派送费", "尾程"]),
        ("退货换标/质检效率", ["退货", "换标", "质检", "二次上架"]),
        ("FBA Prep/贴标送仓", ["FBA Prep", "贴标", "送 Amazon", "送仓"]),
        ("报价/费用拆分不清", ["报价", "收费", "费用", "最低价", "怎么收"]),
        ("旺季扩容/爆仓风险", ["旺季", "爆仓", "扩容"]),
        ("头程/清关不确定", ["头程", "清关", "单清", "双清"]),
        ("入门咨询", ["还没开始", "没店", "开店教程", "全套教程", "教我开店"]),
    ]
    pains = [label for label, words in rules if contains_any(text, words)]
    return "；".join(dict.fromkeys(pains)) if pains else "待确认"


def detect_yqn_ability(text: str, pain: str, market: str) -> str:
    ability = []
    if market.startswith("美国"):
        ability.append("美国仓")
    if contains_any(text + pain, ["一件代发", "FBM", "TikTok Shop", "Shopify"]):
        ability.extend(["3PL 仓配", "FBM", "一件代发"])
    if contains_any(text + pain, ["FBA Prep", "FBA", "贴标", "送仓"]):
        ability.extend(["FBA Prep", "平台仓转运"])
    if contains_any(text + pain, ["退货", "换标", "质检"]):
        ability.extend(["退货换标", "基础质检"])
    if contains_any(text + pain, ["尾程", "派送"]):
        ability.extend(["尾程派送", "TMS / BI"])
    if contains_any(text + pain, ["库存"]):
        ability.extend(["库存可视化", "WMS / BI"])
    if contains_any(text + pain, ["头程", "清关", "托盘"]):
        ability.extend(["头程", "清关"])
    if contains_any(text + pain, ["报价", "费用", "收费"]):
        ability.extend(["仓储/出库/尾程/退货成本拆分"])
    return "；".join(dict.fromkeys(ability)) if ability else "待确认"


def detect_evidence(text: str) -> str:
    text = content_only_text(text)
    priority_words = [
        "美国仓",
        "日均",
        "每天",
        "每月",
        "每周",
        "旺季",
        "库存",
        "尾程",
        "退货",
        "FBA",
        "报价",
        "收费",
        "还没开始",
        "开店",
    ]
    sentences = split_sentences(text)
    for sentence in sentences:
        if contains_any(sentence, priority_words):
            return clip(sentence, 160)
    return clip(sentences[0], 160) if sentences else "待确认"


def detect_summary(text: str) -> str:
    sentences = split_sentences(content_only_text(text))
    return clip(sentences[0], 120) if sentences else "待确认"


def detect_missing(record: dict[str, str]) -> str:
    checks = [
        ("平台", record["platform"]),
        ("市场", record["market"]),
        ("品类", record["category"]),
        ("货量/单量", record["volume"]),
        ("当前履约方式", record["fulfillment"]),
        ("当前供应商", record["supplier"]),
        ("核心痛点", record["pain"]),
    ]
    missing = [label for label, value in checks if value == "待确认"]
    return "；".join(missing) if missing else "无"


def detect_can_be_content(text: str, pain: str, source_type: str) -> str:
    if pain != "待确认":
        return "是"
    if contains_any(source_type + text, ["小红书", "素材", "客户原话", "选题", "评论"]):
        return "是"
    return "否"


def parse_csv_rows(path: Path) -> list[tuple[str, str]]:
    rows = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return [(path.name, read_text_file(path))]
            for idx, row in enumerate(reader, start=1):
                lines = [f"{key}: {value}" for key, value in row.items() if key and value]
                rows.append((f"{path.stem}-row{idx}", "\n".join(lines)))
    except Exception as exc:  # noqa: BLE001 - 需要把读取失败写入 logs
        log_error(f"读取 CSV 失败：{path} - {exc}")
    return rows


def is_sample_path(path: Path, input_dir: Path) -> bool:
    try:
        parts = path.relative_to(input_dir).parts
    except ValueError:
        parts = path.parts
    return any("样例" in part for part in parts)


def load_inputs(input_dir: Path, include_samples: bool) -> list[tuple[Path, str, str]]:
    files = []
    for path in sorted(p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS):
        if not include_samples and is_sample_path(path, input_dir):
            continue
        files.append(path)
    loaded = []
    for path in files:
        try:
            if path.suffix.lower() == ".csv":
                for row_name, row_text in parse_csv_rows(path):
                    loaded.append((path, row_name, row_text))
            else:
                loaded.append((path, path.stem, read_text_file(path)))
        except Exception as exc:  # noqa: BLE001
            log_error(f"读取输入失败：{path} - {exc}")
    return loaded


def build_record(path: Path, fallback_id: str, text: str) -> Record:
    text = clean_text(text)
    source_file = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name
    source_type = detect_source_type(text, path.name)
    info_id = detect_info_id(text, fallback_id)
    evidence = detect_evidence(text)
    platform = detect_platform(text)
    market = detect_market(text)
    category = detect_category(text)
    volume = detect_volume(text)
    fulfillment = detect_fulfillment(text)
    supplier = detect_supplier(text)
    pain = detect_pain(text)
    record_probe = {
        "platform": platform,
        "market": market,
        "category": category,
        "volume": volume,
        "fulfillment": fulfillment,
        "supplier": supplier,
        "pain": pain,
    }
    return Record(
        info_id=info_id,
        source_file=source_file,
        source_type=source_type,
        text=text,
        summary=detect_summary(text),
        evidence=evidence,
        lead_id=detect_lead_id(text),
        channel_id=detect_channel_id(text),
        platform=platform,
        market=market,
        category=category,
        volume=volume,
        fulfillment=fulfillment,
        supplier=supplier,
        pain=pain,
        yqn_ability=detect_yqn_ability(text, pain, market),
        missing_fields=detect_missing(record_probe),
        can_be_content=detect_can_be_content(text, pain, source_type),
    )


def key_count_for(records: list[Record]) -> int:
    platform = any(known(r.platform) for r in records)
    category = any(known(r.category) for r in records)
    volume = any(known(r.volume) for r in records)
    fulfillment_or_supplier = any(known(r.fulfillment) or known(r.supplier) for r in records)
    pain = any(known(r.pain) for r in records)
    return sum([platform, category, volume, fulfillment_or_supplier, pain])


def collect_unique(values: Iterable[str]) -> list[str]:
    result = []
    for value in values:
        for part in str(value).split("；"):
            part = part.strip()
            if part and part != "待确认" and part not in result:
                result.append(part)
    return result


def classify_lead(lead_id: str, records: list[Record]) -> LeadReview:
    text = "\n".join(r.text for r in records)
    us_signal = any(r.market.startswith("美国") for r in records) or contains_any(text, ["美国仓", "北美", "美西", "美东"])
    low_quality = contains_any(text, ["还没开始", "没有店铺", "没店", "开店教程", "全套教程", "教我开店"])
    only_low_price = contains_any(text, ["只看最低价", "最低价"]) and key_count_for(records) < 3
    key_count = key_count_for(records)
    has_pain = any(r.pain != "待确认" and "入门咨询" not in r.pain for r in records)
    has_structured_signal = any(known(r.platform) or known(r.category) or known(r.volume) or known(r.fulfillment) or known(r.supplier) for r in records)

    evidence = collect_unique(r.evidence for r in records)[:3] or ["待确认"]
    missing = []
    for r in records:
        if r.missing_fields != "无":
            missing.extend(r.missing_fields.split("；"))
    missing_fields = list(dict.fromkeys(missing)) or ["无"]
    yqn_ability = "；".join(collect_unique(r.yqn_ability for r in records)) or "待确认"
    profile = "；".join(
        collect_unique(
            [
                *[r.platform for r in records],
                *[r.category for r in records],
                *[r.volume for r in records],
                *[r.fulfillment for r in records],
            ]
        )
    ) or "待确认"

    if low_quality or only_low_price:
        return LeadReview(
            lead_id=lead_id,
            status="红灯",
            reason="证据显示线索偏泛咨询或缺少真实美国业务采购信号。",
            evidence=evidence,
            customer_profile=profile,
            yqn_ability=yqn_ability,
            missing_fields=missing_fields,
            next_owner="私域/客服",
            next_questions=["确认是否已有店铺、货盘和 30 天内美国仓发货计划；没有则用低成本资料承接。"],
            next_action="不建议进入销售深度跟进，可用标准资料低成本回复。",
            low_quality_reason="客户缺少平台、货量、履约需求或明确业务推进信号。",
            no_resource_reason="继续投入销售/报价资源容易消耗精力，短期难转成美国仓 MQL。",
            records=records,
        )

    if us_signal and key_count >= 4 and has_pain:
        return LeadReview(
            lead_id=lead_id,
            status="绿灯",
            reason="美国仓场景明确，平台/品类/货量或当前履约方式/痛点中至少 4 类信息完整。",
            evidence=evidence,
            customer_profile=profile,
            yqn_ability=yqn_ability,
            missing_fields=missing_fields,
            next_owner="销售 + 仓库/运营 + 报价/财务",
            next_questions=[
                "请销售补齐订单、SKU、退货、尾程账单或当前供应商资料。",
                "请仓库/运营确认能力边界和 SLA。",
                "请报价/财务按场景给出报价前置字段。",
            ],
            next_action="优先推进，整理成绿灯样板并反向沉淀内容实验。",
            records=records,
        )

    if us_signal and key_count >= 1 and has_structured_signal:
        return LeadReview(
            lead_id=lead_id,
            status="黄灯",
            reason="有美国仓或海外仓相关需求，但关键字段不足，暂不能直接报价或销售深跟。",
            evidence=evidence,
            customer_profile=profile,
            yqn_ability=yqn_ability,
            missing_fields=missing_fields,
            next_owner="私域/客服",
            next_questions=[
                "补问平台、品类、货量/单量、当前履约方式、当前供应商和核心痛点。",
                "如果涉及报价，请补 SKU、尺寸重量、服务项、目的仓和时效要求。",
            ],
            next_action="先补字段，满足 4 类关键信息后再升级为绿灯。",
            records=records,
        )

    return LeadReview(
        lead_id=lead_id,
        status="灰灯",
        reason="材料不足，不能判断线索质量；灰灯不是低质量。",
        evidence=evidence,
        customer_profile=profile,
        yqn_ability=yqn_ability,
        missing_fields=missing_fields,
        next_owner="私域/客服",
        next_questions=["补问客户平台、市场、品类、货量、当前履约方式和具体痛点。"],
        next_action="补齐证据后再判断，不直接投入销售深度资源。",
        missing_evidence="缺少平台、品类、货量、履约方式或痛点等判断依据。",
        records=records,
    )


def build_lead_reviews(records: list[Record]) -> list[LeadReview]:
    grouped: dict[str, list[Record]] = {}
    for record in records:
        if record.lead_id == "待确认":
            continue
        grouped.setdefault(record.lead_id, []).append(record)
    return [classify_lead(lead_id, group) for lead_id, group in sorted(grouped.items())]


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def fact_rows(records: list[Record]) -> list[dict[str, str]]:
    return [
        {
            "信息ID": r.info_id,
            "来源文件": r.source_file,
            "来源类型": r.source_type,
            "来源内容摘要": r.summary,
            "证据片段": r.evidence,
            "客户/线索ID": r.lead_id,
            "素材/渠道ID": r.channel_id,
            "平台": r.platform,
            "市场": r.market,
            "品类": r.category,
            "货量/单量": r.volume,
            "当前履约方式": r.fulfillment,
            "当前供应商": r.supplier,
            "核心痛点": r.pain,
            "对应YQN能力": r.yqn_ability,
            "待确认字段": r.missing_fields,
            "是否可转内容选题": r.can_be_content,
        }
        for r in records
    ]


def render_mql_report(reviews: list[LeadReview]) -> str:
    by_status = {status: [r for r in reviews if r.status == status] for status in ["绿灯", "黄灯", "红灯", "灰灯"]}
    lines = [
        "# MQL质量复盘",
        "",
        "## 今日 MQL 总览",
        "",
        f"- 识别到的 MQL 数量：{len(reviews)}",
        f"- 绿灯数量：{len(by_status['绿灯'])}",
        f"- 黄灯数量：{len(by_status['黄灯'])}",
        f"- 红灯数量：{len(by_status['红灯'])}",
        f"- 灰灯数量：{len(by_status['灰灯'])}",
    ]

    lines.extend(["", "## 绿灯 MQL"])
    if not by_status["绿灯"]:
        lines.append("- 今日未识别到绿灯 MQL。")
    for review in by_status["绿灯"]:
        lines.extend(
            [
                "",
                f"### {review.lead_id}",
                f"- 线索ID：{review.lead_id}",
                f"- 判断原因：{review.reason}",
                f"- 证据片段：{'；'.join(review.evidence)}",
                f"- 对应客户画像：{review.customer_profile}",
                f"- 对应 YQN 能力：{review.yqn_ability}",
                f"- 下一步建议动作：{review.next_action}",
            ]
        )

    lines.extend(["", "## 黄灯 MQL"])
    if not by_status["黄灯"]:
        lines.append("- 今日未识别到黄灯 MQL。")
    for review in by_status["黄灯"]:
        lines.extend(
            [
                "",
                f"### {review.lead_id}",
                f"- 为什么有潜力：{review.reason}",
                f"- 缺失字段：{'；'.join(review.missing_fields)}",
                f"- 证据片段：{'；'.join(review.evidence)}",
                f"- 下一步应该问谁：{review.next_owner}",
                f"- 下一步问题：{'；'.join(review.next_questions)}",
            ]
        )

    lines.extend(["", "## 红灯 MQL"])
    if not by_status["红灯"]:
        lines.append("- 今日未识别到红灯 MQL。")
    for review in by_status["红灯"]:
        lines.extend(
            [
                "",
                f"### {review.lead_id}",
                f"- 为什么低质量：{review.low_quality_reason or review.reason}",
                f"- 证据片段：{'；'.join(review.evidence)}",
                f"- 不建议投入资源的原因：{review.no_resource_reason or review.next_action}",
            ]
        )

    lines.extend(["", "## 灰灯 MQL"])
    if not by_status["灰灯"]:
        lines.append("- 今日未识别到灰灯 MQL。")
    for review in by_status["灰灯"]:
        lines.extend(
            [
                "",
                f"### {review.lead_id}",
                f"- 为什么无法判断：{review.reason}",
                f"- 缺失证据：{review.missing_evidence or '；'.join(review.missing_fields)}",
                f"- 下一步补问问题：{'；'.join(review.next_questions)}",
            ]
        )
    return "\n".join(lines)


def render_org_radar(records: list[Record], reviews: list[LeadReview]) -> str:
    status_counts = {s: len([r for r in reviews if r.status == s]) for s in ["绿灯", "黄灯", "红灯", "灰灯"]}
    fee_records = [r for r in records if contains_any(r.text + r.pain, ["报价", "费用", "收费", "成本"])]
    capability_records = [r for r in records if "能力" in r.source_type or contains_any(r.text, ["SLA", "SFP", "能力边界", "不能默认承诺"])]
    content_records = [r for r in records if r.channel_id != "待确认" or "小红书" in r.source_type]
    roles = [
        (
            "私域/客服",
            "黄灯和灰灯线索的基础字段不完整：平台、品类、货量、当前履约方式、当前供应商、核心痛点。",
            "私域/客服",
            f"当前黄灯 {status_counts['黄灯']} 条、灰灯 {status_counts['灰灯']} 条，缺字段会导致 MQL 无法升级。",
            "把灰灯/黄灯补成可判断线索，减少销售无效沟通。",
            "能",
            "可转成《问美国仓报价前，先准备这 6 个信息》。",
        ),
        (
            "销售",
            "绿灯线索的数据包和决策链需要补齐：订单、SKU、退货、尾程账单、现有供应商、推进时间。",
            "销售",
            "绿灯如果缺数据包，报价和仓库评估只能停留在泛聊。",
            "用于美西/美东方案、报价模型、案例复盘和销售跟进 SLA。",
            "能",
            "可转成《日单量卖家换美国仓前，为什么要先看订单和 SKU 表》。",
        ),
        (
            "仓库/运营",
            "仓库能力边界、SLA、禁限品、SFP、退货换标和质检 SOP 需要可销售化表达。",
            "仓库/运营",
            "能力边界不清会让内容和销售过度承诺。",
            "用于销售话术、报价前置字段、内容风险边界。",
            "能",
            "可转成《哪些美国仓需求必须先评估，不能直接承诺》。",
        ),
        (
            "报价/财务",
            "费用问题缺统一前置字段：仓储、出库、尾程、退货、FBA Prep、贴标、尺寸重量。",
            "报价/财务",
            f"识别到费用/报价相关记录 {len(fee_records)} 条，缺报价字段会拖慢 MQL 推进。",
            "用于快速报价、标准问诊表和成本拆分内容。",
            "能",
            "可转成《美国仓费用为什么不能只问一口价》。",
        ),
        (
            "产品/系统",
            "库存可视化、尾程账单、订单状态、BI 展示粒度需要明确。",
            "产品/系统",
            "客户痛点经常落在库存和账单透明度，系统能力不清会影响差异化表达。",
            "用于销售演示、内容截图、管理层判断差异化。",
            "能",
            "可转成《旺季真正怕的不是仓租，是库存和尾程账单看不清》。",
        ),
        (
            "投放/代理",
            "素材、私信、表单和 MQL 质量之间的归因关系需要打通。",
            "投放/代理",
            f"识别到小红书/渠道相关记录 {len(content_records)} 条，但线索质量需继续回填。",
            "用于判断哪些素材带来绿灯/黄灯，而不是只看互动。",
            "能",
            "帮助下一轮按痛点、客群和灯号复盘内容实验。",
        ),
        (
            "管理层",
            "阶段 1 需要明确优先客户画像和资源投入门槛。",
            "管理层",
            "没有门槛时，绿灯、黄灯、红灯会争抢同一批销售和报价资源。",
            "用于定义优先跟进 SLA、内容实验优先级和管理层周报口径。",
            "间接能",
            "明确先打日单量、平台、品类还是退货/FBA Prep 场景。",
        ),
    ]
    lines = ["# 组织缺口雷达", ""]
    if capability_records:
        lines.append(f"> 已读取仓库/运营能力边界记录 {len(capability_records)} 条，能力承诺仍以证据为准。")
        lines.append("")
    for title, missing, owner, impact, use, content, help_text in roles:
        lines.extend(
            [
                f"## {title}",
                "",
                f"- 缺什么信息：{missing}",
                f"- 责任方：{owner}",
                f"- 为什么影响 MQL 质量判断：{impact}",
                f"- 补齐后能用于什么：{use}",
                f"- 能不能转成内容选题：{content}",
                f"- 对下一轮内容实验有什么帮助：{help_text}",
                "",
            ]
        )
    return "\n".join(lines)


def build_content_experiments(records: list[Record], reviews: list[LeadReview]) -> list[dict[str, str]]:
    candidates = [r for r in records if r.can_be_content == "是" and "仓库/运营能力边界" not in r.source_type]
    experiments = []
    templates = [
        ("库存可视化不足", "旺季美国仓最怕库存看不清：日单量上来前要盯哪几张表", "图文", "绿灯 MQL"),
        ("尾程费用/账单不清", "美国仓尾程账单为什么会越跑越乱，卖家该提前问什么", "FAQ", "黄灯 / 绿灯 MQL"),
        ("退货换标/质检效率", "退货换标慢，为什么会直接影响 Amazon/Walmart 可售库存", "仓库口播", "黄灯 / 绿灯 MQL"),
        ("FBA Prep/贴标送仓", "FBA Prep 报价前必须问清的 7 个字段", "FAQ", "黄灯 MQL"),
        ("报价/费用拆分不清", "美国仓费用不能只问一口价：仓储、出库、尾程、退货怎么拆", "销售口播", "灰灯转黄灯 MQL"),
        ("旺季扩容/爆仓风险", "日单量 500+ 卖家为什么要提前规划美西/美东分仓", "案例", "绿灯 MQL"),
        ("入门咨询", "美国仓不是开店教程：什么样的卖家适合找 3PL", "图文", "红灯过滤"),
    ]
    exp_id = 1
    used = set()
    for pain_key, title, format_name, mql_type in templates:
        matching = [r for r in candidates if pain_key in r.pain]
        if pain_key == "旺季扩容/爆仓风险":
            source = next((r for r in matching if contains_any(r.text, ["日均", "每天", "爆仓", "分仓"])), None)
        else:
            source = None
        source = source or next((r for r in matching if "客户原话" in r.source_type), None) or next(
            (r for r in matching if r.lead_id != "待确认"), None
        ) or (matching[0] if matching else None)
        if not source or pain_key in used:
            continue
        used.add(pain_key)
        experiments.append(
            {
                "实验ID": f"EXP-S1-{exp_id:03d}",
                "实验标题": title,
                "目标客户": infer_target_customer(source, reviews),
                "平台": source.platform,
                "品类": source.category,
                "对应痛点": source.pain,
                "对应YQN能力": source.yqn_ability,
                "素材形式：图文/实景视频/销售口播/仓库口播/案例/FAQ": format_name,
                "为什么值得测": f"来源资料出现明确痛点：{source.evidence}",
                "预期吸引的MQL类型": mql_type,
                "发布前需要谁确认": infer_confirm_owner(source),
                "上线后看什么指标": "私信是否补齐平台、品类、货量、当前履约方式和痛点；对应 MQL 灯号占比",
                "来源证据": source.evidence,
            }
        )
        exp_id += 1
    if not experiments:
        experiments.append(
            {
                "实验ID": "EXP-S1-001",
                "实验标题": "问美国仓报价前，卖家至少要准备哪 6 个信息",
                "目标客户": "信息不足的美国仓潜在线索",
                "平台": "待确认",
                "品类": "待确认",
                "对应痛点": "待确认",
                "对应YQN能力": "美国仓",
                "素材形式：图文/实景视频/销售口播/仓库口播/案例/FAQ": "FAQ",
                "为什么值得测": "当前输入证据不足，先用问诊内容提升线索质量。",
                "预期吸引的MQL类型": "灰灯转黄灯 MQL",
                "发布前需要谁确认": "私域/客服；报价/财务",
                "上线后看什么指标": "灰灯线索补字段比例",
                "来源证据": "待确认",
            }
        )
    return experiments


def infer_target_customer(record: Record, reviews: list[LeadReview]) -> str:
    if "入门咨询" in record.pain:
        return "跨境新手/无店无货泛咨询线索"
    if record.platform != "待确认" or record.category != "待确认":
        return "；".join([v for v in [record.platform, record.category, record.volume] if v != "待确认"])
    green = next((r for r in reviews if r.status == "绿灯"), None)
    return green.customer_profile if green else "美国仓 / 北美跨境电商潜在客户"


def infer_confirm_owner(record: Record) -> str:
    owners = []
    if contains_any(record.pain + record.text, ["报价", "费用", "收费"]):
        owners.append("报价/财务")
    if contains_any(record.pain + record.text, ["退货", "换标", "质检", "SFP", "能力"]):
        owners.append("仓库/运营")
    if contains_any(record.pain + record.text, ["库存", "账单", "BI", "系统"]):
        owners.append("产品/系统")
    if contains_any(record.source_type, ["小红书", "素材", "投放"]):
        owners.append("投放/代理")
    owners.append("销售")
    return "；".join(dict.fromkeys(owners))


def render_personal_daily(reviews: list[LeadReview], experiments: list[dict[str, str]]) -> str:
    by_status = {status: [r for r in reviews if r.status == status] for status in ["绿灯", "黄灯", "红灯", "灰灯"]}
    top = (by_status["绿灯"] or by_status["黄灯"] or by_status["灰灯"] or by_status["红灯"] or [None])[0]
    top_text = f"{top.lead_id}（{top.status}）：{top.reason}" if top else "今日未识别到 MQL。"
    top_exp = experiments[0] if experiments else None
    lines = [
        "# 个人作战日报",
        "",
        "## 1. 一句话结论",
        "",
        f"今天优先盯 {top_text}",
        "",
        "## 2. 今日 MQL 质量概览",
        "",
        f"- 绿灯：{len(by_status['绿灯'])}",
        f"- 黄灯：{len(by_status['黄灯'])}",
        f"- 红灯：{len(by_status['红灯'])}",
        f"- 灰灯：{len(by_status['灰灯'])}",
        "",
        "## 3. 今日最值得盯的线索",
        "",
        f"- {top_text}",
        "",
        "## 4. 今日最大组织缺口",
        "",
        "- 私域/客服需要补齐黄灯和灰灯线索的基础字段；销售、仓库/运营、报价/财务需要围绕绿灯线索补数据包和能力边界。",
        "",
        "## 5. 今日最值得做的内容实验",
        "",
        f"- {top_exp['实验标题'] if top_exp else '待确认'}",
        f"- 来源证据：{top_exp['来源证据'] if top_exp else '待确认'}",
        "",
        "## 6. 今天应该问谁什么",
        "",
        "- 问私域/客服：黄灯和灰灯线索的平台、品类、货量、当前履约方式和核心痛点是否补齐。",
        "- 问销售：绿灯线索是否拿到订单、SKU、退货、尾程账单和当前供应商信息。",
        "- 问仓库/运营：涉及 SFP、退货换标、质检、带电品或大件时，能力边界和 SLA 是什么。",
        "- 问报价/财务：报价前置字段和费用拆分口径是什么。",
        "- 问投放/代理：小红书素材对应的私信、表单和 MQL 灯号能否回填。",
        "",
        "## 7. 今天最该做的 3 个动作",
        "",
        "1. 先处理绿灯线索，把证据、数据包、报价字段和仓库能力边界补齐。",
        "2. 用标准追问话术处理黄灯/灰灯，不让用户手动打分。",
        "3. 从客户痛点中挑一个内容实验上线或交给投放/代理确认。",
        "",
        "## 8. 可沉淀到 OPC 的资产",
        "",
        "- B2B 线索灯号判断规则：证据、关键信息完整度、低质量信号、证据不足信号。",
        "- B2B 内容实验模板：痛点 -> 能力 -> 素材形式 -> 确认人 -> 指标。",
        "- B2B 组织缺口雷达：责任方、缺口、用途、内容实验价值。",
    ]
    return "\n".join(lines)


def render_management_summary(reviews: list[LeadReview], experiments: list[dict[str, str]]) -> str:
    by_status = {status: [r for r in reviews if r.status == status] for status in ["绿灯", "黄灯", "红灯", "灰灯"]}
    green_feature = by_status["绿灯"][0].customer_profile if by_status["绿灯"] else "暂未形成稳定绿灯画像"
    top_exps = "；".join(exp["实验标题"] for exp in experiments[:3])
    lines = [
        "# 管理层摘要",
        "",
        "## 1. 今日 MQL 质量概览",
        "",
        f"今日识别 MQL {len(reviews)} 条：绿灯 {len(by_status['绿灯'])} 条、黄灯 {len(by_status['黄灯'])} 条、红灯 {len(by_status['红灯'])} 条、灰灯 {len(by_status['灰灯'])} 条。",
        "",
        "## 2. 高价值 MQL 特征",
        "",
        f"当前高价值特征：{green_feature}。重点看平台、品类、货量、当前履约方式、痛点和推进意向是否完整。",
        "",
        "## 3. 低质量/信息不足原因",
        "",
        "低质量主要来自泛咨询、无店无货或开店教程类需求；信息不足主要是只问美国仓报价但缺平台、品类、货量和履约场景。红灯和灰灯已分开处理。",
        "",
        "## 4. 内容实验方向",
        "",
        f"建议优先测试：{top_exps or '待确认'}。",
        "",
        "## 5. 需要协同事项",
        "",
        "- 私域/客服：补齐黄灯和灰灯的基础字段。",
        "- 销售：推动绿灯线索的数据包和决策链确认。",
        "- 仓库/运营：确认能力边界和 SLA。",
        "- 报价/财务：统一报价前置字段和成本拆分口径。",
        "- 投放/代理：回填素材到 MQL 质量的归因。",
        "",
        "## 6. 下一步动作",
        "",
        "先用绿灯线索跑通一次“资料 -> 判断 -> 协同 -> 内容实验”的闭环，再用黄灯/灰灯问诊表提升线索质量。",
    ]
    return "\n".join(lines)


def copy_output(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def save_outputs(records: list[Record], reviews: list[LeadReview], run_dir: Path) -> dict[str, Path]:
    experiments = build_content_experiments(records, reviews)
    paths = {
        "facts": ROOT / "01_事实提取" / "事实提取表.csv",
        "mql": ROOT / "02_MQL质量复盘" / "MQL质量复盘.md",
        "org": ROOT / "03_组织缺口雷达" / "组织缺口雷达.md",
        "experiments": ROOT / "04_内容实验库" / "内容实验库.csv",
        "daily": ROOT / "05_作战日报" / "个人作战日报.md",
        "management": ROOT / "05_作战日报" / "管理层摘要.md",
    }
    write_csv(paths["facts"], fact_rows(records), FACT_FIELDS)
    write_text(paths["mql"], render_mql_report(reviews))
    write_text(paths["org"], render_org_radar(records, reviews))
    write_csv(
        paths["experiments"],
        experiments,
        [
            "实验ID",
            "实验标题",
            "目标客户",
            "平台",
            "品类",
            "对应痛点",
            "对应YQN能力",
            "素材形式：图文/实景视频/销售口播/仓库口播/案例/FAQ",
            "为什么值得测",
            "预期吸引的MQL类型",
            "发布前需要谁确认",
            "上线后看什么指标",
            "来源证据",
        ],
    )
    write_text(paths["daily"], render_personal_daily(reviews, experiments))
    write_text(paths["management"], render_management_summary(reviews, experiments))

    dated_paths = {
        "facts": run_dir / "01_事实提取" / "事实提取表.csv",
        "mql": run_dir / "02_MQL质量复盘" / "MQL质量复盘.md",
        "org": run_dir / "03_组织缺口雷达" / "组织缺口雷达.md",
        "experiments": run_dir / "04_内容实验库" / "内容实验库.csv",
        "daily": run_dir / "05_作战日报" / "个人作战日报.md",
        "management": run_dir / "05_作战日报" / "管理层摘要.md",
    }
    for key, source in paths.items():
        copy_output(source, dated_paths[key])
    return paths | {"run_dir": run_dir}


def main() -> int:
    parser = argparse.ArgumentParser(description="YQN 美国仓增长闭环系统阶段 1 离线 MVP")
    parser.add_argument("--input", default="00_输入收件箱", help="输入目录，默认 00_输入收件箱")
    args = parser.parse_args()

    if not CONSTITUTION_PATH.exists():
        print(f"未找到项目宪法：{CONSTITUTION_PATH}")
        log_error(f"未找到项目宪法：{CONSTITUTION_PATH}")
        return 1
    _constitution = read_text_file(CONSTITUTION_PATH)

    input_dir = (ROOT / args.input).resolve() if not Path(args.input).is_absolute() else Path(args.input)
    if not input_dir.exists():
        print(f"未找到输入目录：{input_dir}")
        log_error(f"未找到输入目录：{input_dir}")
        return 0

    include_samples = "样例" in input_dir.name
    loaded = load_inputs(input_dir, include_samples=include_samples)
    if not loaded:
        print(f"未发现输入文件。请把 .txt / .md / .csv 放入：{input_dir}")
        log_error(f"输入目录为空或无支持格式：{input_dir}")
        return 0

    records = [build_record(path, fallback, text) for path, fallback, text in loaded]
    reviews = build_lead_reviews(records)
    run_dir = RUN_HISTORY_DIR / now_stamp()
    outputs = save_outputs(records, reviews, run_dir)

    print("阶段 1 离线闭环已完成。")
    print(f"读取输入文件/记录：{len(records)} 条")
    print(f"识别 MQL：{len(reviews)} 条")
    print(f"本次运行目录：{outputs['run_dir']}")
    print("已更新 6 个最新输出文件：")
    for key in ["facts", "mql", "org", "experiments", "daily", "management"]:
        print(f"- {outputs[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
