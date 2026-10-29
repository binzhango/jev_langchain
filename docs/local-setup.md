# Run with a local LLM and hosted Jev

This repo uses a local OpenAI-compatible chat server for generation and tool calls, and TypeSafe's hosted API for Jev decisions. The browser talks to the local Python application. The application keeps model credentials on the server side.

Install `uv` and Node.js/npm, then use this single command on macOS, Linux, or WSL:

```bash
bash start.sh
```

The launcher installs the locked Python dependencies with uv (which can provision Python 3.12), installs the locked frontend dependencies, builds the dashboard, and starts its API and frontend together at http://127.0.0.1:8000. It works even when invoked by path from outside the repository. Ctrl+C stops the single server; no background frontend process remains.

If `.env` is missing, first-run prompts collect the model URL, exact model ID, and optional hidden credentials. New settings are saved in a Git-ignored `.env` file readable only by its owner. An existing `.env` is never overwritten. Exported environment variables take precedence and their secrets are not copied into the file. Without an interactive terminal, missing configuration is initialized from `.env.example`; provide environment variables for live runs. No model inference is performed during setup.

A local model server and Jev credential are needed for live comparisons. Start LM Studio or your other model server separately. You can leave the Jev token empty and select **Scripted walkthrough** to explore the app. The setup below explains configuration and optional diagnostics; it is not a required sequence of startup commands.

## Configure the worker model

Start LM Studio's server and load a chat model that supports tool calls. The launcher creates `.env` for you on first run. To change settings later, edit that file and restart with `bash start.sh`.

Set the URL and exact model identifier returned by your server:

```dotenv
LOCAL_LLM_BASE_URL=http://localhost:1234/v1
LOCAL_LLM_MODEL=your-loaded-model-id
LOCAL_LLM_API_KEY=lm-studio
LOCAL_LLM_TIMEOUT=120
LOCAL_LLM_MAX_TOKENS=1536
```

Use your server's required key if it enables authentication. `lm-studio` is only a placeholder for a local server that does not require a real key. If the server runs on another machine, configure its address in your private `.env` rather than editing committed source.

An OpenAI-compatible server provided through another setup, including an Unsloth-based serving workflow, can use the same settings when it implements the chat/tool contract. A model appearing in `/v1/models` establishes discovery, not correct tool calling. Test the selected model and server combination.

Both agent paths use this same worker. Jev uses a separate client and is not routed through the local chat endpoint.

## Make the Jev credential available

The application prefers an exported `JEV_TOKEN` and falls back to `TYPESAFE_API_KEY`. It explicitly maps that value into the TypeSafe client. If `JEV_TOKEN` already exists in your shell, keep using it; there is no need to copy its value into chat, source files, or the dashboard.

Launch the application from the shell that exports the variable. An editor or process started earlier may have a different environment. Check presence without printing the value:

```bash
python -c 'import os; print("Jev credential present" if os.getenv("JEV_TOKEN") or os.getenv("TYPESAFE_API_KEY") else "Jev credential missing")'
```

The example file also supplies `JEV_MODEL=jev-latest` and a request timeout. Keep real credentials out of committed files and exported traces. The hosted requests contain the state and questions shown in the decision inspector; the demo's seeded support records are synthetic.

## Optional connection diagnostics

```bash
uv run jev-lab doctor
```

The doctor performs real provider probes: local model discovery, a local tool-call round trip, and a Jev request covering the three primitive types. Read its separate results. Passing these probes is not proof that all agent scenarios pass; follow them with a real paired scenario.

## Open the dashboard

```bash
bash start.sh
```

Open [the local dashboard](http://localhost:8000). FastAPI serves the built Vite frontend and the local API from the same application. Select a scenario, inspect its task, and choose **Run both**. The two runs use independent copies of the starting fixture.

Keep this application local: it is a teaching sandbox with simulated actions, not an authenticated support portal. In frontend development, Vite proxies `/api` to the backend on port 8000; see the [API contract](api-contract.md).

## Run from the terminal

```bash
uv run jev-lab compare --scenario missing-item
uv run jev-lab evaluate --execution live --repeat 3
```

`compare` prompts for pending reviews in an interactive terminal. `evaluate` defaults to rejecting all pending actions; select `--review approve` or `--review ask` when that is the reviewer policy you intend to measure. The [evaluation guide](evaluation.md) explains how this changes outcome checks. Add `--output artifacts/results.json` to save the full result.

For a credential-free scripted walkthrough:

```bash
uv run jev-lab compare --scenario missing-item --execution fixture
```

Fixture execution uses synthetic decisions and scripted agent behavior. It does not verify either model or produce performance evidence. Live execution calls the configured models, while the support actions remain simulated. Read [evaluation.md](evaluation.md) before interpreting timing or outcome differences.

Runtime data and recorded comparisons go to `JEV_LAB_DATA_DIR`, which defaults to the ignored `artifacts/` directory. Preserve the JSON export when sharing an observed result; include its execution mode and configuration metadata.

Only one runner process can own a data directory. Stop the dashboard server before running CLI comparisons, or give the CLI its own `JEV_LAB_DATA_DIR=artifacts/cli`. Paused reviews can resume after restart with the same execution settings. Changing the model, endpoint, generation limits, or review threshold requires restoring the recorded settings or starting a new comparison; a run must not silently mix configurations.

The runner currently uses macOS/Linux file locking. Runtime traces include the configured endpoint address for reproducibility; inspect exports before sharing infrastructure details.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Connection refused | Server is running, port is correct, and the configured host is reachable from the Python process |
| Model not found | Copy the exact server model ID; confirm it is loaded or can load |
| Text instead of a tool call | The model supports tool use and the server uses an appropriate tool/chat template |
| Slow first response | Model loading, context initialization, or limited local memory; distinguish a cold run from a warm one |
| Jev credential missing | Start from the shell that exports `JEV_TOKEN` or `TYPESAFE_API_KEY`; check presence without echoing it |
| Jev request fails | Inspect the recorded error and provider status; do not interpret a failed assessment as a safe action |
| Dashboard absent | Run `bash start.sh`; it builds and serves the dashboard automatically |
| Port already in use | Open the existing app or stop its terminal with Ctrl+C before starting again |
| Missing uv, node, or npm | Install the prerequisite named by the launcher, then rerun `bash start.sh` |
| One path awaits review | Resolve that path's pending action; inspect the other run independently |

Configuration and commands here describe how to run the project. They do not assert that your model/server combination has been validated or that Jev improves its performance.
