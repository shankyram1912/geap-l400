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

"""Unit tests for A2A agent card specification."""

import pytest
from a2a.types import AgentCard
from app.app_utils.a2a import _get_single_skill, _add_v0_3_compat_interface


@pytest.mark.asyncio
async def test_single_skill_specification() -> None:
    skill = _get_single_skill()
    assert skill.id == "semantic_bug_search"
    assert "semantic search" in skill.description.lower()
    assert "FastAPI returns a 500 on startup after a dependency bump." in skill.examples


@pytest.mark.asyncio
async def test_card_customization() -> None:
    card = AgentCard(name="bq_agent")
    card = await _add_v0_3_compat_interface(card)
    assert len(card.skills) == 1
    assert card.skills[0].id == "semantic_bug_search"
    assert "FastAPI returns a 500 on startup after a dependency bump." in card.skills[0].examples
