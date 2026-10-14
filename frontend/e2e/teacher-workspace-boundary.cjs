/* Acceptance-only workflow boundary; never used by application code. */
const assert = require('node:assert/strict');
function requireCompletedMapping(body) {
    const events = body.replaceAll('\r\n', '\n').split(/\n\n/).flatMap(block => {
        const lines = block.split('\n');
        const name = lines.find(line => line.startsWith('event:'))?.slice(6).trim();
        if (!name) return [];
        const data = lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
        return [{ name, data: JSON.parse(data) }];
    });
    assert(!events.some(event => event.name === 'error'), 'Mapping SSE contains an error event');
    const terminals = events.filter(event => event.name === 'stream_end');
    assert.equal(terminals.length, 1, 'Mapping SSE requires exactly one terminal event');
    assert.equal(events.at(-1), terminals[0], 'Mapping terminal must be the final event');
    assert.equal(terminals[0].data.outcome, 'completed', 'Mapping SSE terminal must be completed');
    return events;
}
function requireConfirmation(actual, expected) {
    assert(actual, 'Existing selection confirmation is required');
    for (const key of ['candidate_revision', 'selection_revision', 'teacher_id', 'selected_candidate_ids', 'excluded_candidate_ids'])
        assert.deepEqual(actual[key], expected[key], `Confirmation ${key} must match saved selection`);
}
module.exports = { requireCompletedMapping, requireConfirmation };
