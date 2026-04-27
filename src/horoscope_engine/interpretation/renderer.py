from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Dict, List, Optional, Sequence, Tuple

from ..content_repository import V2ContentRepository, stable_index
from ..models import (
    ChartSnapshot,
    FactorDetail,
    Period,
    PeriodEvent,
    PeriodMetrics,
    Section,
    SectionInsight,
)
from .rules import RuleSet


WEEKLY_THEMES = [
    "reset_and_refocus",
    "relationship_recalibration",
    "career_momentum",
    "emotional_processing",
    "communication_clarity",
    "discipline_and_structure",
    "inner_healing",
    "creative_expansion",
    "financial_reassessment",
    "social_visibility",
    "spiritual_reflection",
    "action_and_initiative",
]

MONTHLY_THEMES = [
    "reset_and_refocus",
    "relationship_recalibration",
    "career_momentum",
    "emotional_processing",
    "communication_clarity",
    "discipline_and_structure",
    "inner_healing",
    "creative_expansion",
    "financial_reassessment",
    "social_visibility",
    "spiritual_reflection",
    "action_and_initiative",
    "home_and_foundation",
    "visibility_and_recognition",
    "release_and_closure",
    "long_term_rebuild",
]

YEARLY_THEMES = [
    "reset_and_refocus",
    "relationship_recalibration",
    "career_momentum",
    "emotional_processing",
    "communication_clarity",
    "discipline_and_structure",
    "inner_healing",
    "creative_expansion",
    "financial_reassessment",
    "social_visibility",
    "spiritual_reflection",
    "action_and_initiative",
    "home_and_foundation",
    "visibility_and_recognition",
    "release_and_closure",
    "long_term_rebuild",
    "destiny_turning_point",
    "reinvention_cycle",
]

SECTION_FALLBACK_TEMPLATE = {
    "quiet": "A quieter {section} phase favors {keywords} and steady recalibration.",
    "steady": "A steady {section} flow highlights {keywords} and consistent progress.",
    "elevated": "Momentum lifts in {section}; {keywords} are where progress happens.",
    "high": "A high-intensity {section} window puts {keywords} at the center.",
}

SECTION_VOICE = {
    Section.GENERAL: {
        "daily_hook": "Pick one priority and keep decisions anchored to it.",
        "weekly_hook": "Protect focus by limiting scope and confirming timing.",
        "monthly_theme_focus": "priority clarity, practical follow-through, and realistic pacing",
        "yearly_theme_focus": "durable habits, measured strategy, and long-range consistency",
        "monthly_event_impact": "These shifts change pacing and where attention needs to go.",
        "yearly_event_impact": "These pivots shape the long-form direction of your year.",
        "monthly_close": "By month-end, keep what is repeatable and drop what is noisy.",
        "yearly_close": "Across the year, consistent execution beats short bursts of intensity.",
        "checkin_prefix": "Quick check-in",
        "practical_prefix": "Practical note",
    },
    Section.LOVE_SINGLES: {
        "daily_hook": "Lead with standards first, chemistry second.",
        "weekly_hook": "Consistency and reciprocity matter more than fast momentum.",
        "monthly_theme_focus": "clear standards, emotional availability, and reciprocal effort",
        "yearly_theme_focus": "intentional attraction, better boundaries, and compatibility over hype",
        "monthly_event_impact": "These shifts reveal who can meet your standards in practice.",
        "yearly_event_impact": "These pivots reshape your dating filters and long-term fit.",
        "monthly_close": "By month-end, keep standards clear while staying open.",
        "yearly_close": "Across the year, favor reciprocity, clarity, and emotional consistency.",
        "checkin_prefix": "Dating check-in",
        "practical_prefix": "Dating note",
    },
    Section.LOVE_COUPLES: {
        "daily_hook": "Use small repair moments to protect trust and clarity.",
        "weekly_hook": "Partnership improves when honesty and listening stay active together.",
        "monthly_theme_focus": "repair quality, emotional safety, and shared pacing",
        "yearly_theme_focus": "partnership maturity, accountability, and stable intimacy",
        "monthly_event_impact": "These shifts highlight where your rhythm is aligned or drifting.",
        "yearly_event_impact": "These pivots shape your long-term partnership trajectory.",
        "monthly_close": "By month-end, prioritize conversations that reduce friction and rebuild trust.",
        "yearly_close": "Across the year, steady repair and shared accountability bring the strongest gains.",
        "checkin_prefix": "Partnership check-in",
        "practical_prefix": "Partnership note",
    },
    Section.CAREER: {
        "daily_hook": "Ship the work that creates measurable progress.",
        "weekly_hook": "Clear priorities and clean follow-through raise visibility.",
        "monthly_theme_focus": "execution quality, signal clarity, and disciplined leverage",
        "yearly_theme_focus": "positioning, leadership maturity, and sustainable output",
        "monthly_event_impact": "These shifts influence timing, visibility, and decision quality.",
        "yearly_event_impact": "These pivots shape your larger professional arc.",
        "monthly_close": "By month-end, keep work that compounds and cut low-value urgency.",
        "yearly_close": "Across the year, structured consistency beats reactive hustle.",
        "checkin_prefix": "Career check-in",
        "practical_prefix": "Career note",
    },
    Section.FRIENDSHIP: {
        "daily_hook": "Invest where care and effort are mutual.",
        "weekly_hook": "Healthy boundaries improve friendship quality.",
        "monthly_theme_focus": "reciprocity, trust clarity, and social alignment",
        "yearly_theme_focus": "durable community, clear boundaries, and meaningful support",
        "monthly_event_impact": "These shifts reveal who is aligned with your values.",
        "yearly_event_impact": "These pivots reshape your social ecosystem over time.",
        "monthly_close": "By month-end, keep reciprocal connections and release obligation-heavy loops.",
        "yearly_close": "Across the year, choose friendships built on trust and consistency.",
        "checkin_prefix": "Friendship check-in",
        "practical_prefix": "Social note",
    },
    Section.HEALTH: {
        "daily_hook": "Protect baseline energy before adding more load.",
        "weekly_hook": "Recovery and rhythm are core performance systems.",
        "monthly_theme_focus": "recovery quality, nervous-system steadiness, and sustainable habits",
        "yearly_theme_focus": "long-term vitality, recovery consistency, and intelligent pacing",
        "monthly_event_impact": "These shifts affect stress load, energy, and recovery windows.",
        "yearly_event_impact": "These pivots influence which habits remain sustainable.",
        "monthly_close": "By month-end, keep restoring habits and remove high-drain patterns.",
        "yearly_close": "Across the year, rhythm and recovery outperform intensity spikes.",
        "checkin_prefix": "Health check-in",
        "practical_prefix": "Health note",
    },
    Section.MONEY: {
        "daily_hook": "Use value and timing before impulse and urgency.",
        "weekly_hook": "Financial stability improves when decisions are explicit.",
        "monthly_theme_focus": "cashflow clarity, value alignment, and spending discipline",
        "yearly_theme_focus": "resource strategy, compounding gains, and risk-aware choices",
        "monthly_event_impact": "These shifts affect timing, spending behavior, and opportunity cost.",
        "yearly_event_impact": "These pivots shape long-term financial structure.",
        "monthly_close": "By month-end, tighten decisions around value, pricing, and boundaries.",
        "yearly_close": "Across the year, steady discipline beats emotional spending cycles.",
        "checkin_prefix": "Money check-in",
        "practical_prefix": "Money note",
    },
    Section.COMMUNICATION: {
        "daily_hook": "Use concise language and deliberate timing.",
        "weekly_hook": "Listening quality matters as much as message quality.",
        "monthly_theme_focus": "precision, timing, and active listening",
        "yearly_theme_focus": "message maturity, relational clarity, and steady credibility",
        "monthly_event_impact": "These shifts influence what lands clearly and what gets missed.",
        "yearly_event_impact": "These pivots shape voice, credibility, and influence over time.",
        "monthly_close": "By month-end, keep conversations that create clarity and close noisy loops.",
        "yearly_close": "Across the year, precise communication becomes a compounding edge.",
        "checkin_prefix": "Communication check-in",
        "practical_prefix": "Communication note",
    },
    Section.LIFESTYLE: {
        "daily_hook": "Structure the day around sustainability, not over-optimization.",
        "weekly_hook": "Simple repeatable routines outperform complex plans.",
        "monthly_theme_focus": "environment quality, repeatable routines, and sustainable pacing",
        "yearly_theme_focus": "lifestyle architecture, habit quality, and long-range stability",
        "monthly_event_impact": "These shifts show which routines support you and which drain you.",
        "yearly_event_impact": "These pivots shape the structure of daily life over time.",
        "monthly_close": "By month-end, keep routines that stabilize energy and remove noise.",
        "yearly_close": "Across the year, repeatable systems improve quality of life.",
        "checkin_prefix": "Lifestyle check-in",
        "practical_prefix": "Lifestyle note",
    },
}

INTRO_PATTERNS = {
    "daily": [
        "{day}: {sign} has {article} {intensity} signal around {area}. {hook}",
        "Daily brief for {sign} ({day}): expect {article} {intensity} tone in {area}. {hook}",
        "{sign} on {day}: {article} {intensity} cycle runs through {area}. {hook}",
        "{day} snapshot for {sign}: {area} carries {article} {intensity} signal. {hook}",
        "{sign} daily focus on {day}: {area} with {article} {intensity} pacing. {hook}",
    ],
    "weekly": [
        "Weekly brief for {sign}: strongest signal is in {area}. {hook}",
        "{sign}, this week is primarily about {area}. {hook}",
        "This week for {sign}: keep effort centered on {area}. {hook}",
        "{sign} weekly focus: {area} is the highest-leverage zone. {hook}",
        "For {sign}, weekly progress is tied to {area}. {hook}",
    ],
    "monthly": [
        "{month_year} monthly brief: {sign} shows {article} {intensity} signal in {area}.",
        "In {month_year}, {sign} is running {article} {intensity} cycle around {area}.",
        "{month_year} overview for {sign}: primary emphasis is {area} with {article} {intensity} tone.",
        "Monthly read for {sign} ({month_year}): {area} carries the strongest signal.",
        "{sign} in {month_year}: {area} remains the core focus under a {intensity} pattern.",
        "Across {month_year}, {sign} should treat {area} as the priority lane.",
    ],
    "yearly": [
        "{year} yearly brief: {sign} has sustained emphasis in {area}.",
        "For {sign} in {year}, long-range progress is tied to {area}.",
        "{year} sets a long-cycle priority for {sign}: {area}.",
        "{sign} yearly overview ({year}): {area} will define key outcomes.",
        "Across {year}, {sign} should treat {area} as strategic territory.",
        "{year} for {sign}: maintain long-horizon focus on {area}.",
    ],
}

THEME_PATTERNS = {
    "monthly": [
        "Monthly theme: {theme}. Best leverage comes through {focus}.",
        "Theme for this month is {theme}; progress depends on {focus}.",
        "This month runs on {theme}; keep attention on {focus}.",
    ],
    "yearly": [
        "Yearly theme: {theme}. Long-range strength comes from {focus}.",
        "Theme for this year is {theme}; keep decisions aligned with {focus}.",
        "This year tracks {theme}; durable progress depends on {focus}.",
    ],
}

EVENT_ANCHOR_OPTIONS = {
    "weekly": [
        ["Early this week", "Midweek", "By the weekend"],
        ["At the start of the week", "As the week develops", "Toward the weekend"],
        ["Opening the week", "Through midweek", "Closing the week"],
    ],
    "monthly": [
        ["Early in the month", "Around mid-month", "Toward month-end"],
        [
            "In the opening stretch",
            "Through the middle of the month",
            "In the closing stretch",
        ],
        ["At month start", "By the middle of the month", "Near month-end"],
    ],
    "yearly": [
        ["In the opening stretch", "By midyear", "In the later stretch"],
        ["Early in the year", "Around the midpoint", "In the final stretch"],
        ["At the start of the year", "Through midyear", "Late in the year"],
    ],
}

EVENT_IMPACT_LINES = [
    "{impact}",
    "{impact} Use this shift to adjust pace and priorities.",
    "{impact} Treat this as an execution signal, not background noise.",
]

INFLUENCE_CONNECTORS = [
    "At the same time,",
    "In parallel,",
    "Meanwhile,",
    "Also,",
]

SUPPORT_ACTION_OPENERS = [
    "{text}",
    "Practical next step: {text}",
    "Implementation note: {text}",
    "Execution move: {text}",
]

THESIS_TEMPLATES = {
    "monthly": [
        "Monthly signal is {felt_tone}; prioritize {to_state} over {from_state}.",
        "This month can drift toward {from_state}; better results come from {to_state}.",
        "Core monthly lesson: move from {from_state} toward {to_state}.",
    ],
    "yearly": [
        "Yearly signal is {felt_tone}; build {to_state} instead of {from_state}.",
        "This year rewards {to_state} and penalizes {from_state}.",
        "Across the year, choose {to_state} whenever {from_state} shows up.",
    ],
}

PERIOD_BREATH_LINES = {
    "monthly": [
        "Pause briefly before locking decisions.",
        "Let the month reveal pattern before forcing speed.",
        "Use a move-review-move cadence.",
    ],
    "yearly": [
        "Think in quarters, not in sprints.",
        "Repeated patterns matter more than short spikes.",
        "Patience is a strategic tool this year.",
    ],
}

SECTION_CONTRAST_STATES = {
    Section.GENERAL: ("reactive decisions", "intentional pacing"),
    Section.LOVE_SINGLES: ("intensity without fit", "reciprocity with clarity"),
    Section.LOVE_COUPLES: ("defensive loops", "repair with accountability"),
    Section.CAREER: ("busy output", "compounding work"),
    Section.FRIENDSHIP: ("obligation-driven ties", "reciprocal trust"),
    Section.HEALTH: ("overriding fatigue", "rhythm-based recovery"),
    Section.MONEY: ("impulse spending", "value-led decisions"),
    Section.COMMUNICATION: ("overexplaining", "precise and timed delivery"),
    Section.LIFESTYLE: ("chaotic urgency", "repeatable support systems"),
}

CONTRAST_TEMPLATES = [
    "This cycle may pull toward {from_state}, but rewards {to_state}.",
    "Default impulse is {from_state}; better outcomes come from {to_state}.",
    "Short-term motion can be {from_state}; durable progress is {to_state}.",
]

SECTION_CONTRAST_TEMPLATES = {
    Section.COMMUNICATION: [
        "The challenge is timing and framing, not lack of ideas.",
        "You likely need fewer words and clearer sequencing.",
        "Conversations improve when you stop defending and start clarifying.",
    ],
    Section.LIFESTYLE: [
        "The issue is system design more than discipline.",
        "Your environment is either restoring energy or draining it.",
        "A simple repeatable rhythm beats a strict complex routine.",
    ],
    Section.FRIENDSHIP: [
        "This cycle separates mutual connections from familiar ones.",
        "Long history alone is not a quality signal.",
        "Reciprocity matters more than obligation right now.",
    ],
    Section.MONEY: [
        "The key money lesson here is behavioral before numerical.",
        "Fast relief decisions can create expensive follow-up costs.",
        "Urgency is not always the same as value.",
    ],
}

LONGFORM_CADENCE_DEFAULT = [
    "intro",
    "focus",
    "thesis",
    "breath",
    "theme",
    "events",
    "influences",
    "contrast",
    "dynamic_close",
    "close",
]

LONGFORM_CADENCE_BY_PERIOD: Dict[Period, Dict[Section, List[str]]] = {
    Period.MONTHLY: {
        Section.GENERAL: [
            "intro",
            "thesis",
            "breath",
            "theme",
            "events",
            "influences",
            "contrast",
            "dynamic_close",
            "close",
        ],
        Section.LOVE_SINGLES: [
            "intro",
            "theme",
            "events",
            "thesis",
            "influences",
            "contrast",
            "dynamic_close",
            "close",
        ],
        Section.LOVE_COUPLES: [
            "intro",
            "thesis",
            "focus",
            "events",
            "theme",
            "influences",
            "dynamic_close",
            "contrast",
            "close",
        ],
        Section.CAREER: [
            "intro",
            "focus",
            "thesis",
            "breath",
            "theme",
            "influences",
            "events",
            "contrast",
            "dynamic_close",
            "close",
        ],
        Section.FRIENDSHIP: [
            "intro",
            "events",
            "thesis",
            "theme",
            "contrast",
            "influences",
            "dynamic_close",
            "close",
        ],
        Section.HEALTH: [
            "intro",
            "breath",
            "events",
            "thesis",
            "theme",
            "influences",
            "contrast",
            "dynamic_close",
            "close",
        ],
        Section.MONEY: [
            "intro",
            "thesis",
            "theme",
            "events",
            "contrast",
            "influences",
            "dynamic_close",
            "close",
        ],
        Section.COMMUNICATION: [
            "intro",
            "focus",
            "thesis",
            "events",
            "theme",
            "contrast",
            "influences",
            "dynamic_close",
            "close",
        ],
        Section.LIFESTYLE: [
            "intro",
            "breath",
            "theme",
            "events",
            "thesis",
            "influences",
            "contrast",
            "dynamic_close",
            "close",
        ],
    },
    Period.YEARLY: {
        Section.GENERAL: [
            "intro",
            "theme",
            "thesis",
            "breath",
            "events",
            "influences",
            "contrast",
            "dynamic_close",
            "close",
        ],
        Section.LOVE_SINGLES: [
            "intro",
            "theme",
            "thesis",
            "events",
            "contrast",
            "influences",
            "dynamic_close",
            "close",
        ],
        Section.LOVE_COUPLES: [
            "intro",
            "thesis",
            "theme",
            "events",
            "influences",
            "contrast",
            "dynamic_close",
            "close",
        ],
        Section.CAREER: [
            "intro",
            "focus",
            "theme",
            "thesis",
            "events",
            "influences",
            "dynamic_close",
            "contrast",
            "close",
        ],
        Section.FRIENDSHIP: [
            "intro",
            "theme",
            "events",
            "thesis",
            "contrast",
            "influences",
            "dynamic_close",
            "close",
        ],
        Section.HEALTH: [
            "intro",
            "breath",
            "theme",
            "events",
            "thesis",
            "influences",
            "dynamic_close",
            "contrast",
            "close",
        ],
        Section.MONEY: [
            "intro",
            "theme",
            "thesis",
            "events",
            "influences",
            "contrast",
            "dynamic_close",
            "close",
        ],
        Section.COMMUNICATION: [
            "intro",
            "focus",
            "thesis",
            "theme",
            "contrast",
            "events",
            "influences",
            "dynamic_close",
            "close",
        ],
        Section.LIFESTYLE: [
            "intro",
            "breath",
            "theme",
            "thesis",
            "events",
            "contrast",
            "influences",
            "dynamic_close",
            "close",
        ],
    },
}

