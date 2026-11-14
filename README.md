# LandLens

A Vexcel-backed land-intelligence application for urban agriculture discovery
and clear-sky sunlight screening.

## Run the site

```bash
npm install
npm run dev
```

Open the shown local URL, choose **Explore urban agriculture**, choose a globe
scope, and run a query. The Vite development and preview servers expose the
server-side `/api/vexcel/*` routes used by the UI.

Choose **Explore rural agriculture** to compare any semicolon-separated place
names. `/api/rural/compare` geocodes each place with Open-Meteo and reads NASA
POWER agroclimatology for annual solar resource, precipitation, and
temperature. It requires no additional key. The displayed climate-fit score is
a regional screening heuristic; it does not claim that a parcel is farmland or
assess USDA soil capability, water rights, flood risk, ownership, price, or
availability.

## Environment

Set the Vexcel key only on the server:

```bash
export VEXCEL_API_KEY="your-key"
# Optional when the CoStar kit is not in ../costar-hackathon-kit/data:
export COSTAR_DATA_DIR="/absolute/path/to/costar-hackathon-kit/data"
```

For this hackathon workspace only, the server also reads
`../Vexcel_API_Hackathon_Tutorial_PDF_PY/.env`. Do not use a `VITE_*` variable:
Vite exposes those to browser code.

### Deep Agents and tracing

The roof-comparison action runs a LangChain Deep Agent with typed tools for
Vexcel search, CoStar lookup, DSM/DTM geometry, and the same sunlight service
used by the interactive roof view. The default NRP configuration is:

```bash
NRP_API_KEY="your-nrp-key"
LANDLENS_AGENT_BASE_URL="https://ellm.nrp-nautilus.io/v1" # optional default
LANDLENS_AGENT_MODEL="qwen3"                              # default; glm-5 or minimax-m2 also work
LANDLENS_AGENT_TIMEOUT_MS=420000                          # optional, default 420000
LANDLENS_AGENT_RECURSION_LIMIT=80                         # optional, default 80
```

A single agent calls the four tools directly. On NRP, `qwen3` finishes a
four-site comparison in about 35 seconds of model time; a live 12-candidate
search takes about 4 minutes because each roof's geometry and sunlight are computed. `kimi` and the `agents` alias did not
respond in testing, and `deepseek-v4-flash` was several times slower.

If no model key is present, the UI runs the deterministic comparison endpoint
directly and labels the result accordingly. It does not fabricate an agent
answer. Keep every key server-side and restart Vite after changing environment
variables.

LangSmith tracing accepts `LANGSMITH_API_KEY`; this workspace also maps an
existing `LANGCHAIN_API_KEY` to it on the server. To address traces to the local
LandLens agent:

```bash
LANGSMITH_ENDPOINT="https://api.smith.langchain.com"
LANGSMITH_TRACING="true"
LANGSMITH_AGENT_ID="x"
LANGSMITH_AGENT_ENVIRONMENT="local"
```

Do not also set `LANGSMITH_PROJECT` when using the agent address above: they are
alternative trace destinations in the LangSmith SDK.

### Photon opening alerts

The **Watch openings** action uses Photon 2.0 to create or reuse the recipient
User and conversation Space, then sends a confirmation Message. Configure the
three server-only values from the Photon beta dashboard:

```bash
PHOTON_API_KEY="pho_sk_..."
PHOTON_PROJECT_ID="pho_prj_..."
PHOTON_AGENT_USER_ID="pho_usr_..."
```

LandLens stores watches under ignored `runtime/`, checks them every 15 minutes
while the server is running, and detects new candidates or changes to active
CoStar listing and unit-availability evidence. A new opening is passed through
the Deep Agent property, geometry, and sunlight tools before Photon sends the
ranked evidence. Photon accepting a message is not the same as confirmed device
delivery; use the Photon dashboard or message endpoint to inspect delivery.

Only add a destination after receiving its owner’s permission. Photon contact
handles and message contents are customer data and must remain outside source
control.

Live urban discovery uses `embedding/extract`, then resolves returned
coordinates with `property/extract`. An ordinary query searches every standard
embedding collection currently exposed to the authorized Vexcel account;
emergency GraySky collections are excluded. Queries that explicitly say
`near`, `around`, or `in` a place geocode that phrase and use a bounded WKT
search instead. Results are not replaced with a fixed shortlist when access or
geographic coverage is missing. The site workspace
requests Vexcel false-color infrared with `bands=irg`; RGB and CIR can be
switched without leaving the 3D roof view.

The server indexes the local CoStar commercial property, commercial listing,
and apartment listing JSONL files. A Vexcel result is joined only when the
nearest geocoded CoStar property is within 125 meters. The response includes
the match distance, property facts, listing state, availability, primary photo,
and verified Matterport attachments. Restart the Vite server after changing
`COSTAR_DATA_DIR` or replacing the dataset.

Solar analysis projects the georeferenced Vexcel `roofWkt` footprint onto the
imagery and clips the editable growing area to that boundary. Height volumes
come from DSM samples relative to the median roof plane. Shade and
direct-sun-hour metrics remain unknown until that geometry is available. It is
a clear-sky geometry workflow, not measured irradiance or engineering approval.

The comparison panel ranks the same spatial cells that meet the target on every
requested date and keeps sites with missing geometry visible but unranked. The
acceptance comparison uses April 15 and October 15, 2026. “Try December
instead” reruns the tools for April 15 and December 15, 2026 rather than
relabeling the earlier result. Matterport is only a near-tie tiebreaker.

## Add Vexcel imagery

Set the key and run the downloader in the same terminal:

```bash
cd ../Vexcel_API_Hackathon_Tutorial_PDF_PY
export VEXCEL_API_KEY="paste-your-key-here"
python3 vexcel_four_sites.py

cd ../land-intelligence
npm run sync:vexcel
```

The key must remain in the terminal environment. Never store it in React code,
`VITE_*`, or a frontend `.env` file because Vite exposes those values to the
browser.
