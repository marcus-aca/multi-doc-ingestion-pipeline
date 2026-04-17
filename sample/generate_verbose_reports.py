#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / ".codex_cache"
RUNTIME_DIR = BASE_DIR / ".codex_runtime"

CODEX_ENRICHMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "industry_distinctiveness": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "core_identity": {"type": "string"},
                "difference_drivers": {"type": "array", "items": {"type": "string"}},
                "commercial_logic": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["core_identity", "difference_drivers", "commercial_logic"]
        },
        "trend_map": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "trend_name": {"type": "string"},
                    "trend_summary": {"type": "string"},
                    "commercial_impact": {"type": "string"},
                    "credit_relevance": {"type": "string"}
                },
                "required": ["trend_name", "trend_summary", "commercial_impact", "credit_relevance"]
            }
        },
        "risk_matrix": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "risk_name": {"type": "string"},
                    "severity": {"type": "string"},
                    "likelihood": {"type": "string"},
                    "risk_description": {"type": "string"},
                    "early_warning_signals": {"type": "string"},
                    "mitigants": {"type": "string"}
                },
                "required": ["risk_name", "severity", "likelihood", "risk_description", "early_warning_signals", "mitigants"]
            }
        },
        "stability_assessment": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "overall_stability_view": {"type": "string"},
                "stability_factors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "factor_name": {"type": "string"},
                            "stability_view": {"type": "string"},
                            "analysis": {"type": "string"},
                            "rating_rationale": {"type": "string"}
                        },
                        "required": ["factor_name", "stability_view", "analysis", "rating_rationale"]
                    }
                },
                "stability_watchpoints": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["overall_stability_view", "stability_factors", "stability_watchpoints"]
        },
        "credit_analysis": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "industry_credit_overview": {"type": "string"},
                "credit_factors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "credit_factor": {"type": "string"},
                            "credit_view": {"type": "string"},
                            "analysis": {"type": "string"},
                            "lender_questions": {"type": "array", "items": {"type": "string"}}
                        },
                        "required": ["credit_factor", "credit_view", "analysis", "lender_questions"]
                    }
                },
                "cash_flow_considerations": {"type": "array", "items": {"type": "string"}},
                "underwriting_considerations": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["industry_credit_overview", "credit_factors", "cash_flow_considerations", "underwriting_considerations"]
        },
        "strategic_narrative": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "industry_structure": {"type": "string"},
                "competitive_behavior": {"type": "string"},
                "capital_cycle": {"type": "string"},
                "operating_fragility": {"type": "string"}
            },
            "required": ["industry_structure", "competitive_behavior", "capital_cycle", "operating_fragility"]
        }
    },
    "required": [
        "industry_distinctiveness",
        "trend_map",
        "risk_matrix",
        "stability_assessment",
        "credit_analysis",
        "strategic_narrative"
    ]
}

