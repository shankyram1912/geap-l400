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

"""Unit tests for bq-agent tools and error degradation."""

from unittest.mock import MagicMock, patch
from app.tools import find_similar_bugs


def test_find_similar_bugs_empty() -> None:
    assert find_similar_bugs("") == "no similar bugs found"
    assert find_similar_bugs("   \n\t  ") == "no similar bugs found"


def test_find_similar_bugs_embedding_error() -> None:
    with patch("app.tools._get_genai_client") as mock_client:
        mock_client.side_effect = RuntimeError("Embedding quota exceeded")
        res = find_similar_bugs("FastAPI startup error")
        assert "Embedding service is temporarily unavailable" in res


def test_find_similar_bugs_bigquery_error() -> None:
    mock_embed_client = MagicMock()
    mock_embed_resp = MagicMock()
    mock_embed_resp.embeddings = [MagicMock(values=[0.1] * 768)]
    mock_embed_client.models.embed_content.return_value = mock_embed_resp

    with patch("app.tools._get_genai_client", return_value=mock_embed_client):
        with patch("app.tools._get_bigquery_client") as mock_bq_client:
            mock_bq_client.side_effect = RuntimeError("BigQuery connection failure")
            res = find_similar_bugs("FastAPI startup error")
            assert "Bug database is temporarily unavailable" in res


def test_find_similar_bugs_empty_bq_results() -> None:
    mock_embed_client = MagicMock()
    mock_embed_resp = MagicMock()
    mock_embed_resp.embeddings = [MagicMock(values=[0.1] * 768)]
    mock_embed_client.models.embed_content.return_value = mock_embed_resp

    mock_bq = MagicMock()
    mock_job = MagicMock()
    mock_job.result.return_value = []
    mock_bq.query.return_value = mock_job

    with patch("app.tools._get_genai_client", return_value=mock_embed_client):
        with patch("app.tools._get_bigquery_client", return_value=mock_bq):
            res = find_similar_bugs("FastAPI startup error")
            assert res == "no similar bugs found"


def test_find_similar_bugs_canonical_query() -> None:
    """Live test verifying BUG-1001 is retrieved for the canonical query."""
    res = find_similar_bugs("FastAPI returns a 500 on startup after a dependency bump.")
    assert "BUG-1001" in res
    assert "Pydantic" in res or "pydantic" in res
    assert "Cosine Distance:" in res
