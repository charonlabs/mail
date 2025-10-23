# MAIL Standard Library: File System Utilities

**Module**: `mail.stdlib.fs`

These helpers provide controlled filesystem access for agents. Paths are resolved relative to the runtime’s working directory, so they respect whatever sandbox the deployment applies. All actions return a string: either a success message (often the file contents) or an error prefixed with `"Error:"` describing the failure.

> Safety tip: grant these tools only to trusted agents, and pair them with runtime sandboxing. They never follow symlinks intentionally but will operate on whatever the OS exposes.

## `read_file`
- **Import**: `python::mail.stdlib.fs.actions:read_file`
- **Payload**: `{ "path": "./notes/todo.txt" }`
- **Behavior**: Returns the file contents as text. Rejects missing paths, directories, or non-string arguments.

## `write_file`
- **Import**: `python::mail.stdlib.fs.actions:write_file`
- **Payload**: `{ "path": "./notes/todo.txt", "content": "Buy milk" }`
- **Behavior**: Writes the supplied text. Creates parent directories automatically when the file does not exist; overwrites existing files. Requires both `path` and `content` to be strings.

## `delete_file`
- **Import**: `python::mail.stdlib.fs.actions:delete_file`
- **Payload**: `{ "path": "./notes/old.txt" }`
- **Behavior**: Removes the target file. Fails when the path is missing or points to a directory.

## `create_directory`
- **Import**: `python::mail.stdlib.fs.actions:create_directory`
- **Payload**: `{ "path": "./archives/2025" }`
- **Behavior**: Creates the directory (and parent folders) when it does not already exist. Returns an error if the path exists or resolves to a file.

## `read_directory`
- **Import**: `python::mail.stdlib.fs.actions:read_directory`
- **Payload**: `{ "path": "./notes" }`
- **Behavior**: Lists directory entries (files and folders) line by line, sorted by name. Errors when the path is missing or not a directory.

### Usage example

```json
{
  "action_imports": [
    "python::mail.stdlib.fs.actions:read_file",
    "python::mail.stdlib.fs.actions:write_file"
  ],
  "agents": [
    {
      "name": "scribe",
      "actions": ["read_file", "write_file"],
      "agent_params": {}
    }
  ]
}
```

This configuration lets the `scribe` agent read or update files inside the deployment sandbox without redefining schemas in `swarms.json`.
