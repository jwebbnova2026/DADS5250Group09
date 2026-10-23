"""Boston 311 Crew Planner: staffing plan and intake assistant (see docs/architecture.md).

Package map (one line per module; each module's docstring explains more):

* ``config``     - every GIVEN parameter and DEFAULT rule, plus paths and model IDs
* ``data``       - fetch the 2023-2024 files through the data.boston.gov API, clean, aggregate
* ``forecast``   - 2025 monthly demand forecast (seasonal naive)
* ``workload``   - seeded synthetic 2025 request lists, including sensitivity scenarios
* ``simulate``   - daily first-in-first-out queue simulator and penalty events
* ``staffing``   - the hiring / release / seasonal heuristic, the baseline, cost accounting
* ``catalog``    - official request types, queue-mapping audit, aliases
* ``retrieval``  - TF-IDF search over the catalog
* ``llm``        - LangChain model wrapper with live and offline (replay) modes
* ``agent``      - LangGraph intake agent (route, clarify once, or triage)
* ``evaluate``   - intake accuracy metrics on the dev and test sets
* ``manifest``   - one JSON record per run of everything needed to reproduce it
"""

# Use the operating system's certificate store for HTTPS.
#
# Why: Python normally verifies HTTPS certificates against its own bundled
# list. On computers where antivirus or a company network inspects HTTPS
# traffic, that bundled list does not include the inspector's certificate, so
# every download fails with "CERTIFICATE_VERIFY_FAILED" even though a web
# browser works fine. ``truststore`` tells Python to trust whatever the
# operating system trusts, which is what the browser does. On ordinary
# computers this changes nothing. Verification is still fully enabled.
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover - truststore is a declared dependency
    pass

__version__ = "0.1.0"
