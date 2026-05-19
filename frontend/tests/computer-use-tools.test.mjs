import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const toolsSource = readFileSync(new URL('../src/lib/computerTools.ts', import.meta.url), 'utf8');
const promptSource = readFileSync(new URL('../src/lib/computerUsePrompt.ts', import.meta.url), 'utf8');

for (const name of [
  'open_application',
  'open_path',
  'list_directory',
  'find_files',
  'file_read',
  'file_write',
  'create_folder',
  'copy_path',
  'move_path',
  'delete_path',
  'shell_exec',
]) {
  assert.match(toolsSource, new RegExp(`name:\\s*['"]${name}['"]`));
  assert.match(promptSource, new RegExp(name));
}

assert.match(promptSource, /Use tools instead of saying you cannot access the computer/);
assert.match(promptSource, /Never attempt to read secrets/);
