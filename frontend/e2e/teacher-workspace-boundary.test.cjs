const { test } = require('node:test');
const assert = require('node:assert/strict');
const { requireCompletedMapping } = require('./teacher-workspace-boundary.cjs');
const event = (name, data) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
test('rejects HTTP200 streams with errors, failed/missing/duplicate/nonfinal terminal events', () => {
    for (const body of [event('error', { message: 'controlled failure' }) + event('stream_end', { outcome: 'completed' }), event('stream_end', { outcome: 'failed' }), event('text_delta', { text: 'not complete' }), event('stream_end', { outcome: 'completed' }).repeat(2), event('stream_end', { outcome: 'completed' }) + event('error', {})])
        assert.throws(() => requireCompletedMapping(body));
});
test('accepts a complete SSE sequence including CRLF and comments', () => {
    assert.equal(requireCompletedMapping(': keepalive\r\n\r\n' + (event('text_delta', { text: 'done' }) + event('stream_end', { outcome: 'completed' })).replaceAll('\n', '\r\n')).at(-1).data.outcome, 'completed');
});