INDUSTRY_PROFILES = {
    "Cloud Kitchen Services in the United States": {
        "short_name": "cloud kitchen services",
        "operators": ["ghost kitchen networks", "virtual brand operators", "multi-concept kitchen hubs", "delivery-first food groups"],
        "customers": ["delivery app users", "office lunch buyers", "late-night diners", "suburban convenience seekers"],
        "channels": ["third-party marketplaces", "first-party ordering apps", "corporate catering portals", "subscription meal programs"],
        "inputs": ["proteins", "fresh produce", "takeout packaging", "courier availability"],
        "pressures": ["aggregator fees", "food inflation", "labor scheduling gaps", "dense-market competition"],
        "kpis": ["average order value", "kitchen utilization", "repeat order rate", "prep-to-dispatch time"],
        "regions": ["dense urban cores", "inner-ring suburbs", "college districts", "mixed-use corridors"],
        "regulators": ["health departments", "local labor agencies", "municipal zoning offices", "food safety inspectors"]
    },
    "Electric Vehicle Charging Infrastructure in the United States": {
        "short_name": "EV charging infrastructure",
        "operators": ["charge point operators", "site hosts", "network software providers", "energy-integrated charging firms"],
        "customers": ["commuter drivers", "fleet managers", "multifamily property owners", "highway travelers"],
        "channels": ["public fast-charging sites", "fleet depots", "workplace charging programs", "destination charging networks"],
        "inputs": ["grid connections", "power electronics", "transformers", "site leases"],
        "pressures": ["demand charges", "interconnection delays", "maintenance uptime gaps", "capital intensity"],
        "kpis": ["charger utilization", "uptime percentage", "energy dispensed per site", "customer session completion rate"],
        "regions": ["interstate corridors", "urban parking assets", "suburban retail clusters", "fleet logistics zones"],
        "regulators": ["state energy offices", "utility commissions", "transport agencies", "building code authorities"]
    },
    "Vertical Farming Operations in the United States": {
        "short_name": "vertical farming",
        "operators": ["indoor leafy-green growers", "controlled-environment produce firms", "urban farm developers", "seedling specialists"],
        "customers": ["grocers", "foodservice distributors", "meal kit brands", "premium restaurant groups"],
        "channels": ["regional grocery supply", "direct foodservice accounts", "subscription produce boxes", "private-label retail programs"],
        "inputs": ["electricity", "nutrient solutions", "LED lighting systems", "climate control infrastructure"],
        "pressures": ["power costs", "yield variability", "cold-chain spoilage risk", "premium pricing resistance"],
        "kpis": ["crop yield per square foot", "sell-through rate", "shrink rate", "harvest labor efficiency"],
        "regions": ["major metro food sheds", "cool-climate warehouse districts", "distribution-adjacent hubs", "premium retail corridors"],
        "regulators": ["food safety authorities", "water agencies", "occupational safety bodies", "local planning departments"]
    },
    "Telehealth Platform Providers in the United States": {
        "short_name": "telehealth platforms",
        "operators": ["virtual care software vendors", "specialty telehealth platforms", "hybrid-care enablement firms", "remote monitoring integrators"],
        "customers": ["provider groups", "health systems", "payers", "employers"],
        "channels": ["enterprise software contracts", "payer partnerships", "white-labeled virtual clinics", "embedded care workflows"],
        "inputs": ["software engineering talent", "clinical workflow design", "security infrastructure", "interoperability tooling"],
        "pressures": ["reimbursement uncertainty", "provider adoption friction", "cybersecurity requirements", "integration complexity"],
        "kpis": ["visit completion rate", "provider adoption", "patient retention", "implementation cycle time"],
        "regions": ["multi-state provider networks", "employer-sponsored populations", "underserved rural areas", "specialty-care markets"],
        "regulators": ["state licensing boards", "privacy regulators", "payer policy teams", "clinical compliance officers"]
    },
    "Warehouse Robotics and Automation Solutions in the United States": {
        "short_name": "warehouse robotics",
        "operators": ["autonomous mobile robot vendors", "goods-to-person integrators", "robotic picking specialists", "fulfillment orchestration providers"],
        "customers": ["retail distribution centers", "third-party logistics firms", "industrial distributors", "e-commerce operators"],
        "channels": ["direct enterprise sales", "systems integrator partnerships", "robotics-as-a-service contracts", "retrofit automation projects"],
        "inputs": ["machine vision components", "battery systems", "software talent", "field service coverage"],
        "pressures": ["long sales cycles", "integration risk", "capital budgeting scrutiny", "warehouse downtime sensitivity"],
        "kpis": ["units picked per hour", "robot uptime", "deployment payback period", "order accuracy"],
        "regions": ["inland logistics hubs", "port-adjacent warehouses", "same-day fulfillment markets", "mid-market distribution clusters"],
        "regulators": ["workplace safety agencies", "equipment certification bodies", "industrial standards groups", "site safety managers"]
    },
    "Pet Insurance Providers in the United States": {
        "short_name": "pet insurance",
        "operators": ["specialty pet insurers", "digital insurance brands", "underwriting partners", "benefits-distribution platforms"],
        "customers": ["first-time pet owners", "multi-pet households", "employer benefits buyers", "high-spend veterinary clients"],
        "channels": ["direct digital acquisition", "veterinary partnerships", "employer benefits enrollment", "pet adoption funnels"],
        "inputs": ["actuarial models", "claims systems", "customer support teams", "distribution partnerships"],
        "pressures": ["veterinary inflation", "consumer education gaps", "policy lapse risk", "marketing costs"],
        "kpis": ["loss ratio", "policy retention", "claims turnaround time", "average premium per pet"],
        "regions": ["high-income suburban markets", "dense pet-owner metros", "employer-heavy regions", "veterinary referral corridors"],
        "regulators": ["state insurance departments", "product filing teams", "consumer protection offices", "claims compliance teams"]
    },
    "Modular Construction Services in the United States": {
        "short_name": "modular construction",
        "operators": ["off-site manufacturers", "volumetric module builders", "panelized system providers", "design-for-manufacture specialists"],
        "customers": ["multifamily developers", "public agencies", "hospitality owners", "education project sponsors"],
        "channels": ["design-build contracts", "developer partnerships", "public procurement programs", "repeatable housing pipelines"],
        "inputs": ["engineered timber or steel", "factory labor", "transport logistics", "digital coordination tools"],
        "pressures": ["freight constraints", "design lock-in risk", "factory utilization swings", "code interpretation differences"],
        "kpis": ["factory throughput", "installation cycle time", "rework rate", "schedule compression achieved"],
        "regions": ["housing-constrained metros", "institutional building markets", "transport-linked manufacturing corridors", "storm-recovery regions"],
        "regulators": ["building departments", "transport permit offices", "state modular approval programs", "occupational safety agencies"]
    },
    "Electronic Waste Recycling in the United States": {
        "short_name": "electronic waste recycling",
        "operators": ["IT asset disposition firms", "device refurbishers", "certified recyclers", "enterprise collection networks"],
        "customers": ["enterprise IT departments", "public agencies", "consumer collection programs", "retail take-back partners"],
        "channels": ["enterprise contracts", "manufacturer take-back programs", "municipal collection events", "remarketing channels"],
        "inputs": ["reverse logistics capacity", "sorting labor", "secure data destruction systems", "downstream commodity buyers"],
        "pressures": ["commodity volatility", "battery fire risk", "compliance documentation", "low-value device streams"],
        "kpis": ["reuse yield", "material recovery rate", "chain-of-custody accuracy", "processing margin per device"],
        "regions": ["enterprise-heavy metros", "port-connected processing hubs", "municipal collection networks", "refurbishment clusters"],
        "regulators": ["environmental agencies", "data security auditors", "waste transport regulators", "certification bodies"]
    },
    "Creator Economy Software Tools in the United States": {
        "short_name": "creator economy software",
        "operators": ["newsletter platforms", "membership software vendors", "digital storefront tools", "community monetization providers"],
        "customers": ["independent writers", "video creators", "educators", "small creator-led studios"],
        "channels": ["self-serve subscriptions", "creator referrals", "agency partnerships", "integrated commerce workflows"],
        "inputs": ["software development", "payment infrastructure", "customer support", "creator success programming"],
        "pressures": ["creator churn", "platform dependency", "crowded feature competition", "marketing efficiency"],
        "kpis": ["creator retention", "gross merchandise value", "paid conversion rate", "average revenue per creator"],
        "regions": ["digital-first creator hubs", "remote freelance communities", "education-focused markets", "independent media clusters"],
        "regulators": ["payment compliance teams", "privacy authorities", "consumer subscription regulators", "platform policy groups"]
    },
    "Outpatient Behavioral Health Services in the United States": {
        "short_name": "outpatient behavioral health",
        "operators": ["therapy clinic groups", "psychiatry practices", "intensive outpatient programs", "integrated behavioral health providers"],
        "customers": ["commercially insured adults", "adolescents and families", "employer-sponsored populations", "referral-based patients"],
        "channels": ["payer-contracted clinics", "direct private-pay intake", "school or employer partnerships", "hybrid telehealth pathways"],
        "inputs": ["licensed clinicians", "supervision capacity", "practice management systems", "referral relationships"],
        "pressures": ["clinician shortages", "payer authorization burden", "documentation load", "burnout and retention challenges"],
        "kpis": ["days to first appointment", "clinician utilization", "care retention", "payer collection rate"],
        "regions": ["underserved suburban markets", "dense urban referral networks", "college-oriented communities", "integrated health-system regions"],
        "regulators": ["state licensing boards", "privacy and documentation authorities", "payer utilization review teams", "prescribing compliance programs"]
    }
}