LONGFORM_BRIDGE_BANKS: Dict[Section, List[str]] = {
    Section.GENERAL: [
        "That sets the baseline for what follows.",
        "Use that context to read the next signal clearly.",
        "From here, the next layer becomes more actionable.",
    ],
    Section.LOVE_SINGLES: [
        "That context makes dating choices easier to filter.",
        "From there, focus moves to signal quality and fit.",
        "With that in view, standards become easier to apply.",
    ],
    Section.LOVE_COUPLES: [
        "That sets up the next repair checkpoint.",
        "From here, the practical partnership layer becomes clearer.",
        "With that foundation, shared rhythm is easier to protect.",
    ],
    Section.CAREER: [
        "That frames the next execution decision.",
        "From there, convert signal into deliverable action.",
        "With that context, priority sequencing becomes clearer.",
    ],
    Section.FRIENDSHIP: [
        "That leads into the next social quality check.",
        "From here, reciprocity signals become more visible.",
        "With that context, boundary decisions get easier.",
    ],
    Section.HEALTH: [
        "That sets up the next recovery decision.",
        "From here, pacing and load management matter most.",
        "With that baseline, habit choices become clearer.",
    ],
    Section.MONEY: [
        "That frames the next financial trade-off.",
        "From here, value and timing should guide the move.",
        "With that context, downside control gets clearer.",
    ],
    Section.COMMUNICATION: [
        "That sets up the next message decision.",
        "From here, timing and phrasing matter more than volume.",
        "With that in place, clarity lands faster.",
    ],
    Section.LIFESTYLE: [
        "That leads into the next routine adjustment.",
        "From here, keep what is repeatable and reduce drag.",
        "With that context, system choices get simpler.",
    ],
}

LONGFORM_BRIDGE_TOKENS = {"theme", "events", "influences", "contrast", "dynamic_close"}

SECTION_HOUSE_PHRASES: Dict[Section, Dict[str, str]] = {
    Section.COMMUNICATION: {
        "third_house": "speech timing, response habits, and day-to-day signal quality",
        "ninth_house": "belief language, teaching tone, and larger-truth conversations",
        "eleventh_house": "group dynamics, public messaging, and network-level interpretation",
    },
    Section.LIFESTYLE: {
        "first_house": "energy baseline, body rhythm, and how you carry the day",
        "fourth_house": "home atmosphere, emotional decompression, and private stability",
        "sixth_house": "maintenance habits, friction points, and repeatable daily supports",
        "twelfth_house": "recovery windows, solitude, and the quiet leaks draining your pace",
    },
    Section.FRIENDSHIP: {
        "third_house": "casual social flow, familiar voices, and local belonging",
        "seventh_house": "one-to-one reciprocity, direct honesty, and relational accountability",
        "eleventh_house": "community fit, trusted circles, and long-range social belonging",
    },
    Section.MONEY: {
        "second_house": "cashflow stewardship, pricing confidence, and grounded self-worth",
        "eighth_house": "shared obligations, trust economics, and boundary clarity around resources",
        "tenth_house": "earnings visibility through reputation, positioning, and delivery quality",
        "eleventh_house": "network-linked opportunities, future gains, and alliance quality",
    },
}

SECTION_FELT_TONES: Dict[Section, Dict[str, object]] = {
    Section.GENERAL: {
        "transits": {
            "square_tension": ["productive friction around priorities"],
            "opposition_conflict": ["negotiation between competing truths"],
            "retrograde_review": ["revision pressure and strategic slowdown"],
            "trine_harmony": ["usable momentum with fewer blockers"],
            "sextile_opportunity": ["open doors that reward initiative"],
            "action_activation": ["decisive energy asking for follow-through"],
            "decision_point": ["threshold energy that demands commitment"],
        },
        "aspects": {
            "square": ["friction that exposes what is unsustainable"],
            "opposition": ["polarity that demands balance"],
            "trine": ["supportive flow that can be leveraged"],
            "sextile": ["collaborative momentum with clear openings"],
            "conjunction": ["compressed intensity around one central theme"],
            "quincunx": ["adjustment pressure that refines your approach"],
        },
        "retrograde": ["review cycles that reward edits over urgency"],
        "default": ["a reset in pacing and priorities"],
    },
    Section.COMMUNICATION: {
        "transits": {
            "square_tension": [
                "conversational pressure where timing matters more than volume",
                "message friction that rewards restraint and clean sequencing",
            ],
            "opposition_conflict": [
                "a split between being understood and being agreed with",
                "competing viewpoints that need framing, not force",
            ],
            "retrograde_review": [
                "revision energy that exposes mixed signals and old wording loops",
            ],
        },
        "aspects": {
            "square": ["verbal friction that reveals what is still unspoken"],
            "opposition": ["relational polarity that asks for cleaner listening"],
        },
        "house": {
            "third_house": [
                "a local signal-versus-noise cycle in day-to-day exchanges"
            ],
            "ninth_house": ["pressure to align words with deeper beliefs"],
            "eleventh_house": ["group-message dynamics where tone shifts by audience"],
        },
        "retrograde": [
            "review pressure around wording, timing, and conversational repair"
        ],
        "default": [
            "a communication cycle where tone, timing, and clarity must work together"
        ],
    },
    Section.LIFESTYLE: {
        "transits": {
            "square_tension": [
                "friction between pace demands and nervous-system limits"
            ],
            "retrograde_review": [
                "a reset cycle around what your routines actually support"
            ],
        },
        "house": {
            "fourth_house": [
                "home atmosphere becoming the deciding factor in overall steadiness"
            ],
            "sixth_house": ["maintenance pressure to simplify what is hard to sustain"],
            "twelfth_house": [
                "quiet depletion signaling the need for real recovery space"
            ],
        },
        "retrograde": [
            "review energy around habits that look productive but feel draining"
        ],
        "default": [
            "a lifestyle recalibration about reducing drag and restoring breathable rhythm"
        ],
    },
    Section.FRIENDSHIP: {
        "transits": {
            "opposition_conflict": [
                "social polarity separating familiarity from real trust"
            ],
            "retrograde_review": [
                "a friendship review cycle around reciprocity and loyalty"
            ],
            "networking_energy": [
                "network momentum that tests who feels supportive versus performative"
            ],
        },
        "house": {
            "third_house": [
                "local social flow revealing who feels easy to stay in touch with"
            ],
            "seventh_house": [
                "one-to-one accountability in how friendship is practiced"
            ],
            "eleventh_house": [
                "community sorting around belonging, trust, and future fit"
            ],
        },
        "retrograde": [
            "review pressure around one-sided effort and convenient loyalty"
        ],
        "default": [
            "a social quality check where emotional safety matters more than social volume"
        ],
    },
    Section.MONEY: {
        "transits": {
            "financial_focus": [
                "a money-behavior cycle where impulse and conviction diverge"
            ],
            "square_tension": [
                "scarcity pressure that rewards cleaner boundaries, not faster spending"
            ],
            "retrograde_review": [
                "financial review energy around leak points and delayed payoff"
            ],
        },
        "house": {
            "second_house": [
                "a value-and-stewardship cycle around what you earn, keep, and trust"
            ],
            "eighth_house": [
                "shared-resource pressure around debt, trust, and obligation"
            ],
            "tenth_house": [
                "income visibility linked to positioning and delivery standards"
            ],
            "eleventh_house": [
                "future-gains questions tied to alliance quality and network fit"
            ],
        },
        "retrograde": ["review pressure around relief spending and false urgency"],
        "default": [
            "a financial psychology cycle where behavior matters more than theory"
        ],
    },
    Section.LOVE_SINGLES: {
        "transits": {
            "relationship_tension": [
                "dating pressure around standards and emotional availability"
            ],
            "retrograde_review": [
                "a relationship review cycle that filters mixed signals"
            ],
            "action_activation": [
                "active attraction energy that needs grounded choices"
            ],
        },
        "house": {
            "fifth_house": ["romantic momentum that favors play with discernment"],
            "seventh_house": ["partnership-readiness pressure around reciprocity"],
            "ninth_house": ["attraction shaped by shared worldview and long-range fit"],
        },
        "retrograde": ["review pressure around repeating old attraction patterns"],
        "default": [
            "a dating cycle focused on fit, reciprocity, and emotional clarity"
        ],
    },
    Section.LOVE_COUPLES: {
        "transits": {
            "opposition_conflict": [
                "partnership polarity that needs cleaner negotiation"
            ],
            "retrograde_review": [
                "repair pressure around recurring relationship loops"
            ],
            "emotional_flow": ["heightened emotional responsiveness in shared rhythms"],
        },
        "house": {
            "fourth_house": ["home and emotional-safety dynamics becoming central"],
            "seventh_house": [
                "agreement quality and relational accountability in focus"
            ],
            "eighth_house": ["deeper trust and vulnerability work asking for honesty"],
        },
        "retrograde": ["review pressure around unresolved partnership patterns"],
        "default": [
            "a partnership cycle centered on trust repair and clearer agreements"
        ],
    },
    Section.CAREER: {
        "transits": {
            "action_activation": [
                "high execution pressure that rewards clear deliverables"
            ],
            "discipline_restriction": [
                "structural pressure asking for tighter systems"
            ],
            "square_tension": ["workload friction that demands sharper priorities"],
        },
        "house": {
            "sixth_house": [
                "workflow discipline and operational consistency taking priority"
            ],
            "tenth_house": ["public positioning and leadership pressure intensifying"],
            "eleventh_house": ["network leverage and collaborative strategy in focus"],
        },
        "retrograde": ["review pressure around process debt and unfinished loops"],
        "default": [
            "a career cycle focused on output quality and strategic sequencing"
        ],
    },
    Section.HEALTH: {
        "transits": {
            "health_awareness": ["body-feedback pressure requiring smarter pacing"],
            "retrograde_review": ["recovery review cycle around energy leaks"],
            "discipline_restriction": ["habit pressure that rewards consistent basics"],
        },
        "house": {
            "first_house": [
                "baseline vitality and embodiment needing direct attention"
            ],
            "sixth_house": ["daily maintenance habits becoming non-negotiable"],
            "twelfth_house": ["deep recovery and rest quality signaling priority"],
        },
        "retrograde": ["review pressure around routines that quietly drain energy"],
        "default": ["a health cycle centered on recovery rhythm and sustainable load"],
    },
}

SUPPORT_TAILS = {
    Section.GENERAL: {
        "question": [
            "Use the answer to decide your next move.",
            "Treat that answer as your timing signal.",
        ],
        "action": [
            "Keep the step specific and measurable.",
            "Small consistent execution compounds fast.",
        ],
        "reflect": [
            "That perspective improves decision quality.",
            "This reduces noise and keeps progress clean.",
        ],
    },
    Section.LOVE_SINGLES: {
        "question": [
            "Use the answer to filter genuine alignment.",
            "That clarity protects your standards in practice.",
        ],
        "action": [
            "Choose clear signals over fast chemistry.",
            "Let standards define the pace.",
        ],
        "reflect": [
            "This keeps attraction aligned with self-respect.",
            "That stance improves long-term match quality.",
        ],
    },
    Section.LOVE_COUPLES: {
        "question": [
            "Use the answer for repair, not blame.",
            "Let that answer improve your shared rhythm.",
        ],
        "action": [
            "Keep tone calm and expectations explicit.",
            "Small repair moves create outsized trust.",
        ],
        "reflect": [
            "This supports trust in daily interactions.",
            "That emphasis strengthens emotional safety.",
        ],
    },
    Section.CAREER: {
        "question": [
            "Use the answer to sharpen execution.",
            "Use that clarity to tighten scope.",
        ],
        "action": [
            "Tie this to one measurable output.",
            "Keep the move scoped and deliverable.",
        ],
        "reflect": [
            "That framing improves strategic timing.",
            "This keeps output compounding over time.",
        ],
    },
    Section.FRIENDSHIP: {
        "question": [
            "Use the answer to spot real reciprocity.",
            "Let that answer reset social boundaries.",
        ],
        "action": [
            "Invest where loyalty is mutual.",
            "Choose connection quality over social volume.",
        ],
        "reflect": [
            "That perspective protects social energy.",
            "This keeps your circle aligned with values.",
        ],
    },
    Section.HEALTH: {
        "question": [
            "Use the answer to shape recovery planning.",
            "Let that answer protect baseline energy.",
        ],
        "action": [
            "Keep it sustainable before scaling.",
            "Favor rhythm over intensity spikes.",
        ],
        "reflect": [
            "This supports steadier energy management.",
            "That shift improves recovery quality.",
        ],
    },
    Section.MONEY: {
        "question": [
            "Use the answer to tighten value decisions.",
            "Let that clarity guide your next money move.",
        ],
        "action": [
            "Anchor the move to value, not impulse.",
            "Make risk visible before committing.",
        ],
        "reflect": [
            "That perspective strengthens financial discipline.",
            "This helps protect long-term stability.",
        ],
    },
    Section.COMMUNICATION: {
        "question": [
            "Use the answer to refine the message.",
            "Let that answer improve timing decisions.",
        ],
        "action": [
            "Prioritize precision over speed.",
            "Keep the message concise and direct.",
        ],
        "reflect": [
            "That framing improves message landing.",
            "This supports clarity without overexplaining.",
        ],
    },
    Section.LIFESTYLE: {
        "question": [
            "Use the answer to shape daily structure.",
            "Let that answer remove low-value noise.",
        ],
        "action": [
            "Choose routines you can repeat reliably.",
            "Keep the system simple and sustainable.",
        ],
        "reflect": [
            "That emphasis supports a cleaner pace.",
            "This helps habits stay durable.",
        ],
    },
}

DAILY_FACTOR_ORDER = [
    "sun_in_sign",
    "moon_in_sign",
    "rising_sign",
    "transits_archetypes",
    "aspects",
    "daily_house_focus",
]

WEEKLY_FACTOR_ORDER = [
    "sun_in_sign",
    "moon_in_sign",
    "weekly_moon_phase",
    "transits_archetypes",
    "aspects",
    "planetary_focus",
    "retrograde_archetypes",
    "ingress_archetypes",
    "weekly_theme_archetypes",
    "weekly_house_focus",
]

MONTHLY_FACTOR_ORDER = [
    "sun_in_sign",
    "monthly_lunation_archetypes",
    "transits_archetypes",
    "aspects",
    "planetary_focus",
    "retrograde_archetypes",
    "ingress_archetypes",
    "eclipse_archetypes",
    "outer_planet_focus",
    "monthly_theme_archetypes",
    "monthly_house_focus",
]

YEARLY_FACTOR_ORDER = [
    "jupiter_in_sign",
    "saturn_in_sign",
    "chiron_in_sign",
    "transits_archetypes",
    "aspects",
    "planetary_focus",
    "retrograde_archetypes",
    "ingress_archetypes",
    "eclipse_archetypes",
    "outer_planet_focus",
    "nodal_axis",
    "yearly_house_focus",
    "yearly_theme_archetypes",
]

PERIOD_FACTOR_WEIGHTS = {
    Period.DAILY: {
        "sun_in_sign": 1.00,
        "moon_in_sign": 1.15,
        "rising_sign": 1.00,
        "transits_archetypes": 1.30,
        "aspects": 1.20,
        "daily_house_focus": 1.08,
    },
    Period.WEEKLY: {
        "sun_in_sign": 0.90,
        "moon_in_sign": 0.95,
        "weekly_moon_phase": 1.05,
        "transits_archetypes": 1.25,
        "aspects": 1.15,
        "planetary_focus": 1.10,
        "retrograde_archetypes": 1.15,
        "ingress_archetypes": 1.05,
        "weekly_theme_archetypes": 1.20,
        "weekly_house_focus": 1.08,
    },
    Period.MONTHLY: {
        "sun_in_sign": 0.85,
        "monthly_lunation_archetypes": 1.20,
        "transits_archetypes": 1.20,
        "aspects": 1.10,
        "planetary_focus": 1.15,
        "retrograde_archetypes": 1.15,
        "ingress_archetypes": 1.05,
        "eclipse_archetypes": 1.20,
        "outer_planet_focus": 1.10,
        "monthly_theme_archetypes": 1.25,
        "monthly_house_focus": 1.15,
    },
    Period.YEARLY: {
        "jupiter_in_sign": 1.10,
        "saturn_in_sign": 1.10,
        "chiron_in_sign": 1.00,
        "transits_archetypes": 1.10,
        "aspects": 1.00,
        "planetary_focus": 1.20,
        "retrograde_archetypes": 1.10,
        "ingress_archetypes": 1.00,
        "eclipse_archetypes": 1.20,
        "outer_planet_focus": 1.15,
        "nodal_axis": 1.15,
        "yearly_house_focus": 1.20,
        "yearly_theme_archetypes": 1.30,
    },
}

ZODIAC_SIGNS = [
    "ARIES",
    "TAURUS",
    "GEMINI",
    "CANCER",
    "LEO",
    "VIRGO",
    "LIBRA",
    "SCORPIO",
    "SAGITTARIUS",
    "CAPRICORN",
    "AQUARIUS",
    "PISCES",
]

