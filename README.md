# clean_session.py

A small script that reformats a Claude Code session log (`.jsonl`) into a human-readable file. It drops noisy fields and records, renders escaped newlines, and prints a summary header.

Made for studying how Claude Code works.

## Dependencies

- Python 3.8+

## Usage

Claude Code stores session logs at:

```
~/.claude/projects/<project-dir>/<session-id>.jsonl
```

Run:

```bash
./clean_session.py <session-id.jsonl>
```

By default the output is written to the directory set by the `OUTDIR` constant near the top of the script. Override it per run with the `OUTDIR` environment variable:

```bash
OUTDIR=/path/to/dir ./clean_session.py <session-id.jsonl> 
```

Or edit the `OUTDIR` constant in the script directly to change the default permanently. If not specified, the default is set to: `./cleaned`.

Set `RENDER_ONLY=1` to skip all record/field removal and apply only the newline rendering. It writes a separate `<aiTitle>.render-only.jsonl` so you can diff the two side by side (see the [study section](#using-it-to-study-how-an-llm-works)):

```bash
RENDER_ONLY=1 ./clean_session.py <session-id.jsonl>
```

## What it does

It prints a summary header (written as `//` comments at the top) with stats about the session. Run it and read the header to see what it reports.

Editing:

- removes records of type `mode` and `permission-mode`
- removes bookkeeping fields (`uuid`, `requestId`, `cwd`, `gitBranch`, `version`, `timestamp`, `parentUuid`, `sessionId`, ...)
- flattens single text-block `content` arrays into a plain string
- renders escaped `\n` as real line breaks, indented to the field (a literal backslash-`n` in code is kept as-is)
- inserts a separator line before each record with its **original line number** in the input file and its role (`👤 user`, `🤖 assistant`, `⚙️ system`, `📝 summary`)

Because records are numbered by their original line number, the index stays stable even when records are dropped — a gap in the numbering means a record was removed there.

## Using it to study how an LLM works

> [!NOTE]
> **💡 What is JSONL?**
> 
> **JSONL basics:** JSONL (JSON Lines) is a simple format where each line is a separate JSON object.
> - **Record**: One line = one JSON object. Each record represents a single event or message in the session (user input, assistant response, tool call, etc). So when you apply this script, the output is no longer valid JSONL. 
> - **Field**: A key-value pair inside a record. For example, `"role": "user"` is a field where `role` is the key and `"user"` is the value. Fields can also be nested.

**Step 1: Understand what records are**

First, look at the raw `.jsonl` file (before running this script) to see what records actually are and how they get added in real time as you interact with Claude Code. Type different inputs and watch which records get appended. Try triggering tool use to see what records appear. This gives you a baseline understanding of what you're dealing with.

**Step 2: Analyze with the cleaned output**

Use the script to filter and clean the raw data. There is a lot more you can analyze with these files—they are a good way to study how an LLM actually works. 

Also run the script with `RENDER_ONLY=1` and open two files side by side in VS Code and compare them. Look at which fields and records the script drops and how many of each there are — select a field name and press Ctrl+F to count its occurrences. Guess what the fields in the "raw stats" at the top of the file represent.

> **Spoiler:** Naturally, not every record is fed to the model, and not every token that is fed to the model shows up here. For example, the JSON never shows when or how the system prompt or `CLAUDE.md` or git info is injected. Thinking (reasoning) tokens do appear as records — so you can tell that they happened and when the model was thinking — but their content is not shown.

**Step 3: Run experiments and test hypotheses**

Now that you understand the basics, try these experiments to see how different conditions affect what gets logged:

### Experiments to try

Use the `/context` command to see which records are actually fed to the model. Try these:

- Deny (disable) all skills, agents, MCP servers, and memory temporarily for a clearer view.
- Try typing only `"hi"`, `"/clear"`, or `"/context"` at the start of a session.
- Mix `/rewind` with other commands — observe cases where context continues to accumulate but `/rewind` fails to properly undo it.
- Run `claude --system-prompt-file empty.md` with an empty Markdown file, then use `/context`. After that, type only `.` in the file and run `claude` again — compare the output to see how much Claude's coding ability is diminished without system context.
- Once you successfully reduce System prompt tokens to 0 in the `/context` output, try exiting and entering the agents view (`← for agents`), then check `/context` again to see if it changes.
- Discover tools you don't know about by looking for `"type": "attachment"` records in the JSONL file. Ask Claude what they do, then disable the ones you don't need in your `settings.json` file.
- Check what `"type"` value tooluse records have in the JSONL file.