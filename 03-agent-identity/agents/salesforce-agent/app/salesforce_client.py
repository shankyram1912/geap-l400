class SalesforceClient:
    """auth provider to search Salesforce Files (no credentials of its own).

    Holds only the org's My Domain and REST API version. The app access token is
    resolved by Auth Manager and passed in per call; the REST instance URL is
    derived from the My Domain (``https://< domain>``).
    """

    def __init__(
        self,
        domain: str,
        api_version: str | None = None,
    ):
        # Accept either a bare host or a full URL for the org's My Domain.
        self.domain = domain.replace("https://", "").replace("http://", "").strip("/")
        self.api_version = api_version or _DEFAULT_API_VERSION
        # With My Domain / Enhanced Domains, the My Domain host is a valid API
        # instance URL. Auth Manager does not surface Salesforce's instance_url,
        # so the REST base is derived here instead of from the token response.
        self.instance_url = f"https://{self.domain}"

    def download_version_text(
        self, access_token: str, version_id: str, name: str
    ) -> str:
        """Downloads a file version's bytes and extracts plain text.

        Args:
            access_token: An app access token resolved by Auth Manager.
            version_id: The ``ContentVersion`` id.
            name: The file name (its extension selects the text extractor).

        Returns:
            The extracted text, or ``""`` for unsupported file types.
        """
        resp = requests.get(
            f"{self.instance_url}/services/data/{self.api_version}"
            f"/sobjects/ContentVersion/{version_id}/VersionData",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=_CONTENT_TIMEOUT_SECONDS,
        )
        _raise_for_status(resp)
        return _extract_text(name, resp.content)

    def search_files(self, access_token: str, query: str) -> list:
        """Searches Salesforce Files (ContentVersion) via SOSL full-text search.

        Uses ``GET /services/data/vXX.X/search`` with a SOSL ``FIND`` so it spans
        every file the app can read, restricted to the latest version of each.
        The top ``_ENRICH_TOP_K`` hits are enriched with a text excerpt built from
        the downloaded file bytes (SOSL itself returns no content snippet).

        Args:
            access_token: An app access token resolved by Auth Manager.
            query: The user's search terms.

        Returns:
            A list of ``{'name', 'url', 'snippet'}`` dicts for matching files.
        """
        resp = requests.get(
            f"{self.instance_url}/services/data/{self.api_version}/search",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"q": _build_sosl(query)},
            timeout=_TIMEOUT_SECONDS,
        )
        _raise_for_status(resp)

        documents = []
        for i, record in enumerate(resp.json().get("searchRecords", [])):
            version_id = record.get("Id")
            document_id = record.get("ContentDocumentId")
            name = _file_name(record.get("Title"), record.get("FileExtension"))
            snippet = ""
            # Only download + excerpt the top hits to bound latency/cost.
            if i < _ENRICH_TOP_K and version_id:
                try:
                    text = self.download_version_text(access_token, version_id, name)
                    snippet = _build_excerpt(text, query)
                except Exception:
                    # Enrichment is best-effort; a download/parse failure just
                    # leaves an empty snippet (the title still helps the model).
                    snippet = ""
            documents.append(
                {
                    "name": name,
                    "url": (
                        f"{self.instance_url}/lightning/r/ContentDocument/{document_id}/view"
                        if document_id
                        else self.instance_url
                    ),
                    "snippet": snippet,
                }
            )
        return documents