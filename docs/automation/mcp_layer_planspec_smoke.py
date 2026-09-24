"""Execute a layer-aware PlanSpec against its exact verified build manifest."""

from mcp_isolated_smoke import main


if __name__ == "__main__":
    main(plan_fixture="synthetic-layer")
