# Deferred: h2_plant integration
Removed from main on 2026-07-11. These directories depended on an `h2_plant` package
root that was never vendored into this repo (see hardening spec v2, §4).
Revisit as a scoped follow-on: vendor properly under vendor/h2_plant, then bridge
via an adapter onto the existing gRPC AdvanceTime contract — do not replace the
PEMFC model in physical_engine/ directly.