LENSES = [
    "demand formation",
    "pricing architecture",
    "capacity planning",
    "labor deployment",
    "capital allocation",
    "competitive response",
    "customer retention",
    "quality assurance",
    "technology adoption",
    "regional expansion"
]

OPENINGS = [
    "Operators in {industry} are increasingly organized around {lens}, not just headline growth.",
    "A defining feature of {industry} is the way management teams balance {lens} with day-to-day execution.",
    "The commercial profile of {industry} becomes clearer when the market is examined through {lens}.",
    "Recent shifts in {industry} show that {lens} often determines which business models remain durable.",
    "Within {industry}, decisions around {lens} now shape both resilience and valuation."
]

MIDDLES = [
    "In practice, {operator} compete for {customer} demand through {channel}, which creates visible differences in revenue quality and service expectations.",
    "Winning operators tend to match {customer} needs with {channel}, while weaker participants overextend before proving local economics.",
    "Commercial outcomes are closely tied to how {operator} use {channel} to reach {customer} groups that value reliability over novelty.",
    "Managers usually learn that {customer} behavior changes materially depending on whether the business leans on {channel} or builds a more direct route to market.",
    "The most stable performers are often the {operator} that tailor {channel} around the needs of {customer} segments instead of chasing broad volume."
]

PRESSURE_LINES = [
    "That opportunity is offset by pressure from {pressure}, which can narrow margins even when top-line demand appears healthy.",
    "The operating model also has to absorb {pressure}, so revenue growth does not automatically translate into better cash generation.",
    "Even strong businesses remain exposed to {pressure}, especially when management underestimates the operational detail required at scale.",
    "Margin performance can deteriorate quickly when {pressure} is treated as temporary rather than structural.",
    "A recurring challenge comes from {pressure}, because it affects pricing credibility, planning confidence and investor patience."
]

