# Copilot Instructions for MLB-rule-changes

## Project Overview
- This project analyzes the impact of recent MLB rule changes (2019–2023) using R, Python, and Quarto.
- The codebase is organized for reproducible research, with data collection in Python, analysis and reporting in R/Quarto, and containerized development via Docker and VS Code Dev Containers.

## Key Components
- `explore data/`: Quarto (`.qmd`) and HTML files for exploratory analyses, each focused on a specific rule change (e.g., base stealing, defensive shift).
- `report.qmd`: Main Quarto report, synthesizing findings and referencing the bibliography in `resources/`.
- `resources/data/`: Contains both raw data CSVs and Python scripts for data acquisition from MLB APIs. Example: `get_team_steals.py` fetches and processes team stolen base stats.
- `requirements.txt`: Python dependencies (aiohttp, asyncio, pandas, tqdm) for data scripts.
- `Dockerfile`: Builds a container with R, Python, Quarto CLI, and all dependencies. Sets up a Python venv at `/opt/venv`.
- `.devcontainer/`: VS Code Dev Container config for a consistent development environment.

## Developer Workflows
- **Build the environment:**
  - Docker: `docker build -t mlb-rule-changes .`
  - Dev Container: Open in VS Code for automatic setup.
- **Run the container:**
  - `docker run -it -p 8787:8787 -v $(pwd):/workspaces/mlb-rule-changes mlb-rule-changes`
- **Activate Python venv:**
  - `source /opt/venv/bin/activate` (inside container)
- **Render Quarto documents:**
  - `quarto render <file>.qmd` (Quarto CLI is installed in the container)
- **Fetch/update data:**
  - Run Python scripts in `resources/data/` to refresh CSVs.

## Project Conventions & Patterns
- R and Quarto files use relative paths to access data, with logic to handle different working directories (see `explore data/base_stealing.qmd`).
- Data scripts output CSVs to `resources/data/` for downstream analysis.
- R packages are installed globally in the container; Python uses a venv at `/opt/venv`.
- Bibliography and citation style are managed in `resources/` and referenced in Quarto YAML headers.
- All analyses and reports are reproducible from a clean build using only the provided Dockerfile and scripts.

## Integration Points
- Quarto documents can call both R and Python code chunks.
- Data flows: Python scripts → CSVs → R/Quarto analysis → HTML/Quarto reports.
- External data: MLB stats API (see Python scripts in `resources/data/`).

## Examples
- To add a new analysis, create a `.qmd` in `explore data/`, fetch data with a Python script if needed, and use R for analysis/visualization.
- To update data, run the relevant Python script and re-render the Quarto report.

## References
- See `README.md` for basic usage and environment setup.
- See `report.qmd` and `explore data/*.qmd` for analysis structure and data access patterns.

## R Coding Best Practices
- Follow the Tidyverse Style Guide (https://style.tidyverse.org/)
- Use snake_case for variable and function names
- Keep functions small and focused
- Return objects instead of printing them
- Avoid setwd() and use relative paths
- Quarto files
    - Use YAML headers for metadata
    - Name code chunks with 1-3 descriptive words
    - Define chunk code-summary with 1-3 words
