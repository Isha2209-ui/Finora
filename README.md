# Finora

**An AI-powered personal financial intelligence and management platform.**

Finora helps bring your financial information into one place and uses machine learning and artificial intelligence to find meaningful insights.

Finora combines financial tracking, planning tools, machine-learning insights, reports, and a conversational AI CFO in one local application.

### Explore machine-learning insights

Finora includes model-supported tools for transaction categorization, unusual activity, peer comparisons, credit-risk patterns, and cash-flow forecasting. The Model Lab shows information about the models and their evaluation.

### Ask the AI CFO

The AI CFO answers supported questions using calculations based on the selected profile. When configured with Ollama, it uses a local language model. Its tools are read-only, and the backend checks the numbers in its answers. Without Ollama, the assistant can still answer supported questions in calculator mode.

## Quick start

### Requirements

- macOS or Linux (on Windows, use WSL)
- Python 3.11 or newer
- Node.js 20 or newer, with npm
- About 1.5 GB of disk space for packages and the app; the optional language model needs additional memory and disk space

PostgreSQL and Ollama are optional. The default setup can use SQLite and calculator mode for the AI CFO.

### Install and run

```bash
git clone https://github.com/Isha2209-ui/Finora.git
cd Finora
./setup.sh
./run.sh
```

Open [**http://localhost:5173**](http://localhost:5173) in your browser. Create a local account with an email address and password, then sign in. The API documentation is available at [**http://127.0.0.1:8001/docs**](http://127.0.0.1:8001/docs).

Keep the terminal running while you use Finora. Press **Ctrl+C** in that terminal to stop the app. In VS Code, after setup, you can also run the **Run Finora** build task with **Cmd+Shift+B**.

### Setup notes

- `setup.sh` creates a Python environment in `backend/venv`, installs backend and frontend dependencies, prepares the local database, loads demo data, and checks the shipped model files.
- The default database is `backend/finora.db`. Local databases, virtual environments, and environment files are excluded from Git.
- If your local database already contains accounts or profiles, the demo seed step refuses to replace them. Don’t use the seed script’s `--force` option unless you intentionally want to delete that local data.
- If setup stops before installing frontend packages, install them with:
  ```bash
  cd frontend
  npm install
  ```

For more setup details and common fixes, see [docs/SETUP.md](docs/SETUP.md).

## Choose how to start

After signing in, you can explore a demo identity or start a private profile of your own.

### Explore a demo identity

Finora includes four fictional profiles with synthetic financial data:

| Demo identifier | Profile                      |
| --------------- | ---------------------------- |
| `ABCDE1234F`    | Balanced saver               |
| `PQRST5678K`    | Overspender with three cards |
| `LMNOP2345D`    | Loan-heavy profile           |
| `XYZAB9876C`    | Freelancer                   |

You can select a demo person from the start screen or open one using its demo identifier. Finora creates a private sandbox copy for your account, so you can explore and edit it. Resetting restores the original demo data. Sandboxes expire after 24 hours; the read-only templates remain unchanged.

### Create your own private profile

Choose **Start with my own data** to create a profile visible only to your account. Finora asks for basic details such as your name, age, employment type, and target retirement age; city is optional. Your profile starts empty, so Finora does not invent financial details for you.

## Optional: enable the local AI CFO model

The AI CFO can use [Ollama](https://ollama.com/) and the local `qwen2.5:3b` model. Install Ollama and download the model:

```bash
ollama pull qwen2.5:3b
```

Keep Ollama running locally, then start Finora. Without the model, the assistant uses calculator mode. Finora refuses remote or cloud models for the AI CFO.

## Technology

- **Frontend:** React 19, Vite 7, Tailwind CSS 4, Recharts
- **Backend:** Python, FastAPI, SQLAlchemy
- **Database:** SQLite by default; optional PostgreSQL
- **Machine learning:** scikit-learn, XGBoost, SHAP
- **Optional local language model:** Qwen 2.5 3B through Ollama

## Models and limitations

The trained model files are shipped with the project. Their datasets, methods, evaluation, and provenance are described in [docs/ML_PROVENANCE.md](docs/ML_PROVENANCE.md).

| Capability                 | Method                         | Important limitation                                                                                        |
| -------------------------- | ------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| Credit-risk patterns       | XGBoost with SHAP explanations | Trained on Taiwan credit-card data from 2005. This is not an Indian credit score or bureau assessment.      |
| Peer benchmarking          | Weighted K-Means               | Uses US household survey data, not Indian household benchmarks.                                             |
| Transaction categorization | TF-IDF and logistic regression | Performance is not established for Indian UPI or NEFT descriptions; low-confidence suggestions need review. |
| Unusual activity           | Isolation Forest               | Flags activity that is unusual for a profile. It does not identify or prove fraud.                          |
| Cash-flow forecasting      | XGBoost regression             | In the documented evaluation, it did not beat a simple three-month-average baseline.                        |
| Model Lab                  | Model registry and checks      | Shows model versions, provenance, metrics, and checks; it is not a predictive model.                        |

## Project structure

```text
backend/
  app/             API routes, services, data models, ML, and AI CFO
  artifacts/       Shipped model files and metadata
  tests/           Backend tests
  requirements.txt Python dependencies
frontend/
  src/             React application
  e2e/             Browser walkthroughs
docs/              Setup, demo, model, verification, and project documentation
report/            Project report files
setup.sh           One-time local setup
run.sh             Starts the backend and frontend
```

## Development commands

Run these from the project root unless stated otherwise.

```bash
# Start the app after setup
./run.sh

# Run backend tests
cd backend
source venv/bin/activate
pytest -q

# Check the shipped machine-learning models
python -m app.ml.train check
```

Only one backend process can use a given database at a time. Finora enforces this with a database lock; don’t start multiple Uvicorn workers against the same database.

## Documentation

- [Setup guide](docs/SETUP.md)
- [Demo walkthrough](docs/DEMO_SCRIPT.md)
- [Project status](docs/PROJECT_STATUS.md)
- [ML provenance and evaluation](docs/ML_PROVENANCE.md)
- [Screenshots](docs/SCREENSHOTS.md)
- [Verification notes](docs/PHASE_9_VERIFICATION.md)
- [Viva questions and answers](docs/VIVA_QA.md)

## Security and local data

The local app stores account and profile data in its configured database. Keep `backend/.env`, local databases, backups, and uploaded statements private. The repository’s `.gitignore` excludes these local files, but review `git status` before committing changes.

The local setup is intended for development and demonstration, not direct public deployment. Review the security and configuration requirements in [docs/SETUP.md](docs/SETUP.md) before exposing the service.

##