BODY_HOUSE_WEIGHTS_BY_PERIOD = {
    Period.DAILY: {
        "Sun": 1.1,
        "Moon": 1.35,
        "Mercury": 1.1,
        "Venus": 1.1,
        "Mars": 1.15,
        "Jupiter": 1.0,
        "Saturn": 1.0,
        "Uranus": 0.8,
        "Neptune": 0.8,
        "Pluto": 0.8,
        "Chiron": 0.95,
        "North Node": 1.0,
        "South Node": 0.9,
    },
    Period.WEEKLY: {
        "Sun": 1.2,
        "Moon": 1.3,
        "Mercury": 1.15,
        "Venus": 1.15,
        "Mars": 1.2,
        "Jupiter": 1.35,
        "Saturn": 1.35,
        "Uranus": 1.0,
        "Neptune": 1.0,
        "Pluto": 1.0,
        "Chiron": 1.1,
        "North Node": 1.2,
        "South Node": 1.1,
    },
    Period.MONTHLY: {
        "Sun": 1.1,
        "Moon": 0.9,
        "Mercury": 1.05,
        "Venus": 1.05,
        "Mars": 1.1,
        "Jupiter": 1.5,
        "Saturn": 1.5,
        "Uranus": 1.25,
        "Neptune": 1.25,
        "Pluto": 1.25,
        "Chiron": 1.3,
        "North Node": 1.45,
        "South Node": 1.35,
    },
    Period.YEARLY: {
        "Sun": 0.8,
        "Moon": 0.65,
        "Mercury": 0.8,
        "Venus": 0.8,
        "Mars": 0.9,
        "Jupiter": 1.9,
        "Saturn": 1.9,
        "Uranus": 1.45,
        "Neptune": 1.45,
        "Pluto": 1.45,
        "Chiron": 1.5,
        "North Node": 1.7,
        "South Node": 1.6,
    },
}

EVENT_HOUSE_WEIGHTS = {
    "ingress": 1.15,
    "station": 1.4,
    "lunation": 1.6,
    "eclipse": 2.0,
    "exact_aspect": 1.2,
    "retrograde_emphasis": 0.95,
}

SECTION_HOUSE_BIAS = {
    Section.GENERAL: {1, 10, 11, 4, 9},
    Section.LOVE_SINGLES: {5, 7, 11},
    Section.LOVE_COUPLES: {4, 7, 8, 12},
    Section.CAREER: {2, 6, 10, 11},
    Section.FRIENDSHIP: {3, 11, 7},
    Section.HEALTH: {1, 6, 12},
    Section.MONEY: {2, 8, 10, 11},
    Section.COMMUNICATION: {3, 9, 11},
    Section.LIFESTYLE: {1, 4, 6, 12},
}

RETROGRADE_WEEKLY = {
    "Mercury": "mercury_retrograde",
    "Venus": "venus_retrograde",
    "Mars": "mars_retrograde",
    "Jupiter": "jupiter_retrograde",
    "Saturn": "saturn_retrograde",
}

RETROGRADE_MONTHLY = {
    "Mercury": "mercury_retrograde",
    "Venus": "venus_retrograde",
    "Mars": "mars_retrograde",
    "Jupiter": "jupiter_retrograde",
    "Saturn": "saturn_retrograde",
    "Uranus": "uranus_retrograde",
    "Neptune": "neptune_retrograde",
    "Pluto": "pluto_retrograde",
}

RETROGRADE_YEARLY = {
    "Mercury": "communication_review",
    "Venus": "relationship_reassessment",
    "Mars": "drive_recalibration",
    "Jupiter": "expansion_revision",
    "Saturn": "discipline_rebuild",
    "Uranus": "deep_reorientation",
    "Neptune": "deep_reorientation",
    "Pluto": "deep_reorientation",
}

NODAL_AXIS_BY_SIGNS = {
    frozenset(("ARIES", "LIBRA")): "aries_libra",
    frozenset(("TAURUS", "SCORPIO")): "taurus_scorpio",
    frozenset(("GEMINI", "SAGITTARIUS")): "gemini_sagittarius",
    frozenset(("CANCER", "CAPRICORN")): "cancer_capricorn",
    frozenset(("LEO", "AQUARIUS")): "leo_aquarius",
    frozenset(("VIRGO", "PISCES")): "virgo_pisces",
}

TIP_KEYS = ["daily_tip", "weekly_tip", "monthly_tip", "yearly_tip"]


@dataclass(frozen=True)
class FactorSpec:
    factor_type: str
    factor_value: str
    weight: float


