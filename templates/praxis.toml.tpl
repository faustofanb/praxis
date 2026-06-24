schema_version = 1
name = "{{ workspace_name }}"
project_index = "praxis.projects.toml"
core = ".praxis/core.toml"
adapter = ".praxis/project-adapter.toml"
extensions_dir = ".praxis/extensions"
output_dir = ".praxis/out"

[entrypoint]
primary_command = "task"
taskfile = "Taskfile.yml"

[portability]
paths = "workspace-relative"
windows_supported = true

[agents]
guide = "AGENTS.md"
contracts = ".praxis/contracts/agents"