CLOSINGS = [
    "For that reason, leadership teams track {kpi} closely and redesign workflows when the metric drifts from target levels.",
    "This is why {kpi} remains one of the most useful indicators for comparing disciplined operators with expansion-heavy peers.",
    "The clearest proof of execution quality is usually found in {kpi}, which ties together operational choices and customer outcomes.",
    "As a result, {kpi} often becomes the metric that lenders, boards and commercial partners return to during performance reviews.",
    "In most submarkets, sustained improvement in {kpi} says more about strategic fit than broad narrative claims ever could."
]


def cyc(items, idx):
    return items[idx % len(items)]

def build_passage(profile, industry, idx, section, emphasis):
    lens = cyc(LENSES, idx + len(section))
    operator = cyc(profile["operators"], idx)
    customer = cyc(profile["customers"], idx + 1)
    channel = cyc(profile["channels"], idx + 2)
    pressure = cyc(profile["pressures"], idx + 3)
    kpi = cyc(profile["kpis"], idx + 4)
    region = cyc(profile["regions"], idx + 5)
    regulator = cyc(profile["regulators"], idx + 6)
    input_item = cyc(profile["inputs"], idx + 7)

    sentences = [
        cyc(OPENINGS, idx).format(industry=industry, lens=lens),
        cyc(MIDDLES, idx + len(emphasis)).format(
            operator=operator, customer=customer, channel=channel
        ),
        f"This {section} narrative is specific to entry {idx}, where the emphasis falls on {emphasis} and the trade-offs are evaluated against the current operating shape of {profile['short_name']}.",
        f"The {section} angle in item {idx} highlights how {input_item} and local conditions in {region} alter cost structure, service reliability and the pace of expansion.",
        cyc(PRESSURE_LINES, idx + len(section)).format(pressure=pressure),
        f"Regulatory touchpoints are also relevant because {regulator} can influence documentation, reporting cadence and the amount of operational flexibility available to management teams.",
        cyc(CLOSINGS, idx + len(industry)).format(kpi=kpi),
        f"Seen together, these factors make {emphasis} a concrete operating issue rather than an abstract industry theme."
    ]
    return " ".join(sentences)


def build_segment(profile, industry, idx):
    return {
        "segment_id": f"segment-{idx:03d}",
        "segment_name": f"{profile['short_name'].title()} segment {idx}",
        "segment_theme": cyc(["value-tier demand", "premium service", "institutional accounts", "specialized workflows", "growth geography"], idx),
        "revenue_share_commentary": build_passage(profile, industry, idx, "segment mix", "segment economics"),
        "buyer_profile": build_passage(profile, industry, idx + 20, "buyer profile", "customer qualification and retention"),
        "pricing_model": build_passage(profile, industry, idx + 40, "pricing model", "price realization and discount discipline"),
        "operating_model": build_passage(profile, industry, idx + 60, "operating model", "throughput, staffing and utilization"),
        "risk_notes": [
            build_passage(profile, industry, idx + 80, "risk note", "execution variance"),
            build_passage(profile, industry, idx + 100, "risk note", "regional volatility")
        ]
    }


