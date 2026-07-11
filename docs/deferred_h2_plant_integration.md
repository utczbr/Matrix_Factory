# Deferred H2 Plant Integration

The Python-based `h2_plant` subsystem was removed from the `main` branch to streamline the active repository state. Its modules (`core/`, `components/`, `models/`, `optimization/`, `config/`) were originally designed for a multi-physics co-simulation architecture that has not yet been fully wired to the JaCaMo/CArtAgO agent framework.

## Why Defer?
- **Incomplete Packaging**: The directories lacked a proper `pyproject.toml` or `setup.py`, making them unresolvable by the Python interpreter without manual `PYTHONPATH` manipulation.
- **Unused by Main Twin**: The primary JaCaMo twin (Order Holons, Resource Holons, AMR fleet) currently runs against the verified PEMFC model in `pem_physics.py` directly or operates independently. The larger system dynamics graph builder (`graph_builder.py`, etc.) is out-of-band for current development priorities.
- **Hygiene**: Keeping incomplete or dead code in `main` masks real errors and complicates CI/CD and dependency management.

## Future Re-integration
When the time comes to integrate the full `h2_plant` physics backend:
1. Restore the code from history (prior to this commit).
2. Create a properly structured Python package (e.g., `h2_plant/`).
3. Add a `pyproject.toml` using a modern build backend (like `hatchling` or `poetry`).
4. Install it into the project's virtual environment (`pip install -e ./h2_plant`).
5. Ensure the Python-to-Java bridges (gRPC or zeroMQ) are updated to route simulation ticks to the unified graph execution rather than individual models.
