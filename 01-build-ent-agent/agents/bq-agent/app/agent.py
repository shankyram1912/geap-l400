# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from dotenv import load_dotenv

load_dotenv()

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from app.tools import find_similar_bugs

MODEL = os.getenv("MODEL", "gemini-3.5-flash")

AGENT_INSTRUCTION = """\
You are a specialist bug database assistant that answers one question well: \
"Have we seen this software problem before, and how was it fixed?"

You perform semantic search over an internal database of past engineering incidents in BigQuery \
using the `find_similar_bugs` tool.

Operational Rules:
1. When presented with any software problem, error message, stack trace, dependency issue, or symptom, \
always call the `find_similar_bugs` tool with the problem description to find matching incidents.
2. Grounded answers only: Summarize and explain ONLY what the search results return. Never invent, \
hallucinate, or assume past incidents, causes, bug IDs, or resolutions.
3. Citations: Explicitly cite each `bug_id` (e.g. BUG-1001) used in your answer.
4. Precision and Conciseness: Be concise, practical, and clear. State the problem seen in the past incident, \
and detail the concrete resolution that fixed it.
5. If the search returns "no similar bugs found" or if the retrieved incidents are completely unrelated \
to the user's issue, clearly and politely inform the user that no similar bugs or past incidents \
were found in the database.
6. If the search tool indicates that the service or database is unavailable, relay that graceful \
degradation message directly.
"""

root_agent = Agent(
    # Keep in sync with agents-cli-manifest.yaml: agents-cli derives this name
    # from the project `name:` recorded there, and telemetry reports it as
    # gen_ai.agent.name. Renaming the agent only here makes the two disagree,
    # and anything selecting traces by name stops finding this agent's.
    name="bq_agent",
    description="Specialist agent that searches internal BigQuery bug database for past incidents and resolutions.",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=AGENT_INSTRUCTION,
    tools=[find_similar_bugs],
)

app = App(
    root_agent=root_agent,
    name="app",
)