def build_company(profile, industry, idx):
    return {
        "company_id": f"company-{idx:03d}",
        "company_archetype": cyc(
            ["scaled incumbent", "regional consolidator", "specialist challenger", "technology-led operator", "disciplined niche provider"],
            idx,
        ),
        "positioning_statement": build_passage(profile, industry, idx + 120, "company positioning", "competitive posture"),
        "commercial_strategy": build_passage(profile, industry, idx + 140, "commercial strategy", "market selection and account development"),
        "operational_priorities": [
            build_passage(profile, industry, idx + 160, "operations", "workflow standardization"),
            build_passage(profile, industry, idx + 180, "operations", "quality assurance"),
            build_passage(profile, industry, idx + 200, "operations", "capacity utilization")
        ],
        "watch_items": [
            f"Management needs to protect {cyc(profile['kpis'], idx)} while scaling through {cyc(profile['channels'], idx + 1)}.",
            f"Competitive risk increases when {cyc(profile['pressures'], idx + 2)} is not priced correctly.",
            f"Expansion success depends on how well the firm adapts to {cyc(profile['regions'], idx + 3)}."
        ]
    }


def build_kpi(profile, industry, idx):
    kpi = cyc(profile["kpis"], idx)
    return {
        "metric_name": kpi,
        "definition": build_passage(profile, industry, idx + 220, "KPI definition", f"measurement of {kpi}"),
        "management_use": build_passage(profile, industry, idx + 240, "KPI management use", "operational monitoring"),
        "improvement_levers": [
            build_passage(profile, industry, idx + 260, "improvement lever", "commercial refinement"),
            build_passage(profile, industry, idx + 280, "improvement lever", "process redesign")
        ],
        "warning_pattern": build_passage(profile, industry, idx + 300, "warning pattern", "early detection of underperformance")
    }


def build_trend(profile, industry, idx):
    return {
        "trend_id": f"trend-{idx:03d}",
        "time_horizon": cyc(["current year", "two-to-three years", "longer horizon"], idx),
        "trend_title": f"{profile['short_name'].title()} trend {idx}",
        "market_description": build_passage(profile, industry, idx + 320, "trend description", "structural change"),
        "operator_implications": build_passage(profile, industry, idx + 340, "operator implications", "required management response"),
        "investor_interpretation": build_passage(profile, industry, idx + 360, "investor interpretation", "capital market framing")
    }


def build_regulatory_item(profile, industry, idx):
    regulator = cyc(profile["regulators"], idx)
    return {
        "regulation_theme": f"{regulator} oversight topic {idx}",
        "summary": build_passage(profile, industry, idx + 380, "regulation summary", "compliance planning"),
        "cost_effect": build_passage(profile, industry, idx + 400, "cost effect", "administrative and operating burden"),
        "strategic_response": build_passage(profile, industry, idx + 420, "strategic response", "control design and documentation")
    }


def build_supply_item(profile, industry, idx):
    input_item = cyc(profile["inputs"], idx)
    return {
        "input_name": input_item,
        "sourcing_context": build_passage(profile, industry, idx + 440, "sourcing context", "procurement reliability"),
        "price_sensitivity": build_passage(profile, industry, idx + 460, "price sensitivity", "margin protection"),
        "substitution_pathways": build_passage(profile, industry, idx + 480, "substitution pathways", "risk mitigation"),
        "operator_comment": f"In sourcing review {idx}, management teams compare {input_item} exposure against {cyc(profile['kpis'], idx + 1)} before changing strategy, because the cost and service trade-offs rarely look identical from one input category to the next."
    }


def build_region(profile, industry, idx):
    region = cyc(profile["regions"], idx)
    return {
        "region_name": region,
        "demand_conditions": build_passage(profile, industry, idx + 500, "regional demand", "local market fit"),
        "cost_profile": build_passage(profile, industry, idx + 520, "regional cost profile", "labor and logistics intensity"),
        "entry_strategy": build_passage(profile, industry, idx + 540, "regional entry", "sequencing of expansion decisions")
    }


def build_industry_aspect(profile, industry, idx):
    return {
        "aspect_name": cyc(
            [
                "industry structure",
                "customer concentration",
                "pricing power",
                "cost absorption capacity",
                "capacity flexibility",
                "barriers to entry",
                "supplier leverage",
                "substitution exposure",
                "cyclicality",
                "capital discipline"
            ],
            idx,
        ),
        "description": build_passage(profile, industry, idx + 1300, "industry aspect", "core industry mechanics"),
        "management_relevance": build_passage(profile, industry, idx + 1320, "industry aspect relevance", "decision-making implications"),
        "investor_takeaway": build_passage(profile, industry, idx + 1340, "industry aspect takeaway", "valuation and resilience framing")
    }