class InterpretationEngine:
    def __init__(
        self,
        rules: RuleSet,
        content_repository: Optional[V2ContentRepository] = None,
        strict_content_mode: bool = False,
    ):
        self.rules = rules
        self.content_repository = content_repository
        self.strict_content_mode = strict_content_mode
        self._variation_cycle_seed = ""

    def calculate_period_factor_map(
        self,
        sign: str,
        snapshot: ChartSnapshot,
        period: Period,
        metrics: PeriodMetrics | None,
        period_events: Optional[Sequence[PeriodEvent]] = None,
        factor_type_allowlist: Optional[Sequence[str]] = None,
        focus_body: Optional[str] = None,
    ) -> Dict[str, str]:
        specs = self._factor_specs(
            period,
            sign,
            Section.GENERAL,
            snapshot,
            metrics,
            period_events=period_events,
            factor_type_allowlist=factor_type_allowlist,
            focus_body=focus_body,
        )
        return {spec.factor_type: spec.factor_value for spec in specs}

    def build_section_insights(
        self,
        sign: str,
        snapshot: ChartSnapshot,
        sections: List[Section],
        period: Period,
        metrics: PeriodMetrics | None,
        notable_events: List[str],
        period_events: Optional[Sequence[PeriodEvent]] = None,
        factor_type_allowlist: Optional[Sequence[str]] = None,
        focus_body: Optional[str] = None,
    ) -> List[SectionInsight]:
        results: List[SectionInsight] = []
        events = list(period_events or [])
        cadence_state: Dict[str, str] = {}
        for section in sections:
            weights = self._weights_for_section(section)
            scores = self._score_section(
                weights=weights,
                snapshot=snapshot,
                metrics=metrics,
                period=period,
                section=section,
                period_events=events,
            )
            intensity = self._intensity(scores)
            title = self._title(section, sign, period, intensity)

            rendered = self._render_lite_insights(
                section=section,
                sign=sign,
                snapshot=snapshot,
                period=period,
                metrics=metrics,
                intensity=intensity,
                notable_events=notable_events,
                period_events=events,
                cadence_state=cadence_state,
                factor_type_allowlist=factor_type_allowlist,
                focus_body=focus_body,
            )
            summary, highlights, cautions, actions, factor_details = rendered

            results.append(
                SectionInsight(
                    section=section,
                    title=title,
                    summary=summary,
                    highlights=highlights,
                    cautions=cautions,
                    actions=actions,
                    scores=scores,
                    intensity=intensity,
                    factor_details=factor_details,
                )
            )
        return results

    def _render_lite_insights(
        self,
        section: Section,
        sign: str,
        snapshot: ChartSnapshot,
        period: Period,
        metrics: PeriodMetrics | None,
        intensity: str,
        notable_events: List[str],
        period_events: Optional[Sequence[PeriodEvent]] = None,
        cadence_state: Optional[Dict[str, str]] = None,
        factor_type_allowlist: Optional[Sequence[str]] = None,
        focus_body: Optional[str] = None,
    ) -> Tuple[str, List[str], List[str], List[str], List[FactorDetail]]:
        factor_specs = self._factor_specs(
            period=period,
            sign=sign,
            section=section,
            snapshot=snapshot,
            metrics=metrics,
            period_events=period_events,
            factor_type_allowlist=factor_type_allowlist,
            focus_body=focus_body,
        )
        if not factor_specs:
            summary, highlights, cautions, actions = self._render_fallback(
                section=section,
                sign=sign,
                snapshot=snapshot,
                period=period,
                scores={},
                notable_events=notable_events,
                intensity=intensity,
            )
            return summary, highlights, cautions, actions, []

        factor_details = [
            self._build_lite_factor_detail(
                section=section,
                period=period,
                spec=spec,
            )
            for spec in factor_specs
        ]

        seed = f"lite|{period.value}|{sign}|{section.value}|{snapshot.timestamp.date().isoformat()}|{intensity}"
        previous_seed = self._variation_cycle_seed
        self._variation_cycle_seed = seed
        try:
            summary = self._compose_summary(
                period=period,
                sign=sign,
                section=section,
                intensity=intensity,
                factor_details=factor_details,
                notable_events=notable_events,
                period_events=period_events,
                timestamp=snapshot.timestamp,
                cadence_state=cadence_state,
                focus_body=focus_body,
            )
            highlights = self._compose_highlights(
                period=period,
                section=section,
                factor_details=factor_details,
                notable_events=notable_events,
                period_events=period_events,
                limit=4,
            )

            caution_weighted = [
                (
                    detail.weight,
                    detail.factor_insights.get("caution", ""),
                    detail.factor_type,
                    detail.factor_value,
                )
                for detail in factor_details
                if detail.factor_insights.get("caution")
            ]
            tip_key = self._tip_key_for_period(period)
            action_weighted = [
                (
                    detail.weight,
                    detail.factor_insights.get(tip_key)
                    or detail.factor_insights.get("affirmation", ""),
                    detail.factor_type,
                    detail.factor_value,
                )
                for detail in factor_details
                if detail.factor_insights.get(tip_key)
                or detail.factor_insights.get("affirmation")
            ]
            cautions_raw = self._pick_top_weighted(caution_weighted, limit=6)
            actions_raw = self._pick_top_weighted(action_weighted, limit=6)

            cautions = self._editorialize_list_lines(
                lines=cautions_raw,
                section=section,
                kind="caution",
                narrative_seed=f"{seed}|cautions",
                limit=4,
            )
            actions = self._editorialize_list_lines(
                lines=actions_raw,
                section=section,
                kind="action",
                narrative_seed=f"{seed}|actions",
                limit=4,
            )
        finally:
            self._variation_cycle_seed = previous_seed

        if not highlights:
            highlights = ["Focus on grounded progress this cycle."]
        if not cautions:
            cautions = ["Avoid overextending your energy before priorities are clear."]
        if not actions:
            actions = ["Take one concrete step that matches your current priorities."]
        return summary, highlights[:4], cautions[:4], actions[:4], factor_details

    def _build_lite_factor_detail(
        self,
        section: Section,
        period: Period,
        spec: FactorSpec,
    ) -> FactorDetail:
        tip_key = self._tip_key_for_period(period)
        meaning = self._lite_meaning_line(spec.factor_type, spec.factor_value, section)
        reflection = self._lite_reflection_line(
            spec.factor_type, spec.factor_value, section
        )
        caution = self._lite_caution_line(spec.factor_type, spec.factor_value, section)
        action = self._lite_action_line(spec.factor_type, spec.factor_value, section)
        affirmation = "Consistency compounds better than urgency in this cycle."
        return FactorDetail(
            factor_type=spec.factor_type,
            factor_value=spec.factor_value,
            weight=spec.weight,
            factor_insights={
                "lite_meaning": meaning,
                "motivation": meaning,
                "reflection": reflection,
                "caution": caution,
                tip_key: action,
                "affirmation": affirmation,
            },
        )

    def _tip_key_for_period(self, period: Period) -> str:
        return {
            Period.DAILY: "daily_tip",
            Period.WEEKLY: "weekly_tip",
            Period.MONTHLY: "monthly_tip",
            Period.YEARLY: "yearly_tip",
        }[period]

    def _lite_meaning_line(
        self, factor_type: str, factor_value: str, section: Section
    ) -> str:
        readable = self._readable_factor_value(factor_value)
        if factor_type == "sun_in_sign":
            return self._ensure_terminal(
                f"Sun in {factor_value.title()} sets the baseline tone for this cycle"
            )
        if factor_type == "moon_in_sign":
            return self._ensure_terminal(
                f"Moon in {factor_value.title()} shapes emotional timing and response"
            )
        if factor_type == "rising_sign":
            return self._ensure_terminal(
                f"Rising-sign emphasis in {factor_value.title()} affects presentation and pacing"
            )
        if factor_type in (
            "daily_house_focus",
            "weekly_house_focus",
            "monthly_house_focus",
            "yearly_house_focus",
        ):
            focus = self._house_focus_line(factor_value, section=section)
            return self._ensure_terminal(f"House activation highlights {focus}")
        if factor_type == "planetary_focus" and factor_value.endswith("_focus"):
            planet = factor_value.replace("_focus", "").replace("_", " ").title()
            return self._ensure_terminal(
                f"{planet} is foregrounded, so its themes have stronger consequence"
            )
        if factor_type == "retrograde_archetypes":
            return self._ensure_terminal(
                f"{readable.capitalize()} favors review, edits, and better timing"
            )
        if factor_type == "eclipse_archetypes":
            return self._ensure_terminal(
                f"{readable.capitalize()} raises consequence, so clear choices matter more"
            )
        if factor_type == "aspects":
            return self._ensure_terminal(
                f"Aspect climate is centered on {readable}, shaping pressure and flow"
            )
        return self._ensure_terminal(
            f"{factor_type.replace('_', ' ').title()} is currently {readable}"
        )

    def _lite_reflection_line(
        self, factor_type: str, factor_value: str, section: Section
    ) -> str:
        focus = self._section_focus(section)
        if factor_type in (
            "monthly_theme_archetypes",
            "yearly_theme_archetypes",
            "weekly_theme_archetypes",
        ):
            return self._ensure_terminal(
                f"Use this theme to keep {focus} intentional and measurable"
            )
        if factor_type in (
            "daily_house_focus",
            "weekly_house_focus",
            "monthly_house_focus",
            "yearly_house_focus",
        ):
            return self._ensure_terminal(
                "Concentrate effort where the house signal is strongest"
            )
        section_reflections = {
            Section.GENERAL: "Keep decisions aligned with priority, not noise.",
            Section.LOVE_SINGLES: "Let standards and reciprocity guide attraction choices.",
            Section.LOVE_COUPLES: "Use this pattern to improve trust and shared rhythm.",
            Section.CAREER: "Translate this signal into scoped, measurable execution.",
            Section.FRIENDSHIP: "Invest where reciprocity and reliability are visible.",
            Section.HEALTH: "Prioritize recovery rhythm before adding extra load.",
            Section.MONEY: "Anchor money moves in value, timing, and downside awareness.",
            Section.COMMUNICATION: "Keep the message concise, timed, and listener-aware.",
            Section.LIFESTYLE: "Support energy with simpler, repeatable daily systems.",
        }
        return self._ensure_terminal(
            section_reflections.get(section, f"Keep {focus} aligned with this pattern")
        )

    def _lite_caution_line(
        self, factor_type: str, factor_value: str, section: Section
    ) -> str:
        if factor_type == "aspects" and factor_value in (
            "square",
            "opposition",
            "quincunx",
        ):
            return "Avoid forcing timing while friction is still clarifying priorities."
        if (
            factor_type == "retrograde_archetypes"
            and factor_value != "no_major_retrograde"
        ):
            return "Avoid locking irreversible decisions before review is complete."
        if factor_type == "eclipse_archetypes" and factor_value in (
            "solar_eclipse",
            "lunar_eclipse",
            "eclipse_window",
            "nodal_activation",
        ):
            return "Avoid all-or-nothing moves under high eclipse pressure."
        if factor_type in (
            "daily_house_focus",
            "weekly_house_focus",
            "monthly_house_focus",
            "yearly_house_focus",
        ):
            return "Avoid scattering your effort across too many life areas."
        section_cautions = {
            Section.GENERAL: "Avoid overextending before priorities are clear.",
            Section.LOVE_SINGLES: "Avoid ignoring red flags just to keep momentum.",
            Section.LOVE_COUPLES: "Avoid defensive tone when repair is possible.",
            Section.CAREER: "Avoid confusing urgency with priority.",
            Section.FRIENDSHIP: "Avoid one-sided social effort loops.",
            Section.HEALTH: "Avoid trading recovery for short-term output.",
            Section.MONEY: "Avoid impulse spending under emotional pressure.",
            Section.COMMUNICATION: "Avoid overexplaining when one clear message is enough.",
            Section.LIFESTYLE: "Avoid adding complexity to already overloaded routines.",
        }
        return section_cautions.get(
            section, "Avoid overextending before priorities are clear."
        )

    def _lite_action_line(
        self, factor_type: str, factor_value: str, section: Section
    ) -> str:
        focus = self._section_focus(section)
        if factor_type == "planetary_focus" and factor_value.endswith("_focus"):
            planet = factor_value.replace("_focus", "").replace("_", " ").title()
            return f"Use {planet} themes to choose one measurable next step in {focus}."
        if factor_type in (
            "daily_house_focus",
            "weekly_house_focus",
            "monthly_house_focus",
            "yearly_house_focus",
        ):
            house_focus = self._house_focus_line(factor_value, section=section)
            return f"Focus your next move on {house_focus}."
        if factor_type in (
            "monthly_theme_archetypes",
            "yearly_theme_archetypes",
            "weekly_theme_archetypes",
        ):
            readable = self._readable_factor_value(factor_value)
            return f"Set one concrete goal that matches the {readable} theme."
        if (
            factor_type == "retrograde_archetypes"
            and factor_value != "no_major_retrograde"
        ):
            return "Review existing commitments before launching something new."
        section_actions = {
            Section.GENERAL: f"Take one practical step that supports {focus}.",
            Section.LOVE_SINGLES: "Send one clear signal that matches your standards.",
            Section.LOVE_COUPLES: "Schedule one short check-in focused on repair and alignment.",
            Section.CAREER: "Ship one scoped task that moves a key priority forward.",
            Section.FRIENDSHIP: "Reach out to one reciprocal connection and deepen the thread.",
            Section.HEALTH: "Protect one recovery block on your calendar today.",
            Section.MONEY: "Review one spending decision against value and timing.",
            Section.COMMUNICATION: "Draft the core message in one clear sentence first.",
            Section.LIFESTYLE: "Remove one low-value routine and reinforce one useful one.",
        }
        return section_actions.get(
            section, f"Take one practical step that supports {focus}."
        )

    def _weights_for_section(self, section: Section) -> Dict[str, float]:
        weights = self.rules.section_weights.get(section.value)
        if weights is not None:
            return weights
        if section in (Section.LOVE_SINGLES, Section.LOVE_COUPLES):
            return self.rules.section_weights.get("love", {})
        return {}

    def _score_section(
        self,
        weights: Dict[str, float],
        snapshot: ChartSnapshot,
        metrics: PeriodMetrics | None,
        period: Period,
        section: Section,
        period_events: Sequence[PeriodEvent],
    ) -> Dict[str, float]:
        base = {
            "momentum": 50.0,
            "clarity": 50.0,
            "opportunity": 50.0,
            "focus": 50.0,
            "stability": 50.0,
            "connection": 50.0,
        }

        for position in snapshot.positions:
            weight = weights.get(position.name)
            if not weight:
                continue
            base["momentum"] += weight * (6 if not position.retrograde else -4)
            base["clarity"] += weight * (4 if position.speed >= 0 else -3)
            base["opportunity"] += weight * 5
            base["focus"] += weight * (4 if position.name in ("Saturn", "Vesta") else 2)
            base["connection"] += weight * (
                3 if position.name in ("Venus", "Moon", "Juno") else 1
            )

        for aspect in snapshot.aspects:
            if aspect.aspect in ("square", "opposition"):
                base["focus"] += 1.5
                base["clarity"] -= 1.5
                base["stability"] -= 1.0
            elif aspect.aspect in ("trine", "sextile"):
                base["opportunity"] += 1.5
                base["momentum"] += 1.0
                base["connection"] += 1.0
            elif aspect.aspect == "conjunction":
                base["momentum"] += 2.0

        if metrics:
            hard = metrics.aspect_counts.get("square", 0) + metrics.aspect_counts.get(
                "opposition", 0
            )
            soft = metrics.aspect_counts.get("trine", 0) + metrics.aspect_counts.get(
                "sextile", 0
            )
            base["stability"] -= min(8.0, hard * 0.3)
            base["opportunity"] += min(8.0, soft * 0.3)
            if "Mercury" in metrics.retrograde_bodies:
                base["clarity"] -= 4.0

        house_scores = self._house_scores(
            period=period,
            snapshot=snapshot,
            metrics=metrics,
            period_events=period_events,
        )
        relevant_houses = SECTION_HOUSE_BIAS.get(
            section, SECTION_HOUSE_BIAS[Section.GENERAL]
        )
        relevant_pressure = sum(
            house_scores.get(house, 0.0) for house in relevant_houses
        )
        total_pressure = sum(house_scores.values()) or 1.0
        focus_share = min(1.0, (relevant_pressure / total_pressure) * 1.4)

        base["focus"] += min(10.0, relevant_pressure * 0.7)
        base["opportunity"] += min(8.0, relevant_pressure * 0.55)
        if section in (Section.LOVE_SINGLES, Section.LOVE_COUPLES, Section.FRIENDSHIP):
            base["connection"] += min(8.0, relevant_pressure * 0.65)
        if section in (Section.CAREER, Section.MONEY):
            base["stability"] += min(6.0, relevant_pressure * 0.45)
        if section == Section.HEALTH:
            base["clarity"] += min(5.0, relevant_pressure * 0.4)
        if focus_share < 0.25:
            base["focus"] -= 2.5

        for event in period_events:
            bias = event.section_bias.get(section.value, 0.0) + (
                event.section_bias.get("general", 0.0) * 0.35
            )
            if bias <= 0:
                continue
            exact_bonus = 1.0
            if event.exactness is not None:
                exact_bonus += max(0.0, 1.0 - min(1.0, event.exactness / 12.0)) * 0.35
            signal = min(2.8, event.narrative_priority * 0.9) * bias * exact_bonus

            if event.event_type == "station":
                base["focus"] += signal * 1.05
                base["clarity"] -= signal * 0.2
                base["stability"] -= signal * 0.35
            elif event.event_type == "lunation":
                base["connection"] += signal * 0.5
                base["opportunity"] += signal * 0.55
            elif event.event_type == "eclipse":
                base["focus"] += signal * 0.95
                base["opportunity"] += signal * 0.4
                base["stability"] -= signal * 0.5
            elif event.event_type == "exact_aspect":
                if event.aspect in ("square", "opposition", "quincunx"):
                    base["focus"] += signal * 0.8
                    base["clarity"] -= signal * 0.45
                else:
                    base["opportunity"] += signal * 0.75
                    base["momentum"] += signal * 0.4
            elif event.event_type == "ingress":
                base["momentum"] += signal * 0.55
                base["opportunity"] += signal * 0.4
            elif event.event_type == "retrograde_emphasis":
                base["clarity"] -= signal * 0.5
                base["focus"] += signal * 0.35

        return {k: round(max(0.0, min(100.0, v)), 1) for k, v in base.items()}

    def _intensity(self, scores: Dict[str, float]) -> str:
        avg = sum(scores.values()) / len(scores)
        if avg >= 70:
            return "high"
        if avg >= 58:
            return "elevated"
        if avg >= 45:
            return "steady"
        return "quiet"

    def _title(
        self, section: Section, sign: str, period: Period, intensity: str
    ) -> str:
        tone = self.rules.sign_tone.get(sign, "balanced")
        label = section.value.replace("_", " ").title()
        return f"{label} {period.value} outlook: {tone} ({intensity})"

    def _render_from_content(
        self,
        section: Section,
        sign: str,
        snapshot: ChartSnapshot,
        period: Period,
        metrics: PeriodMetrics | None,
        intensity: str,
        notable_events: List[str],
        period_events: Optional[Sequence[PeriodEvent]] = None,
        cadence_state: Optional[Dict[str, str]] = None,
        factor_type_allowlist: Optional[Sequence[str]] = None,
        focus_body: Optional[str] = None,
    ) -> Optional[Tuple[str, List[str], List[str], List[str], List[FactorDetail]]]:
        if not self.content_repository or not self.content_repository.has_period_data(
            period
        ):
            return None

        section_candidates = self._section_candidates(section)
        factor_specs = self._factor_specs(
            period=period,
            sign=sign,
            section=section,
            snapshot=snapshot,
            metrics=metrics,
            period_events=period_events,
            factor_type_allowlist=factor_type_allowlist,
            focus_body=focus_body,
        )
        seed = f"{period.value}|{sign}|{section.value}|{snapshot.timestamp.date().isoformat()}|{intensity}"

        weighted: Dict[str, List[Tuple[float, str, str, str]]] = {
            "motivation": [],
            "caution": [],
            "reflection": [],
            "tip": [],
            "affirmation": [],
        }
        factor_details: List[FactorDetail] = []

        for spec in factor_specs:
            selection = self.content_repository.select(
                period=period,
                sign=sign,
                section_candidates=section_candidates,
                intensity=intensity,
                factor_candidates=[(spec.factor_type, spec.factor_value)],
                seed=f"{seed}|{spec.factor_type}|{spec.factor_value}",
                allow_section_fallback=False,
                allow_any_value_for_factor=not self.strict_content_mode,
            )
            if selection is None:
                continue

            normalized_blocks: Dict[str, List[str]] = {}
            for key, value in selection.content_blocks.items():
                lines = self._as_str_list(value)
                if lines:
                    normalized_blocks[key] = lines

            sampled = self._sample_factor_blocks(
                blocks=normalized_blocks,
                tip_key=selection.tip_key,
                seed=f"{seed}|sample|{spec.factor_type}|{spec.factor_value}",
            )
            if not sampled:
                continue

            for key, line in sampled.items():
                bucket = "tip" if key in TIP_KEYS else key
                if bucket in weighted:
                    weighted[bucket].append(
                        (spec.weight, line, spec.factor_type, spec.factor_value)
                    )

            factor_details.append(
                FactorDetail(
                    factor_type=spec.factor_type,
                    factor_value=spec.factor_value,
                    weight=spec.weight,
                    factor_insights=sampled,
                )
            )

        if not factor_details:
            return None

        previous_seed = self._variation_cycle_seed
        self._variation_cycle_seed = seed
        try:
            summary_text = self._compose_summary(
                period=period,
                sign=sign,
                section=section,
                intensity=intensity,
                factor_details=factor_details,
                notable_events=notable_events,
                period_events=period_events,
                timestamp=snapshot.timestamp,
                cadence_state=cadence_state,
                focus_body=focus_body,
            )

            highlights = self._compose_highlights(
                period=period,
                section=section,
                factor_details=factor_details,
                notable_events=notable_events,
                period_events=period_events,
                limit=4,
            )
            cautions_raw = self._pick_top_weighted(weighted["caution"], limit=6)
            tips_raw = self._pick_top_weighted(weighted["tip"], limit=4)
            affirmations_raw = self._pick_top_weighted(weighted["affirmation"], limit=3)
            actions_raw = tips_raw + affirmations_raw
            cautions = self._editorialize_list_lines(
                lines=cautions_raw,
                section=section,
                kind="caution",
                narrative_seed=f"{seed}|cautions",
                limit=4,
            )
            actions = self._editorialize_list_lines(
                lines=actions_raw,
                section=section,
                kind="action",
                narrative_seed=f"{seed}|actions",
                limit=4,
            )
        finally:
            self._variation_cycle_seed = previous_seed

        if not highlights:
            highlights = ["Focus on grounded progress this cycle."]
        if not cautions:
            cautions = ["Avoid overextending your energy before priorities are clear."]
        if not actions:
            actions = ["Take one concrete step that matches your current priorities."]

        return summary_text, highlights[:4], cautions[:4], actions[:4], factor_details

    def _sample_factor_blocks(
        self, blocks: Dict[str, List[str]], tip_key: str, seed: str
    ) -> Dict[str, str]:
        sampled: Dict[str, str] = {}
        ordered_keys = ["motivation", "caution", "reflection", tip_key, "affirmation"]

        # If requested period tip key is missing, use any available tip key in data.
        if tip_key not in blocks:
            for candidate in TIP_KEYS:
                if candidate in blocks:
                    ordered_keys[3] = candidate
                    break

        for key in ordered_keys:
            lines = blocks.get(key, [])
            if not lines:
                continue
            idx = stable_index(f"{seed}|{key}", len(lines))
            sampled[key] = lines[idx]
        return sampled

    def _pick_top_weighted(
        self, values: Sequence[Tuple[float, str, str, str]], limit: int
    ) -> List[str]:
        ranked = sorted(
            values,
            key=lambda row: (
                -row[0],
                stable_index(f"{row[1]}|{row[2]}|{row[3]}", 1_000_000),
            ),
        )
        output: List[str] = []
        seen = set()
        for _, line, _, _ in ranked:
            cleaned = self._clean_line(line)
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            output.append(cleaned)
            if len(output) >= limit:
                break
        return output

    def _editorialize_list_lines(
        self,
        lines: Sequence[str],
        section: Section,
        kind: str,
        narrative_seed: str,
        limit: int,
    ) -> List[str]:
        output: List[str] = []
        seen = set()
        for idx, line in enumerate(lines):
            rewritten = self._editorialize_list_item(
                line=line,
                section=section,
                kind=kind,
                narrative_seed=narrative_seed,
                index=idx,
            )
            if not rewritten:
                continue
            if rewritten in seen:
                continue
            seen.add(rewritten)
            output.append(rewritten)
            if len(output) >= limit:
                break
        return output

    def _editorialize_list_item(
        self,
        line: str,
        section: Section,
        kind: str,
        narrative_seed: str,
        index: int,
    ) -> str:
        text = self._clean_line(line)
        if not text:
            return ""
        text = self._normalize_sign_case(text)
        text = text.replace("e. g.", "e.g.").replace("i. e.", "i.e.")

        if kind == "caution":
            return self._editorialize_caution_text(text, section, narrative_seed, index)
        if kind == "action":
            return self._editorialize_action_text(text, section, narrative_seed, index)
        return self._ensure_terminal(text)

    def _editorialize_caution_text(
        self, text: str, section: Section, narrative_seed: str, index: int
    ) -> str:
        lower = text.lower()
        if lower.startswith("avoid "):
            core = text[6:].strip().rstrip(".")
            prefix = self._pick_phrase(
                ["Avoid", "Keep clear of", "Steer clear of", "Monitor"],
                f"{narrative_seed}|caution_avoid|{index}",
            )
            sentence = self._ensure_terminal(f"{prefix} {core}")
            return self._with_section_caution_prefix(
                sentence, section, narrative_seed, index
            )
        if lower.startswith("watch for "):
            core = text[10:].strip().rstrip(".")
            prefix = self._pick_phrase(
                ["Watch for", "Keep clear of", "Steer clear of", "Monitor"],
                f"{narrative_seed}|caution_watch|{index}",
            )
            sentence = self._ensure_terminal(f"{prefix} {core}")
            return self._with_section_caution_prefix(
                sentence, section, narrative_seed, index
            )
        if lower.startswith("resist "):
            prefix = self._pick_phrase(
                ["Resist", "Hold back from", "Keep in check"],
                f"{narrative_seed}|caution_resist|{index}",
            )
            rest = text.split(" ", 1)[1] if " " in text else text
            sentence = self._ensure_terminal(f"{prefix} {rest}")
            return self._with_section_caution_prefix(
                sentence, section, narrative_seed, index
            )
        sentence = self._ensure_terminal(text)
        return self._with_section_caution_prefix(
            sentence, section, narrative_seed, index
        )

    def _with_section_caution_prefix(
        self, text: str, section: Section, narrative_seed: str, index: int
    ) -> str:
        body = self._clean_line(text)
        if not body:
            return ""
        body = re.sub(
            r"^(?:general|direction|money|career|relational|dating|partnership|health|friendship|communication|lifestyle)\s+caution:\s*",
            "",
            body,
            flags=re.IGNORECASE,
        )
        body = re.sub(r"^caution:\s*", "", body, flags=re.IGNORECASE)
        return self._ensure_terminal(body)

    def _editorialize_action_text(
        self, text: str, section: Section, narrative_seed: str, index: int
    ) -> str:
        converted = self._affirmation_to_action(text)
        converted = re.sub(r"\bI trust\b", "Trust", converted, flags=re.IGNORECASE)
        converted = re.sub(r"\bI honor\b", "Honor", converted, flags=re.IGNORECASE)
        converted = re.sub(r"\bI release\b", "Release", converted, flags=re.IGNORECASE)
        converted = self._rephrase_action_opening(converted, narrative_seed, index)
        converted = re.sub(
            r"^(?:next move|follow-?through|execution step|apply this|anchor move|direction step|execution move|"
            r"relational move|heart-level step|connection move|dating move|attraction step|connection filter|"
            r"partnership move|repair step|relationship follow-?through|career move|delivery step|career apply|"
            r"social move|circle step|friendship follow-?through|social apply|wellbeing move|recovery step|"
            r"energy follow-?through|health apply|money move|cashflow step|resource follow-?through|money apply|"
            r"conversation move|message step|clarity follow-?through|dialogue apply|routine move|lifestyle step|"
            r"environment follow-?through|lifestyle apply)\s*:\s*",
            "",
            converted,
            flags=re.IGNORECASE,
        )
        converted = converted[:1].upper() + converted[1:] if converted else converted
        return self._ensure_terminal(converted)

    def _rephrase_action_opening(
        self, text: str, narrative_seed: str, index: int
    ) -> str:
        value = self._clean_line(text)
        if not value:
            return ""
        lower = value.lower()
        if lower.startswith("start "):
            repl = self._pick_phrase(
                ["Start", "Begin", "Open"],
                f"{narrative_seed}|action_verb|start|{index}",
            )
            return repl + value[5:]
        if lower.startswith("end "):
            repl = self._pick_phrase(
                ["End", "Close", "Wrap"], f"{narrative_seed}|action_verb|end|{index}"
            )
            return repl + value[3:]
        if lower.startswith("schedule "):
            repl = self._pick_phrase(
                ["Schedule", "Block", "Set"],
                f"{narrative_seed}|action_verb|schedule|{index}",
            )
            return repl + value[8:]
        if lower.startswith("invest in "):
            repl = self._pick_phrase(
                ["Invest in", "Allocate toward", "Commit to"],
                f"{narrative_seed}|action_verb|invest|{index}",
            )
            return repl + value[9:]
        if lower.startswith("use the "):
            repl = self._pick_phrase(
                ["Use the", "Apply the", "Work with the"],
                f"{narrative_seed}|action_verb|use|{index}",
            )
            return repl + value[7:]
        return value

    def _affirmation_to_action(self, text: str) -> str:
        value = self._clean_line(text)
        if not value:
            return ""
        value = re.sub(
            r"^(today|this week|this month|this year|right now),?\s+",
            "",
            value,
            flags=re.IGNORECASE,
        )
        lower = value.lower()
        replacements = [
            (r"^i am\b", "Be"),
            (r"^i'm\b", "Be"),
            (r"^i release\b", "Release"),
            (r"^i trust\b", "Trust"),
            (r"^i choose\b", "Choose"),
            (r"^i honor\b", "Honor"),
            (r"^i welcome\b", "Welcome"),
            (r"^i focus\b", "Focus"),
            (r"^i allow\b", "Allow"),
            (r"^i commit\b", "Commit"),
            (r"^i will\b", "Commit to"),
            (r"^i can\b", "Use your ability to"),
        ]
        for pattern, replacement in replacements:
            if re.match(pattern, lower):
                converted = re.sub(pattern, replacement, value, flags=re.IGNORECASE)
                return converted[:1].upper() + converted[1:]
        if lower.startswith("i "):
            converted = value[2:].strip()
            return converted[:1].upper() + converted[1:] if converted else value
        return value

    def _render_fallback(
        self,
        section: Section,
        sign: str,
        snapshot: ChartSnapshot,
        period: Period,
        scores: Dict[str, float],
        notable_events: List[str],
        intensity: str,
    ) -> Tuple[str, List[str], List[str], List[str]]:
        key_planets = self._weights_for_section(section)
        top_planets = sorted(
            key_planets.items(), key=lambda item: item[1], reverse=True
        )[:2]
        keywords: List[str] = []
        for planet, _ in top_planets:
            keywords.extend(self.rules.planet_keywords.get(planet, []))

        summary_template = SECTION_FALLBACK_TEMPLATE[intensity]
        summary = summary_template.format(
            section=section.value.replace("_", " "),
            keywords=", ".join(keywords[:2]) or "clarity and balance",
        )

        highlights = [
            f"Moon themes in {snapshot.moon_sign} shape this {period.value} cycle.",
            f"Keep attention on {keywords[0]}."
            if keywords
            else "Keep attention on practical priorities.",
        ]
        if notable_events:
            highlights.append(notable_events[0])

        cautions = [
            "Avoid rushing decisions when clarity is still forming.",
            "Leave room for adjustment before locking in commitments.",
        ]
        actions = [
            "Set one measurable goal for this section and review it mid-cycle.",
            "Protect time for focused execution and reflection.",
        ]
        return summary, highlights, cautions, actions

    def _section_candidates(self, section: Section) -> List[str]:
        return [section.value]

    def _factor_specs(
        self,
        period: Period,
        sign: str,
        section: Section,
        snapshot: ChartSnapshot,
        metrics: PeriodMetrics | None,
        period_events: Optional[Sequence[PeriodEvent]] = None,
        factor_type_allowlist: Optional[Sequence[str]] = None,
        focus_body: Optional[str] = None,
    ) -> List[FactorSpec]:
        dominant_aspect = self._dominant_aspect(
            metrics, snapshot, focus_body=focus_body
        )
        transit_archetype = self._transit_archetype(
            metrics,
            snapshot,
            dominant_aspect,
            focus_body=focus_body,
        )
        house_focus = self._house_focus_value(
            period=period,
            snapshot=snapshot,
            metrics=metrics,
            period_events=period_events or [],
            focus_body=focus_body,
        )

        values: Dict[str, Optional[str]] = {
            "sun_in_sign": snapshot.sun_sign,
            "moon_in_sign": snapshot.moon_sign,
            "rising_sign": snapshot.rising_sign,
            "transits_archetypes": transit_archetype,
            "aspects": dominant_aspect,
            "daily_house_focus": house_focus,
            "weekly_moon_phase": self._weekly_moon_phase(snapshot),
            "planetary_focus": self._planetary_focus(
                period, snapshot, metrics, focus_body=focus_body
            ),
            "retrograde_archetypes": self._retrograde_archetype(
                period, metrics, snapshot
            ),
            "ingress_archetypes": self._ingress_archetype(period, metrics),
            "weekly_theme_archetypes": self._pick_theme(
                WEEKLY_THEMES, f"{sign}|{section.value}|weekly"
            ),
            "monthly_lunation_archetypes": self._monthly_lunation(snapshot),
            "eclipse_archetypes": self._eclipse_archetype(period, snapshot),
            "outer_planet_focus": self._outer_planet_focus(snapshot, metrics),
            "monthly_theme_archetypes": self._pick_theme(
                MONTHLY_THEMES,
                f"{sign}|{section.value}|monthly|{snapshot.timestamp.month}",
            ),
            "jupiter_in_sign": self._position_sign(snapshot, "Jupiter", sign),
            "saturn_in_sign": self._position_sign(snapshot, "Saturn", sign),
            "chiron_in_sign": self._position_sign(snapshot, "Chiron", sign),
            "nodal_axis": self._nodal_axis(snapshot),
            "yearly_theme_archetypes": self._pick_theme(
                YEARLY_THEMES,
                f"{sign}|{section.value}|yearly|{snapshot.timestamp.year}",
            ),
            "weekly_house_focus": house_focus,
            "monthly_house_focus": house_focus,
            "yearly_house_focus": house_focus,
        }

        if period == Period.DAILY:
            order = DAILY_FACTOR_ORDER
        elif period == Period.WEEKLY:
            order = WEEKLY_FACTOR_ORDER
        elif period == Period.MONTHLY:
            order = MONTHLY_FACTOR_ORDER
        else:
            order = YEARLY_FACTOR_ORDER

        weights = PERIOD_FACTOR_WEIGHTS[period]
        allow = None
        if factor_type_allowlist:
            allow = {
                value.strip()
                for value in factor_type_allowlist
                if value and value.strip()
            }
        return [
            FactorSpec(
                factor_type=factor_type,
                factor_value=values[factor_type] or "",
                weight=weights.get(factor_type, 1.0),
            )
            for factor_type in order
            if values.get(factor_type) and (allow is None or factor_type in allow)
        ]

    def _dominant_aspect(
        self,
        metrics: PeriodMetrics | None,
        snapshot: ChartSnapshot,
        focus_body: Optional[str] = None,
    ) -> str:
        tracked = [
            "conjunction",
            "trine",
            "sextile",
            "square",
            "opposition",
            "quincunx",
        ]
        counts = {name: 0 for name in tracked}

        if focus_body:
            for aspect in snapshot.aspects:
                if aspect.body1 != focus_body and aspect.body2 != focus_body:
                    continue
                if aspect.aspect in counts:
                    counts[aspect.aspect] += 1
            if sum(counts.values()) > 0:
                return max(tracked, key=lambda key: counts[key])

        if metrics:
            for aspect, count in metrics.aspect_counts.items():
                if aspect in counts:
                    counts[aspect] += count

        if sum(counts.values()) == 0:
            for aspect in snapshot.aspects:
                if aspect.aspect in counts:
                    counts[aspect.aspect] += 1

        return max(tracked, key=lambda key: counts[key])

    def _transit_archetype(
        self,
        metrics: PeriodMetrics | None,
        snapshot: ChartSnapshot,
        dominant_aspect: str,
        focus_body: Optional[str] = None,
    ) -> str:
        retrogrades = (
            set(metrics.retrograde_bodies)
            if metrics
            else {p.name for p in snapshot.positions if p.retrograde}
        )
        if focus_body and focus_body in retrogrades:
            return "retrograde_review"
        if retrogrades and not focus_body:
            return "retrograde_review"

        mapping = {
            "conjunction": "conjunction_growth",
            "trine": "trine_harmony",
            "sextile": "sextile_opportunity",
            "square": "square_tension",
            "opposition": "opposition_conflict",
            "quincunx": "decision_point",
        }
        from_aspect = mapping.get(dominant_aspect)
        if from_aspect:
            return from_aspect

        if focus_body:
            by_planet = {
                "Sun": "action_activation",
                "Moon": "emotional_flow",
                "Mercury": "communication_flow",
                "Venus": "relationship_tension",
                "Mars": "action_activation",
                "Jupiter": "adventure_call",
                "Saturn": "discipline_restriction",
                "Uranus": "decision_point",
                "Neptune": "spiritual_alignment",
                "Pluto": "introspection_phase",
                "Chiron": "health_awareness",
            }
            return by_planet.get(focus_body, "action_activation")
        return "action_activation"

    def _weekly_moon_phase(self, snapshot: ChartSnapshot) -> str:
        phase = self._moon_phase_angle(snapshot)
        if phase < 22.5 or phase >= 337.5:
            return "new_moon"
        if phase < 67.5:
            return "waxing_crescent"
        if phase < 112.5:
            return "first_quarter"
        if phase < 157.5:
            return "waxing_gibbous"
        if phase < 202.5:
            return "full_moon"
        if phase < 247.5:
            return "waning_gibbous"
        if phase < 292.5:
            return "last_quarter"
        return "waning_crescent"

    def _monthly_lunation(self, snapshot: ChartSnapshot) -> str:
        phase = self._moon_phase_angle(snapshot)
        eclipse = self._eclipse_archetype(Period.MONTHLY, snapshot)
        if eclipse in ("solar_eclipse", "lunar_eclipse", "eclipse_window"):
            return "eclipse_lunation"

        if phase < 22.5 or phase >= 337.5:
            return "new_moon_reset"
        if phase < 90.0:
            return "waxing_build_up"
        if phase < 135.0:
            return "first_quarter_action"
        if phase < 202.5:
            return "full_moon_culmination"
        if phase < 270.0:
            return "waning_integration"
        if phase < 315.0:
            return "last_quarter_release"
        return "balanced_lunation_cycle"

    def _planetary_focus(
        self,
        period: Period,
        snapshot: ChartSnapshot,
        metrics: PeriodMetrics | None,
        focus_body: Optional[str] = None,
    ) -> str:
        activity = self._planet_activity(snapshot, metrics)
        if period == Period.WEEKLY:
            candidates = [
                "Sun",
                "Moon",
                "Mercury",
                "Venus",
                "Mars",
                "Jupiter",
                "Saturn",
            ]
            if focus_body in candidates:
                return f"{focus_body.lower()}_focus"
            chosen = self._top_activity(activity, candidates, default="Sun")
            return f"{chosen.lower()}_focus"

        if period == Period.MONTHLY:
            candidates = [
                "Sun",
                "Mercury",
                "Venus",
                "Mars",
                "Jupiter",
                "Saturn",
                "Uranus",
                "Neptune",
                "Pluto",
                "Chiron",
            ]
            if focus_body in candidates:
                return f"{focus_body.lower()}_focus"
            chosen = self._top_activity(activity, candidates, default="Sun")
            return f"{chosen.lower()}_focus"

        if period == Period.YEARLY:
            yearly_candidates = [
                "Jupiter",
                "Saturn",
                "Uranus",
                "Neptune",
                "Pluto",
                "Chiron",
            ]
            if focus_body in yearly_candidates:
                return f"{focus_body.lower()}_focus"

            eclipse = self._eclipse_archetype(period, snapshot)
            if eclipse in (
                "solar_eclipse",
                "lunar_eclipse",
                "eclipse_window",
                "nodal_activation",
            ):
                return "eclipse_focus"
            node_score = activity.get("North Node", 0) + activity.get("South Node", 0)
            if node_score >= 3:
                return "nodes_focus"

            chosen = self._top_activity(activity, yearly_candidates, default="Jupiter")
            return f"{chosen.lower()}_focus"

        return "sun_focus"

    def _retrograde_archetype(
        self, period: Period, metrics: PeriodMetrics | None, snapshot: ChartSnapshot
    ) -> str:
        retrogrades = [p.name for p in snapshot.positions if p.retrograde]
        if metrics and metrics.retrograde_bodies:
            retrogrades = metrics.retrograde_bodies

        if period == Period.WEEKLY:
            for planet, value in RETROGRADE_WEEKLY.items():
                if planet in retrogrades:
                    return value
            return "no_major_retrograde"

        if period == Period.MONTHLY:
            matched = [
                value
                for planet, value in RETROGRADE_MONTHLY.items()
                if planet in retrogrades
            ]
            if len(matched) >= 2:
                return "mixed_retrogrades"
            if matched:
                return matched[0]
            return "no_major_retrograde"

        if period == Period.YEARLY:
            matched = [
                value
                for planet, value in RETROGRADE_YEARLY.items()
                if planet in retrogrades
            ]
            if len(matched) >= 2:
                return "mixed_retrogrades"
            if matched:
                return matched[0]
            return "no_major_retrograde"

        return "retrograde_review"

    def _ingress_archetype(self, period: Period, metrics: PeriodMetrics | None) -> str:
        sign_changes = metrics.sign_changes if metrics else []
        changed_bodies = {
            line.split(" enters ")[0] for line in sign_changes if " enters " in line
        }

        if period == Period.WEEKLY:
            if "Sun" in changed_bodies:
                return "sun_ingress"
            if "Moon" in changed_bodies:
                return "moon_ingress"
            if "Mercury" in changed_bodies:
                return "mercury_ingress"
            if "Venus" in changed_bodies:
                return "venus_ingress"
            if "Mars" in changed_bodies:
                return "mars_ingress"
            return "no_major_ingress"

        if period == Period.MONTHLY:
            priorities = ["Sun", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"]
            matches = [name for name in priorities if name in changed_bodies]
            if len(matches) >= 2:
                return "multi_ingress_month"
            if matches:
                return f"{matches[0].lower()}_ingress"
            return "no_major_ingress"

        if period == Period.YEARLY:
            if "North Node" in changed_bodies or "South Node" in changed_bodies:
                return "nodal_shift"
            priorities = ["Jupiter", "Saturn", "Uranus", "Neptune", "Pluto", "Chiron"]
            matches = [name for name in priorities if name in changed_bodies]
            if len(matches) >= 2:
                return "multi_ingress_year"
            if matches:
                return f"{matches[0].lower()}_ingress"
            return "no_major_ingress"

        return "no_major_ingress"

    def _eclipse_archetype(self, period: Period, snapshot: ChartSnapshot) -> str:
        sun_moon_sep, sun_node_dist, moon_node_dist = self._eclipse_distances(snapshot)

        is_near_new = sun_moon_sep <= 15.0
        is_near_full = abs(sun_moon_sep - 180.0) <= 15.0
        near_node_sun = sun_node_dist <= 18.0
        near_node_moon = moon_node_dist <= 18.0
        near_window = min(sun_node_dist, moon_node_dist) <= 25.0

        if period == Period.MONTHLY:
            if is_near_new and near_node_sun:
                return "solar_eclipse"
            if is_near_full and near_node_moon:
                return "lunar_eclipse"
            if near_window:
                return "eclipse_window"
            return "no_eclipse"

        if period == Period.YEARLY:
            if is_near_new and near_node_sun:
                return "solar_eclipse"
            if is_near_full and near_node_moon:
                return "lunar_eclipse"
            if near_window:
                return "nodal_activation"
            return "no_eclipse"

        return "no_eclipse"

    def _outer_planet_focus(
        self, snapshot: ChartSnapshot, metrics: PeriodMetrics | None
    ) -> str:
        activity = self._planet_activity(snapshot, metrics)
        mapping = {
            "Uranus": "uranus_shift",
            "Neptune": "neptune_dreamwork",
            "Pluto": "pluto_transformation",
            "Chiron": "chiron_healing",
            "Saturn": "saturn_structure",
            "Jupiter": "jupiter_expansion",
        }
        chosen = self._top_activity(activity, list(mapping.keys()), default="Chiron")
        return mapping[chosen]

    def _nodal_axis(self, snapshot: ChartSnapshot) -> str:
        north = self._position_sign(snapshot, "North Node", "ARIES")
        south = self._position_sign(snapshot, "South Node", "LIBRA")
        mapped = NODAL_AXIS_BY_SIGNS.get(frozenset((north, south)))
        if mapped:
            return mapped
        options = [
            "aries_libra",
            "taurus_scorpio",
            "gemini_sagittarius",
            "cancer_capricorn",
            "leo_aquarius",
            "virgo_pisces",
        ]
        return options[stable_index(f"{north}|{south}", len(options))]

    def _planet_activity(
        self, snapshot: ChartSnapshot, metrics: PeriodMetrics | None
    ) -> Dict[str, float]:
        activity: Dict[str, float] = {}
        for aspect in snapshot.aspects:
            activity[aspect.body1] = activity.get(aspect.body1, 0.0) + 1.0
            activity[aspect.body2] = activity.get(aspect.body2, 0.0) + 1.0
            if aspect.aspect in ("square", "opposition", "conjunction"):
                activity[aspect.body1] = activity.get(aspect.body1, 0.0) + 0.4
                activity[aspect.body2] = activity.get(aspect.body2, 0.0) + 0.4

        retro_set = set(metrics.retrograde_bodies) if metrics else set()
        for position in snapshot.positions:
            if position.retrograde or position.name in retro_set:
                activity[position.name] = activity.get(position.name, 0.0) + 1.5

        return activity

    def _top_activity(
        self, activity: Dict[str, float], candidates: Sequence[str], default: str
    ) -> str:
        best_name = default
        best_score = activity.get(default, -1.0)
        for name in candidates:
            score = activity.get(name, 0.0)
            if score > best_score:
                best_name = name
                best_score = score
        return best_name

    def _moon_phase_angle(self, snapshot: ChartSnapshot) -> float:
        sun = self._position_longitude(snapshot, "Sun")
        moon = self._position_longitude(snapshot, "Moon")
        if sun is None or moon is None:
            return 0.0
        return (moon - sun) % 360.0

    def _eclipse_distances(self, snapshot: ChartSnapshot) -> Tuple[float, float, float]:
        sun = self._position_longitude(snapshot, "Sun") or 0.0
        moon = self._position_longitude(snapshot, "Moon") or 0.0
        north = self._position_longitude(snapshot, "North Node")
        south = self._position_longitude(snapshot, "South Node")

        if north is None and south is not None:
            north = (south + 180.0) % 360.0
        if south is None and north is not None:
            south = (north + 180.0) % 360.0
        if north is None:
            north = 0.0
        if south is None:
            south = 180.0

        sun_moon_sep = self._angle_distance(sun, moon)
        sun_node_dist = min(
            self._angle_distance(sun, north), self._angle_distance(sun, south)
        )
        moon_node_dist = min(
            self._angle_distance(moon, north), self._angle_distance(moon, south)
        )
        return sun_moon_sep, sun_node_dist, moon_node_dist

    def _position_sign(
        self, snapshot: ChartSnapshot, body_name: str, default: str
    ) -> str:
        for position in snapshot.positions:
            if position.name == body_name:
                return position.sign
        return default

    def _position_longitude(
        self, snapshot: ChartSnapshot, body_name: str
    ) -> Optional[float]:
        for position in snapshot.positions:
            if position.name == body_name:
                return position.longitude
        return None

    def _angle_distance(self, a: float, b: float) -> float:
        diff = abs(a - b) % 360.0
        return min(diff, 360.0 - diff)

    def _pick_theme(self, values: Sequence[str], seed: str) -> str:
        return values[stable_index(seed, len(values))]

    def _house_focus_value(
        self,
        period: Period,
        snapshot: ChartSnapshot,
        metrics: PeriodMetrics | None,
        period_events: Sequence[PeriodEvent],
        focus_body: Optional[str] = None,
    ) -> Optional[str]:
        if focus_body:
            rising_sign = snapshot.rising_sign
            house = self._position_house(snapshot, focus_body)
            if house is None and rising_sign:
                sign = self._position_sign(snapshot, focus_body, "")
                if sign:
                    house = self._whole_sign_house(rising_sign, sign)
            if house is not None:
                return self._house_value_key(house)

        scores = self._house_scores(period, snapshot, metrics, period_events)
        if not any(scores.values()):
            return None
        top_house = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0][0]
        return self._house_value_key(top_house)

    def _house_scores(
        self,
        period: Period,
        snapshot: ChartSnapshot,
        metrics: PeriodMetrics | None,
        period_events: Sequence[PeriodEvent],
    ) -> Dict[int, float]:
        scores: Dict[int, float] = {house: 0.0 for house in range(1, 13)}
        rising_sign = snapshot.rising_sign
        has_direct_houses = any(
            (position.house is not None) for position in snapshot.positions
        )
        if not rising_sign and not has_direct_houses:
            return scores

        body_weights = BODY_HOUSE_WEIGHTS_BY_PERIOD.get(
            period, BODY_HOUSE_WEIGHTS_BY_PERIOD[Period.MONTHLY]
        )

        for position in snapshot.positions:
            house = position.house
            if house is None and rising_sign:
                house = self._whole_sign_house(rising_sign, position.sign)
            if house is None:
                continue
            weight = body_weights.get(position.name, 0.9)
            if position.retrograde:
                weight *= 1.05
            scores[house] += weight

        if metrics:
            for name in metrics.retrograde_bodies:
                house = self._position_house(snapshot, name)
                if house is None and rising_sign:
                    sign = self._position_sign(snapshot, name, "")
                    if sign:
                        house = self._whole_sign_house(rising_sign, sign)
                if house is None:
                    continue
                scores[house] += 0.35

            for line in metrics.sign_changes:
                if " enters " not in line:
                    continue
                body, right = line.split(" enters ", 1)
                house = self._position_house(snapshot, body)
                if house is None:
                    sign = right.split(" on ", 1)[0].strip().upper()
                    house = self._house_for_sign(snapshot, sign, rising_sign)
                if house is None:
                    continue
                scores[house] += 0.7 + (body_weights.get(body, 1.0) * 0.35)

        for aspect in snapshot.aspects:
            if not aspect.exact:
                continue
            if aspect.aspect in ("square", "opposition", "quincunx"):
                aspect_bonus = 0.8
            else:
                aspect_bonus = 0.55
            for body in (aspect.body1, aspect.body2):
                house = self._position_house(snapshot, body)
                if house is None and rising_sign:
                    sign = self._position_sign(snapshot, body, "")
                    if sign:
                        house = self._whole_sign_house(rising_sign, sign)
                if house is None:
                    continue
                scores[house] += aspect_bonus

        for event in period_events:
            event_weight = EVENT_HOUSE_WEIGHTS.get(event.event_type, 1.0)
            exact_bonus = 1.0
            if event.exactness is not None:
                exact_bonus += max(0.0, 1.0 - min(1.0, event.exactness / 12.0)) * 0.4
            influence = event_weight * exact_bonus

            if event.sign and event.sign.upper() in ZODIAC_SIGNS:
                house = self._house_for_sign(snapshot, event.sign.upper(), rising_sign)
                if house is not None:
                    scores[house] += influence

            for body in (event.body1, event.body2):
                if not body:
                    continue
                house = self._position_house(snapshot, body)
                if house is None and rising_sign:
                    sign = self._position_sign(snapshot, body, "")
                    if sign:
                        house = self._whole_sign_house(rising_sign, sign)
                if house is None:
                    continue
                body_weight = body_weights.get(body, 1.0)
                scores[house] += influence * body_weight * 0.45

        return scores

    def _position_house(self, snapshot: ChartSnapshot, body_name: str) -> Optional[int]:
        for position in snapshot.positions:
            if position.name != body_name:
                continue
            house = position.house
            if house is None:
                return None
            return int(house)
        return None

    def _house_for_sign(
        self, snapshot: ChartSnapshot, sign: str, rising_sign: Optional[str]
    ) -> Optional[int]:
        if sign not in ZODIAC_SIGNS:
            return None
        if snapshot.house_cusps:
            sign_index = ZODIAC_SIGNS.index(sign)
            midpoint = sign_index * 30.0 + 15.0
            house = self._house_from_cusps(midpoint, snapshot.house_cusps)
            if house is not None:
                return house
        if rising_sign:
            return self._whole_sign_house(rising_sign, sign)
        return None

    def _house_from_cusps(
        self, longitude: float, cusps: Sequence[float]
    ) -> Optional[int]:
        if len(cusps) != 12:
            return None
        lon = longitude % 360.0
        normalized = [(float(cusp) % 360.0) for cusp in cusps]
        for idx in range(12):
            start = normalized[idx]
            end = normalized[(idx + 1) % 12]
            arc = (end - start) % 360.0
            if arc <= 0:
                continue
            offset = (lon - start) % 360.0
            if offset < arc or (idx == 11 and offset <= arc):
                return idx + 1
        return None

    def _whole_sign_house(self, rising_sign: str, target_sign: str) -> int:
        try:
            rising_idx = ZODIAC_SIGNS.index(rising_sign.upper())
            target_idx = ZODIAC_SIGNS.index(target_sign.upper())
        except ValueError:
            return 1
        return ((target_idx - rising_idx) % 12) + 1

    def _house_value_key(self, house: int) -> str:
        labels = [
            "first_house",
            "second_house",
            "third_house",
            "fourth_house",
            "fifth_house",
            "sixth_house",
            "seventh_house",
            "eighth_house",
            "ninth_house",
            "tenth_house",
            "eleventh_house",
            "twelfth_house",
        ]
        idx = min(max(1, house), 12) - 1
        return labels[idx]

    def _house_focus_line(self, value: str, section: Optional[Section] = None) -> str:
        mapping = {
            "first_house": "identity, visibility, and personal momentum",
            "second_house": "money decisions, values, and resource steadiness",
            "third_house": "communication, learning, and daily movement",
            "fourth_house": "home base, emotional safety, and foundations",
            "fifth_house": "romance, creativity, and self-expression",
            "sixth_house": "work systems, health habits, and consistency",
            "seventh_house": "partnership dynamics, agreements, and reciprocity",
            "eighth_house": "shared resources, intimacy, and deeper trust work",
            "ninth_house": "beliefs, expansion, travel, and perspective shifts",
            "tenth_house": "career direction, visibility, and leadership pressure",
            "eleventh_house": "friendships, community, and long-range goals",
            "twelfth_house": "rest, release, healing, and inner processing",
        }
        base = mapping.get(value, self._readable_factor_value(value))
        if section is None:
            return base

        section_defaults = {
            Section.GENERAL: "{base}",
            Section.LOVE_SINGLES: "{base}",
            Section.LOVE_COUPLES: "{base}",
            Section.CAREER: "{base}",
            Section.FRIENDSHIP: "{base}",
            Section.HEALTH: "{base}",
            Section.MONEY: "{base}",
            Section.COMMUNICATION: "{base}",
            Section.LIFESTYLE: "{base}",
        }
        section_overrides: Dict[Section, Dict[str, str]] = {
            Section.CAREER: {
                "ninth_house": "teaching voice, publishing, and long-range market expansion",
                "tenth_house": "public positioning, leadership pressure, and reputation decisions",
                "sixth_house": "workflow discipline, delivery quality, and operational consistency",
                "eleventh_house": "network leverage, alliances, and strategic visibility",
            },
            Section.LOVE_SINGLES: {
                "fifth_house": "chemistry, playful openness, and romantic confidence",
                "seventh_house": "reciprocity standards and partnership readiness",
                "ninth_house": "attraction through shared beliefs and wider horizons",
                "sixth_house": "consistency in dating effort, standards in practice, and emotional discernment",
            },
            Section.LOVE_COUPLES: {
                "fourth_house": "emotional safety, home rhythm, and private repair",
                "seventh_house": "agreements, fairness, and relational accountability",
                "eighth_house": "trust depth, intimacy courage, and shared vulnerability",
                "sixth_house": "shared routines, daily teamwork, and practical care",
            },
            Section.COMMUNICATION: {
                "third_house": "clean speech, listening rhythm, and immediate message clarity",
                "ninth_house": "teaching voice, worldview honesty, and message reach",
                "eleventh_house": "community conversations and network-level signal strength",
                "sixth_house": "communication hygiene, follow-through, and signal discipline",
            },
            Section.MONEY: {
                "second_house": "cashflow choices, pricing integrity, and value boundaries",
                "eighth_house": "shared-resource agreements, debt strategy, and trust economics",
                "tenth_house": "income visibility through reputation and delivery quality",
                "sixth_house": "income routines, operational efficiency, and spending discipline",
            },
            Section.HEALTH: {
                "sixth_house": "daily regulation, habit fidelity, and body maintenance",
                "twelfth_house": "deep rest, emotional decompression, and nervous-system recovery",
                "first_house": "energy baseline, embodiment, and physical presence",
            },
        }
        section_overrides.update(SECTION_HOUSE_PHRASES)
        scoped = section_overrides.get(section, {})
        if value in scoped:
            return scoped[value]
        template = section_defaults.get(section, "{base}")
        return template.format(base=base)

    def _compose_summary(
        self,
        period: Period,
        sign: str,
        section: Section,
        intensity: str,
        factor_details: Sequence[FactorDetail],
        notable_events: Sequence[str],
        period_events: Optional[Sequence[PeriodEvent]],
        timestamp: datetime,
        cadence_state: Optional[Dict[str, str]] = None,
        focus_body: Optional[str] = None,
    ) -> str:
        narrative_seed = self._narrative_seed(
            period=period,
            sign=sign,
            section=section,
            timestamp=timestamp,
            intensity=intensity,
        )
        if period in (Period.MONTHLY, Period.YEARLY):
            return self._compose_editorial_longform(
                period=period,
                sign=sign,
                section=section,
                intensity=intensity,
                factor_details=factor_details,
                notable_events=notable_events,
                period_events=period_events,
                timestamp=timestamp,
                narrative_seed=narrative_seed,
                cadence_state=cadence_state,
                focus_body=focus_body,
            )

        intro = self._period_intro(
            period, sign, section, intensity, timestamp, narrative_seed
        )
        focus_line = self._planet_focus_line(
            period, section, focus_body, narrative_seed
        )
        event_line = self._period_event_line(
            period, period_events or [], notable_events, narrative_seed
        )
        rank_limit = {
            Period.DAILY: 2,
            Period.WEEKLY: 3,
            Period.MONTHLY: 4,
            Period.YEARLY: 4,
        }.get(period, 3)
        top_factors = sorted(
            factor_details, key=lambda item: item.weight, reverse=True
        )[:rank_limit]

        influence_lines: List[str] = []
        for index, detail in enumerate(top_factors):
            influence = self._factor_influence(
                period, section, detail.factor_type, detail.factor_value
            )
            influence = self._apply_section_lens(
                influence, section, detail.factor_type, index
            )
            support = self._editorialize_support(
                self._supporting_line(detail, period, index),
                section,
                narrative_seed,
                index,
            )
            if support and index < 2:
                influence_lines.append(
                    self._connect_influence_line(
                        influence, support, index, narrative_seed
                    )
                )
            else:
                influence_lines.append(influence)

        close = self._period_close(period, section, factor_details, narrative_seed)

        parts = [intro]
        if focus_line:
            parts.append(focus_line)
        if event_line:
            parts.append(event_line)
        parts.extend(influence_lines)
        if close:
            parts.append(close)
        paragraph = " ".join(part.strip() for part in parts if part and part.strip())
        return self._smooth_narrative(paragraph)

    def _compose_editorial_longform(
        self,
        period: Period,
        sign: str,
        section: Section,
        intensity: str,
        factor_details: Sequence[FactorDetail],
        notable_events: Sequence[str],
        period_events: Optional[Sequence[PeriodEvent]],
        timestamp: datetime,
        narrative_seed: str,
        cadence_state: Optional[Dict[str, str]] = None,
        focus_body: Optional[str] = None,
    ) -> str:
        intro = self._period_intro(
            period, sign, section, intensity, timestamp, narrative_seed
        )
        focus_line = self._planet_focus_line(
            period, section, focus_body, narrative_seed
        )
        thesis_line = self._editorial_thesis_line(
            period, section, factor_details, narrative_seed
        )
        breath_line = self._editorial_breath_line(period, narrative_seed, cadence_state)
        events = self._timeline_events(
            period, period_events or [], notable_events, limit=3
        )
        event_arc = self._editorial_event_arc(period, section, events, narrative_seed)
        theme_line = self._editorial_theme_line(
            period, section, factor_details, narrative_seed
        )
        influence_lines = self._editorial_influence_lines(
            period, section, factor_details, narrative_seed
        )
        contrast_line = self._editorial_contrast_line(section, narrative_seed)
        close = self._period_close(period, section, factor_details, narrative_seed)
        voice = self._section_voice(section)
        dynamic_close = (
            self._dynamic_close_line(voice["monthly_close"], "monthly", narrative_seed)
            if period == Period.MONTHLY
            else self._dynamic_close_line(
                voice["yearly_close"], "yearly", narrative_seed
            )
        )

        slots: Dict[str, List[str]] = {
            "intro": [intro] if intro else [],
            "focus": [focus_line] if focus_line else [],
            "thesis": [thesis_line] if thesis_line else [],
            "breath": [breath_line] if breath_line else [],
            "theme": [theme_line] if theme_line else [],
            "events": [event_arc] if event_arc else [],
            "influences": list(influence_lines),
            "contrast": [contrast_line] if contrast_line else [],
            "dynamic_close": [dynamic_close] if dynamic_close else [],
            "close": [close] if close else [],
        }
        flow = self._longform_cadence_flow(period, section)
        parts: List[str] = []
        previous_token: Optional[str] = None
        for token in flow:
            chunk = slots.get(token, [])
            if not chunk:
                continue
            bridge = self._cadence_bridge_line(
                period=period,
                section=section,
                from_token=previous_token,
                to_token=token,
                narrative_seed=narrative_seed,
            )
            if bridge:
                parts.append(bridge)
            parts.extend(chunk)
            previous_token = token

        paragraph = " ".join(part.strip() for part in parts if part and part.strip())
        return self._smooth_narrative(paragraph)

    def _longform_cadence_flow(self, period: Period, section: Section) -> List[str]:
        period_map = LONGFORM_CADENCE_BY_PERIOD.get(period, {})
        return period_map.get(section, LONGFORM_CADENCE_DEFAULT)

    def _cadence_bridge_line(
        self,
        period: Period,
        section: Section,
        from_token: Optional[str],
        to_token: str,
        narrative_seed: str,
    ) -> str:
        if from_token is None:
            return ""
        if to_token not in LONGFORM_BRIDGE_TOKENS:
            return ""
        bank = LONGFORM_BRIDGE_BANKS.get(
            section, LONGFORM_BRIDGE_BANKS[Section.GENERAL]
        )
        if not bank:
            return ""
        # Keep connectors sparse so cadence improves without bloating paragraphs.
        if to_token not in {"events", "influences", "contrast"}:
            return ""
        template = self._pick_phrase(
            bank,
            f"{narrative_seed}|bridge|{period.value}|{section.value}|{from_token}|{to_token}",
        )
        return self._ensure_terminal(template)

    def _editorial_breath_line(
        self,
        period: Period,
        narrative_seed: str,
        cadence_state: Optional[Dict[str, str]] = None,
    ) -> str:
        if period not in (Period.MONTHLY, Period.YEARLY):
            return ""
        key = period.value
        options = PERIOD_BREATH_LINES.get(key, [])
        if not options:
            return ""
        choice = self._pick_phrase(options, f"{narrative_seed}|breath|{key}")
        state_key = f"{key}_last_breath"
        if cadence_state is not None:
            previous = cadence_state.get(state_key)
            if previous == choice and len(options) > 1:
                base_idx = stable_index(f"{narrative_seed}|breath|{key}", len(options))
                choice = options[(base_idx + 1) % len(options)]
            cadence_state[state_key] = choice
        return choice

    def _planet_focus_line(
        self,
        period: Period,
        section: Section,
        focus_body: Optional[str],
        narrative_seed: str,
    ) -> str:
        if not focus_body:
            return ""
        readable_period = {
            Period.DAILY: "today",
            Period.WEEKLY: "this week",
            Period.MONTHLY: "this month",
            Period.YEARLY: "this year",
        }[period]
        area = self._section_focus(section)
        planet = focus_body.strip()
        templates = [
            "{planet} is the lead signal {period_span}, so {area} carries stronger consequence.",
            "{period_span_cap}, keep {planet} as your guiding lens; {area} responds quickly to intent.",
            "{planet} is foregrounded {period_span}, bringing sharper focus to {area}.",
        ]
        template = self._pick_phrase(
            templates, f"{narrative_seed}|planet_focus|{section.value}|{period.value}"
        )
        return template.format(
            planet=planet,
            period_span=readable_period,
            period_span_cap=readable_period[:1].upper() + readable_period[1:],
            area=area,
        )

    def _editorial_felt_tone(
        self,
        section: Section,
        factor_details: Sequence[FactorDetail],
        narrative_seed: str,
    ) -> str:
        bank = SECTION_FELT_TONES.get(section, SECTION_FELT_TONES[Section.GENERAL])

        def _pick(options: object, suffix: str) -> str:
            if isinstance(options, list) and options:
                return self._pick_phrase(
                    options,
                    f"{narrative_seed}|felt_tone|{section.value}|{suffix}",
                )
            if isinstance(options, str):
                return options
            return ""

        transit = self._factor_detail_by_type(factor_details, "transits_archetypes")
        if transit:
            transit_map = bank.get("transits", {})
            if isinstance(transit_map, dict):
                scoped = _pick(
                    transit_map.get(transit.factor_value),
                    f"transit|{transit.factor_value}",
                )
                if scoped:
                    return scoped

        aspect = self._factor_detail_by_type(factor_details, "aspects")
        if aspect:
            aspect_map = bank.get("aspects", {})
            if isinstance(aspect_map, dict):
                scoped = _pick(
                    aspect_map.get(aspect.factor_value), f"aspect|{aspect.factor_value}"
                )
                if scoped:
                    return scoped

        retro = self._factor_detail_by_type(factor_details, "retrograde_archetypes")
        if retro and retro.factor_value != "no_major_retrograde":
            retro_map = bank.get("retrograde_map", {})
            if isinstance(retro_map, dict):
                scoped = _pick(
                    retro_map.get(retro.factor_value), f"retro_map|{retro.factor_value}"
                )
                if scoped:
                    return scoped
            scoped = _pick(bank.get("retrograde"), "retrograde|default")
            if scoped:
                return scoped

        house = next(
            (
                detail
                for detail in factor_details
                if detail.factor_type
                in (
                    "daily_house_focus",
                    "weekly_house_focus",
                    "monthly_house_focus",
                    "yearly_house_focus",
                )
            ),
            None,
        )
        if house:
            house_map = bank.get("house", {})
            if isinstance(house_map, dict):
                scoped = _pick(
                    house_map.get(house.factor_value), f"house|{house.factor_value}"
                )
                if scoped:
                    return scoped
            return f"strong life-area pressure around {self._readable_factor_value(house.factor_value)}"
        scoped = _pick(bank.get("default"), "fallback")
        if scoped:
            return scoped
        return "a reset in pacing and priorities"

    def _editorial_thesis_line(
        self,
        period: Period,
        section: Section,
        factor_details: Sequence[FactorDetail],
        narrative_seed: str,
    ) -> str:
        period_key = "monthly" if period == Period.MONTHLY else "yearly"
        templates = THESIS_TEMPLATES[period_key]
        from_state, to_state = SECTION_CONTRAST_STATES.get(
            section, SECTION_CONTRAST_STATES[Section.GENERAL]
        )
        felt_tone = self._editorial_felt_tone(section, factor_details, narrative_seed)
        template = self._pick_phrase(templates, f"{narrative_seed}|thesis|{period_key}")
        return template.format(
            felt_tone=felt_tone,
            from_state=from_state,
            to_state=to_state,
        )

    def _editorial_contrast_line(self, section: Section, narrative_seed: str) -> str:
        from_state, to_state = SECTION_CONTRAST_STATES.get(
            section, SECTION_CONTRAST_STATES[Section.GENERAL]
        )
        templates = SECTION_CONTRAST_TEMPLATES.get(section, CONTRAST_TEMPLATES)
        template = self._pick_phrase(
            templates, f"{narrative_seed}|contrast|{section.value}"
        )
        return template.format(from_state=from_state, to_state=to_state)

    def _editorial_theme_line(
        self,
        period: Period,
        section: Section,
        factor_details: Sequence[FactorDetail],
        narrative_seed: str,
    ) -> str:
        theme_keys = (
            ("monthly_theme_archetypes", "monthly theme")
            if period == Period.MONTHLY
            else ("yearly_theme_archetypes", "yearly theme")
        )
        detail = self._factor_detail_by_type(factor_details, theme_keys[0])
        if not detail:
            return ""
        readable = self._readable_factor_value(detail.factor_value)
        voice = self._section_voice(section)
        if period == Period.MONTHLY:
            template = self._pick_phrase(
                THEME_PATTERNS["monthly"], f"{narrative_seed}|theme|monthly"
            )
            theme_article = self._indefinite_article(readable)
            return template.format(
                theme=readable,
                focus=voice["monthly_theme_focus"],
                theme_article=theme_article,
            )
        template = self._pick_phrase(
            THEME_PATTERNS["yearly"], f"{narrative_seed}|theme|yearly"
        )
        return template.format(theme=readable, focus=voice["yearly_theme_focus"])

    def _editorial_event_arc(
        self,
        period: Period,
        section: Section,
        events: Sequence[str],
        narrative_seed: str,
    ) -> str:
        if not events:
            return ""
        key = period.value
        anchor_sets = EVENT_ANCHOR_OPTIONS.get(
            key, [EVENT_ANCHOR_OPTIONS["monthly"][0]]
        )
        anchors = self._pick_phrase(anchor_sets, f"{narrative_seed}|anchors|{key}")
        lines = [f"{anchor}, {event}." for anchor, event in zip(anchors, events)]
        voice = self._section_voice(section)
        impact = (
            voice["monthly_event_impact"]
            if period == Period.MONTHLY
            else voice["yearly_event_impact"]
        )
        impact_line = self._pick_phrase(
            EVENT_IMPACT_LINES,
            f"{narrative_seed}|impact_line|{key}",
        ).format(impact=impact)
        return " ".join(lines + [impact_line])

    def _editorial_influence_lines(
        self,
        period: Period,
        section: Section,
        factor_details: Sequence[FactorDetail],
        narrative_seed: str,
    ) -> List[str]:
        skip_types = {"monthly_theme_archetypes", "yearly_theme_archetypes"}
        ordered = sorted(
            [
                detail
                for detail in factor_details
                if detail.factor_type not in skip_types
            ],
            key=lambda item: (
                self._factor_priority(period, item.factor_type),
                -item.weight,
            ),
        )
        selected = ordered[:3]
        lines: List[str] = []
        for idx, detail in enumerate(selected):
            influence = self._factor_influence(
                period, section, detail.factor_type, detail.factor_value
            )
            influence = self._apply_section_lens(
                influence, section, detail.factor_type, idx
            )
            support = self._editorialize_support(
                self._supporting_line(detail, period, idx),
                section,
                narrative_seed,
                idx,
            )
            if support and idx < 2:
                lines.append(
                    self._connect_influence_line(
                        influence, support, idx, narrative_seed
                    )
                )
            else:
                lines.append(influence)
        return lines[:3]

    def _factor_priority(self, period: Period, factor_type: str) -> int:
        monthly = {
            "monthly_theme_archetypes": 0,
            "monthly_lunation_archetypes": 1,
            "eclipse_archetypes": 2,
            "monthly_house_focus": 3,
            "planetary_focus": 4,
            "retrograde_archetypes": 5,
            "ingress_archetypes": 6,
            "transits_archetypes": 7,
            "aspects": 8,
            "sun_in_sign": 9,
        }
        yearly = {
            "yearly_theme_archetypes": 0,
            "yearly_house_focus": 1,
            "planetary_focus": 2,
            "jupiter_in_sign": 3,
            "saturn_in_sign": 4,
            "chiron_in_sign": 5,
            "nodal_axis": 6,
            "eclipse_archetypes": 7,
            "outer_planet_focus": 8,
            "retrograde_archetypes": 9,
            "ingress_archetypes": 10,
            "transits_archetypes": 11,
            "aspects": 12,
        }
        if period == Period.MONTHLY:
            return monthly.get(factor_type, 99)
        if period == Period.YEARLY:
            return yearly.get(factor_type, 99)
        return 99

    def _factor_detail_by_type(
        self, factor_details: Sequence[FactorDetail], factor_type: str
    ) -> Optional[FactorDetail]:
        for detail in factor_details:
            if detail.factor_type == factor_type:
                return detail
        return None

    def _compose_highlights(
        self,
        period: Period,
        section: Section,
        factor_details: Sequence[FactorDetail],
        notable_events: Sequence[str],
        period_events: Optional[Sequence[PeriodEvent]],
        limit: int,
    ) -> List[str]:
        highlights: List[str] = []
        seen = set()

        top_factors = sorted(factor_details, key=lambda item: item.weight, reverse=True)
        for detail in top_factors[:limit]:
            highlight = self._factor_highlight(period, section, detail)
            if not highlight or highlight in seen:
                continue
            seen.add(highlight)
            highlights.append(highlight)
            if len(highlights) >= limit:
                return highlights[:limit]

        for event in self._timeline_events(
            period, period_events or [], notable_events, limit=3
        ):
            if len(highlights) >= limit:
                break
            event_line = self._ensure_terminal(event)
            if event_line not in seen:
                seen.add(event_line)
                highlights.append(event_line)

        return highlights[:limit]

    def _period_intro(
        self,
        period: Period,
        sign: str,
        section: Section,
        intensity: str,
        timestamp: datetime,
        narrative_seed: str,
    ) -> str:
        sign_label = sign.title()
        area = self._section_focus(section)
        voice = self._section_voice(section)
        intensity_word = {
            "quiet": "softer",
            "steady": "steady",
            "elevated": "active",
            "high": "high-voltage",
        }.get(intensity, "balanced")

        if period == Period.DAILY:
            day = timestamp.strftime("%B %d").replace(" 0", " ")
            article = self._indefinite_article(intensity_word)
            template = self._pick_phrase(
                INTRO_PATTERNS["daily"], f"{narrative_seed}|intro|daily"
            )
            return template.format(
                day=day,
                article=article,
                intensity=intensity_word,
                sign=sign_label,
                area=area,
                hook=voice["daily_hook"],
            )
        if period == Period.WEEKLY:
            template = self._pick_phrase(
                INTRO_PATTERNS["weekly"], f"{narrative_seed}|intro|weekly"
            )
            return template.format(
                sign=sign_label, area=area, hook=voice["weekly_hook"]
            )
        if period == Period.MONTHLY:
            month_name = timestamp.strftime("%B %Y")
            article = self._indefinite_article(intensity_word)
            template = self._pick_phrase(
                INTRO_PATTERNS["monthly"], f"{narrative_seed}|intro|monthly"
            )
            return template.format(
                month_year=month_name,
                article=article,
                intensity=intensity_word,
                sign=sign_label,
                area=area,
            )
        template = self._pick_phrase(
            INTRO_PATTERNS["yearly"], f"{narrative_seed}|intro|yearly"
        )
        return template.format(year=timestamp.year, sign=sign_label, area=area)

    def _period_event_line(
        self,
        period: Period,
        period_events: Sequence[PeriodEvent],
        notable_events: Sequence[str],
        narrative_seed: str,
    ) -> str:
        if period == Period.DAILY:
            events = self._timeline_events(
                period, period_events, notable_events, limit=1
            )
            if not events:
                return ""
            return f" {events[0]}."

        if period == Period.WEEKLY:
            cues = self._pick_phrase(
                EVENT_ANCHOR_OPTIONS["weekly"], f"{narrative_seed}|anchors|weekly"
            )
            events = self._timeline_events(
                period, period_events, notable_events, limit=3
            )
        elif period == Period.MONTHLY:
            cues = self._pick_phrase(
                EVENT_ANCHOR_OPTIONS["monthly"], f"{narrative_seed}|anchors|monthly"
            )
            events = self._timeline_events(
                period, period_events, notable_events, limit=3
            )
        else:
            cues = self._pick_phrase(
                EVENT_ANCHOR_OPTIONS["yearly"], f"{narrative_seed}|anchors|yearly"
            )
            events = self._timeline_events(
                period, period_events, notable_events, limit=3
            )

        if not events:
            return ""
        lines = [f"{cue}, {event}." for cue, event in zip(cues, events)]
        return " ".join(lines)

    def _period_close(
        self,
        period: Period,
        section: Section,
        factor_details: Sequence[FactorDetail],
        narrative_seed: str,
    ) -> str:
        if not factor_details:
            return ""
        top = sorted(factor_details, key=lambda item: item.weight, reverse=True)[0]
        tip_key = {
            Period.DAILY: "daily_tip",
            Period.WEEKLY: "weekly_tip",
            Period.MONTHLY: "monthly_tip",
            Period.YEARLY: "yearly_tip",
        }[period]
        tip = (
            top.factor_insights.get(tip_key)
            or top.factor_insights.get("affirmation")
            or ""
        )
        tip = self._editorialize_tip_text(
            tip=tip,
            section=section,
            period=period,
            narrative_seed=narrative_seed,
        )
        if not tip:
            return ""
        return self._ensure_terminal(tip)

    def _factor_highlight(
        self, period: Period, section: Section, detail: FactorDetail
    ) -> str:
        readable = self._readable_factor_value(detail.factor_value)

        if detail.factor_type in (
            "weekly_theme_archetypes",
            "monthly_theme_archetypes",
            "yearly_theme_archetypes",
        ):
            return self._ensure_terminal(
                f"{readable.capitalize()} is setting the tone; consistency beats urgency"
            )
        if detail.factor_type == "retrograde_archetypes":
            return self._ensure_terminal(
                f"{readable.capitalize()} favors review, cleanup, and smarter timing"
            )
        if detail.factor_type == "ingress_archetypes":
            return self._ensure_terminal(
                f"{readable.capitalize()} marks a pivot in focus and pacing"
            )
        if detail.factor_type == "eclipse_archetypes":
            return self._ensure_terminal(
                f"{readable.capitalize()} increases consequence, so intentional choices matter more"
            )
        if detail.factor_type in (
            "daily_house_focus",
            "weekly_house_focus",
            "monthly_house_focus",
            "yearly_house_focus",
        ):
            focus = self._house_focus_line(detail.factor_value, section=section)
            return self._ensure_terminal(
                f"House activation highlights {focus} as the most activated life areas this cycle"
            )

        return self._factor_influence(
            period=period,
            section=section,
            factor_type=detail.factor_type,
            factor_value=detail.factor_value,
        )

    def _factor_influence(
        self, period: Period, section: Section, factor_type: str, factor_value: str
    ) -> str:
        readable = self._readable_factor_value(factor_value)
        sign_tone = self._sign_tone_phrase(factor_value)

        if factor_type == "sun_in_sign":
            return f"Sun in {factor_value.title()} sets the baseline tone: {sign_tone}."
        if factor_type == "moon_in_sign":
            return f"Moon in {factor_value.title()} sets emotional pacing with a {sign_tone} pattern."
        if factor_type == "rising_sign":
            return f"Rising-sign emphasis in {factor_value.title()} shifts presentation toward {sign_tone} expression."
        if factor_type == "jupiter_in_sign":
            return f"Jupiter in {factor_value.title()} supports growth through steady, intentional expansion."
        if factor_type == "saturn_in_sign":
            return f"Saturn in {factor_value.title()} rewards structure, pacing, and durable boundaries."
        if factor_type == "chiron_in_sign":
            return f"Chiron in {factor_value.title()} emphasizes repair, integration, and practical self-trust."

        if factor_type == "aspects":
            if factor_value in ("trine", "sextile", "conjunction"):
                return self._factor_line_variation(
                    [
                        "{readable_cap} aspect pressure supports smoother execution and cleaner timing.",
                        "{readable_cap} patterns improve coordination and reduce friction.",
                        "With {readable} active, progress is easier when plans stay simple.",
                    ],
                    period,
                    section,
                    factor_type,
                    factor_value,
                    readable=readable,
                    readable_cap=readable.capitalize(),
                )
            if factor_value in ("square", "opposition", "quincunx"):
                return self._factor_line_variation(
                    [
                        "{readable_cap} aspect pressure adds friction that requires deliberate pacing.",
                        "{readable_cap} dynamics increase load, but clear priorities keep it workable.",
                        "With {readable} active, precision matters more than speed.",
                    ],
                    period,
                    section,
                    factor_type,
                    factor_value,
                    readable=readable,
                    readable_cap=readable.capitalize(),
                )
            return self._factor_line_variation(
                [
                    "Current aspect climate is centered on {readable} patterns.",
                    "{readable_cap} signatures are carrying most of the current pressure.",
                ],
                period,
                section,
                factor_type,
                factor_value,
                readable=readable,
                readable_cap=readable.capitalize(),
            )

        if factor_type == "transits_archetypes":
            mapping = {
                "conjunction_growth": "Conjunction growth concentrates effort into one clear opportunity.",
                "conjunction_challenge": "Conjunction challenge compresses pressure and requires tighter prioritization.",
                "trine_harmony": [
                    "Trine harmony improves flow when collaboration and timing are aligned.",
                    "Trine harmony keeps momentum usable with less resistance.",
                    "With trine harmony active, straightforward execution works best.",
                ],
                "sextile_opportunity": "Sextile opportunity rewards initiative and practical follow-through.",
                "square_tension": "Square tension forces clearer trade-offs between competing priorities.",
                "opposition_conflict": "Opposition conflict highlights two valid needs that must be balanced.",
                "retrograde_review": [
                    "Retrograde review favors revision before expansion.",
                    "Retrograde review is active, so edits beat rushed decisions.",
                    "This review cycle rewards cleanup before new commitments.",
                ],
                "emotional_flow": "Emotional flow increases sensitivity and timing awareness.",
                "communication_flow": "Communication flow favors direct language and clear intent.",
                "relationship_tension": "Relationship tension requires explicit standards and cleaner boundaries.",
                "action_activation": [
                    "Action activation rewards decisive movement with measurable follow-through.",
                    "Action activation is high, so traction comes from clear next steps.",
                    "With action activation online, commitment plus execution works best.",
                ],
                "discipline_restriction": "Discipline restriction rewards structure over impulse.",
                "creativity_flow": "Creativity flow is strongest when paired with routine execution.",
                "introspection_phase": "Introspection phase supports review before the next push.",
                "decision_point": "Decision point asks for commitment after honest review.",
                "financial_focus": "Financial focus highlights budgeting, pricing, and value alignment.",
                "health_awareness": "Health awareness emphasizes recovery and energy management.",
                "networking_energy": "Networking energy favors outreach and practical alliances.",
                "adventure_call": "Adventure call supports calculated expansion and perspective shifts.",
                "learning_opportunity": "Learning opportunity links progress to skill-building.",
                "spiritual_alignment": "Spiritual alignment supports value-led decisions over noise.",
            }
            mapped = mapping.get(factor_value)
            if isinstance(mapped, list):
                return self._factor_line_variation(
                    mapped,
                    period,
                    section,
                    factor_type,
                    factor_value,
                )
            if isinstance(mapped, str):
                return mapped
            return f"Transit driver {readable} is influencing decisions in this cycle."

        if factor_type in (
            "weekly_theme_archetypes",
            "monthly_theme_archetypes",
            "yearly_theme_archetypes",
        ):
            return self._factor_line_variation(
                [
                    "Core theme is {readable}; consistency matters more than speed.",
                    "{readable_cap} is dominant, so steady execution is the advantage.",
                    "With {readable} leading this cycle, durable progress comes from consistency.",
                ],
                period,
                section,
                factor_type,
                factor_value,
                readable=readable,
                readable_cap=readable.capitalize(),
            )
        if factor_type in ("weekly_moon_phase", "monthly_lunation_archetypes"):
            return self._factor_line_variation(
                [
                    "Lunation rhythm points to {readable}, setting the emotional pace for this {period_value} window.",
                    "{readable_cap} lunar timing sets the emotional cadence of this {period_value} cycle.",
                    "With {readable} active, emotional pacing matters as much as action timing.",
                ],
                period,
                section,
                factor_type,
                factor_value,
                readable=readable,
                readable_cap=readable.capitalize(),
                period_value=period.value,
            )
        if factor_type == "retrograde_archetypes":
            return self._factor_line_variation(
                [
                    "Retrograde signature highlights {readable}; review and cleanup beat rushing.",
                    "{readable_cap} retrograde tone favors revision and better timing.",
                    "With {readable} active, slower review beats fast assumptions.",
                ],
                period,
                section,
                factor_type,
                factor_value,
                readable=readable,
                readable_cap=readable.capitalize(),
            )
        if factor_type == "ingress_archetypes":
            return self._factor_line_variation(
                [
                    "Ingress pattern shows {readable}, signaling a shift in focus and timing.",
                    "{readable_cap} ingress movement marks a clear priority pivot.",
                    "Ingress timing points to {readable}, so the cycle is reorienting.",
                ],
                period,
                section,
                factor_type,
                factor_value,
                readable=readable,
                readable_cap=readable.capitalize(),
            )
        if factor_type == "planetary_focus":
            if factor_value == "eclipse_focus":
                return "Eclipse windows are active focus, so clarity and pacing are non-negotiable."
            if factor_value == "nodes_focus":
                return "Lunar nodes are active focus, pointing to directional pivots."
            if factor_value.endswith("_focus"):
                planet = factor_value.replace("_focus", "").replace("_", " ").title()
                return f"{planet} is the active focus; prioritize its themes for faster traction."
            return (
                f"Planetary focus is {readable}; this is where traction builds fastest."
            )
        if factor_type == "eclipse_archetypes":
            if factor_value == "no_eclipse":
                return "Eclipse activity is low this cycle, so consistency and pacing carry the edge."
            return self._factor_line_variation(
                [
                    "Eclipse tone of {readable} raises stakes and increases consequence.",
                    "{readable_cap} eclipse emphasis requires clearer decisions.",
                    "With {readable} active in the eclipse layer, choices carry longer effects.",
                ],
                period,
                section,
                factor_type,
                factor_value,
                readable=readable,
                readable_cap=readable.capitalize(),
            )
        if factor_type == "outer_planet_focus":
            mapping = {
                "uranus_shift": "Outer-planet signal: Uranus shift favors reinvention and strategic flexibility.",
                "neptune_dreamwork": "Outer-planet signal: Neptune dreamwork raises intuition and requires reality checks.",
                "pluto_transformation": "Outer-planet signal: Pluto transformation supports deep restructuring.",
                "chiron_healing": "Outer-planet signal: Chiron healing supports repair and integration.",
                "saturn_structure": "Outer-planet signal: Saturn structure rewards discipline and planning.",
                "jupiter_expansion": "Outer-planet signal: Jupiter expansion opens growth when choices stay intentional.",
            }
            return mapping.get(
                factor_value,
                f"Outer-planet thread of {readable} shapes slower but durable background effects.",
            )
        if factor_type == "nodal_axis":
            return f"Nodal axis emphasis on {readable} points toward growth through reorientation."
        if factor_type in (
            "daily_house_focus",
            "weekly_house_focus",
            "monthly_house_focus",
            "yearly_house_focus",
        ):
            focus = self._house_focus_line(factor_value, section=section)
            house_label = readable.replace(" house", "").strip()
            return self._factor_line_variation(
                [
                    "House activation centers on {readable}, making {focus} the primary life-area driver.",
                    "{house_label_cap} house emphasis keeps attention on {focus}.",
                    "House layer is concentrated in {readable}, so {focus} remains central.",
                    "{focus_cap} stays highlighted because house signal is strongest in {readable}.",
                ],
                period,
                section,
                factor_type,
                factor_value,
                readable=readable,
                house_label_cap=house_label[:1].upper() + house_label[1:],
                focus=focus,
                focus_cap=focus[:1].upper() + focus[1:],
            )
        return f"{factor_type.replace('_', ' ').title()} driver is {readable}."

    def _section_voice(self, section: Section) -> Dict[str, str]:
        if section in SECTION_VOICE:
            return SECTION_VOICE[section]
        if section in (Section.LOVE_SINGLES, Section.LOVE_COUPLES):
            return SECTION_VOICE[section]
        return SECTION_VOICE[Section.GENERAL]

    def _apply_section_lens(
        self, line: str, section: Section, factor_type: str, index: int
    ) -> str:
        if index != 0 or section == Section.GENERAL:
            return line
        lens_map = {
            Section.LOVE_SINGLES: "Dating lens: keep standards explicit and prioritize reciprocity.",
            Section.LOVE_COUPLES: "Partnership lens: favor repair, listening, and aligned expectations.",
            Section.CAREER: "Career lens: translate this into measurable output and clear priorities.",
            Section.FRIENDSHIP: "Friendship lens: invest where effort and loyalty are mutual.",
            Section.HEALTH: "Health lens: convert this into recovery and sustainable pacing.",
            Section.MONEY: "Money lens: apply this through value-led decisions and disciplined timing.",
            Section.COMMUNICATION: "Communication lens: prioritize precision, timing, and active listening.",
            Section.LIFESTYLE: "Lifestyle lens: keep routines that stabilize energy and reduce noise.",
        }
        lens = lens_map.get(section)
        if not lens:
            return line
        return f"{line} {lens}"

    def _section_focus(self, section: Section) -> str:
        mapping = {
            Section.GENERAL: "your overall direction",
            Section.LOVE_SINGLES: "dating, attraction, and emotional openness",
            Section.LOVE_COUPLES: "partnership rhythm, repair, and intimacy",
            Section.CAREER: "work visibility, priorities, and execution",
            Section.FRIENDSHIP: "community, loyalty, and social alignment",
            Section.HEALTH: "energy management, recovery, and habits",
            Section.MONEY: "resources, spending choices, and value alignment",
            Section.COMMUNICATION: "clarity, timing, and message impact",
            Section.LIFESTYLE: "daily structure, environment, and sustainability",
        }
        return mapping.get(section, section.value.replace("_", " "))

    def _sign_tone_phrase(self, sign: str) -> str:
        sign = sign.upper()
        if sign in {"ARIES", "LEO", "SAGITTARIUS"}:
            return "bold, direct, and action-led"
        if sign in {"TAURUS", "VIRGO", "CAPRICORN"}:
            return "practical, grounded, and steady"
        if sign in {"GEMINI", "LIBRA", "AQUARIUS"}:
            return "social, idea-driven, and mentally agile"
        if sign in {"CANCER", "SCORPIO", "PISCES"}:
            return "intuitive, emotional, and receptive"
        return "focused and intentional"

    def _timeline_events(
        self,
        period: Period,
        period_events: Sequence[PeriodEvent],
        notable_events: Sequence[str],
        limit: int,
    ) -> List[str]:
        candidates: List[Tuple[int, Optional[Tuple[int, int]], int, str]] = []
        seen = set()

        for index, event in enumerate(period_events):
            rendered = self._render_period_event(event)
            if not rendered:
                continue
            dedupe_key = self._event_dedupe_key(rendered)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            body = event.body1 or event.body2 or self._event_body(rendered)
            priority = self._event_priority(period, body)
            date_key = (event.timestamp.month, event.timestamp.day)
            candidates.append((priority, date_key, index, rendered))

        if len(candidates) < limit:
            offset = len(candidates)
            for index, raw in enumerate(notable_events):
                normalized = self._humanize_event(raw)
                if not normalized:
                    continue
                dedupe_key = self._event_dedupe_key(normalized)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                body = self._event_body(normalized)
                priority = self._event_priority(period, body)
                date_key = self._event_date_key(normalized)
                candidates.append((priority, date_key, offset + index, normalized))

        if not candidates:
            return []

        shortlist_size = max(limit * 3, limit)
        prioritized = sorted(candidates, key=lambda row: (row[0], row[2]))[
            :shortlist_size
        ]
        chronological = sorted(
            prioritized,
            key=lambda row: (
                row[1] if row[1] is not None else (99, 99),
                row[2],
            ),
        )
        picked: List[str] = []
        used_dates = set()
        for _, date_key, _, text in chronological:
            if (
                period in (Period.WEEKLY, Period.MONTHLY, Period.YEARLY)
                and date_key is not None
                and date_key in used_dates
            ):
                continue
            if date_key is not None:
                used_dates.add(date_key)
            picked.append(text)
            if len(picked) >= limit:
                return picked

        for _, _, _, text in chronological:
            if text in picked:
                continue
            picked.append(text)
            if len(picked) >= limit:
                break
        return picked[:limit]

    def _render_period_event(self, event: PeriodEvent) -> str:
        date_part = event.timestamp.strftime("%b %d")
        event_type = event.event_type
        if event_type == "ingress" and event.body1 and event.sign:
            return f"{event.body1} moves into {event.sign.title()} on {date_part}"
        if event_type == "station" and event.body1:
            detail = "stations"
            if event.description:
                lowered = event.description.lower()
                if "retrograde" in lowered:
                    detail = "stations retrograde"
                elif "direct" in lowered:
                    detail = "stations direct"
            return f"{event.body1} {detail} on {date_part}"
        if (
            event_type == "exact_aspect"
            and event.body1
            and event.body2
            and event.aspect
        ):
            return f"{event.body1} {event.aspect} {event.body2} peaks on {date_part}"
        if event_type == "lunation":
            label = "New Moon window"
            if event.description and "full" in event.description.lower():
                label = "Full Moon window"
            return f"{label} on {date_part}"
        if event_type == "eclipse":
            label = "Eclipse window"
            if event.description:
                if "solar" in event.description.lower():
                    label = "Solar eclipse window"
                elif "lunar" in event.description.lower():
                    label = "Lunar eclipse window"
            return f"{label} on {date_part}"
        if event_type == "retrograde_emphasis" and event.body1:
            return f"{event.body1} keeps review themes active"
        return self._humanize_event(event.description)

    def _humanize_event(self, event: str) -> str:
        line = self._clean_line(event).rstrip(".")
        if not line:
            return ""
        if " enters " in line:
            body, rest = line.split(" enters ", 1)
            line = f"{body} moves into {rest}"
        if line.endswith("retrograde emphasis"):
            line = line.replace(" retrograde emphasis", " keeps review themes active")
        return self._normalize_sign_case(line)

    def _event_body(self, event: str) -> str:
        for node_body in ("North Node", "South Node"):
            if event.startswith(node_body):
                return node_body
        return event.split(" ", 1)[0]

    def _event_priority(self, period: Period, body: str) -> int:
        if period == Period.WEEKLY:
            order = ["Moon", "Mercury", "Venus", "Mars", "Sun", "Jupiter", "Saturn"]
        elif period == Period.MONTHLY:
            order = [
                "Sun",
                "Mercury",
                "Venus",
                "Mars",
                "Moon",
                "Jupiter",
                "Saturn",
                "North Node",
                "South Node",
            ]
        elif period == Period.YEARLY:
            order = [
                "Jupiter",
                "Saturn",
                "North Node",
                "South Node",
                "Uranus",
                "Neptune",
                "Pluto",
                "Chiron",
                "Sun",
                "Moon",
            ]
        else:
            order = ["Moon", "Sun", "Mercury", "Venus", "Mars"]
        if body in order:
            return order.index(body)
        return len(order) + 5

    def _event_date_key(self, event: str) -> Optional[Tuple[int, int]]:
        match = re.search(r" on ([A-Za-z]{3}) (\d{2})$", event)
        if not match:
            return None
        month_map = {
            "Jan": 1,
            "Feb": 2,
            "Mar": 3,
            "Apr": 4,
            "May": 5,
            "Jun": 6,
            "Jul": 7,
            "Aug": 8,
            "Sep": 9,
            "Oct": 10,
            "Nov": 11,
            "Dec": 12,
        }
        month = month_map.get(match.group(1).title())
        if not month:
            return None
        return month, int(match.group(2))

    def _event_dedupe_key(self, event: str) -> str:
        if " on " in event:
            return event.rsplit(" on ", 1)[0]
        return event

    def _supporting_line(
        self, detail: FactorDetail, period: Period, position: int
    ) -> str:
        tip_key = {
            Period.DAILY: "daily_tip",
            Period.WEEKLY: "weekly_tip",
            Period.MONTHLY: "monthly_tip",
            Period.YEARLY: "yearly_tip",
        }[period]
        key_orders = [
            ["motivation", "reflection", "affirmation"],
            ["reflection", "motivation", "affirmation"],
            [tip_key, "affirmation", "motivation"],
        ]
        keys = key_orders[min(position, len(key_orders) - 1)]
        for key in keys:
            line = detail.factor_insights.get(key)
            cleaned = self._clean_line(line)
            if cleaned:
                return cleaned
        return ""

    def _editorialize_tip_text(
        self, tip: str, section: Section, period: Period, narrative_seed: str
    ) -> str:
        text = self._clean_line(tip)
        if not text:
            return ""
        text = self._normalize_sign_case(text)
        text = text.replace("e. g.", "e.g.").replace("i. e.", "i.e.")
        lower = text.lower()

        for marker in ("daily tip:", "weekly tip:", "monthly tip:", "yearly tip:"):
            if lower.startswith(marker):
                text = text.split(":", 1)[1].strip()
                lower = text.lower()
                break

        if "?" in text:
            prompt, _, remainder = text.partition("?")
            question = f"{prompt.strip()}?"
            tail = self._support_tail(
                section, "question", f"{narrative_seed}|close_tip", 0
            )
            if remainder.strip():
                return self._ensure_terminal(f"{question} {remainder.strip()} {tail}")
            return self._ensure_terminal(f"{question} {tail}")

        if lower.startswith(
            (
                "start ",
                "pair ",
                "delegate ",
                "schedule ",
                "invest ",
                "end ",
                "set ",
                "block ",
                "write ",
                "review ",
                "choose ",
                "focus ",
                "avoid ",
                "use ",
            )
        ):
            tail = self._support_tail(
                section, "action", f"{narrative_seed}|close_tip", 0
            )
            return self._ensure_terminal(f"{text} {tail}")

        tail = self._support_tail(section, "reflect", f"{narrative_seed}|close_tip", 0)
        return self._ensure_terminal(f"{text} {tail}")

    def _editorialize_support(
        self, line: str, section: Section, narrative_seed: str, index: int
    ) -> str:
        text = self._clean_line(line)
        if not text:
            return ""
        text = self._normalize_sign_case(text)
        text = text.replace("e. g.", "e.g.").replace("i. e.", "i.e.")
        lower = text.lower()
        if lower.startswith("ask yourself:"):
            text = text.split(":", 1)[1].strip()
        elif lower.startswith("ask:"):
            text = text.split(":", 1)[1].strip()

        if lower.startswith(
            (
                "start ",
                "pair ",
                "delegate ",
                "schedule ",
                "invest ",
                "end ",
                "set ",
                "block ",
                "write ",
                "review ",
                "choose ",
                "focus ",
                "avoid ",
                "use ",
            )
        ):
            opener = self._pick_phrase(
                SUPPORT_ACTION_OPENERS,
                f"{narrative_seed}|support_action_opener|{section.value}|{index}",
            )
            if opener.strip() == "{text}":
                phrased_text = text
            else:
                phrased_text = opener.format(text=self._lowercase_initial(text))
            phrased_text = (
                phrased_text[:1].upper() + phrased_text[1:]
                if phrased_text
                else phrased_text
            )
            tail = self._support_tail(section, "action", narrative_seed, index)
            return self._ensure_terminal(f"{phrased_text} {tail}")

        tail = self._support_tail(section, "reflect", narrative_seed, index)
        return self._ensure_terminal(f"{text} {tail}")

    def _support_tail(
        self, section: Section, mode: str, narrative_seed: str, index: int
    ) -> str:
        section_tails = SUPPORT_TAILS.get(section, SUPPORT_TAILS[Section.GENERAL])
        options = section_tails.get(mode, SUPPORT_TAILS[Section.GENERAL]["reflect"])
        return self._pick_phrase(
            options, f"{narrative_seed}|support_tail|{section.value}|{mode}|{index}"
        )

    def _ensure_terminal(self, text: str) -> str:
        out = self._clean_line(text)
        if not out:
            return ""
        if out.endswith((".", "!", "?")):
            return out
        return f"{out}."

    def _connect_influence_line(
        self, influence: str, support: str, index: int, narrative_seed: str
    ) -> str:
        if index <= 0:
            return f"{influence} {support}"
        connector = self._pick_phrase(
            INFLUENCE_CONNECTORS,
            f"{narrative_seed}|influence_connector|{index}",
        )
        influence = self._decapitalize_leading(influence)
        return f"{connector} {influence} {support}"

    def _dynamic_close_line(
        self, base: str, period_key: str, narrative_seed: str
    ) -> str:
        options = [
            base,
            f"{base} Keep this as your closing compass.",
            f"{base} Let that set the next move.",
        ]
        return self._pick_phrase(
            options, f"{narrative_seed}|dynamic_close|{period_key}"
        )

    def _smooth_narrative(self, paragraph: str) -> str:
        text = " ".join(paragraph.split())
        text = self._normalize_sign_case(text)
        text = text.replace("..", ".")
        text = text.replace(" .", ".")
        text = text.replace(" ,", ",")
        text = text.replace("Final note: Final note:", "Final note:")
        text = text.replace("Bottom line: Bottom line:", "Bottom line:")
        text = re.sub(r"\s+([!?])", r"\1", text)
        segments = [
            chunk.strip() for chunk in re.split(r"(?<=[.!?])\s+", text) if chunk.strip()
        ]
        deduped: List[str] = []
        seen = set()
        for segment in segments:
            key = re.sub(r"[^a-z0-9]+", "", segment.lower())
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(segment)
        return " ".join(deduped).strip()

    def _narrative_seed(
        self,
        period: Period,
        sign: str,
        section: Section,
        timestamp: datetime,
        intensity: str,
    ) -> str:
        return (
            f"{period.value}|{sign}|{section.value}|{timestamp.date().isoformat()}|"
            f"{timestamp.year}|{timestamp.month}|{intensity}"
        )

    def _pick_phrase(self, options: Sequence, seed: str):
        if not options:
            return ""
        index = stable_index(seed, len(options))
        return options[index]

    def _factor_line_variation(
        self,
        options: Sequence[str],
        period: Period,
        section: Section,
        factor_type: str,
        factor_value: str,
        **kwargs: str,
    ) -> str:
        seed = (
            f"{self._variation_cycle_seed}|{period.value}|{section.value}|"
            f"{factor_type}|{factor_value}|line_variant"
        )
        template = self._pick_phrase(options, seed)
        return template.format(**kwargs)

    def _readable_factor_value(self, value: str) -> str:
        return value.replace("_", " ").strip()

    def _normalize_sign_case(self, text: str) -> str:
        return re.sub(
            r"\b(ARIES|TAURUS|GEMINI|CANCER|LEO|VIRGO|LIBRA|SCORPIO|SAGITTARIUS|CAPRICORN|AQUARIUS|PISCES)\b",
            lambda m: m.group(1).title(),
            text,
        )

    def _indefinite_article(self, word: str) -> str:
        return "an" if word[:1].lower() in {"a", "e", "i", "o", "u"} else "a"

    def _clean_line(self, line: str) -> str:
        if not line:
            return ""
        text = " ".join(str(line).split())
        return text.replace("*", "").strip()

    def _decapitalize_leading(self, text: str) -> str:
        if not text:
            return ""
        for token in (
            "The ",
            "A ",
            "An ",
            "With ",
            "Retrograde ",
            "Ingress ",
            "Eclipse ",
            "Lunation ",
            "House ",
            "Aspect ",
            "Trine ",
            "Square ",
            "Opposition ",
        ):
            if text.startswith(token):
                return token.lower() + text[len(token) :]
        return text

    def _lowercase_initial(self, text: str) -> str:
        if not text:
            return ""
        if len(text) == 1:
            return text.lower()
        return text[0].lower() + text[1:]

    def _as_str_list(self, value) -> List[str]:
        if not isinstance(value, list):
            return []
        return [
            self._clean_line(item)
            for item in value
            if isinstance(item, str) and self._clean_line(item)
        ]
