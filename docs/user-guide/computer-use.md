# Computer Use

OpenJarvis can perform local computer actions through dedicated tools when the active model and server route support tool calling.

Available actions:

- `open_application` opens installed desktop apps.
- `open_path` opens a local file or folder in the system UI.
- `list_directory` lists folder contents.
- `find_files` searches for files by pattern.
- `file_read` reads safe local text files.
- `file_write` writes text files.
- `create_folder` creates directories.
- `copy_path` copies files or folders.
- `move_path` moves or renames files or folders.
- `delete_path` deletes files or folders.
- `shell_exec` runs a command only when no safer tool fits.

Confirmation policy:

- Low-risk actions such as `open_application`, `open_path`, `list_directory`, `find_files`, and `file_read` can run without confirmation.
- Riskier actions such as `create_folder`, `file_write`, `copy_path`, `move_path`, `delete_path`, and `shell_exec` require approval in the UI.
- Sensitive paths such as `.env` files, SSH keys, private keys, and common credential stores are blocked.

Safety notes:

- Prefer the most specific computer-use tool over `shell_exec`.
- Avoid requesting secrets, browser credentials, SSH material, or password vault contents.
- Deletion and overwrite operations should be treated as high-risk actions.