def build_trend_map_item(profile, industry, idx):
    return {
        "trend_name": cyc(
            [
                "technology deepening",
                "channel mix migration",
                "regulatory normalization",
                "procurement professionalization",
                "margin discipline",
                "regional expansion selectivity",
                "service-level transparency",
                "buyer sophistication"
            ],
            idx,
        ),
        "trend_summary": build_passage(profile, industry, idx + 1360, "trend map", "observable market evolution"),
        "commercial_impact": build_passage(profile, industry, idx + 1380, "trend commercial impact", "revenue and mix effects"),
        "credit_relevance": build_passage(profile, industry, idx + 1400, "trend credit relevance", "cash flow durability and lender perspective")
    }


def build_risk_matrix_item(profile, industry, idx):
    return {
        "risk_name": cyc(
            [
                "demand compression",
                "input cost shock",
                "execution slippage",
                "regulatory tightening",
                "customer churn",
                "capital scarcity",
                "technology transition risk",
                "reputation damage",
                "working capital stress",
                "competitive price pressure"
            ],
            idx,
        ),
        "severity": cyc(["moderate", "meaningful", "elevated", "contained"], idx),
        "likelihood": cyc(["low", "moderate", "moderately high", "high"], idx + 1),
        "risk_description": build_passage(profile, industry, idx + 1420, "risk matrix", "downside exposure"),
        "early_warning_signals": build_passage(profile, industry, idx + 1440, "risk signals", "monitoring of deterioration"),
        "mitigants": build_passage(profile, industry, idx + 1460, "risk mitigants", "defensive controls and response plans")
    }


def build_stability_factor(profile, industry, idx):
    return {
        "factor_name": cyc(
            [
                "revenue visibility",
                "customer renewal behavior",
                "input cost predictability",
                "operating continuity",
                "regulatory stability",
                "competitive intensity",
                "service consistency",
                "balance between growth and discipline"
            ],
            idx,
        ),
        "stability_view": cyc(["stable", "mostly stable", "mixed", "watch closely"], idx),
        "analysis": build_passage(profile, industry, idx + 1480, "stability analysis", "continuity of operating performance"),
        "rating_rationale": build_passage(profile, industry, idx + 1500, "stability rationale", "why the factor supports or weakens resilience")
    }


def build_credit_factor(profile, industry, idx):
    return {
        "credit_factor": cyc(
            [
                "cash flow durability",
                "margin volatility",
                "working capital pressure",
                "capex burden",
                "refinancing flexibility",
                "customer concentration sensitivity",
                "liquidity resilience",
                "covenant headroom"
            ],
            idx,
        ),
        "credit_view": cyc(["supportive", "balanced", "cautious", "pressured"], idx),
        "analysis": build_passage(profile, industry, idx + 1520, "credit factor", "debt service capacity"),
        "lender_questions": [
            build_passage(profile, industry, idx + 1540, "credit question", "underwriting diligence"),
            build_passage(profile, industry, idx + 1560, "credit question", "stress-case review")
        ]
    }


def build_persona(profile, industry, idx):
    customer = cyc(profile["customers"], idx)
    return {
        "persona_name": f"{customer.title()} persona {idx}",
        "procurement_style": build_passage(profile, industry, idx + 560, "persona procurement", "buying process and account expectations"),
        "pain_points": [
            build_passage(profile, industry, idx + 580, "persona pain point", "service confidence"),
            build_passage(profile, industry, idx + 600, "persona pain point", "price-value trade-offs")
        ],
        "conversion_triggers": [
            f"Clear evidence that {cyc(profile['kpis'], idx)} is improving in the accounts they benchmark.",
            f"A delivery model built around {cyc(profile['channels'], idx + 1)} instead of generic outreach.",
            f"More confidence that {cyc(profile['pressures'], idx + 2)} will not disrupt service quality."
        ]
    }


def build_glossary(profile, industry, idx):
    term = f"{profile['short_name'].title()} term {idx}"
    return {
        "term": term,
        "definition": build_passage(profile, industry, idx + 620, "glossary definition", f"shared language around {term}"),
        "usage_note": build_passage(profile, industry, idx + 640, "glossary usage", "interpretation in diligence and operations")
    }


def build_long_list(profile, industry, start_idx, count, section, emphasis):
    return [
        build_passage(profile, industry, start_idx + i, section, emphasis)
        for i in range(count)
    ]


