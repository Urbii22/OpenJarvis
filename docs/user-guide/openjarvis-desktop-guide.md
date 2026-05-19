# OpenJarvis Desktop Guide

## What OpenJarvis Is

OpenJarvis is a local-first AI assistant and agent platform. It combines chat, local models, tools, agents, data sources, and desktop workflows in a single app. Depending on how you configure it, it can behave as a simple assistant, a research agent, a code assistant, or a desktop operator that acts on your computer.

This guide focuses on practical day-to-day use of the desktop experience that is currently present in this repository.

## Main Use Cases

- Chat with local or remote models from one interface.
- Switch between lightweight and stronger models depending on the task.
- Use computer actions such as opening apps, listing folders, searching files, and reading safe local text files.
- Connect data sources and channels so the assistant can work with your own information.
- Run agent workflows that can use tools and take multi-step actions.
- Inspect activity, logs, costs, and basic system telemetry from the UI.

## Main Areas Of The App

- Chat: the main conversation interface where you send prompts, see tool calls, and receive streamed answers.
- Dashboard: the monitoring area for system and runtime information.
- Data Sources: where connectors and knowledge sources are configured.
- Agents: where managed agents and agent-related workflows are handled.
- Logs: where recent activity and runtime events can be reviewed.
- Settings: where model, API, UI, and behavior options are adjusted.
- Get Started: onboarding and setup help.

## Getting Started

1. Start the backend server and open the desktop or web UI.
2. Make sure at least one model provider is available, such as Ollama.
3. Choose a model in the session panel before starting heavier tasks.
4. Open a chat and begin with a simple request to confirm the model responds correctly.
5. If you want the assistant to act on the machine, keep Computer Use enabled.

## Model Selection Advice

Not every model is equally capable at tool use.

- Small models are fine for light chat, summaries, and simple reformulation tasks.
- Mid-size or larger models are better for tool calling, computer actions, and multi-step reasoning.
- For computer-use tasks, stronger local models generally perform better than very small ones.

Practical guidance based on recent validation in this workspace:

- `qwen3.5:9b` is a strong choice for local computer-use behavior.
- `llama3.1:latest` is a reasonable alternative.
- Very small models may ignore tools and answer like plain text assistants.

## Computer Use

OpenJarvis can perform local computer actions through dedicated tools when the model and server route support tool calling.

Low-friction actions that can run without confirmation:

- Open an installed application.
- Open a local file or folder in the system UI.
- List the contents of a directory.
- Search for files.
- Read safe local text files.

Higher-risk actions that require confirmation:

- Create folders.
- Write files.
- Copy files or folders.
- Move or rename files or folders.
- Delete files or folders.
- Execute shell commands when no safer tool fits.

Sensitive targets are blocked. Examples include `.env` files, SSH material, private keys, and common credential stores.

## File Search And Reading

The file search flow is designed so you do not need to remember exact filenames.

- You can ask for a file approximately by name.
- The assistant can search across the whole system and return likely matches.
- Results include full paths so the assistant can then open the file or read its contents.
- This is especially useful when you only remember part of a filename or a similar phrase.

Example requests:

- "Busca el archivo del presupuesto de abril y dime dónde está."
- "Encuentra archivos que se parezcan a invoice final."
- "Busca mis notas de Docker y léeme el contenido del archivo que mejor encaje."

## Voice Shell

This repository also includes a new voice-first desktop shell that is feature-flagged.

- It can be enabled with `VITE_VOICE_SHELL_ENABLED=true`.
- It can also be enabled through local storage using `openjarvis-desktop-voice-shell-enabled`.
- The shell persists its mode using `openjarvis-desktop-voice-shell-mode`.
- Runtime states include `READY`, `LISTENING`, `THINKING`, `SPEAKING`, `INTERRUPTED`, and `ERROR`.

If needed, you can roll back to the legacy UI by disabling the feature flag.

## Good Prompting Patterns

- Be direct when you want an action: "Abre Spotify."
- Ask for discovery first when you do not know a path: "Busca archivos que se parezcan a contratos 2025."
- Ask for inspection after search: "Lee el contenido del archivo que mejor encaje."
- Keep risky actions explicit: "Crea una carpeta llamada facturas-2026 en Documentos."

## Safety And Expectations

- Prefer using dedicated computer-use tools rather than shell execution.
- Do not ask the assistant to fetch secrets, tokens, passwords, SSH keys, or vault contents.
- Treat destructive requests such as deleting or overwriting files as intentional actions that deserve review.
- If a model refuses to use tools, switch to a stronger model before assuming the feature is broken.

## Troubleshooting

If the assistant answers as if it were only a text bot:

- Confirm that Computer Use is enabled in the session.
- Switch to a stronger model.
- Restart the backend if you recently changed tool policy or server behavior.

If an app opens but confirmations still appear too often:

- Check whether the requested action falls into the high-risk group.
- Make sure you are testing on the current backend version and not an older running process.

If file search is noisy:

- Add a few more keywords about the filename.
- Ask for the file type if you know it, such as `.md`, `.txt`, or `.py`.

## Suggested First Commands

- "Abre Spotify."
- "Busca archivos que se parezcan a roadmap desktop."
- "Lee el contenido del archivo que mejor encaje."
- "Abre la carpeta donde está ese archivo."
- "Crea una carpeta llamada pruebas-openjarvis en el escritorio."

## Summary

OpenJarvis is best understood as a local AI control surface: chat, agents, models, your own data, and computer actions in one place. For the desktop experience, the most important habits are choosing a model with enough capability, using file search before file reading when paths are unclear, and reserving destructive actions for deliberate approval.
