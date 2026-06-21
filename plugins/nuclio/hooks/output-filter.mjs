// This PostToolUse hook emits a filtered post-use summary for Bash output.
// It is not relied on to replace or hide the original Bash output from Claude Code context.
const lines = (process.env.CLAUDE_TOOL_OUTPUT || '').split('\n');
const filtered = lines.filter((line) => /FAIL|ERROR|Traceback|Expected|Actual/.test(line));

console.log((filtered.length ? filtered : lines.slice(-20)).join('\n'));