def run_codex_enrichment(data, profile, model=None, force=False):
    CACHE_DIR.mkdir(exist_ok=True)
    RUNTIME_DIR.mkdir(exist_ok=True)
    cache_path = CACHE_DIR / f"{data['report_id']}.json"
    error_path = CACHE_DIR / f"{data['report_id']}.error.txt"
    if cache_path.exists() and not force:
        return json.loads(cache_path.read_text())

    prompt = f"""
You are enriching a synthetic market research report.

Return JSON only that matches the provided schema.
Do not repeat phrasing across fields.
Make the content clearly specific to this single industry rather than generic business analysis.
Write in a commercial research style with concrete operating detail, trend analysis, stability commentary, and lender-oriented credit framing.

Industry: {data["title"]}
Geography: {data["geography"]}
Industry code: {data["industry_code"]}
Keywords: {", ".join(data["keywords"])}

Industry profile:
Operators: {", ".join(profile["operators"])}
Customers: {", ".join(profile["customers"])}
Channels: {", ".join(profile["channels"])}
Inputs: {", ".join(profile["inputs"])}
Pressures: {", ".join(profile["pressures"])}
KPIs: {", ".join(profile["kpis"])}
Regions: {", ".join(profile["regions"])}
Regulators: {", ".join(profile["regulators"])}

Existing report context:
Executive summary: {" ".join(data["executive_summary"])}
Competitive landscape: {" ".join(data["competitive_landscape"])}
Market dynamics: {" ".join(data["market_dynamics"])}
Major trends: {" ".join(data["major_trends"])}
Risks and outlook: {" ".join(data["risks_and_outlook"])}

Make the resulting sections meaningfully different from reports about the other industries in this dataset.
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        schema_path = tmp / "schema.json"
        output_path = tmp / "output.json"
        schema_path.write_text(json.dumps(CODEX_ENRICHMENT_SCHEMA))

        cmd = [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--cd",
            str(BASE_DIR.parent),
            "--output-schema",
            str(schema_path),
            "-o",
            str(output_path),
            "--color",
            "never",
            "--full-auto",
            "--ephemeral",
        ]
        if model:
            cmd.extend(["--model", model])
        cmd.append(prompt.strip())

        env = os.environ.copy()
        env["CODEX_HOME"] = str(RUNTIME_DIR)
        env["CODEX_CONFIG_HOME"] = str(RUNTIME_DIR)
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)
            result = json.loads(output_path.read_text())
            cache_path.write_text(json.dumps(result, indent=2) + "\n")
            if error_path.exists():
                error_path.unlink()
            return result
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            error_path.write_text(
                "\n".join(
                    [
                        f"codex command failed for {data['report_id']}",
                        f"exit_code={exc.returncode}",
                        "",
                        "STDERR:",
                        stderr,
                        "",
                        "STDOUT:",
                        stdout,
                    ]
                )
                + "\n"
            )
            return None


def enrich_report(path: Path, use_codex=True, codex_model=None, force_codex=False) -> None:
    with path.open() as f:
        data = json.load(f)

    industry = data["title"]
    profile = INDUSTRY_PROFILES[industry]

    data["report_metadata"] = {
        "source_type": "synthetic sample document",
        "document_purpose": "long-form ingestion and parsing fixture",
        "schema_version": "3.0",
        "editorial_style": "industry-specific, highly structured, non-repeating narrative",
        "document_notes": build_passage(profile, industry, 0, "document notes", "dataset design and retrieval coverage")
    }

    data["industry_at_a_glance"] = {
        "headline_observation": build_passage(profile, industry, 1, "headline observation", "market positioning"),
        "demand_drivers": build_long_list(profile, industry, 10, 18, "demand driver", "sources of commercial momentum"),
        "margin_pressures": build_long_list(profile, industry, 40, 18, "margin pressure", "profitability constraints"),
        "buyer_behavior_patterns": build_long_list(profile, industry, 70, 18, "buyer behavior", "renewal and conversion dynamics"),
        "innovation_vectors": build_long_list(profile, industry, 100, 18, "innovation vector", "product and operating model change")
    }

    data["market_segments_detailed"] = [build_segment(profile, industry, i) for i in range(1, 31)]
    data["representative_companies"] = [build_company(profile, industry, i) for i in range(1, 21)]
    data["key_performance_indicators"] = [build_kpi(profile, industry, i) for i in range(1, 25)]
    data["structural_trends_expanded"] = [build_trend(profile, industry, i) for i in range(1, 21)]
    data["regulatory_and_compliance_map"] = [build_regulatory_item(profile, industry, i) for i in range(1, 16)]
    data["supply_chain_dependencies"] = [build_supply_item(profile, industry, i) for i in range(1, 16)]
    data["regional_market_profiles"] = [build_region(profile, industry, i) for i in range(1, 13)]
    data["industry_aspects_expanded"] = [build_industry_aspect(profile, industry, i) for i in range(1, 21)]
    data["trend_map"] = [build_trend_map_item(profile, industry, i) for i in range(1, 17)]
    data["risk_matrix"] = [build_risk_matrix_item(profile, industry, i) for i in range(1, 21)]
    data["stability_assessment"] = {
        "overall_stability_view": build_passage(profile, industry, 1600, "overall stability", "industry resilience over the cycle"),
        "stability_factors": [build_stability_factor(profile, industry, i) for i in range(1, 13)],
        "stability_watchpoints": build_long_list(profile, industry, 1620, 24, "stability watchpoint", "conditions that could weaken the sector")
    }
    data["credit_analysis"] = {
        "industry_credit_overview": build_passage(profile, industry, 1700, "credit overview", "broad lender perspective on the sector"),
        "credit_factors": [build_credit_factor(profile, industry, i) for i in range(1, 13)],
        "cash_flow_considerations": build_long_list(profile, industry, 1720, 18, "cash flow consideration", "conversion, liquidity and debt service"),
        "underwriting_considerations": build_long_list(profile, industry, 1760, 18, "underwriting consideration", "questions for creditors and risk committees")
    }
    data["buyer_personas"] = [build_persona(profile, industry, i) for i in range(1, 13)]
    data["industry_glossary"] = [build_glossary(profile, industry, i) for i in range(1, 31)]

    data["scenario_analysis"] = {
        "base_case": {
            "commercial_context": build_passage(profile, industry, 700, "base case", "most probable demand and margin profile"),
            "operator_response": build_passage(profile, industry, 701, "base case response", "steady execution priorities")
        },
        "upside_case": {
            "commercial_context": build_passage(profile, industry, 702, "upside case", "conditions for above-plan performance"),
            "operator_response": build_passage(profile, industry, 703, "upside case response", "reinvestment and share capture")
        },
        "downside_case": {
            "commercial_context": build_passage(profile, industry, 704, "downside case", "demand and cost stress"),
            "operator_response": build_passage(profile, industry, 705, "downside case response", "defensive operating actions")
        }
    }

    data["interview_guide_topics"] = build_long_list(profile, industry, 800, 70, "interview guide", "management diligence topics")
    data["research_questions"] = build_long_list(profile, industry, 900, 70, "research question", "follow-up analytical work")
    data["appendix"] = {
        "methodology_notes": build_long_list(profile, industry, 1000, 45, "methodology note", "interpretation boundaries"),
        "data_quality_considerations": build_long_list(profile, industry, 1100, 45, "data quality note", "comparability and caveats"),
        "additional_observations": build_long_list(profile, industry, 1200, 45, "additional observation", "miscellaneous operating insight")
    }

    if use_codex:
        enrichment = run_codex_enrichment(data, profile, model=codex_model, force=force_codex)
        if enrichment:
            data["report_metadata"]["generation_method"] = "hybrid local template plus codex cli enrichment"
            data["report_metadata"]["codex_enrichment_status"] = "applied"
            data["industry_distinctiveness"] = enrichment["industry_distinctiveness"]
            data["strategic_narrative"] = enrichment["strategic_narrative"]
            data["trend_map"] = enrichment["trend_map"]
            data["risk_matrix"] = enrichment["risk_matrix"]
            data["stability_assessment"] = enrichment["stability_assessment"]
            data["credit_analysis"] = enrichment["credit_analysis"]
        else:
            data["report_metadata"]["generation_method"] = "local template with attempted codex cli enrichment"
            data["report_metadata"]["codex_enrichment_status"] = "failed_fell_back_to_local"
    else:
        data["report_metadata"]["generation_method"] = "local template only"
        data["report_metadata"]["codex_enrichment_status"] = "disabled"

    with path.open("w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-codex", action="store_true", help="Disable codex cli enrichment and use local generation only.")
    parser.add_argument("--force-codex", action="store_true", help="Refresh cached codex cli enrichment responses.")
    parser.add_argument("--codex-model", help="Optional model name passed through to codex exec.")
    parser.add_argument("--limit", type=int, help="Only process the first N JSON reports.")
    args = parser.parse_args()

    paths = sorted(BASE_DIR.glob("*.json"))
    if args.limit:
        paths = paths[: args.limit]

    for path in paths:
        enrich_report(
            path,
            use_codex=not args.no_codex,
            codex_model=args.codex_model,
            force_codex=args.force_codex,
        )


if __name__ == "__main__":
    main()
