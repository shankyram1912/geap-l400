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

"""Tools for bq-agent: BigQuery semantic bug search."""

import logging
import os

from google import genai
from google.cloud import bigquery

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-004"
DEFAULT_EMBEDDING_LOCATION = "us-central1"
DEFAULT_BQ_DATASET = "code_assist_bugs"
DEFAULT_BQ_TABLE = "known_bugs"


def _get_project_id() -> str:
    return (
        os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("PROJECT_ID")
        or "qwiklabs-gcp-04-e1403f6389d6"
    )


def _get_genai_client() -> genai.Client:
    project_id = _get_project_id()
    location = os.getenv("EMBEDDING_LOCATION", DEFAULT_EMBEDDING_LOCATION)
    return genai.Client(vertexai=True, project=project_id, location=location)


def _get_bigquery_client() -> bigquery.Client:
    project_id = _get_project_id()
    location = os.getenv("BIGQUERY_LOCATION", "US")
    return bigquery.Client(project=project_id, location=location)


def find_similar_bugs(query: str) -> str:
    """Perform semantic search over internal engineering incidents in BigQuery.

    Embeds the problem description using text-embedding-004 and retrieves the top 3
    most similar past incidents and their resolutions via BigQuery VECTOR_SEARCH.

    Args:
        query: Free-text problem description, including error messages, stack traces,
               symptoms, or affected frameworks.

    Returns:
        Structured string listing matching bugs with their bug_id, title, description,
        resolution, and cosine distance, or 'no similar bugs found'.
    """
    if not query or not query.strip():
        return "no similar bugs found"

    # Step 1: Embed query with text-embedding-004 in table's region (us-central1)
    try:
        genai_client = _get_genai_client()
        embed_resp = genai_client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=query.strip(),
        )
        if not embed_resp.embeddings or not embed_resp.embeddings[0].values:
            logger.error("Empty embeddings returned from embedding model")
            return "Unable to generate query embedding at this time."
        query_vector = embed_resp.embeddings[0].values
    except Exception as e:
        logger.warning("Error generating embedding for query: %s", e)
        return "Embedding service is temporarily unavailable. Unable to search bug database at this time."

    # Step 2: Query BigQuery VECTOR_SEARCH over code_assist_bugs.known_bugs
    try:
        project_id = _get_project_id()
        bq_client = _get_bigquery_client()

        table_ref = f"`{project_id}.{DEFAULT_BQ_DATASET}.{DEFAULT_BQ_TABLE}`"
        sql = f"""
        SELECT
            base.bug_id,
            base.title,
            base.description,
            base.resolution,
            distance
        FROM VECTOR_SEARCH(
            TABLE {table_ref},
            'description_embedding',
            (SELECT @query_vector AS query_vector),
            top_k => 3,
            distance_type => 'COSINE'
        )
        ORDER BY distance ASC
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("query_vector", "FLOAT64", query_vector)
            ]
        )
        query_job = bq_client.query(sql, job_config=job_config)
        rows = list(query_job.result())
    except Exception as e:
        logger.warning("Error executing BigQuery VECTOR_SEARCH: %s", e)
        return "Bug database is temporarily unavailable. Unable to search past incidents at this time."

    if not rows:
        return "no similar bugs found"

    matches = []
    for row in rows:
        distance_val = f"{row.distance:.4f}" if row.distance is not None else "N/A"
        matches.append(
            f"Bug ID: {row.bug_id}\n"
            f"Title: {row.title}\n"
            f"Cosine Distance: {distance_val}\n"
            f"Description: {row.description}\n"
            f"Resolution: {row.resolution}"
        )

    return "\n\n---\n\n".join(matches)
