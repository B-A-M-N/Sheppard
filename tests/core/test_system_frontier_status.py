from src.core.system import SystemManager


def test_status_exposes_frontier_state():
    sm = SystemManager()
    sm._initialized = True
    sm._startup_stage = "ready"
    sm.model_router = type("Router", (), {"summary": lambda self: {"main": "x"}})()
    sm.budget = type(
        "Budget",
        (),
        {
            "all_statuses": lambda self: {
                "mission-1": type(
                    "Status",
                    (),
                    {"topic_name": "Topic", "usage_ratio": 0.2, "raw_bytes": 1024},
                )()
            }
        },
    )()
    sm.crawler = type("Crawler", (), {"queue_size": 3})()
    sm._crawl_tasks = {}
    sm.active_frontiers = {
        "mission-1": type(
            "Frontier",
            (),
            {
                "respawn_count": 1,
                "noop_respawn_count": 0,
                "consecutive_zero_yield": 2,
                "failed": False,
                "failure_reason": None,
            },
        )()
    }

    status = sm.status()

    assert status["startup"]["stage"] == "ready"
    assert status["startup"]["last_error"] is None
    assert status["missions"]["mission-1"]["frontier_state"]["respawn_count"] == 1
    assert status["missions"]["mission-1"]["frontier_state"]["consecutive_zero_yield"] == 2
