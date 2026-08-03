#!/usr/bin/env python3
"""Provider discovery and candidate ranking for Website Image Finder."""
from __future__ import annotations

from common import host_matches, redact
from image_search_core import *


def discover_candidates(args, session, queries, preferred_domains, allowed_domains, blocked_domains, api_key, requested_provider, primary_provider):
    all_candidates: list[Candidate] = []
    warnings_list: list[str] = []
    providers_used: list[str] = []
    secrets = [api_key]

    for query in queries:
        query_results: list[Candidate] = []
        provider_for_query = primary_provider
        for page in range(args.page, args.page + args.pages):
            try:
                if provider_for_query == "serpapi":
                    found = search_serpapi(session, query, api_key, args.max_results, args.region, page, args.orientation, args.image_type, args.license_filter, args.safe_search, args.size, args.color, args.time_limit)
                else:
                    found = search_ddgs(query, args.max_results, args.region, page, args.ddgs_backend, args.orientation, args.image_type, args.license_filter, args.safe_search, args.size, args.color, args.time_limit)
                if provider_for_query not in providers_used:
                    providers_used.append(provider_for_query)
                if provider_for_query == "serpapi" and not found and not args.no_provider_fallback and requested_provider == "auto":
                    fallback_found = search_ddgs(query, args.max_results, args.region, page, args.ddgs_backend, args.orientation, args.image_type, args.license_filter, args.safe_search, args.size, args.color, args.time_limit)
                    if "ddgs" not in providers_used:
                        providers_used.append("ddgs")
                    query_results.extend(fallback_found)
                    warnings_list.append(f"{query} page {page}: SerpApi returned no images; used DDGS fallback")
                else:
                    query_results.extend(found)
            except Exception as exc:
                warnings_list.append(redact(f"{query} page {page} via {provider_for_query}: {type(exc).__name__}: {exc}", secrets))
                if provider_for_query == "serpapi" and not args.no_provider_fallback and requested_provider == "auto":
                    provider_for_query = "ddgs"
                    try:
                        found = search_ddgs(query, args.max_results, args.region, page, args.ddgs_backend, args.orientation, args.image_type, args.license_filter, args.safe_search, args.size, args.color, args.time_limit)
                        if "ddgs" not in providers_used:
                            providers_used.append("ddgs")
                        query_results.extend(found)
                        warnings_list.append(f"{query} page {page}: fell back from SerpApi to DDGS")
                    except Exception as fallback_exc:
                        warnings_list.append(redact(f"{query} page {page} DDGS fallback: {type(fallback_exc).__name__}: {fallback_exc}", secrets))
        for candidate in query_results:
            candidate.score = score_candidate(candidate, preferred_domains, args.orientation)
        all_candidates.extend(query_results)

    candidates = merge_candidates(all_candidates)
    if allowed_domains:
        candidates = [candidate for candidate in candidates if host_matches(candidate.source_page_url, allowed_domains) or host_matches(candidate.image_url, allowed_domains)]
    if blocked_domains:
        candidates = [candidate for candidate in candidates if not (host_matches(candidate.source_page_url, blocked_domains) or host_matches(candidate.image_url, blocked_domains))]
    candidates.sort(key=lambda candidate: (-candidate.score, candidate.provider_position, candidate.id))
    for rank, candidate in enumerate(candidates, 1):
        candidate.rank = rank
    return candidates, warnings_list, providers_used
