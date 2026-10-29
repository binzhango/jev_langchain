# Decision lab dashboard

The frontend for the local Jev + LangChain comparison experiment. It calls the Python API under `/api`; model credentials remain in the backend.

For normal use, run **`bash start.sh` from the repository root**. It builds and serves the frontend and backend together. See the [setup guide](../docs/local-setup.md).

The commands below are only for frontend development, with the Python backend already running. Run them from `dashboard/`.

```bash
npm ci
npm run dev
```

The development server uses `http://127.0.0.1:5173` and proxies `/api` to the Python server on port 8000.

```bash
npm run build
```

The build writes `dist/`, which the Python server serves for the normal single-server workflow.

The primary action sends one task to both agents. Each receives independent copies of the same starting data. Trace events show actual observations; the normal path has no invented confidence scores. Scripted walkthroughs are explicitly labeled and suppress performance timings. A threshold slider explores a saved Jev prediction locally without changing or resuming its run.

API shapes are documented in `../docs/api-contract.md`.
