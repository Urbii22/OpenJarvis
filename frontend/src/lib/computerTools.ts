export const COMPUTER_USE_TOOLS = [
  {
    type: 'function',
    function: {
      name: 'open_application',
      description: 'Open a local desktop app by app name or executable path. Use this when the user asks to launch Notepad, Explorer, Spotify, or another installed application.',
      parameters: {
        type: 'object',
        properties: {
          app: { type: 'string', description: 'App name or executable path.' },
          args: { type: 'string', description: 'Optional arguments.' },
        },
        required: ['app'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'open_path',
      description: 'Open a local file or folder in the operating system interface, such as Explorer on Windows.',
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'File or folder path.' },
        },
        required: ['path'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'list_directory',
      description: 'List files and folders in a local directory. Prefer this over shell_exec for browsing local paths.',
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'Directory path.' },
          recursive: { type: 'boolean', description: 'Recursive listing.' },
          max_entries: { type: 'number', description: 'Max entries to return.' },
        },
        required: ['path'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'find_files',
      description: 'Find files by fuzzy name or glob pattern. Use this when the user only knows part of a filename and wants possible matches with their full paths.',
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'Optional search root path. If omitted, search the whole system.' },
          pattern: { type: 'string', description: 'Optional pattern, e.g. *.txt or *report*' },
          query: { type: 'string', description: 'Optional fuzzy filename query, e.g. presupuesto abril or project plan' },
          recursive: { type: 'boolean', description: 'Recursive search.' },
          max_results: { type: 'number', description: 'Max results.' },
        },
        required: [],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'create_folder',
      description: 'Create a local folder, optionally with parent directories. Use this for safe directory creation instead of shell_exec.',
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'Folder path.' },
          parents: { type: 'boolean', description: 'Create parent dirs too.' },
        },
        required: ['path'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'copy_path',
      description: 'Copy a local file or folder to another path. This is safer than shell_exec for file copies.',
      parameters: {
        type: 'object',
        properties: {
          source: { type: 'string', description: 'Source path.' },
          destination: { type: 'string', description: 'Destination path.' },
          overwrite: { type: 'boolean', description: 'Overwrite destination if exists.' },
        },
        required: ['source', 'destination'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'move_path',
      description: 'Move or rename a local file or folder. Use this for file management actions that change paths.',
      parameters: {
        type: 'object',
        properties: {
          source: { type: 'string', description: 'Source path.' },
          destination: { type: 'string', description: 'Destination path.' },
          overwrite: { type: 'boolean', description: 'Overwrite destination if exists.' },
        },
        required: ['source', 'destination'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'delete_path',
      description: 'Delete a local file or folder. This is a high-risk action and should only be used when the user clearly asks for deletion.',
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'Path to delete.' },
          recursive: { type: 'boolean', description: 'Required for directories.' },
          missing_ok: { type: 'boolean', description: 'Do not fail if missing.' },
        },
        required: ['path'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'shell_exec',
      description:
        'Execute a shell command on the local machine. Use this only when no safer, more specific computer-use tool can accomplish the task.',
      parameters: {
        type: 'object',
        properties: {
          command: {
            type: 'string',
            description: 'Command to execute (e.g. start spotify, mkdir C:\\\\temp\\\\demo, dir C:\\\\Users).',
          },
          timeout: {
            type: 'number',
            description: 'Optional timeout in seconds.',
          },
          cwd: {
            type: 'string',
            description: 'Optional working directory.',
          },
        },
        required: ['command'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'file_read',
      description:
        'Read a text file from disk. Use this to inspect safe local text files when the user asks for their contents.',
      parameters: {
        type: 'object',
        properties: {
          path: {
            type: 'string',
            description: 'Absolute or relative file path.',
          },
          encoding: {
            type: 'string',
            description: 'Optional text encoding (default utf-8).',
          },
        },
        required: ['path'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'file_write',
      description:
        'Write or append text to a file. Use this to create or edit local notes, scripts, and text-based config files.',
      parameters: {
        type: 'object',
        properties: {
          path: {
            type: 'string',
            description: 'Absolute or relative file path.',
          },
          content: {
            type: 'string',
            description: 'Text content to write.',
          },
          mode: {
            type: 'string',
            enum: ['overwrite', 'append'],
            description: 'Write mode (default overwrite).',
          },
          encoding: {
            type: 'string',
            description: 'Optional text encoding (default utf-8).',
          },
        },
        required: ['path', 'content'],
      },
    },
  },
] as const;
