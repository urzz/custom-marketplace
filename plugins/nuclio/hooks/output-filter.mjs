const lines = (process.env.CLAUDE_TOOL_OUTPUT || '').split('\n');
const filtered = lines.filter((line) => /FAIL|ERROR|Traceback|Expected|Actual/.test(line));

console.log((filtered.length ? filtered : lines.slice(-20)).join('\n'));
