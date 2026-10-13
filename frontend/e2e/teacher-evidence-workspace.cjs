/* Controlled real-database acceptance. No API response mocks. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { execFileSync, spawn } = require('node:child_process');
const path = require('node:path');
const { chromium } = require('playwright');
const UI = process.env.WORKSPACE_UI_URL;
const API = process.env.WORKSPACE_API_URL;
const manifestPath = process.env.WORKSPACE_FIXTURE_PATH;
const phase = process.env.WORKSPACE_SCENARIO || 'all';
const safeError = error => String(error.message ?? error).replace(/Bearer\s+[A-Za-z0-9_.-]+/g, 'Bearer [REDACTED]');
const action = (name, payload, extra = []) => JSON.parse(execFileSync('/Applications/Docker.app/Contents/Resources/bin/docker', ['exec', '-i', 'lab_tutor_workspace_acceptance_api', '/app/.venv/bin/python', '-m', 'tests.acceptance.teacher_workspace_server', '--manifest', '/tmp/teacher-workspace.json', '--action', name, ...extra], { input: payload ? JSON.stringify(payload) : undefined, encoding: 'utf8' }));
const sourceFile = process.argv.find(arg => arg.endsWith('/teacher-evidence-workspace.cjs'));
const output = process.env.WORKSPACE_OUTPUT_DIR || path.resolve(path.dirname(sourceFile), '../../output/teacher-evidence-workspace/acceptance');
(async () => {
    assert(UI && API && manifestPath, 'Explicit isolated URLs and private manifest required');
    assert.equal(fs.statSync(manifestPath).mode & 0o777, 0o600, 'Manifest must be private');
    const fixture = JSON.parse(fs.readFileSync(manifestPath));
    assert.equal(fixture.database, 'lab_tutor_workspace_acceptance');
    if (phase === 'all') {
        assert.equal(action('sql-readback').publication_revision, 0, 'Full orchestration requires fresh owned fixture');
        fs.mkdirSync(output, { recursive: true });
        fs.writeFileSync(path.join(output, 'student-before.json'), JSON.stringify(action('seed-student'), null, 2));
        fs.writeFileSync(path.join(output, 'corpus-sql-readback.json'), JSON.stringify(action('seed-corpus'), null, 2));
        for (const scenario of ['purge', 'layout', 'tooltip', 'tooltip-variants', 'tooltip-five-roles', 'context', 'workflow', 'corpus', 'approval', 'revisions', 'lifecycle', 'load-failures', 'recovery', 'supplemental', 'provenance', 'reset-proof']) {
            console.log(`START ${scenario}`);
            execFileSync(process.execPath, [process.argv[1], sourceFile], { env: { ...process.env, WORKSPACE_SCENARIO: scenario }, stdio: 'inherit' });
            console.log(`EXIT 0 ${scenario}`);
        }
        console.log('PASS every controlled real-database acceptance phase');
        return;
    }
    const browser = await chromium.launch({ headless: true, channel: "chrome" });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    const consoleErrors = [];
    const mutations = [];
    let chartModuleURL;
    let disabledStorageVerified = false;
    const page = await context.newPage();
    page.setDefaultTimeout(20000);
    page.on('console', message => {
        if (message.type() === 'error')
            consoleErrors.push({ text: message.text(), url: message.location().url });
    });
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
        if (/echarts_core\.js/.test(request.url()))
            chartModuleURL = request.url();
        if (request.url().includes('/market-demand/') && request.method() !== 'GET')
            mutations.push({ method: request.method(), url: request.url() });
    });
    await page.addInitScript(tokens => {
        localStorage.setItem('access_token', tokens.access_token);
        localStorage.setItem('refresh_token', tokens.refresh_token);
    }, fixture.teacher);
    try {
        let review;
        const chart = page.getByRole('region', { name: 'Demand overview' }).locator('[role=img]').first();
        if (!['supplemental', 'reset-proof'].includes(phase)) {
            const read = await context.request.get(`${API}/courses/${fixture.course.id}/market-demand/skill-review`, { headers: { Authorization: `Bearer ${fixture.teacher.access_token}` } });
            assert.equal(read.status(), 200);
            review = await read.json();
            assert.equal(review.candidates.length, 30);
            assert.equal(review.candidate_revision, 1);
            await page.goto(`${UI}/courses/${fixture.course.id}/market-analyst`);
            await page.getByRole('region', { name: 'Demand overview' }).waitFor();
            await chart.locator('svg').waitFor();
            assert.equal(await page.getByLabel('Overview values').locator(':scope > li').count(), 12);
            await page.screenshot({ path: path.join(output, ['tooltip-three-roles', 'tooltip-four-roles'].includes(phase) ? `${phase}-initial-1440.png` : 'initial-1440.png'), fullPage: true });
            const before = mutations.length;
            const bar = chart.locator('path[fill="#2563eb"]').first();
            await bar.scrollIntoViewIfNeeded();
            const mark = await bar.boundingBox();
            assert(mark && mark.width > 0 && mark.height > 0);
            await page.mouse.click(mark.x + mark.width / 2, mark.y + mark.height / 2);
            await page.getByRole('region', { name: 'Focused evidence' }).getByRole('heading', { name: 'Python', exact: true }).waitFor();
            assert.equal(mutations.length, before, 'Actual ECharts mark focus must not write or chat');
            console.log('PASS actual SVG bar click focuses Python without mutation');
        }
        if (phase === 'metadata') {
            const proof = action('metadata-compatibility');
            const prior = JSON.parse(fs.readFileSync(path.join(output, 'corpus-sql-readback.json'))).find(item => item.name === 'max_two_no_repeated_skill');
            assert.deepEqual(proof.normal_review, prior.review, 'Later HEAD normal API must equal original d1a3660 corpus facts');
            await page.goto(`${UI}/courses/${proof.course_id}/market-analyst`);
            await page.getByRole('region', { name: 'Demand overview' }).waitFor();
            await page.getByRole('button', { name: 'Compare', exact: true }).click();
            const compare = page.getByRole('region', { name: 'Occupation comparison' });
            await compare.getByRole('button', { name: 'Across occupations', exact: true }).click();
            const roles = proof.normal_review.analysis_metadata.occupations;
            for (const role of roles)
                await compare.getByRole('checkbox', { name: `Display ${role.title}`, exact: true }).check();
            const plot = compare.locator('[role=img]').first();
            await plot.locator('svg').waitFor();
            const values = await plot.evaluate(async (element, url) => {
                const core = await import(url);
                return core.getInstanceByDom(element).getOption().series[0].data.map(item => item.value);
            }, chartModuleURL);
            const expected = [];
            [...proof.normal_review.candidates].sort((a, b) => a.display_name.localeCompare(b.display_name)).forEach((candidate, y) => roles.forEach((role, x) => {
                const association = candidate.onet_associations.find(item => item.relation === 'equivalent' && item.evidence.soc_code === role.soc_code);
                expected.push([x, y, association.evidence.ratings.IM.value]);
            }));
            assert.deepEqual(values, expected);
            assert.equal(mutations.length, 0, 'Metadata and chart inspection are read-only');
            fs.writeFileSync(path.join(output, 'metadata-compatibility.json'), JSON.stringify({ productHead: '62ab13ec792c8103b58c993b110d6184d896d2a4', ...proof, chartValues: values, baselineEquality: true }, null, 2));
            await page.screenshot({ path: path.join(output, 'metadata-current-head.png'), fullPage: true });
            console.log('PASS later HEAD real authenticated missing/null/blank title fallback; exact SQL config restored; normal metadata/evidence/chart identical to d1a3660; no writes');
        }
        if (['all', 'purge'].includes(phase)) {
            const focused = page.getByRole('region', { name: 'Focused evidence' });
            const disclosure = focused.getByText('Evidence for Python', { exact: true });
            await disclosure.click();
            const activeRef = review.candidates.find(c => c.display_name === 'Python').evidence_references.find(ref => ref.status === 'active');
            assert(activeRef, 'An active synthetic posting is required');
            const snapshotIndex = fixture.snapshot_ids.indexOf(activeRef.snapshot_id);
            const original = await (await context.request.get(`${API}/courses/${fixture.course.id}/market-demand/skill-review/postings/${activeRef.snapshot_id}`, { headers: { Authorization: `Bearer ${fixture.teacher.access_token}` } })).json();
            assert(original.description_text);
            await focused.getByRole('button', { name: 'Load full posting evidence' }).nth(snapshotIndex).click();
            await focused.getByText(original.description_text, { exact: true }).first().waitFor();
            console.log('PASS owned full posting inspected');
            execFileSync('/Applications/Docker.app/Contents/Resources/bin/docker', ['exec', 'lab_tutor_workspace_acceptance_api', '/app/.venv/bin/python', '-m', 'tests.acceptance.teacher_workspace_server', '--manifest', '/tmp/teacher-workspace.json', '--action', 'purge-first-posting', '--snapshot-index', String(snapshotIndex)], { stdio: 'pipe' });
            const purged = await context.request.get(`${API}/courses/${fixture.course.id}/market-demand/skill-review/postings/${activeRef.snapshot_id}`, { headers: { Authorization: `Bearer ${fixture.teacher.access_token}` } });
            assert.equal(purged.status(), 200);
            const posting = await purged.json();
            assert(posting.purged_at);
            assert(!posting.description_text);
            await disclosure.click();
            await focused.getByRole('button', { name: /Load|Reload full posting evidence/ }).first().waitFor({ state: 'detached' });
            await disclosure.click();
            await page.screenshot({ path: path.join(output, 'posting-after-purge.png'), fullPage: true });
            assert.equal(await focused.getByText(original.description_text, { exact: true }).count(), 0, 'Reopening purged posting must not show cached source body');
            await focused.getByText(/Posting content unavailable: purged/).waitFor();
            assert.deepEqual(errors, [], 'Unexpected runtime errors');
            console.log('PASS current purged inspection has no cached source body');
        }
        if (phase === 'tooltip') {
            const results = [];
            for (const width of [320, 390, 768, 1024, 1440]) {
                await page.setViewportSize({ width, height: 1000 });
                for (const theme of ['Light', 'Dark']) {
                    await page.getByRole('button', { name: 'Toggle theme', exact: true }).click();
                    await page.getByRole('menuitem', { name: theme, exact: true }).click();
                    const pane = page.getByRole('tab', { name: 'Workspace', exact: true });
                    if (await pane.isVisible())
                        await pane.click();
                    await chart.scrollIntoViewIfNeeded();
                    await chart.locator('svg').waitFor();
                    const mark = await chart.locator('path[fill="#2563eb"]').last().boundingBox();
                    await page.mouse.move(mark.x + mark.width / 2, mark.y + mark.height / 2);
                    await chart.locator('text').filter({ hasText: 'supporting / assessed' }).waitFor();
                    const measured = await chart.evaluate(element => {
                        const box = element.getBoundingClientRect();
                        return { chart: { left: box.left, right: box.right, width: box.width }, texts: [...element.querySelectorAll('svg text')].map(node => { const r = node.getBoundingClientRect(); return { text: node.textContent, left: r.left, right: r.right, width: r.width }; }) };
                    });
                    assert(measured.texts.map(row => row.text).join('').replace(/\s/g, '').includes('Synthetic competency 24: 70% · 7 / 10 supporting / assessed'.replace(/\s/g, '')), 'Complete demand label, metric and denominator visible in SVG');
                    results.push({ width, theme, ...measured });
                    fs.writeFileSync(path.join(output, 'tooltip-geometry.json'), JSON.stringify(results, null, 2));
                    await page.screenshot({ path: path.join(output, `tooltip-${width}-${theme.toLowerCase()}.png`), fullPage: true });
                    for (const text of measured.texts)
                        assert(text.left >= measured.chart.left - 1 && text.right <= measured.chart.right + 1, `Clipped chart text at ${width}/${theme}: ${JSON.stringify(text)} chart=${JSON.stringify(measured.chart)}`);
                }
            }
            console.log('PASS actual long-label tooltip hover fits all five widths in light/dark');
        }
        if (['tooltip-variants', 'tooltip-three-roles', 'tooltip-four-roles', 'tooltip-five-roles'].includes(phase)) {
            const roleCount = { 'tooltip-variants': 2, 'tooltip-three-roles': 3, 'tooltip-four-roles': 4, 'tooltip-five-roles': 5 }[phase];
            const existing = process.env.WORKSPACE_EXISTING_TOOLTIP_COURSE;
            const seeded = existing ? { course: { id: Number(existing) }, review: await (await context.request.get(`${API}/courses/${Number(existing)}/market-demand/skill-review`, { headers: { Authorization: `Bearer ${fixture.teacher.access_token}` } })).json() } : action('seed-tooltip', undefined, ['--role-count', String(roleCount)]);
            assert.equal(seeded.review.analysis_metadata.occupations.length, roleCount);
            const boundedRoleFix = [3, 4].includes(roleCount);
            const modelCallsBefore = boundedRoleFix ? action('model-readback').length : null;
            if (boundedRoleFix) {
                assert(process.env.WORKSPACE_FIXTURE_GENERATION && process.env.WORKSPACE_PROOF_HEAD);
                assert.equal(modelCallsBefore, 0);
                const source = JSON.parse(fs.readFileSync(path.join(output, 'roles-fix-source.json')))[0].review;
                assert.deepEqual(seeded.review.analysis_metadata.occupations.slice(0, 2), source.analysis_metadata.occupations);
                seeded.review.candidates.forEach((candidate, index) => {
                    assert.deepEqual(candidate.job_metrics, source.candidates[index].job_metrics);
                    assert.deepEqual(candidate.onet_associations, source.candidates[index].onet_associations);
                });
                for (const role of seeded.review.analysis_metadata.occupations.slice(2)) {
                    assert.match(role.title, /^SYNTHETIC NO-RATING LAYOUT ROLE/);
                    assert(!seeded.review.candidates.some(candidate => candidate.onet_associations.some(a => a.evidence.soc_code === role.soc_code)));
                }
            }
            const records = [];
            await page.goto(`${UI}/courses/${seeded.course.id}/market-analyst`);
            const before = mutations.length;
            for (const width of [320, 390, 768]) {
                await page.setViewportSize({ width, height: 1000 });
                for (const theme of ['Light', 'Dark']) {
                    await page.getByRole('button', { name: 'Toggle theme', exact: true }).click();
                    await page.getByRole('menuitem', { name: theme, exact: true }).click();
                    const pane = page.getByRole('tab', { name: 'Workspace', exact: true });
                    if (await pane.isVisible())
                        await pane.click();
                    for (const variant of ['demand', 'scatter', 'heatmap']) {
                        await page.getByRole('button', { name: variant === 'demand' ? 'Overview' : 'Compare', exact: true }).click();
                        const region = page.getByRole('region', { name: variant === 'demand' ? 'Demand overview' : 'Occupation comparison' });
                        if (variant !== 'demand') {
                            await region.getByRole('button', { name: variant === 'scatter' ? 'Demand and importance' : 'Across occupations', exact: true }).click();
                            for (const role of seeded.review.analysis_metadata.occupations)
                                await region.getByRole('checkbox', { name: `Display ${role.title}`, exact: true }).check();
                            if (variant === 'scatter')
                                await region.getByLabel('Compare occupation', { exact: true }).selectOption('15-1252.00');
                        }
                        const element = region.locator('[role=img]').first();
                        await element.locator('svg').waitFor();
                        await element.scrollIntoViewIfNeeded();
                        await page.waitForFunction(() => [...document.querySelectorAll('[role=img]')].filter(e => e.querySelector('svg')).every(e => Math.abs(e.clientWidth - Number(e.querySelector('svg').getAttribute('width'))) <= 1));
                        if (width < 768) {
                            await page.getByRole('tab', { name: /^Conversation/ }).click();
                            await page.getByRole('tab', { name: 'Workspace', exact: true }).click();
                            await element.locator('svg').waitFor();
                        }
                        await element.scrollIntoViewIfNeeded();
                        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
                        const point = await element.evaluate(async (e, url) => { const instance = (await import(url)).getInstanceByDom(e); const data = instance.getOption().series[0].data[0]; const type = instance.getOption().series[0].type; return { pixel: instance.convertToPixel({ seriesIndex: 0 }, type === 'bar' ? [data.value, 0] : data.value), expected: data.tooltipText }; }, chartModuleURL);
                        const box = await element.boundingBox();
                        await page.mouse.move(0, 0);
                        await page.mouse.move(box.x + point.pixel[0] - (variant === 'demand' ? 5 : 0), box.y + point.pixel[1]);
                        const escaped = point.expected.replaceAll('{', '｛').replaceAll('}', '｝');
                        await page.waitForFunction(({ expected }) => [...document.querySelectorAll('[role=img] svg text')].map(e => e.textContent).join('').replace(/\s/g, '').includes(expected.replace(/\s/g, '')), { expected: escaped });
                        const measured = await element.evaluate(e => { const r = e.getBoundingClientRect(); return { box: { left: r.left, right: r.right, top: r.top, bottom: r.bottom }, texts: [...e.querySelectorAll('svg text')].map(t => { const r = t.getBoundingClientRect(); return { text: t.textContent, left: r.left, right: r.right, top: r.top, bottom: r.bottom }; }) }; });
                        for (const text of measured.texts)
                            assert(text.left >= measured.box.left - 1 && text.right <= measured.box.right + 1 && text.top >= measured.box.top - 1 && text.bottom <= measured.box.bottom + 1, `Clipped ${variant} tooltip text ${width}/${theme}: ${JSON.stringify(text)}`);
                        assert.equal(await element.locator('script').count(), 0);
                        assert.equal(mutations.length, before, 'Hover is readonly');
                        const headers = variant === 'heatmap' ? measured.texts.filter(t => t.top > measured.box.top + 50 && t.bottom < measured.box.top + 100).sort((a, b) => a.left - b.left) : [];
                        if (variant === 'heatmap') {
                            assert.equal(headers.length, seeded.review.analysis_metadata.occupations.length, 'Every occupation header rendered');
                            for (let i = 1; i < headers.length; i++)
                                assert(headers[i - 1].right <= headers[i].left, 'Occupation headers overlap');
                        }
                        records.push({ roleCount, width, theme, variant, headers, expected: escaped, ...measured });
                        if (width === 320)
                            await page.screenshot({ path: path.join(output, `${phase}-${variant}-${theme.toLowerCase()}.png`), fullPage: true });
                    }
                }
            }
            fs.writeFileSync(path.join(output, `${phase}.json`), JSON.stringify({ fixture: seeded, records, ...(boundedRoleFix ? { fixtureGeneration: process.env.WORKSPACE_FIXTURE_GENERATION, proofHead: process.env.WORKSPACE_PROOF_HEAD, roleCount, modelCallsBefore, modelCallsAfter: action('model-readback').length, browserMutations: mutations.length } : {}) }, null, 2));
            if (boundedRoleFix) {
                assert.equal(action('model-readback').length, 0);
                assert.equal(mutations.length, 0);
                const current = await context.request.get(`${API}/courses/${seeded.course.id}/market-demand/skill-review`, { headers: { Authorization: `Bearer ${fixture.teacher.access_token}` } });
                assert.equal(current.status(), 200);
                assert.deepEqual(await current.json(), seeded.review, 'Read-only geometry must not change SQL-backed review');
            }
            console.log('PASS demand/scatter/heatmap complete source-token/nonASCII/unbroken labels and exact metrics inside SVG at320/390/768 in both themes; readonly actual hover');
        }
        if (['all', 'layout'].includes(phase)) {
            const geometry = [];
            for (const width of [1440, 1024, 768, 390, 320]) {
                await page.setViewportSize({ width, height: 1000 });
                for (const theme of ['Light', 'Dark']) {
                    await page.getByRole('button', { name: 'Toggle theme', exact: true }).click();
                    await page.getByRole('menuitem', { name: theme, exact: true }).click();
                    await page.waitForFunction(dark => document.documentElement.classList.contains('dark') === dark, theme === 'Dark');
                    const pane = page.getByRole('tab', { name: 'Workspace', exact: true });
                    if (await pane.isVisible())
                        await pane.click();
                    await chart.scrollIntoViewIfNeeded();
                    await chart.locator('svg').waitFor();
                    await page.waitForFunction(() => { const e = document.querySelector('[aria-label="Demand overview"] [role=img]'); return e && Math.abs(e.clientWidth - Number(e.querySelector('svg')?.getAttribute('width'))) <= 1; });
                    const measure = await chart.evaluate(element => {
                        const svg = element.querySelector('svg');
                        const box = element.getBoundingClientRect();
                        const ticks = [...svg.querySelectorAll('text')].filter(node => /^\d+$/.test(node.textContent)).map(node => { const r = node.getBoundingClientRect(); return { text: node.textContent, left: r.left, right: r.right, top: r.top }; }).sort((a, b) => a.left - b.left);
                        return { ticks, width: innerWidth, documentWidth: document.documentElement.scrollWidth, boxWidth: box.width, svgWidth: Number(svg.getAttribute('width')), svgHeight: Number(svg.getAttribute('height')), bars: svg.querySelectorAll('path[fill="#2563eb"]').length };
                    });
                    geometry.push({ theme, ...measure });
                    assert(measure.documentWidth <= width, `Document overflow at ${width}/${theme}: ${measure.documentWidth}`);
                    assert(measure.boxWidth > 0 && measure.svgWidth > 0 && measure.svgHeight > 0);
                    assert(Math.abs(measure.boxWidth - measure.svgWidth) <= 1, `ResizeObserver chart width stale at ${width}/${theme}`);
                    assert.equal(measure.bars, 12);
                    for (let i = 1; i < measure.ticks.length; i++)
                        assert(measure.ticks[i - 1].right <= measure.ticks[i].left, `Overlapping chart tick labels at ${width}/${theme}: ${JSON.stringify(measure.ticks)}`);
                    await page.screenshot({ path: path.join(output, `chart-${width}-${theme.toLowerCase()}.png`), fullPage: true });
                    if (width >= 768) {
                        await page.locator('[data-sidebar=trigger]').click();
                        await page.waitForFunction(() => {
                            const e = document.querySelector('[aria-label="Demand overview"] [role=img]');
                            return e && Math.abs(e.clientWidth - Number(e.querySelector('svg')?.getAttribute('width'))) <= 1;
                        });
                        const size = await chart.boundingBox();
                        assert(size.width > 0);
                    }
                }
                console.log(`PASS chart resize/theme/sidebar at ${width}`);
            }
            fs.writeFileSync(path.join(output, 'geometry.json'), JSON.stringify(geometry, null, 2));
        }
        if (['all', 'context'].includes(phase)) {
            const headers = { Authorization: `Bearer ${fixture.teacher.access_token}` };
            const reviewURL = `${API}/courses/${fixture.course.id}/market-demand/skill-review`;
            const fresh = async () => { const r = await context.request.get(reviewURL, { headers }); assert.equal(r.status(), 200); return r.json(); };
            const pane = page.getByRole('region', { name: 'Skill draft review' });
            const question = page.getByRole('textbox', { name: 'Question', exact: true });
            await page.getByRole('button', { name: 'Data', exact: true }).click();
            const table = page.getByRole('region', { name: 'Evidence data' });
            assert.equal(await table.locator('tbody tr').count(), 25);
            await table.getByRole('button', { name: 'Next rows', exact: true }).click();
            assert.equal(await table.locator('tbody tr').count(), 5);
            await table.getByRole('button', { name: 'Previous rows', exact: true }).click();
            await table.getByRole('button', { name: 'Inspect Python', exact: true }).focus();
            await page.keyboard.press('Enter');
            await page.getByRole('region', { name: 'Focused evidence' }).getByRole('heading', { name: 'Python', exact: true }).waitFor();
            const withoutWrites = mutations.length;
            await table.getByRole('button', { name: 'Ask about Python', exact: true }).click();
            assert.match(await question.inputValue(), /Python/);
            assert.equal(mutations.length, withoutWrites);
            await page.getByRole('textbox', { name: 'Filter evidence', exact: true }).fill('Python');
            await pane.getByRole('checkbox', { name: 'Select category Programming (15 current members)', exact: true }).check();
            assert.match(await pane.innerText(), /15 selected/);
            await page.getByRole('textbox', { name: 'Filter evidence', exact: true }).fill('');
            await pane.getByRole('checkbox', { name: 'Select Critical Thinking', exact: true }).uncheck();
            assert.match(await pane.innerText(), /14 selected/);
            await pane.getByRole('button', { name: 'Undo local change', exact: true }).click();
            await pane.getByRole('checkbox', { name: 'Select Critical Thinking', exact: true }).uncheck();
            assert.equal((await fresh()).selected_candidate_ids.length, review.selected_candidate_ids.length, 'Local category/exclusion controls must not save');
            await pane.getByRole('button', { name: 'Save draft', exact: true }).click();
            await pane.getByText('Draft saved', { exact: false }).waitFor();
            const saved = await fresh();
            assert.equal(saved.selected_candidate_ids.length, 14);
            assert(saved.excluded_candidate_ids.includes(fixture.candidate_ids[1]));
            await pane.getByRole('checkbox', { name: 'Select Synthetic competency 16', exact: true }).check();
            await page.getByRole('button', { name: 'Refresh context', exact: true }).click();
            assert.equal(await pane.getByRole('checkbox', { name: 'Select Synthetic competency 16', exact: true }).isChecked(), true, 'Dirty same-run refresh retains local choices');
            assert.equal((await fresh()).selected_candidate_ids.length, 14);
            console.log('PASS keyboard Data/paging, filter/category/exclusion/undo, real save and dirty refresh');
            action('model-queue', [{ content: 'Controlled explanation of the saved Python evidence.', delay: 1 }]);
            await question.fill('Explain the displayed Python evidence.');
            const chatResponse = page.waitForResponse(r => r.url().endsWith('/market-demand/chat'));
            await page.getByRole('button', { name: 'Send message', exact: true }).click();
            await (await chatResponse).finished();
            await page.getByText('Controlled explanation of the saved Python evidence.', { exact: true }).waitFor();
            await page.waitForFunction(() => document.querySelector('textarea[aria-label="Question"]')?.value === '');
            let calls = action('model-readback');
            assert.deepEqual(calls.at(-1).tools, []);
            assert.equal((await fresh()).selected_candidate_ids.length, 14);
            assert(calls.at(-1).evidence.candidates.some(c => c.candidate_id === fixture.candidate_ids[0]));
            console.log('PASS contextual Explain used real graph/checkpointer, zero model tools, no selection write');
            await table.getByRole('button', { name: 'Ask about Synthetic competency 17', exact: true }).click();
            const proposalCandidate = fixture.candidate_ids[16];
            action('model-queue', [{ tool_calls: [{ id: 'task12-proposal', name: 'propose_skill_selection', args: { changes: [{ candidate_id: proposalCandidate, action: 'add', reason: 'Synthetic evidence merits teacher review' }] } }] }]);
            await page.getByRole('button', { name: 'Save draft and suggest', exact: true }).click();
            await page.getByRole('button', { name: 'Apply proposal to draft', exact: true }).waitFor();
            const proposed = await fresh();
            assert.equal(proposed.selected_candidate_ids.length, 15);
            assert(!proposed.selected_candidate_ids.includes(proposalCandidate));
            assert.equal(proposed.recommendations.length, 1);
            calls = action('model-readback');
            assert.deepEqual(calls.at(-1).tools, ['propose_skill_selection']);
            await page.getByRole('button', { name: 'Apply proposal to draft', exact: true }).click();
            assert.equal((await fresh()).selected_candidate_ids.length, 15, 'Proposal apply stays local');
            assert.equal(await pane.getByRole('checkbox', { name: 'Select Synthetic competency 17', exact: true }).isChecked(), true);
            await pane.getByRole('button', { name: 'Save draft', exact: true }).click();
            await pane.getByText('Draft saved', { exact: false }).waitFor();
            assert.equal((await fresh()).selected_candidate_ids.length, 16);
            fs.writeFileSync(path.join(output, 'context-calls.json'), JSON.stringify(calls, null, 2));
            console.log('PASS Save and suggest persists exact dirty draft, immutable proposal only, explicit local apply/save');
        }
        if (['all', 'workflow'].includes(phase)) {
            const created = await context.request.post(`${API}/courses`, { headers: { Authorization: `Bearer ${fixture.teacher.access_token}` }, data: { title: `SYNTHETIC acceptance — Workflow checkpoints ${Date.now()}` } });
            assert.equal(created.status(), 201);
            fixture.empty_course = await created.json();
            await page.goto(`${UI}/courses/${fixture.empty_course.id}/market-analyst`);
            await page.getByText('Start an analysis to collect job evidence for this course.', { exact: true }).waitFor();
            assert.equal(await page.getByRole('region', { name: 'Demand overview' }).count(), 0, 'Genuine empty analysis has no fallback chart');
            const noWrites = mutations.length;
            await page.getByRole('button', { name: 'Explore O*NET occupations', exact: true }).click();
            const reference = page.getByRole('region', { name: 'O*NET occupation reference' });
            await reference.getByLabel('O*NET release', { exact: true }).selectOption('31.0');
            await reference.getByRole('textbox', { name: 'Search occupations', exact: true }).fill('Data');
            await reference.getByRole('button', { name: 'Search', exact: true }).click();
            await reference.getByRole('button', { name: 'Browse Data Scientists (15-2051.00)', exact: true }).click();
            await reference.getByRole('article', { name: 'Reading Comprehension', exact: true }).waitFor();
            assert.match(await reference.innerText(), /IM: 4/);
            await reference.getByRole('button', { name: 'Ask about Reading Comprehension', exact: true }).click();
            assert.match(await page.getByLabel('Attached context', { exact: true }).innerText(), /Occupation reference · O\*NET 31.0/);
            assert.equal(mutations.length, noWrites, 'Imported reference browsing/staging never starts analysis');
            await page.screenshot({ path: path.join(output, 'imported-reference-31.png'), fullPage: true });
            await page.reload();
            await page.getByRole('button', { name: 'Analysis setup', exact: true }).click();
            await page.getByRole('combobox', { name: 'Market country', exact: true }).click();
            await page.getByRole('option', { name: 'Uzbekistan', exact: true }).click();
            for (const name of ['Indeed', 'LinkedIn'])
                await page.getByRole('checkbox', { name, exact: true }).uncheck();
            await page.getByRole('checkbox', { name: 'HeadHunter', exact: true }).check();
            const question = page.getByRole('textbox', { name: 'Question', exact: true });
            action('model-queue', [{ content: 'Search Terms: "Python developer" and "Software engineer". Please confirm the search queries.', delay: 3 }]);
            await question.fill('Find synthetic job evidence for this course.');
            const first = page.waitForResponse(r => r.url().endsWith('/market-demand/chat'));
            await page.getByRole('button', { name: 'Send message', exact: true }).click();
            await page.getByText(/Waiting for the current work/).waitFor();
            assert.equal(await page.getByRole('button', { name: 'Start an analysis', exact: true }).isDisabled(), true, 'Repeat Start is guarded during initial workflow');
            await question.fill('Retained follow-up while initial run arrives.');
            await (await first).finished();
            await page.getByText('Search Terms: "Python developer" and "Software engineer". Please confirm the search queries.', { exact: true }).waitFor();
            assert.equal(await question.inputValue(), 'Retained follow-up while initial run arrives.');
            await question.fill('');
            action('model-queue', [{ tool_calls: [{ id: 'task12-handoff', name: 'transfer_to_skill_finder', args: {} }] }, { tool_calls: [{ id: 'task12-fetch', name: 'fetch_jobs', args: { search_terms: 'Python developer, Software engineer', country: 'Uzbekistan' } }] }, { content: 'Synthetic jobs are collected. Please confirm a job group.' }]);
            await page.getByRole('button', { name: 'Select all', exact: true }).click();
            await page.getByRole('button', { name: /Confirm Selection/ }).click();
            await page.getByText('Synthetic jobs are collected. Please confirm a job group.', { exact: true }).waitFor();
            await page.getByText('Select Job Groups', { exact: true }).waitFor();
            action('model-queue', [{ tool_calls: [{ id: 'task12-groups', name: 'select_jobs_by_group', args: { group_names: 'all' } }] }, { content: 'The teacher-confirmed synthetic job group is selected.' }]);
            await page.getByRole('button', { name: 'Select all', exact: true }).click();
            await page.getByRole('button', { name: /Confirm Selection/ }).click();
            await page.getByText('The teacher-confirmed synthetic job group is selected.', { exact: true }).waitFor();
            const history = await context.request.get(`${API}/courses/${fixture.empty_course.id}/market-demand/history`, { headers: { Authorization: `Bearer ${fixture.teacher.access_token}` } });
            assert.equal(history.status(), 200);
            const state = { history: await history.json(), state: await (await context.request.get(`${API}/courses/${fixture.empty_course.id}/market-demand/state`, { headers: { Authorization: `Bearer ${fixture.teacher.access_token}` } })).json() };
            fs.writeFileSync(path.join(output, 'workflow-checkpoints.json'), JSON.stringify(state, null, 2));
            assert(state.state.selected_jobs.length === 3, 'Repeated provider query identities must deduplicate to 3 jobs');
            assert(state.state.fetched_jobs.length === 3);
            assert(state.state.run_id);
            await page.screenshot({ path: path.join(output, 'workflow-confirmed.png'), fullPage: true });
            const secondCourse = await context.request.post(`${API}/courses`, { headers: { Authorization: `Bearer ${fixture.teacher.access_token}` }, data: { title: 'SYNTHETIC unchanged initial composer completion' } });
            assert.equal(secondCourse.status(), 201);
            const secondId = (await secondCourse.json()).id;
            await page.goto(`${UI}/courses/${secondId}/market-analyst`);
            await page.getByRole('button', { name: 'Analysis setup', exact: true }).click();
            await page.getByRole('combobox', { name: 'Market country', exact: true }).click();
            await page.getByRole('option', { name: 'Uzbekistan', exact: true }).click();
            for (const name of ['Indeed', 'LinkedIn'])
                await page.getByRole('checkbox', { name, exact: true }).uncheck();
            await page.getByRole('checkbox', { name: 'HeadHunter', exact: true }).check();
            action('model-queue', [{ content: 'Synthetic initial completion without a typed follow-up.' }]);
            await question.fill('Unchanged initial workflow question.');
            await page.getByRole('button', { name: 'Send message', exact: true }).click();
            await page.getByText('Work completed', { exact: true }).waitFor();
            assert.equal(await question.inputValue(), '', 'Initial submitted text clears after acknowledged completion');
            console.log('PASS unchanged initial composer clears only after completion; modified follow-up retained in first workflow');
            console.log('PASS genuine empty/imported 31.0 reference, initial workflow retains follow-up, Start guard, real query and group tool checkpoints/deduplication');
        }
        if (phase === 'provenance') {
            const expected = action('seed-provenance');
            const id = expected.course.id;
            const headers = { Authorization: `Bearer ${fixture.teacher.access_token}` };
            assert.equal(expected.input_reference_count, 3);
            assert.equal(expected.unique_snapshot_count, 10);
            assert.deepEqual(expected.query_membership, ['first query', 'second query']);
            await page.goto(`${UI}/courses/${id}/market-analyst`);
            const overview = page.getByRole('region', { name: 'Demand overview' });
            await overview.locator('[role=img] svg').waitFor();
            const values = await overview.getByLabel('Overview values').innerText();
            assert.match(values, /20% · 2 \/ 10/);
            const options = await overview.locator('[role=img]').first().evaluate(async (element, url) => (await import(url)).getInstanceByDom(element).getOption(), chartModuleURL);
            assert.deepEqual(options.series[0].data.map(row => row.value), [20]);
            await overview.getByRole('button', { name: 'Inspect SYNTHETIC Python services', exact: true }).click();
            const focused = page.getByRole('region', { name: 'Focused evidence' });
            await focused.getByText('Evidence for SYNTHETIC Python services', { exact: true }).click();
            const ref = expected.review.candidates[0].evidence_references[0];
            const response = await context.request.get(`${API}/courses/${id}/market-demand/skill-review/postings/${ref.snapshot_id}`, { headers });
            assert.equal(response.status(), 200);
            const posting = await response.json();
            assert.equal(posting.description_text.slice(ref.excerpt_start, ref.excerpt_end), ref.excerpt);
            assert.equal(await focused.getByText(`Validated source passage: ${ref.original_phrase}`, { exact: true }).count(), 0, 'Source phrase withheld until current inspection');
            await focused.getByRole('button', { name: 'Load full posting evidence', exact: true }).first().click();
            await focused.getByText(`Validated source passage: ${ref.original_phrase}`, { exact: true }).waitFor();
            await focused.getByText(`Cleaned text offsets: ${ref.excerpt_start}–${ref.excerpt_end} (end exclusive)`, { exact: true }).waitFor();
            assert.equal(await focused.getByRole('link', { name: 'Original job posting', exact: true }).first().getAttribute('href'), ref.original_url);
            assert.match(await focused.innerText(), new RegExp('retrieved ' + posting.retrieved_at.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
            await page.screenshot({ path: path.join(output, 'duplicate-provenance.png'), fullPage: true });
            fs.writeFileSync(path.join(output, 'provenance-readback.json'), JSON.stringify({ expected, posting, barValues: options.series[0].data.map(row => row.value) }, null, 2));
            execFileSync('/Applications/Docker.app/Contents/Resources/bin/docker', ['exec', 'lab_tutor_workspace_acceptance_api', '/app/.venv/bin/python', '-m', 'tests.acceptance.teacher_workspace_server', '--manifest', '/tmp/teacher-workspace.json', '--action', 'purge-first-posting', '--snapshot-id', ref.snapshot_id], { stdio: 'pipe' });
            const purged = await (await context.request.get(`${API}/courses/${id}/market-demand/skill-review/postings/${ref.snapshot_id}`, { headers })).json();
            assert(purged.purged_at);
            assert.equal(purged.description_text, null);
            assert.deepEqual(purged.raw_payload, {});
            await focused.getByText('Evidence for SYNTHETIC Python services', { exact: true }).click();
            await focused.getByRole('button', { name: /Load|Reload full posting evidence/ }).first().waitFor({ state: 'detached' });
            await focused.getByText('Evidence for SYNTHETIC Python services', { exact: true }).click();
            await focused.getByText(/Posting content unavailable: purged/).waitFor();
            assert.equal(await focused.getByText(`Validated source passage: ${ref.original_phrase}`, { exact: true }).count(), 0);
            assert.equal(await focused.getByText(/Cleaned text offsets/).count(), 0);
            assert.equal(await focused.getByText(posting.description_text, { exact: true }).count(), 0);
            assert.equal(await focused.getByText('Full returned provider data', { exact: true }).count(), 0);
            assert.equal(await focused.getByRole('link', { name: 'Original job posting', exact: true }).first().getAttribute('href'), ref.original_url);
            await page.screenshot({ path: path.join(output, 'provenance-current-purged.png'), fullPage: true });
            fs.writeFileSync(path.join(output, 'provenance-purged-readback.json'), JSON.stringify(purged, null, 2));
            console.log('PASS duplicate observations/references count 2/10 not 3/10, exact SVG 20%, real source link/full posting/Unicode offsets/current-inspection gate');
        }
        if (phase === 'reset-proof') {
            const headers = { Authorization: `Bearer ${fixture.teacher.access_token}` };
            const durable = action('sql-readback');
            const beforeSQL = action('reset-readback');
            const calls = action('model-readback').length;
            const read = async (id, name) => { const response = await context.request.get(`${API}/courses/${id}/market-demand/${name}`, { headers }); assert.equal(response.status(), 200); return response.json(); };
            const records = [];
            const retry = async (id, label) => {
                const beforeCalls = action('model-readback').length;
                await page.getByRole('button', { name: 'Retry reset', exact: true }).waitFor();
                assert(await page.getByRole('button', { name: 'Send message', exact: true }).isDisabled());
                const start = page.getByRole('button', { name: 'Start an analysis', exact: true });
                if (await start.count())
                    assert(await start.isDisabled());
                const before = action('reset-readback');
                const thread = `mda-${fixture.course.teacher_id}-course-${id}`;
                assert(!before.active_threads.includes(thread));
                assert(before.checkpoints.some(row => row.thread_id === thread && row.count > 0));
                const history = await read(id, 'history');
                await page.getByRole('button', { name: 'Retry reset', exact: true }).click();
                let release;
                let arrived;
                const gate = new Promise(resolve => { release = resolve; });
                const captured = new Promise(resolve => { arrived = resolve; });
                await page.route(`**/courses/${id}/market-demand/history`, async (route) => {
                    if (route.request().method() !== 'DELETE')
                        return route.continue();
                    const response = await route.fetch();
                    assert.equal(response.status(), 200);
                    arrived();
                    await gate;
                    await route.fulfill({ response });
                });
                await page.getByRole('alertdialog').getByRole('button', { name: 'Confirm reset retry', exact: true }).click();
                await captured;
                assert(await page.getByRole('alertdialog').isVisible(), 'No UI clear before acknowledgement');
                release();
                await page.getByRole('alertdialog').waitFor({ state: 'hidden' });
                await page.unroute(`**/courses/${id}/market-demand/history`);
                await page.getByText('Start an analysis to collect job evidence for this course.', { exact: true }).waitFor();
                assert.equal(await page.getByRole('textbox', { name: 'Question', exact: true }).inputValue(), '');
                const after = action('reset-readback');
                assert(!after.checkpoints.some(row => row.thread_id === thread));
                assert.equal(action('model-readback').length, beforeCalls);
                records.push({ label, history, before, after, healthyRetryStatus: 200 });
                await page.screenshot({ path: path.join(output, `reset-${label}-recovered.png`), fullPage: true });
            };
            await page.goto(`${UI}/courses/${fixture.course.id}/market-analyst`);
            if (!beforeSQL.active_threads.includes(`mda-${fixture.course.teacher_id}-course-${fixture.course.id}`))
                await retry(fixture.course.id, 'preserved-contextual');
            action('restore-main-snapshot');
            await page.reload();
            await page.getByRole('region', { name: 'Demand overview' }).waitFor();
            await page.getByLabel('Overview values').getByRole('button', { name: 'Inspect Python', exact: true }).click();
            await page.getByRole('region', { name: 'Focused evidence' }).getByRole('button', { name: 'Ask about Python', exact: true }).click();
            action('model-queue', [{ content: 'Synthetic contextual checkpoint for physical reset acceptance.' }]);
            await page.getByRole('button', { name: 'Send message', exact: true }).click();
            await page.getByText('Work completed', { exact: true }).waitFor();
            const workflow = JSON.parse(fs.readFileSync(path.join(output, 'workflow-checkpoints.json')));
            for (const [id, label] of [[fixture.course.id, 'contextual'], [workflow.state.course_id, 'workflow-only']]) {
                await page.goto(`${UI}/courses/${id}/market-analyst`);
                await page.getByRole('button', { name: 'New analysis', exact: true }).waitFor();
                const question = page.locator('textarea[aria-label=Question]');
                await question.fill(`Retain ${label} question until acknowledged reset.`);
                if (label === 'contextual')
                    await page.getByRole('button', { name: 'Data', exact: true }).click();
                const history = await read(id, 'history');
                assert(history.messages.length > 0);
                assert.equal(history.messages.some(row => row.workspace_context?.run_id), label === 'contextual');
                action('arm-reset-failure');
                try {
                    await page.getByRole('button', { name: 'New analysis', exact: true }).click();
                    const failed = page.waitForEvent('requestfailed', r => r.url().endsWith('/market-demand/history') && r.method() === 'DELETE');
                    await page.getByRole('alertdialog').getByRole('button', { name: 'Start new analysis', exact: true }).click();
                    await failed;
                    await page.getByRole('alertdialog').getByRole('alert').waitFor();
                    assert.equal(await question.inputValue(), `Retain ${label} question until acknowledged reset.`);
                    if (label === 'contextual')
                        assert(await page.getByRole('region', { name: 'Evidence data' }).isVisible());
                    await page.screenshot({ path: path.join(output, `reset-${label}-failed-retained.png`), fullPage: true });
                }
                finally {
                    action('disarm-reset-failure');
                }
                await page.getByRole('alertdialog').getByRole('button', { name: 'Cancel', exact: true }).click();
                await page.getByRole('button', { name: 'Retry reset', exact: true }).waitFor();
                assert.equal(await question.inputValue(), `Retain ${label} question until acknowledged reset.`);
                await page.reload();
                await retry(id, label);
            }
            assert.deepEqual(action('sql-readback'), durable);
            assert.deepEqual(action('reset-readback').durable_counts, beforeSQL.durable_counts);
            const student = {};
            for (const [name, endpoint] of Object.entries({ path: 'path', quiz: 'chapters/1/quiz', reading: 'readings/task12-reading/content' })) {
                const response = await context.request.get(`${API}/student-learning-path/${fixture.course.id}/${endpoint}`, { headers: { Authorization: `Bearer ${fixture.student.access_token}` } });
                assert.equal(response.status(), 200);
                student[name] = await response.json();
            }
            assert.deepEqual(student, JSON.parse(fs.readFileSync(path.join(output, 'student-before.json'))));
            assert.equal(action('model-readback').length, calls + 1);
            fs.writeFileSync(path.join(output, 'reset-recovery-readback.json'), JSON.stringify({ records, durable, student, automaticModelCalls: 0 }, null, 2));
            action('restore-main-snapshot');
            console.log('PASS preserved/contextual/workflow-only physical partial resets, retained input/view, fresh confirmed healthy retry, no auto model/collection, durable run/evidence/approval/student preservation');
        }
        if (phase === 'supplemental') {
            const headers = { Authorization: `Bearer ${fixture.teacher.access_token}` };
            const workflow = JSON.parse(fs.readFileSync(path.join(output, 'workflow-checkpoints.json')));
            const courseId = workflow.state.course_id;
            await page.goto(`${UI}/courses/${courseId}/market-analyst`);
            await page.getByText('Workflow progress and actions', { exact: true }).click();
            await page.getByRole('button', { name: 'Stage workflow response', exact: true }).click();
            action('model-queue', [{ tool_calls: [{ id: 'task12-source-error', name: 'fetch_jobs', args: { search_terms: 'sourceerror', country: 'Uzbekistan' } }] }, { content: 'The synthetic provider failed. No fallback provider was used.' }]);
            await page.getByRole('button', { name: 'Send message', exact: true }).click();
            await page.getByText('The synthetic provider failed. No fallback provider was used.', { exact: true }).last().waitFor();
            await page.getByText('Work completed', { exact: true }).waitFor();
            await page.getByRole('region', { name: 'Source progress' }).getByText('headhunter: error', { exact: true }).waitFor();
            const sourceState = await (await context.request.get(`${API}/courses/${courseId}/market-demand/state`, { headers })).json();
            assert.equal(sourceState.source_outcomes.headhunter.status, 'error');
            assert.deepEqual(sourceState.sources, ['headhunter']);
            assert.equal(sourceState.fetched_jobs.length, 0);
            const unknownRequests = [];
            await page.route('**/market-demand/execution-status', async (route) => { unknownRequests.push(route.request().url()); await route.abort('failed'); });
            await page.reload();
            await page.waitForEvent('requestfailed', r => r.url().endsWith('/execution-status'));
            await page.getByText('Execution outcome unknown', { exact: true }).waitFor();
            assert(unknownRequests.length);
            assert.equal(await page.getByText('Work completed', { exact: true }).count(), 0);
            await page.screenshot({ path: path.join(output, 'source-error-unknown-status.png'), fullPage: true });
            await page.unroute('**/market-demand/execution-status');
            await page.goto(`${UI}/courses/${fixture.course.id}`);
            const agentDestinations = [];
            for (const [name, route] of [['Reading Agent', 'reading-agent'], ['Video Agent', 'video-agent']]) {
                await page.goto(`${UI}/courses/${fixture.course.id}`);
                await page.getByText(name, { exact: true }).click();
                await page.waitForURL(`${UI}/home`);
                agentDestinations.push({ name, configuredRoute: `/courses/${fixture.course.id}/${route}`, actualDestination: '/home', classification: 'Verified unchanged baseline limitation: page route absent' });
            }
            await page.goto(`${UI}/courses/${fixture.course.id}`);
            await page.getByText('Curricular Alignment Architect', { exact: true }).click();
            const agentDialog = page.getByRole('dialog');
            await agentDialog.waitFor();
            await agentDialog.getByRole('link', { name: 'Open architect workspace', exact: true }).click();
            await page.waitForURL(`**/courses/${fixture.course.id}/architect`);
            await page.getByText('Curricular Alignment Architect', { exact: true }).first().waitFor();
            await page.reload();
            await page.getByText('Curricular Alignment Architect', { exact: true }).first().waitFor();
            agentDestinations.push({ name: 'Architect', actualDestination: `/courses/${fixture.course.id}/architect`, directReload: true });
            const storageResponse = await context.request.get(`${API}/courses/${fixture.course.id}/presentations`, { headers });
            assert.equal(storageResponse.status(), 500);
            const storageUnavailable = await storageResponse.json();
            assert.equal(storageUnavailable.detail, 'Failed to list presentations: Blob service is not configured');
            disabledStorageVerified = true;
            const seeded = action('seed-reconciliation');
            await page.goto(`${UI}/courses/${seeded.course.id}/market-analyst`);
            const pane = page.getByRole('region', { name: 'Skill draft review' });
            await pane.waitFor();
            await pane.getByRole('checkbox', { name: 'Select SYNTHETIC original 1', exact: true }).check();
            const merged = action('merge-reconciliation');
            assert.equal(merged.review.candidate_revision, 2);
            assert.equal(merged.review.selected_candidate_ids.length, 0);
            assert.equal(merged.review.reconciliations.length, 1);
            await page.getByRole('button', { name: 'Refresh context', exact: true }).click();
            await pane.getByRole('checkbox', { name: 'Select SYNTHETIC merged identity', exact: true }).waitFor();
            assert.equal(await pane.getByRole('checkbox', { name: 'Select SYNTHETIC merged identity', exact: true }).isChecked(), false);
            assert.equal(await pane.getByRole('checkbox', { name: 'Select SYNTHETIC newly observed', exact: true }).isChecked(), false);
            assert.match(await pane.innerText(), /Candidates removed or merged/);
            await page.screenshot({ path: path.join(output, 'candidate-reconciliation.png'), fullPage: true });
            // Delay an actual response across a client-side course navigation. Return its original bytes only after leaving.
            await pane.getByRole('button', { name: 'I reviewed the changed revisions', exact: true }).click();
            let release;
            let captured;
            const delayed = new Promise(resolve => { captured = resolve; });
            const gate = new Promise(resolve => { release = resolve; });
            await page.route(`**/courses/${seeded.course.id}/market-demand/skill-review`, async (route) => { const response = await route.fetch(); captured(); await gate; await route.fulfill({ response }); });
            await page.getByRole('button', { name: 'Refresh context', exact: true }).click();
            await delayed;
            await page.getByRole('link', { name: 'My Courses', exact: true }).click();
            if (await page.getByRole('alertdialog').count())
                await page.getByRole('alertdialog').getByRole('button', { name: 'Discard', exact: true }).click();
            await page.waitForURL(`${UI}/courses`);
            const courseCard = page.locator('[data-slot=card]').filter({ has: page.getByText(fixture.course.title, { exact: true }) });
            await courseCard.getByRole('button', { name: 'Manage', exact: true }).click();
            await page.getByText('Market Demand Analyst', { exact: true }).click();
            await page.getByRole('link', { name: 'Open market analyst', exact: true }).click();
            release();
            await page.waitForURL(`**/courses/${fixture.course.id}/market-analyst`);
            await page.unroute(`**/courses/${seeded.course.id}/market-demand/skill-review`);
            assert.equal(await page.getByRole('checkbox', { name: 'Select SYNTHETIC merged identity', exact: true }).count(), 0, 'Late previous-course response cannot populate new course');
            fs.writeFileSync(path.join(output, 'supplemental-readback.json'), JSON.stringify({ sourceState, unknownRequests, agentDestinations, storageUnavailable, reconciliation: merged }, null, 2));
            console.log('PASS actual provider error/no fallback, unknown status request failure, other agent entry points, merged/new candidate reconciliation, late response ignored across course navigation');
        }
        if (['all', 'lifecycle'].includes(phase)) {
            await page.goto(`${UI}/courses/${fixture.course.id}`);
            await page.getByText('Market Demand Analyst', { exact: true }).click();
            await page.getByRole('link', { name: 'Open market analyst', exact: true }).click();
            await page.getByRole('region', { name: 'Demand overview' }).waitFor();
            assert.equal(new URL(page.url()).pathname, `/courses/${fixture.course.id}/market-analyst`);
            const before = mutations.length;
            const lifecycle = [];
            for (let i = 0; i < 4; i++) {
                const element = page.getByRole('region', { name: 'Demand overview' }).locator('[role=img]').first();
                await element.locator('svg').waitFor();
                const handlers = await element.evaluate(async (element, url) => { const core = await import(url); const instance = core.getInstanceByDom(element); window.task12LastChart = { instance, element, core }; return instance._$handlers.click.length; }, chartModuleURL);
                assert.equal(handlers, 1);
                await page.getByRole('button', { name: 'Data', exact: true }).click();
                assert(await page.evaluate(() => window.task12LastChart.instance.isDisposed() && !window.task12LastChart.core.getInstanceByDom(window.task12LastChart.element)));
                await page.getByRole('button', { name: 'Compare', exact: true }).click();
                await page.getByRole('region', { name: 'Occupation comparison' }).waitFor();
                await page.getByRole('button', { name: 'Overview', exact: true }).click();
                lifecycle.push({ cycle: i, clickHandlers: handlers, oldInstanceDisposed: true });
            }
            assert.equal(mutations.length, before);
            await page.getByLabel('Overview values').getByRole('button', { name: 'Inspect Python', exact: true }).click();
            await page.getByRole('region', { name: 'Focused evidence' }).getByRole('button', { name: 'Ask about Python', exact: true }).click();
            const question = page.getByRole('textbox', { name: 'Question', exact: true });
            await question.fill('Retain focused question across hidden panes.');
            await question.evaluate(e => { window.task12Composer = e; });
            await page.setViewportSize({ width: 390, height: 844 });
            await page.getByRole('tab', { name: 'Workspace', exact: true }).click();
            await page.locator('[data-sidebar=trigger]').click();
            await page.getByRole('dialog').waitFor();
            await page.keyboard.press('Escape');
            await page.getByRole('tab', { name: 'Conversation', exact: true }).click();
            assert.equal(await question.inputValue(), 'Retain focused question across hidden panes.');
            assert(await question.evaluate(e => e === window.task12Composer));
            await page.getByRole('tab', { name: 'Workspace', exact: true }).click();
            await page.getByRole('region', { name: 'Focused evidence' }).getByRole('heading', { name: 'Python', exact: true }).waitFor();
            await page.getByRole('button', { name: 'Overview', exact: true }).click();
            const shown = page.getByRole('region', { name: 'Demand overview' }).locator('[role=img]').first();
            await shown.locator('svg').waitFor();
            assert((await shown.boundingBox()).width > 0);
            await page.screenshot({ path: path.join(output, 'hidden-pane-reopened.png'), fullPage: true });
            await page.setViewportSize({ width: 1440, height: 1000 });
            await question.fill('');
            const pane = page.getByRole('region', { name: 'Skill draft review' });
            await pane.getByRole('checkbox', { name: 'Select Synthetic competency 18', exact: true }).check();
            await page.getByRole('link', { name: 'My Courses', exact: true }).click();
            const guard = page.getByRole('alertdialog');
            await guard.getByText('Unsaved shortlist', { exact: true }).waitFor();
            await guard.getByRole('button', { name: 'Cancel', exact: true }).click();
            await page.evaluate(() => history.back());
            await guard.getByText('Unsaved shortlist', { exact: true }).waitFor();
            await guard.getByRole('button', { name: 'Cancel', exact: true }).click();
            const unload = page.waitForEvent('dialog');
            await page.evaluate(() => setTimeout(() => location.reload(), 0));
            const confirmation = await unload;
            assert.equal(confirmation.type(), 'beforeunload');
            await confirmation.dismiss();
            assert(await pane.getByRole('checkbox', { name: 'Select Synthetic competency 18', exact: true }).isChecked());
            await page.getByRole('link', { name: 'My Courses', exact: true }).click();
            await guard.getByRole('button', { name: 'Save', exact: true }).click();
            await page.waitForURL(`${UI}/courses`);
            await page.goto(`${UI}/courses/${fixture.course.id}/market-analyst`);
            await pane.getByRole('checkbox', { name: 'Select Synthetic competency 18', exact: true }).waitFor();
            assert(await pane.getByRole('checkbox', { name: 'Select Synthetic competency 18', exact: true }).isChecked());
            action('model-queue', [{ content: Array.from({ length: 70 }, (_, i) => `Synthetic explanation paragraph ${i + 1}: the saved sample is limited to the assessed postings and does not imply complete market coverage.`).join('\n\n') }]);
            await question.fill('Create a long controlled explanation for transcript scroll acceptance.');
            await page.getByRole('button', { name: 'Send message', exact: true }).click();
            await page.getByText('Work completed', { exact: true }).waitFor();
            const log = page.getByRole('log', { name: 'Conversation messages', exact: true });
            await log.evaluate(e => { e.scrollTop = 0; e.dispatchEvent(new Event('scroll')); });
            action('model-queue', [{ content: 'Newest synthetic response below the retained scroll position.' }]);
            await question.fill('Add one controlled reply.');
            await page.getByRole('button', { name: 'Send message', exact: true }).click();
            await page.getByRole('button', { name: 'Show new messages', exact: true }).waitFor();
            assert.equal(await log.evaluate(e => e.scrollTop), 0);
            await page.getByRole('button', { name: 'Show new messages', exact: true }).click();
            assert((await log.evaluate(e => e.scrollTop)) > 0);
            await page.getByText('Work completed', { exact: true }).waitFor();
            fs.writeFileSync(path.join(output, 'lifecycle.json'), JSON.stringify(lifecycle, null, 2));
            console.log('PASS hub/deep link, live/disposed ECharts instances and single handlers, mobile sidebar/hidden panes/composer, link/back/reload guards, save navigation, unread transcript attention');
        }
        if (['all', 'revisions'].includes(phase)) {
            const headers = { Authorization: `Bearer ${fixture.teacher.access_token}` };
            const base = `${API}/courses/${fixture.course.id}/market-demand`;
            const fresh = async () => (await context.request.get(`${base}/skill-review`, { headers })).json();
            const initial = await fresh();
            const valid = { kind: 'run_review', version: 1, intent: 'explain', run_id: initial.run_id, expected_candidate_revision: initial.candidate_revision, expected_selection_revision: initial.selection_revision, view: 'overview', focused_candidate_id: fixture.candidate_ids[0], candidate_ids: [], filters: { category_ids: [], search: '', scope: 'all' }, occupation_codes: [], metric: 'frequency', descriptor_choices: [], insight_kind: null, has_unsaved_changes: false };
            const count = action('model-readback').length;
            const rejected = [];
            for (const [name, body] of [['foreign', { ...valid, focused_candidate_id: '00000000-0000-0000-0000-000000009999' }], ['stale', { ...valid, expected_selection_revision: 0 }], ['oversized', { ...valid, candidate_ids: Array.from({ length: 21 }, (_, i) => fixture.candidate_ids[i]) }]]) {
                const response = await context.request.post(`${base}/chat`, { headers, data: { message: 'Should be rejected before inference', workspace_context: body } });
                assert([409, 422].includes(response.status()));
                rejected.push({ name, status: response.status(), body: await response.json() });
            }
            assert.equal(action('model-readback').length, count, 'Rejected context must never invoke model');
            action('adversarial-source');
            action('model-queue', [{ content: 'Source text remains evidence and cannot grant tool authority.' }]);
            await page.getByRole('region', { name: 'Focused evidence' }).getByRole('button', { name: 'Ask about Python', exact: true }).click();
            const question = page.getByRole('textbox', { name: 'Question', exact: true });
            const attached = await page.getByLabel('Attached context', { exact: true }).innerText();
            assert.match(attached, /Python/);
            await page.getByRole('button', { name: 'Send message', exact: true }).click();
            await page.getByText('Source text remains evidence and cannot grant tool authority.', { exact: true }).waitFor();
            const model = action('model-readback').at(-1);
            assert.deepEqual(model.tools, []);
            assert(model.evidence.candidates.find(c => c.candidate_id === fixture.candidate_ids[0]).postings.some(p => p.excerpt.includes('SYNTHETIC ADVERSARIAL SOURCE')));
            assert.equal((await fresh()).selection_revision, initial.selection_revision);
            const second = await context.newPage();
            await second.goto(`${UI}/courses/${fixture.course.id}/market-analyst`);
            const other = second.getByRole('region', { name: 'Skill draft review' });
            await other.waitFor();
            await other.getByRole('checkbox', { name: 'Select Critical Thinking', exact: true }).check();
            await other.getByRole('button', { name: 'Save draft', exact: true }).click();
            await other.getByText('Draft saved', { exact: false }).waitFor();
            const local = page.getByRole('region', { name: 'Skill draft review' });
            await local.getByRole('checkbox', { name: 'Select Communication', exact: true }).check();
            const stale = page.waitForResponse(r => r.url().endsWith('/skill-review/draft') && r.request().method() === 'PUT');
            await local.getByRole('button', { name: 'Save draft', exact: true }).click();
            assert.equal((await stale).status(), 409);
            await local.getByRole('alert').waitFor();
            assert(await local.getByRole('checkbox', { name: 'Select Communication', exact: true }).isChecked());
            await page.getByRole('button', { name: 'Refresh context', exact: true }).click();
            await local.getByRole('button', { name: 'I reviewed the changed revisions', exact: true }).waitFor();
            assert(await local.getByRole('checkbox', { name: 'Select Communication', exact: true }).isChecked());
            const proposal = page.getByRole('button', { name: 'Apply proposal to draft', exact: true });
            if (await proposal.count())
                assert(await proposal.isDisabled(), 'Stale immutable proposal cannot apply');
            await local.getByRole('button', { name: 'I reviewed the changed revisions', exact: true }).click();
            await local.getByRole('button', { name: 'Save draft', exact: true }).click();
            await local.getByText('Draft saved', { exact: false }).waitFor();
            await second.close();
            fs.writeFileSync(path.join(output, 'context-rejections.json'), JSON.stringify({ rejected, adversarialModel: model, final: await fresh() }, null, 2));
            assert.equal(await question.inputValue(), '');
            console.log('PASS invalid/foreign/stale/oversized context before inference, adversarial source has zero tools, stale second-tab save/proposal rejected, dirty choices retained');
        }
        if (['all', 'recovery'].includes(phase)) {
            const headers = { Authorization: `Bearer ${fixture.teacher.access_token}` };
            const base = `${API}/courses/${fixture.course.id}/market-demand`;
            const question = page.locator('textarea[aria-label=Question]');
            await page.getByRole('region', { name: 'Focused evidence' }).getByRole('button', { name: 'Ask about Python', exact: true }).click();
            action('model-queue', [{ exception: 'Synthetic inference outage' }]);
            await question.fill('Retain this question after failed inference.');
            await page.getByRole('button', { name: 'Send message', exact: true }).click();
            await page.getByText('Work failed', { exact: true }).waitFor();
            assert.equal(await question.inputValue(), 'Retain this question after failed inference.');
            const calls = action('model-readback').length;
            action('model-queue', [{ content: 'Synthetic delayed response after detachment.', delay: 6 }]);
            await page.getByRole('button', { name: 'Send message', exact: true }).click();
            await page.getByRole('button', { name: 'Close live response', exact: true }).click();
            await page.getByText('Live response closed. Server work may continue; refresh to check its state before sending again.', { exact: true }).waitFor();
            assert.equal(await question.inputValue(), 'Retain this question after failed inference.');
            await page.getByText('Execution outcome unknown', { exact: true }).waitFor();
            const beforeDetachCount = mutations.filter(r => r.url.endsWith('/chat')).length;
            await page.waitForTimeout(7000);
            const status = await (await context.request.get(`${base}/execution-status`, { headers })).json();
            assert.equal(status.status, 'idle');
            assert.equal(action('model-readback').length, calls + 1);
            assert.equal(mutations.filter(r => r.url.endsWith('/chat')).length, beforeDetachCount, 'Detachment does not retry');
            await page.getByRole('button', { name: 'Refresh context', exact: true }).click();
            await page.getByText('Execution outcome unknown', { exact: true }).waitFor();
            await page.screenshot({ path: path.join(output, 'detached-unknown.png'), fullPage: true });
            await page.getByRole('button', { name: 'New analysis', exact: true }).click();
            const dialog = page.getByRole('alertdialog');
            await dialog.waitFor();
            const lease = spawn('/Applications/Docker.app/Contents/Resources/bin/docker', ['exec', 'lab_tutor_workspace_acceptance_api', '/app/.venv/bin/python', '-m', 'tests.acceptance.teacher_workspace_server', '--manifest', '/tmp/teacher-workspace.json', '--action', 'hold-lease'], { stdio: ['ignore', 'pipe', 'pipe'] });
            await new Promise((resolve, reject) => {
                lease.stdout.on('data', data => {
                    if (data.toString().includes('lease held'))
                        resolve();
                });
                lease.on('error', reject);
                lease.on('exit', code => {
                    if (code)
                        reject(Error('Lease helper failed'));
                });
            });
            const busy = await (await context.request.get(`${base}/execution-status`, { headers })).json();
            assert.equal(busy.status, 'busy');
            const resetResponse = page.waitForResponse(r => r.url().endsWith('/market-demand/history') && r.request().method() === 'DELETE');
            await dialog.getByRole('button', { name: 'Start new analysis', exact: true }).click();
            assert.equal((await resetResponse).status(), 409);
            await dialog.getByRole('alert').waitFor();
            assert.equal(await question.inputValue(), 'Retain this question after failed inference.');
            assert.equal(await page.getByLabel('Overview values').locator(':scope > li').count(), 12);
            await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
            await page.getByRole('button', { name: 'Refresh context', exact: true }).click();
            await page.getByText('Server work is running', { exact: true }).waitFor();
            assert.equal(await page.getByRole('button', { name: 'New analysis', exact: true }).isDisabled(), true);
            if (lease.exitCode === null)
                await new Promise((resolve, reject) => { lease.on('exit', code => code === 0 ? resolve() : reject(Error('Lease helper release failed'))); });
            else
                assert.equal(lease.exitCode, 0);
            await page.getByRole('button', { name: 'Refresh context', exact: true }).click();
            fs.writeFileSync(path.join(output, 'recovery-readback.json'), JSON.stringify({ busy, status, chatRequests: beforeDetachCount }, null, 2));
            console.log('PASS failed stream retention, real detach/idle-unknown, cross-process busy 409 and UI guards');
        }
        if (['all', 'approval'].includes(phase)) {
            const headers = { Authorization: `Bearer ${fixture.teacher.access_token}` };
            const base = `${API}/courses/${fixture.course.id}/market-demand`;
            const fresh = async () => { const response = await context.request.get(`${base}/skill-review`, { headers }); assert.equal(response.status(), 200); return response.json(); };
            const revision = review => ({ run_id: review.run_id, expected_candidate_revision: review.candidate_revision, expected_selection_revision: review.selection_revision });
            const pane = page.getByRole('region', { name: 'Skill draft review' });
            for (const label of ['Programming', 'Professional']) {
                const box = pane.getByRole('checkbox', { name: `Select category ${label} (15 current members)`, exact: true });
                await box.check();
                await box.uncheck();
            }
            await pane.getByRole('checkbox', { name: 'Select Python', exact: true }).check();
            await pane.getByRole('checkbox', { name: 'Select Synthetic competency 30', exact: true }).check();
            if (await pane.getByRole('button', { name: 'Save draft', exact: true }).isEnabled()) {
                await pane.getByRole('button', { name: 'Save draft', exact: true }).click();
                await pane.getByText('Draft saved', { exact: false }).waitFor();
            }
            assert.equal((await fresh()).selected_candidate_ids.length, 2);
            if (await pane.getByRole('button', { name: 'Continue with available evidence', exact: true }).count())
                await pane.getByRole('button', { name: 'Continue with available evidence', exact: true }).click();
            await pane.getByRole('button', { name: 'Continue with available evidence', exact: true }).waitFor({ state: 'detached' });
            let prepared = action('prepare-review');
            const unsupportedRequest = { ...revision(prepared), review_digest: prepared.integration_review.review_digest, approved_candidate_ids: prepared.selected_candidate_ids };
            let rejected = await context.request.post(`${base}/integration-approval`, { headers, data: unsupportedRequest });
            assert.equal(rejected.status(), 422);
            const rejection = await rejected.json();
            assert.equal(rejection.detail.code, 'missing_job_evidence');
            assert(rejection.detail.candidate_ids.includes(fixture.candidate_ids[29]));
            assert.equal(action('sql-readback').publication_revision, 0);
            await page.reload();
            await pane.getByRole('checkbox', { name: 'Select Synthetic competency 30', exact: true }).uncheck();
            await pane.getByRole('button', { name: 'Save draft', exact: true }).click();
            await pane.getByText('Draft saved', { exact: false }).waitFor();
            prepared = action('prepare-review');
            await page.reload();
            const integration = page.getByRole('region', { name: 'Final integration review' });
            await integration.waitFor();
            const approvalResponse = page.waitForResponse(r => r.url().endsWith('/integration-approval') && r.request().method() === 'POST');
            await integration.getByRole('button', { name: 'Approve integration', exact: true }).click();
            const approvedResponse = await approvalResponse;
            assert.equal(approvedResponse.status(), 200);
            const submitted = approvedResponse.request().postDataJSON();
            assert.equal(submitted.review_digest, prepared.integration_review.review_digest);
            assert.deepEqual(submitted.approved_candidate_ids, [fixture.candidate_ids[0]]);
            const approved = await approvedResponse.json();
            assert.equal(approved.projection_status, 'projected');
            await integration.getByText('Approval saved; publication projected', { exact: true }).waitFor();
            const sql = action('sql-readback');
            assert.equal(sql.publication_revision, 1);
            assert.equal(sql.approvals.length, 1);
            assert.equal(sql.approvals[0].review_digest, submitted.review_digest);
            for (const [index, item] of prepared.integration_review.items.entries()) {
                const stored = sql.approvals[0].items[index];
                for (const key of ['candidate_id', 'disposition', 'target', 'chapters', 'concepts', 'qualifying_posting_links'])
                    assert.deepEqual(stored[key], item[key], key);
                assert.deepEqual(stored.vacancy_bindings.map(b => b.snapshot_id).sort(), [...item.evidence_snapshot_ids].sort());
            }
            const repeated = await context.request.post(`${base}/integration-approval`, { headers, data: submitted });
            assert.equal(repeated.status(), 200);
            assert.equal(action('sql-readback').approvals.length, 1);
            const beforeStudent = JSON.parse(fs.readFileSync(path.join(output, 'student-before.json')));
            const afterStudent = {};
            for (const [name, endpoint] of Object.entries({ path: 'path', quiz: 'chapters/1/quiz', reading: 'readings/task12-reading/content' })) {
                const response = await context.request.get(`${API}/student-learning-path/${fixture.course.id}/${endpoint}`, { headers: { Authorization: `Bearer ${fixture.student.access_token}` } });
                assert.equal(response.status(), 200);
                afterStudent[name] = await response.json();
            }
            assert.deepEqual(afterStudent, beforeStudent, 'Saved graph-backed student path, quiz mastery and reading unchanged by teacher publication');
            fs.writeFileSync(path.join(output, 'approval-readback.json'), JSON.stringify({ rejection, submitted, approved, sql, afterStudent }, null, 2));
            await page.screenshot({ path: path.join(output, 'approval-projected.png'), fullPage: true });
            console.log('PASS final missing_job_evidence 422, exact digest/mappings, actual Neo4j projection, idempotency, unchanged student APIs');
        }
        if (phase === 'approval-readback') {
            const headers = { Authorization: `Bearer ${fixture.teacher.access_token}` };
            const base = `${API}/courses/${fixture.course.id}/market-demand`;
            const prepared = await (await context.request.get(`${base}/skill-review`, { headers })).json();
            const sql = action('sql-readback');
            assert.equal(sql.publication_revision, 1);
            assert.equal(sql.approvals.length, 1);
            assert.equal(sql.approvals[0].projection_status, 'projected');
            assert.equal(sql.approvals[0].review_digest, prepared.integration_review.review_digest);
            for (const [index, item] of prepared.integration_review.items.entries()) {
                const stored = sql.approvals[0].items[index];
                for (const key of ['candidate_id', 'disposition', 'target', 'chapters', 'concepts', 'qualifying_posting_links'])
                    assert.deepEqual(stored[key], item[key], key);
                assert.deepEqual(stored.vacancy_bindings.map(b => b.snapshot_id).sort(), [...item.evidence_snapshot_ids].sort());
            }
            const submitted = { run_id: prepared.run_id, expected_candidate_revision: prepared.candidate_revision, expected_selection_revision: prepared.selection_revision, review_digest: prepared.integration_review.review_digest, approved_candidate_ids: prepared.selected_candidate_ids };
            const repeat = await context.request.post(`${base}/integration-approval`, { headers, data: submitted });
            assert.equal(repeat.status(), 200);
            assert.equal(action('sql-readback').approvals.length, 1);
            const afterStudent = {};
            for (const [name, endpoint] of Object.entries({ path: 'path', quiz: 'chapters/1/quiz', reading: 'readings/task12-reading/content' })) {
                const response = await context.request.get(`${API}/student-learning-path/${fixture.course.id}/${endpoint}`, { headers: { Authorization: `Bearer ${fixture.student.access_token}` } });
                assert.equal(response.status(), 200);
                afterStudent[name] = await response.json();
            }
            assert.deepEqual(afterStudent, JSON.parse(fs.readFileSync(path.join(output, 'student-before.json'))));
            fs.writeFileSync(path.join(output, 'approval-readback.json'), JSON.stringify({ submitted, sql, afterStudent }, null, 2));
            await page.getByRole('region', { name: 'Final integration review' }).scrollIntoViewIfNeeded();
            await page.screenshot({ path: path.join(output, 'approval-projected.png'), fullPage: true });
            console.log('PASS actual projection, exact durable approved mapping/digest, idempotency, unchanged student path/quiz/resource');
        }
        if (['all', 'corpus'].includes(phase)) {
            const corpus = JSON.parse(fs.readFileSync(path.join(output, 'corpus-sql-readback.json')));
            const plotFacts = [];
            const chartOptions = async (region) => {
                const element = region.locator('[role=img]').first();
                await element.locator('svg').waitFor();
                return element.evaluate(async (element, url) => {
                    if (!url)
                        throw Error('Loaded ECharts module URL not observed');
                    const core = await import(url);
                    const instance = core.getInstanceByDom(element);
                    if (!instance)
                        throw Error('Rendered chart has no live ECharts instance');
                    window.task12ChartInstances ??= [];
                    window.task12ChartInstances.push(instance);
                    return instance.getOption();
                }, chartModuleURL);
            };
            for (const item of corpus) {
                const canonical = patterns => patterns.map(({ coverage, ...fact }) => fact);
                assert.deepEqual(canonical(item.resolved.model_bundle.patterns), canonical(item.source_case.expected), item.name + ' server pattern facts');
                const prior = mutations.length;
                await page.goto(`${UI}/courses/${item.course.id}/market-analyst`);
                await page.getByRole('region', { name: 'Demand overview' }).waitFor();
                if (item.context.filters.search) {
                    await page.getByRole('button', { name: 'Data', exact: true }).click();
                    await page.getByRole('textbox', { name: 'Filter evidence', exact: true }).fill(item.context.filters.search);
                    await page.getByRole('button', { name: 'Overview', exact: true }).click();
                }
                const overview = page.getByRole('region', { name: 'Demand overview' });
                if (item.name === 'denominator_10') {
                    const option = await chartOptions(overview);
                    assert.deepEqual(option.series[0].data.map(d => d.value), [50]);
                    assert.match(await overview.getByLabel('Overview values').innerText(), /50% · 3 \/ 10/);
                }
                await page.getByRole('button', { name: 'Compare', exact: true }).click();
                const compare = page.getByRole('region', { name: 'Occupation comparison' });
                await compare.getByRole('button', { name: 'Across occupations', exact: true }).click();
                for (const code of item.context.occupation_codes)
                    await compare.getByRole('checkbox', { name: `Display SYNTHETIC TEST CORPUS ${code}`, exact: true }).check();
                if (item.name === 'explicit_descriptor_choice') {
                    const mapped = item.context.descriptor_choices[0].evidence_id;
                    await compare.getByLabel('Descriptor for Programming · SYNTHETIC TEST CORPUS 15-1252.00', { exact: true }).selectOption(mapped);
                }
                const expected = [];
                const filtered = item.context.filters.search ? [] : [...item.review.candidates].sort((a, b) => a.display_name.trim().toLowerCase().localeCompare(b.display_name.trim().toLowerCase()) || a.candidate_id.localeCompare(b.candidate_id));
                filtered.forEach((candidate, y) => item.context.occupation_codes.forEach((code, x) => {
                    const eligible = candidate.onet_associations.filter(a => a.relation === 'equivalent' && a.evidence.family !== 'software' && a.evidence.soc_code === code && a.evidence.release === item.review.analysis_metadata.onet_release);
                    const chosen = item.context.descriptor_choices.find(c => c.candidate_id === candidate.candidate_id && eligible.some(a => a.evidence.id === c.evidence_id));
                    const eligibleIds = [...new Set(eligible.map(a => a.evidence.id))];
                    const association = chosen ? eligible.find(a => a.evidence.id === chosen.evidence_id) : eligibleIds.length === 1 ? eligible[0] : null;
                    const rating = association?.evidence.ratings.IM;
                    if (rating?.status === 'reported' && rating.value >= 1 && rating.value <= 5)
                        expected.push([x, y, rating.value]);
                }));
                let actual = [];
                if (expected.length)
                    actual = (await chartOptions(compare)).series[0].data.map(d => d.value);
                else {
                    await compare.getByText(item.context.filters.search ? 'No matching skills. Change the filters to inspect evidence.' : 'No reported comparable ratings available. Inspect unavailable reasons below.', { exact: true }).waitFor();
                    assert.equal(await compare.locator('[role=img] svg').count(), 0);
                }
                assert.deepEqual(actual, expected, item.name + ' heatmap values');
                if (item.name === 'ambiguous_cell')
                    await compare.getByText(/Multiple matched descriptors/).waitFor();
                if (item.name === 'suppressed_numeric_not_plotted')
                    await compare.getByText('Unavailable: suppressed', { exact: true }).waitFor();
                if (item.name === 'missing_cell')
                    await compare.getByText('Unavailable: no equivalent association in this release', { exact: true }).waitFor();
                if (['spread_1_0_distinct_role_ids', 'ambiguous_cell', 'software_reference_not_numeric'].includes(item.name))
                    await page.screenshot({ path: path.join(output, `corpus-${item.name}.png`), fullPage: true });
                if (item.name === 'max_two_no_repeated_skill') {
                    await compare.getByRole('button', { name: 'Demand and importance', exact: true }).click();
                    await compare.getByLabel('Compare occupation', { exact: true }).selectOption('15-1252.00');
                    const option = await chartOptions(compare);
                    const source = item.review.candidates[0].onet_associations[0].evidence.ratings.IM.value;
                    assert.deepEqual(option.series[0].data.map(d => d.value), [[50, source]]);
                    plotFacts.push({ name: item.name, scatter: option.series[0].data.map(d => d.value) });
                }
                await page.getByRole('button', { name: 'Overview', exact: true }).click();
                await overview.waitFor();
                const observedPatternCount = await overview.locator('article').count();
                assert.equal(observedPatternCount, item.source_case.expected.length, item.name + ' bounded rendered patterns');
                assert(observedPatternCount <= 2);
                assert.equal(mutations.length, prior, 'Course/filter/occupation/descriptor changes must not mutate');
                plotFacts.push({ name: item.name, heatmap: actual, expectedPatterns: item.source_case.expected, observedPatternCount });
                console.log(`PASS corpus SQL/server/heatmap/patterns ${item.name}`);
            }
            fs.writeFileSync(path.join(output, 'corpus-browser-facts.json'), JSON.stringify(plotFacts, null, 2));
        }
        if (['all', 'load-failures'].includes(phase)) {
            const failures = [];
            for (const kind of ['chart', 'comparison']) {
                const isolated = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
                await isolated.addInitScript(tokens => { localStorage.setItem('access_token', tokens.access_token); localStorage.setItem('refresh_token', tokens.refresh_token); }, fixture.teacher);
                const current = await isolated.newPage();
                const injected = [];
                const consoleErrors = [];
                const pageErrors = [];
                current.on('console', message => {
                    if (message.type() === 'error')
                        consoleErrors.push(message.text());
                });
                current.on('pageerror', error => pageErrors.push(error.message));
                await current.route(kind === 'chart' ? '**/echarts_core.js*' : '**/WorkspaceCompare.tsx*', async (route) => { injected.push(route.request().url()); await route.abort('failed'); });
                await current.goto(`${UI}/courses/${fixture.course.id}/market-analyst`);
                await current.getByRole('region', { name: 'Demand overview' }).waitFor();
                if (kind === 'comparison')
                    await current.getByRole('button', { name: 'Compare', exact: true }).click();
                await current.getByRole('alert').filter({ hasText: kind === 'chart' ? 'Chart unavailable.' : 'Charts unavailable.' }).waitFor();
                assert(injected.length > 0, 'Actual lazy import network request must be rejected');
                await current.getByRole('button', { name: 'Data', exact: true }).click();
                const fallback = current.getByRole('region', { name: 'Evidence data' });
                assert.equal(await fallback.locator('tbody tr').count(), 25);
                await fallback.getByRole('button', { name: 'Inspect Python', exact: true }).click();
                await current.getByRole('region', { name: 'Focused evidence' }).getByRole('heading', { name: 'Python', exact: true }).waitFor();
                const box = fallback.getByRole('checkbox', { name: 'Select Communication', exact: true });
                const selected = await box.isChecked();
                await box.setChecked(!selected);
                assert.equal(await box.isChecked(), !selected);
                assert.deepEqual(pageErrors, [], 'Expected import failure must be contained by UI');
                for (const error of consoleErrors)
                    assert(/net::ERR_FAILED|Failed to fetch dynamically imported module|WorkspaceCompare|error occurred in the <.*> component/.test(error), `Unexpected console error: ${error}`);
                await current.screenshot({ path: path.join(output, `network-failure-${kind}.png`), fullPage: true });
                failures.push({ kind, injected, consoleErrors, pageErrors, dataRows: 25 });
                await isolated.close();
                console.log(`PASS actual ${kind} import rejection leaves Data/shortlist usable`);
            }
            fs.writeFileSync(path.join(output, 'network-failures.json'), JSON.stringify(failures, null, 2));
        }
        for (const item of consoleErrors) {
            const expectedConflict = /409 \(Conflict\)|422 \(Unprocessable/.test(item.text) && ['revisions', 'recovery', 'approval'].includes(phase);
            const expectedReset = ['recovery', 'reset-proof'].includes(phase) && (/market-demand\/history/.test(item.url) || /market-demand\/history/.test(item.text)) && /CORS|ERR_FAILED|500/.test(item.text);
            const expectedStorage = phase === 'supplemental' && item.url === `${API}/courses/${fixture.course.id}/presentations` && item.text === 'Failed to load resource: the server responded with a status of 500 (Internal Server Error)';
            const expectedStorageCompanion = phase === 'supplemental' && disabledStorageVerified && consoleErrors.some(error => error.url === `${API}/courses/${fixture.course.id}/presentations` && error.text === 'Failed to load resource: the server responded with a status of 500 (Internal Server Error)') && item.url === `${UI}/src/components/CourseMaterialsTable.tsx` && item.text === 'Failed to fetch course materials: AxiosError';
            const expectedStatus = phase === 'supplemental' && /execution-status/.test(item.url + item.text) && /ERR_FAILED/.test(item.text);
            assert(expectedConflict || expectedReset || expectedStatus || expectedStorage || expectedStorageCompanion, `Unexpected console error: ${JSON.stringify(item)}`);
        }
        fs.writeFileSync(path.join(output, `console-${phase}.json`), JSON.stringify({ consoleErrors, runtimeErrors: errors }, null, 2));
        assert.deepEqual(errors, [], 'Unexpected main-page runtime errors');
        console.log('PASS initial saved SQL review and rendered chart');
    }
    catch (error) {
        fs.mkdirSync(output, { recursive: true });
        await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true });
        fs.writeFileSync(path.join(output, 'failure.json'), JSON.stringify({ error: safeError(error), runtimeErrors: errors, mutations, url: page.url() }, null, 2));
        throw error;
    }
    finally {
        await browser.close();
    }
})().catch(error => { console.error(safeError(error)); process.exitCode = 1; });
