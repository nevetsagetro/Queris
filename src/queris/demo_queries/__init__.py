"""Prepared, deterministic SQL builders for the curated demo surface."""

from queris.demo_queries.generic import build_generic_query
from queris.demo_queries.revenue import build_revenue_query

__all__ = ["build_generic_query", "build_revenue_query"]
