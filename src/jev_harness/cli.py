"""uv run jev-lab: server, provider checks, paired runs, and repeatable evaluation."""
import argparse
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter

import httpx

from .config import Settings
from .decisions import JevDecisions
from .domain import SCENARIOS
from .models import local_model
from .runner import ComparisonRunner


def doctor(settings):
    """Actual provider probes, no credential values or credential-bearing URLs printed."""
    results = {}
    try:
        headers = {"Authorization": "Bearer " + settings.llm_api_key}
        response = httpx.get(settings.base_url.rstrip("/") + "/models", headers=headers, timeout=10)
        response.raise_for_status()
        model_ids = [model["id"] for model in response.json().get("data", [])]
        results["local_models"] = {"status": "ok", "configured_model_listed": settings.model in model_ids, "models": model_ids}
    except Exception as error:
        results["local_models"] = {"status": "error", "message": settings.safe_error(error)}
    try:
        llm = local_model(settings)
        tool = {"type": "function", "function": {"name": "probe_echo", "description": "Echo a short text to verify tool calling.",
                "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}}
        started = perf_counter()
        # Some local servers reject forced tool_choice despite supporting tools.
        answer = llm.bind_tools([tool]).invoke("Call probe_echo with text='connection verified'.")
        if not answer.tool_calls or answer.tool_calls[0]["name"] != "probe_echo":
            raise ValueError("Model did not return a parseable tool call.")
        from langchain_core.messages import HumanMessage, ToolMessage
        final = llm.invoke([HumanMessage(content="Call probe_echo with text='connection verified'."), answer,
                            ToolMessage(content="connection verified", tool_call_id=answer.tool_calls[0]["id"])])
        if not final.text.strip():
            raise ValueError("Tool round trip did not produce a final response.")
        results["local_tool_roundtrip"] = {"status": "ok", "model": settings.model, "elapsed_ms": round((perf_counter()-started)*1000)}
    except Exception as error:
        results["local_tool_roundtrip"] = {"status": "error", "message": settings.safe_error(error)}
    try:
        answer = JevDecisions(settings).classify({"task": "My edamame was missing. Please refund it.", "fixture": {"missing_item": "Edamame", "price": 9}})
        results["jev"] = {"status": "ok", "model": answer["model"], "answers": answer["answers"], "elapsed_ms": answer["elapsed_ms"]}
    except Exception as error:
        results["jev"] = {"status": "error", "message": settings.safe_error(error)}
    print(json.dumps(results, indent=2))
    return 0 if all(item["status"] == "ok" for item in results.values()) else 1


def resolve_reviews(runner, value, review_policy):
    for path in ("normal", "jev"):
        while value["runs"][path]["status"] == "awaiting_review":
            pending = value["runs"][path]["pending_review"]
            decision, args = review_policy, None
            if review_policy == "ask":
                print(f"\n{path}: {pending['reason']}\n{json.dumps(pending['args'], indent=2)}")
                if not sys.stdin.isatty():
                    print("Review remains pending. Open this comparison in the dashboard or rerun with --review approve/reject.", file=sys.stderr)
                    break
                decision = input("Approve, edit, or reject? [approve/edit/reject]: ").strip().lower()
                if decision not in {"approve", "edit", "reject"}:
                    continue
                if decision == "edit":
                    args = json.loads(input("Complete replacement arguments as JSON: "))
            value = runner.review(value["id"], path, pending["id"], decision, args, background=False)
    return value


def main():
    parser = argparse.ArgumentParser(description="One task, two agents. Inspect the effect of Jev.")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Serve the local dashboard and API")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--host", default="127.0.0.1")
    sub.add_parser("doctor", help="Probe local model discovery, tool calling, and Jev primitives")
    sub.add_parser("scenarios", help="List deterministic support tasks")
    bench = sub.add_parser("benchmark", help="Same decision tasks: existing local LLM vs hosted Jev")
    bench.add_argument("--repeat", type=int, default=1)
    bench.add_argument("--limit", type=int, default=None)
    bench.add_argument("--seed", type=int, default=17)
    bench.add_argument("--no-warmup", action="store_true")
    bench.add_argument("--output", type=Path, default=Path("artifacts/benchmark"))
    primitives = sub.add_parser("primitives", help="Print a real Jev request and full typed response")
    primitives.add_argument("--execution", choices=["live", "fixture"], default="live")
    for command in ("compare", "evaluate"):
        child = sub.add_parser(command)
        child.add_argument("--execution", choices=["live", "fixture"], default="live")
        child.add_argument("--scenario", choices=[item["id"] for item in SCENARIOS], default="missing-item" if command == "compare" else None)
        child.add_argument("--review", choices=["ask", "approve", "reject"], default="ask" if command == "compare" else "reject")
        child.add_argument("--output", type=Path)
        if command == "compare":
            child.add_argument("--task")
        else:
            child.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.command == "benchmark":
        from .benchmark import run
        if not 1 <= args.repeat <= 100 or (args.limit is not None and not 1 <= args.limit <= 18):
            parser.error("--repeat must be 1–100; --limit must be 1–18")
        try:
            run(settings, args.output, args.repeat, args.limit, not args.no_warmup, args.seed)
        except Exception as error:
            print(settings.safe_error(error), file=sys.stderr)
            raise SystemExit(1)
        print(f"Reports: {args.output / 'report.md'} and {args.output / 'report.html'}")
        return
    if args.command == "serve":
        import uvicorn
        from .api import create_app
        uvicorn.run(create_app(settings), host=args.host, port=args.port)
        return
    if args.command == "doctor":
        raise SystemExit(doctor(settings))
    if args.command == "scenarios":
        print(json.dumps(SCENARIOS, indent=2))
        return
    if args.command == "primitives":
        print(json.dumps(JevDecisions(settings, fixture=args.execution == "fixture").classify({"scenario_id": "missing-item", "task": SCENARIOS[1]["task"], "fixture": SCENARIOS[1]["fixture"]}), indent=2))
        return
    if args.command == "evaluate" and not 1 <= args.repeat <= 100:
        parser.error("--repeat must be between 1 and 100")
    try:
        runner = ComparisonRunner(settings)
    except ValueError as error:
        parser.error(str(error))
    try:
        if args.command == "compare":
            result = runner.create(args.scenario, task=args.task, execution=args.execution, background=False)
            result = resolve_reviews(runner, result, args.review)
        else:
            cases = [args.scenario] if args.scenario else [item["id"] for item in SCENARIOS]
            comparisons = []
            for repetition in range(args.repeat):
                for case in cases:
                    first = "normal" if repetition % 2 == 0 else "jev"
                    value = runner.create(case, execution=args.execution, first=first, background=False)
                    comparisons.append(resolve_reviews(runner, value, args.review))
            summary = {}
            for path in ("normal", "jev"):
                runs = [c["runs"][path] for c in comparisons]
                complete = [r for r in runs if r["status"] == "completed"]
                summary[path] = {"runs": len(runs), "completed": len(complete), "degraded": sum(bool(r.get("degraded")) for r in runs),
                                 "passed": sum(r["outcome"]["passed"] is True for r in complete),
                                 "ungraded": sum(r["outcome"]["passed"] is None for r in complete),
                                 "median_duration_ms": median(r["metrics"]["duration_ms"] for r in complete) if complete and args.execution == "live" else None}
            result = {"source": args.execution, "review_policy": args.review, "repetitions": args.repeat,
                      "note": "Whole-harness comparison, not an isolated model benchmark. Review policy affects outcomes. Scripted fixtures are not model evidence.",
                      "summary": summary, "comparisons": comparisons}
        serialized = json.dumps(result, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(serialized + "\n")
            print(f"Saved {args.output}")
        else:
            print(serialized)
    except (ValueError, KeyError) as error:
        print(settings.safe_error(error), file=sys.stderr)
        raise SystemExit(1)
    finally:
        runner.close()


if __name__ == "__main__":
    main()
