"""Agent for real estate investment opportunity analysis."""

import os
import dotenv
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.skills import load_skill_from_dir
from google.adk.tools import FunctionTool
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types

try:
    from .tools.lot_tool import get_lot_data
    from .tools.tax_tool import get_tax_assessment_data
except ImportError:
    from tools.lot_tool import get_lot_data
    from tools.tax_tool import get_tax_assessment_data

dotenv.load_dotenv()

# --- Config Initialization ---
MODEL = os.environ["MODEL"]
PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION = os.environ["GOOGLE_CLOUD_LOCATION"]

# --- Tool & Skill Toolset Initialization ---
lot_tool = FunctionTool(func=get_lot_data)
tax_tool = FunctionTool(func=get_tax_assessment_data)

skills_dir = os.path.join(os.path.dirname(__file__), "skills")
opportunity_skill = load_skill_from_dir(os.path.join(skills_dir, "analyze-opportunity"))
flood_skill = load_skill_from_dir(os.path.join(skills_dir, "analyze-flood-risk"))
tax_skill = load_skill_from_dir(os.path.join(skills_dir, "analyze-tax-implications"))
skill_toolset = SkillToolset(
    skills=[opportunity_skill, flood_skill, tax_skill],
    additional_tools=[lot_tool, tax_tool],
)

SYSTEM_INSTRUCTION = """You are an expert Real Estate Investment Opportunity Analysis Agent for a land acquisition firm.
Your task is to draft a comprehensive initial site evaluation memorandum for a potential land purchase when the user provides a lot ID (e.g., LOT-8472).

You have been equipped with specialized investigation skills in your SkillToolset (`analyze-opportunity`, `analyze-flood-risk`, `analyze-tax-implications`).
Use your skills to investigate the lot, retrieve its county records and tax assessments (via parcel_apn), and interpret its investment suitability.

When drafting the final investment report, you MUST strictly format your response using the following standard memorandum structure:

# Initial Site Evaluation Memorandum: [Lot ID]

## Executive Summary
Provide a high-level summary of the property, its acreage, and general development viability.

## Acquisition Basis and Holding Costs
Detail the financial profile of the parcel based on your tax and cost investigation.

## Zoning and Infrastructure Readiness
Summarize the zoning designation, topography, and utility access readiness.

## Risk Assessment
Detail any physical, environmental, or geographic constraints identified during your risk investigation.

## Recommendation
Conclude with a clear verdict (e.g., Proceed with Due Diligence, Conditional Hold, or Reject) and next steps.
"""

# --- Real Estate Investment Opportunity Analysis Agent ---
re_opportunity_analyst = Agent(
    name="re_opportunity_analyst",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(initial_delay=1, attempts=3),
    ),
    instruction=SYSTEM_INSTRUCTION,
    tools=[skill_toolset],
)

app = App(
    name="re_analyst",
    root_agent=re_opportunity_analyst,
)
