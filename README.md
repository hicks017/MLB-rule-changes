# MLB-rule-changes

## Abstract

*Placeholder for the report in progress.*

---

## Project Usage Instructions

### 1. Using the Dockerfile

Build the Docker image:

```bash
docker build -t mlb-rule-changes .
```

Run the container:

```bash
docker run -it -p 8787:8787 -v $(pwd):/workspaces/mlb-rule-changes mlb-rule-changes
```

### 2. Using the .devcontainer Folder

If you are using VS Code, open the project in a Dev Container for a pre-configured development environment. This ensures all dependencies are installed and the environment matches the project requirements.


### 3. Activating the Python Virtual Environment

To use the Python virtual environment inside the container or dev environment, run:

```bash
source /opt/venv/bin/activate
```

To deactivate, run:

```bash
deactivate
```

---

For more details, see the individual scripts and documentation in the project folders.
