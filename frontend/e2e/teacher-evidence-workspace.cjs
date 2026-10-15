/* Controlled real-database acceptance. No API response mocks. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const { chromium } = require('playwright');
const { expect } = require('playwright/test');
const UI = process.env.WORKSPACE_UI_URL;
const API = process.env.WORKSPACE_API_URL;
const manifestPath = process.env.WORKSPACE_FIXTURE_PATH;
const phase = process.env.WORKSPACE_SCENARIO || 'all';
const backendContainer = process.env.WORKSPACE_BACKEND_CONTAINER || 'lab_tutor_workspace_acceptance_api';
const backendEnvArgs = process.env.WORKSPACE_BACKEND_ENV_FILE ? ['--env-file', process.env.WORKSPACE_BACKEND_ENV_FILE] : [];
const safeError = error => String(error.message ?? error).replace(/Bearer\s+[A-Za-z0-9_.-]+/g, 'Bearer [REDACTED]');
let fixtureManifest = process.env.WORKSPACE_SERVER_MANIFEST || '/tmp/teacher-workspace.json';
const action = (name, payload, extra = []) => JSON.parse(execFileSync('/Applications/Docker.app/Contents/Resources/bin/docker', ['exec', '-i', ...backendEnvArgs, backendContainer, '/app/.venv/bin/python', '-m', 'tests.acceptance.teacher_workspace_server', '--manifest', fixtureManifest, '--action', name, ...extra], { input: payload ? JSON.stringify(payload) : undefined, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 }));
const sourceFile = process.argv.find(arg => arg.endsWith('/teacher-evidence-workspace.cjs'));
const { requireCompletedMapping, requireConfirmation } = require(path.join(path.dirname(sourceFile), 'teacher-workspace-boundary.cjs'));
const output = process.env.WORKSPACE_OUTPUT_DIR || path.resolve(path.dirname(sourceFile), '../../output/teacher-evidence-workspace/acceptance');
(async () => {
    assert(UI && API && manifestPath, 'Explicit isolated URLs and private manifest required');
    assert.equal(fs.statSync(manifestPath).mode & 0o777, 0o600, 'Manifest must be private');
    const fixture = JSON.parse(fs.readFileSync(manifestPath));
    assert.equal(fixture.database, 'lab_tutor_workspace_acceptance');
    // Historical callers may retain these names; all use current presentation contracts.
    const legacyScenarios = {
        purge: ['simple-contracts'], provenance: ['simple-flow', 'simple-layout'],
        layout: ['simple-layout'], context: ['simple-flow', 'simple-contracts'],
        workflow: ['simple-workflow'], 'pending-composer': ['simple-flow', 'simple-workflow'],
        lifecycle: ['simple-contracts'], revisions: ['simple-contracts'],
        recovery: ['simple-workflow'], 'reset-proof': ['simple-workflow'],
        supplemental: ['simple-contracts', 'simple-workflow'],
        approval: ['simple-flow'], 'approval-readback': ['simple-flow'],
        corpus: ['simple-corpus'], metadata: ['simple-corpus'],
        tooltip: ['simple-corpus'], 'tooltip-variants': ['simple-corpus'],
        'tooltip-three-roles': ['simple-corpus'], 'tooltip-four-roles': ['simple-corpus'],
        'tooltip-five-roles': ['simple-corpus'], 'load-failures': ['simple-contracts'],
    };
    if (phase === 'all' || legacyScenarios[phase]) {
        // Current presentation: retain data/security/recovery contracts through
        // the real simple-flow suites, rather than resurrecting the dashboard.
        for (const scenario of legacyScenarios[phase] ?? ['simple-boundary-negative', 'simple-flow', 'simple-contracts', 'simple-workflow', 'simple-corpus', 'simple-layout']) {
            console.log(`START ${scenario}`);
            execFileSync(process.execPath, [process.argv[1], sourceFile], { env: { ...process.env, WORKSPACE_SCENARIO: scenario }, stdio: 'inherit' });
            console.log(`EXIT 0 ${scenario}`);
        }
        console.log('PASS current real-database acceptance suites');
        return;
    }
    const browser = await chromium.launch({ headless: true, channel: "chrome" });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    const consoleErrors = [];
    const mutations = [];
    const verifyConsole = (expectedPath = null) => {
        for (const entry of consoleErrors) {
            assert(expectedPath && (entry.url.includes(expectedPath) || entry.text.includes(expectedPath)) && /CORS|ERR_FAILED|500|Failed to fetch/.test(entry.text), `Unexpected browser console error: ${JSON.stringify(entry)}`);
        }
        assert.deepEqual(errors, [], 'Unexpected main-page runtime errors');
        fs.writeFileSync(path.join(path.dirname(manifestPath), `task6-console-${phase}.json`), JSON.stringify({ consoleErrors, runtimeErrors: errors }, null, 2));
    };
    let chartModuleURL;
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
    const validateMappingResponse = async (response, base) => {
        assert.equal(response.url(), `${base}/chat`);
        assert.equal(response.status(), 200);
        const request = response.request().postDataJSON();
        assert.equal(request.workspace_context ?? null, null, 'Mapping must use workflow mode, not contextual chat');
        assert.equal(request.message, 'Map the confirmed selected skills to the curriculum and prepare the curriculum fit review. Do not approve or publish.');
        await response.finished();
        return requireCompletedMapping(await response.text());
    };
    const verifyBeforePreparation = async (base, headers, expected) => {
        const get = async endpoint => {
            const response = await context.request.get(`${base}/${endpoint}`, { headers });
            assert.equal(response.status(), 200);
            return response.json();
        };
        const state = await get('state');
        const sql = action('sql-readback');
        for (const actual of [state, sql]) {
            assert.equal(actual.run_id, expected.run_id);
            assert.equal(actual.publication_revision, 0);
            requireConfirmation(actual.selection_confirmation, expected);
        }
        assert.deepEqual(sql.approvals, []);
        assert.equal((await get('execution-status')).status, 'idle');
    };
    const verifyInspectionFocus = async () => {
        const skills = page.getByRole('region', { name: 'Choose skills', exact: true });
        await skills.waitFor();
        for (const name of ['SQL', 'ETL / ELT']) {
            const trigger = skills.getByRole('button', { name: `Inspect ${name}`, exact: true });
            await trigger.focus();
            await page.keyboard.press('Enter');
            await page.getByRole('dialog', { name: `Evidence for ${name}`, exact: true }).waitFor();
            assert.equal(await page.getByRole('dialog').count(), 1);
            await page.keyboard.press('Escape');
            await page.waitForFunction(label => document.activeElement?.getAttribute('aria-label') === label, `Inspect ${name}`);
        }
        const browse = skills.getByRole('button', { name: /^(Browse skills|Review all \d+)$/ });
        await browse.focus();
        await page.keyboard.press('Enter');
        const dialog = page.getByRole('dialog', { name: 'Browse skills', exact: true });
        await dialog.getByRole('button', { name: 'Inspect SQL', exact: true }).focus();
        await page.keyboard.press('Enter');
        await page.getByRole('dialog', { name: 'Evidence for SQL', exact: true }).waitFor();
        assert.equal(await page.getByRole('dialog').count(), 1);
        await page.keyboard.press('Escape');
        await page.waitForFunction(() => /^(Browse skills|Review all \d+)$/.test(document.activeElement?.textContent ?? ''));
        assert(await browse.evaluate(e => document.activeElement === e));
        await page.screenshot({ path: path.join(output, 'keyboard-focus-restored.png'), fullPage: true });
        verifyConsole();
    };
    try {
        if (phase === 'skill-priority') {
            fs.mkdirSync(output, { recursive: true });
            assert.equal(fixture.source_kind, 'copied_big_data', 'Use the isolated copied course, never a live course');
            const headers = { Authorization: `Bearer ${fixture.teacher.access_token}` };
            const base = `${API}/courses/${fixture.course.id}/market-demand`;
            const fresh = async () => {
                const response = await context.request.get(`${base}/skill-review`, { headers });
                assert.equal(response.status(), 200);
                return response.json();
            };
            const initial = await fresh();
            const before = action('sql-readback');
            const callsBefore = action('model-readback').length;
            const baseline = JSON.parse(fs.readFileSync(process.env.WORKSPACE_PRIORITY_BASELINE || path.join(output, 'baseline.json')));
            const skills = page.getByRole('region', { name: 'Choose skills', exact: true });
            const eligible = initial.candidates.filter(candidate => candidate.posting_support === 'supported' && candidate.qualifying_posting_links.some(url => /^https?:\/\//.test(url)));
            const categories = initial.categories.filter(category => eligible.some(candidate => candidate.category_id === category.category_id));
            const receipt = {
                scenario: phase, status: 'running', courseId: fixture.course.id,
                counts: { candidates: initial.candidates.length, jobBacked: eligible.length, categories: categories.length, selectedSkills: initial.selected_candidate_ids.length, retainedPostings: fixture.snapshot_ids.length, materials: fixture.material_count },
                viewports: [], labels: [], evidence: [], selection: null,
                mapping: 'Not exercised: copied run has no original graph checkpoint; controlled reply checks confirmation only.', publication: 'Not exercised',
                invocation: { runner: sourceFile, backendContainer, backendEnvFile: process.env.WORKSPACE_BACKEND_ENV_FILE ?? null, ui: UI, api: API, manifestPath, serverManifest: fixtureManifest, output, headless: true },
            };
            const saveReceipt = () => fs.writeFileSync(path.join(output, 'skill-priority-summary.json'), JSON.stringify(receipt, null, 2));
            saveReceipt();
            const categoryOrder = () => skills.getByRole('button', { name: /^(Expand|Collapse) / }).evaluateAll(elements => elements.map(element => element.getAttribute('aria-label').replace(/^(Expand|Collapse) /, '')));
            const rowOrder = () => skills.getByRole('checkbox').evaluateAll(elements => elements.map(element => element.getAttribute('aria-label')));
            const normalizeControls = controls => controls.map(item => item.name.replace(/^Confirm Selection \(\d+\)$/, 'Confirm Selection')).sort();
            const geometry = async () => {
                const bounds = await page.evaluate(() => ({ width: innerWidth, height: innerHeight, pageHeight: document.documentElement.scrollHeight, pageWidth: document.documentElement.scrollWidth }));
                const main = await page.locator('[aria-label="Teacher evidence workspace"]').evaluate(element => ({ height: element.clientHeight, contentHeight: element.scrollHeight, width: element.clientWidth, contentWidth: element.scrollWidth }));
                const conversation = await page.getByRole('log', { name: 'Conversation messages', exact: true }).evaluate(element => ({ height: element.clientHeight, contentHeight: element.scrollHeight, width: element.clientWidth, contentWidth: element.scrollWidth }));
                assert(bounds.pageHeight <= bounds.height + 1, `Page must fit vertically: ${JSON.stringify(bounds)}`);
                assert(bounds.pageWidth <= bounds.width + 1, `Page must fit horizontally: ${JSON.stringify(bounds)}`);
                assert(main.contentHeight <= main.height + 1 && main.contentWidth <= main.width + 1, `Main decision must not scroll: ${JSON.stringify(main)}`);
                assert(conversation.contentHeight <= conversation.height + 1 && conversation.contentWidth <= conversation.width + 1, `Decision content must fit without scrolling the conversation: ${JSON.stringify(conversation)}`);
                const confirm = await skills.getByRole('button', { name: /^Confirm Selection/ }).boundingBox();
                assert(confirm && confirm.y >= 0 && confirm.y + confirm.height <= bounds.height + 1, 'Existing confirmation remains in the viewport');
                return { ...bounds, main, conversation };
            };
            // Record real layout even when assessment integration is still absent.
            for (const [width, height] of [[1440, 900], [1280, 720], [390, 844]]) {
                await page.setViewportSize({ width, height });
                await page.goto(`${UI}/courses/${fixture.course.id}/market-analyst`);
                await skills.waitFor();
                const controls = await skills.getByRole('button').evaluateAll(elements => elements.map(element => ({ name: element.getAttribute('aria-label') || element.textContent })));
                const old = baseline.receipts.find(item => item.width === width && item.height === height);
                assert(old, `Missing before-layout baseline for ${width}×${height}`);
                assert.deepEqual(normalizeControls(controls), normalizeControls(old.controls), 'Importance adds no card buttons or teacher decision');
                assert.equal(await skills.count(), 1, 'One existing skill selection card');
                assert.equal(await skills.getByRole('button', { name: /^Confirm Selection/ }).count(), 1, 'One existing selection confirmation');
                assert.equal(await skills.getByRole('combobox').count(), 0, 'No occupation/source picker in skill selection');
                assert.equal(await skills.getByRole('slider').count(), 0, 'No score slider');
                assert.equal(await skills.getByRole('img').count(), 0, 'No new importance chart');
                receipt.viewports.push({ width, height, controls: controls.length, ...await geometry() });
                await page.screenshot({ path: path.join(output, `priority-main-${width}.png`), fullPage: true });
                saveReceipt();
            }
            assert.equal(mutations.length, 0, 'Restoring the assessment adds no API mutations');
            assert.equal(action('model-readback').length, callsBefore, 'Ordinary reads/restoration do not invoke inference');
            assert.deepEqual(action('sql-readback'), before, 'Ordinary reads/restoration preserve choices and revisions');
            const assessment = initial.priority_assessment;
            assert(assessment, 'Current saved priority assessment required; real API returned null (integration/evaluation must finish before acceptance)');
            assert.equal(assessment.run_id, initial.run_id);
            assert.equal(assessment.candidate_revision, initial.candidate_revision);
            assert(['ready', 'partial', 'unavailable'].includes(assessment.status), 'Saved assessment must be terminal and current');
            assert(Date.parse(assessment.deadline_at) - Date.parse(assessment.started_at) <= 60000, 'Assessment budget is at most 60 seconds');
            const scored = eligible.filter(candidate => candidate.priority?.value != null);
            receipt.assessment = { status: assessment.status, expectedPairs: assessment.expected_pair_count, completedPairs: assessment.completed_pair_count, scoredSkills: scored.length, missingSkills: eligible.length - scored.length };
            saveReceipt();
            assert(scored.length > 0, 'At least one scored real-course row is required for numeric display acceptance; no-score coverage is recorded honestly');
            for (const candidate of scored) {
                assert(Number.isFinite(candidate.priority.value) && candidate.priority.value >= 1 && candidate.priority.value <= 5, 'Importance is finite on the 1–5 scale');
            }
            const referencesById = new Map([...initial.candidates.flatMap(candidate => candidate.onet_associations.map(item => item.evidence)), ...(assessment.references ?? [])].map(reference => [reference.id, reference]));
            for (const result of assessment.results) {
                for (const referenceId of [result.direct_reference_id, ...result.associations.map(item => item.reference_id)].filter(Boolean)) {
                    assert(referencesById.has(referenceId), 'Each cited reference resolves to saved evidence');
                }
                if (result.basis === 'onet') {
                    const reference = referencesById.get(result.direct_reference_id);
                    assert(reference && reference.ratings.IM?.status === 'reported', 'Official score needs a reported IM reference');
                    assert.equal(reference.soc_code, result.soc_code);
                    assert.equal(reference.ratings.IM.scale_id, 'IM');
                    assert.equal(result.official_value, reference.ratings.IM.value, 'Official value is unchanged from saved O*NET evidence');
                    assert.equal(result.value, result.official_value);
                    assert.equal(result.estimate, null, 'Official scores are separate from estimates');
                } else if (result.basis === 'ai_estimate') {
                    assert(Number.isInteger(result.estimate) && result.estimate >= 1 && result.estimate <= 5, 'AI estimates are integers on 1–5');
                    assert.equal(result.official_value, null, 'AI estimates never claim an official source value');
                    assert.equal(result.value, result.estimate);
                } else {
                    assert.equal(result.value, null, 'Unavailable importance is null, never zero');
                }
            }
            const expectedLabel = (priority, category = false) => {
                if (priority.value == null || priority.basis === 'unavailable') return 'Not assessed';
                const basis = category ? priority.basis === 'ai_estimate' ? 'Estimated' : 'O*NET average' : priority.basis === 'onet' ? 'O*NET' : priority.basis === 'onet_aggregate' ? 'O*NET average' : 'AI estimate';
                return `${Number(priority.value.toFixed(1))}/5 · ${basis}${priority.complete ? '' : ' · Partial'}`;
            };
            await page.setViewportSize({ width: 1440, height: 900 });
            const mountedOrder = await categoryOrder();
            assert.deepEqual(mountedOrder, [...categories].sort((a, b) => a.priority.display_order - b.priority.display_order).map(category => category.label), 'Saved display order controls category order');
            // Every visible category/member label must match the actual saved number and basis.
            for (const category of categories) {
                assert(category.priority, 'Every current category has an explicit priority summary');
                if (category.priority.estimated_count > 0) assert.equal(category.priority.basis, 'ai_estimate', 'A category containing estimates is labeled Estimated');
                const expand = skills.getByRole('button', { name: `Expand ${category.label}`, exact: true });
                const label = expectedLabel(category.priority, true);
                assert((await expand.innerText()).includes(label), `${category.label}: expected ${label}`);
                receipt.labels.push({ kind: 'category', label, basis: category.priority.basis, complete: category.priority.complete });
                await expand.click();
                const members = eligible.filter(candidate => candidate.category_id === category.category_id).sort((a, b) => a.priority.display_order - b.priority.display_order);
                for (let offset = 0; offset < members.length; offset += 10) {
                    const visible = members.slice(offset, offset + 10);
                    assert.deepEqual(await skills.getByRole('checkbox', { name: /^Select / }).evaluateAll(elements => elements.map(element => element.getAttribute('aria-label')).filter(label => !label.startsWith('Select category '))), visible.map(candidate => `Select ${candidate.display_name}`));
                    for (const candidate of visible) {
                        const row = skills.getByRole('checkbox', { name: `Select ${candidate.display_name}`, exact: true }).locator('..');
                        const expected = expectedLabel(candidate.priority);
                        assert((await row.innerText()).includes(expected), `${candidate.display_name}: expected ${expected}`);
                        receipt.labels.push({ kind: 'skill', label: expected, basis: candidate.priority.basis, complete: candidate.priority.complete });
                    }
                    if (offset + 10 < members.length) await skills.getByRole('button', { name: `Next ${category.label} page`, exact: true }).click();
                }
                await skills.getByRole('button', { name: `Collapse ${category.label}`, exact: true }).click();
                saveReceipt();
            }
            // Inspect the strongest provenance case, plus each numeric basis present.
            const referenceIds = candidate => assessment.results.filter(result => result.candidate_id === candidate.candidate_id).flatMap(result => [result.direct_reference_id, ...result.associations.map(item => item.reference_id)]).filter(Boolean);
            const inspection = new Map();
            const withReference = scored.find(candidate => referenceIds(candidate).length > 0 || candidate.onet_associations.length > 0);
            assert(withReference, 'At least one assessed row must expose readable O*NET reference provenance');
            inspection.set(withReference.candidate_id, withReference);
            for (const basis of new Set(scored.map(candidate => candidate.priority.basis))) {
                const candidate = scored.find(candidate => candidate.priority.basis === basis);
                inspection.set(candidate.candidate_id, candidate);
            }
            for (const candidate of inspection.values()) {
                const category = categories.find(item => item.category_id === candidate.category_id);
                await skills.getByRole('button', { name: `Expand ${category.label}`, exact: true }).click();
                const previous = skills.getByRole('button', { name: `Previous ${category.label} page`, exact: true });
                while (await previous.count() && await previous.isEnabled()) await previous.click();
                const trigger = skills.getByRole('button', { name: `Inspect ${candidate.display_name}`, exact: true });
                while (!await trigger.count()) await skills.getByRole('button', { name: `Next ${category.label} page`, exact: true }).click();
                await trigger.focus();
                await page.keyboard.press('Enter');
                const dialog = page.getByRole('dialog', { name: `Evidence for ${candidate.display_name}`, exact: true });
                await dialog.waitFor();
                assert.equal(await page.getByRole('dialog').count(), 1, 'Existing inspector opens without stacked dialogs');
                const importance = dialog.getByRole('region', { name: 'Skill importance evidence', exact: true });
                await importance.waitFor();
                assert((await importance.innerText()).includes(expectedLabel(candidate.priority)));
                assert((await importance.innerText()).includes(`${candidate.priority.scored_contexts} of ${candidate.priority.expected_contexts} role contexts assessed`));
                for (const result of assessment.results.filter(item => item.candidate_id === candidate.candidate_id)) {
                    if (result.basis === 'onet') assert((await importance.innerText()).includes(`O*NET source value: ${result.official_value}/5`));
                    if (result.basis === 'ai_estimate') assert((await importance.innerText()).includes(`AI estimate: ${result.estimate}/5`));
                    if (result.explanation) assert((await importance.innerText()).includes(result.explanation));
                }
                const originalLinks = dialog.getByRole('link', { name: /^Original posting ·/ });
                assert.deepEqual(new Set(await originalLinks.evaluateAll(elements => elements.map(element => element.href))), new Set(candidate.qualifying_posting_links), 'Original posting URLs survive unchanged');
                const onetLinks = dialog.getByRole('link', { name: /^O\*NET reference:/ });
                const onetCount = await onetLinks.count();
                if (candidate.candidate_id === withReference.candidate_id) {
                    assert(onetCount > 0, 'Referenced O*NET evidence must have a named link');
                    const references = [...candidate.onet_associations.map(item => item.evidence), ...(assessment.references ?? []).filter(item => referenceIds(candidate).includes(item.id))];
                    for (const reference of references) assert(await dialog.locator('[data-evidence-id]').filter({ hasText: reference.definition }).count() > 0, 'Reference definition remains readable');
                }
                await dialog.getByText('Validated source passage:', { exact: false }).first().waitFor();
                assert(await dialog.locator('blockquote').count() > 0, 'Retained source passage is actually fetched from the API');
                for (const [width, height] of [[1440, 900], [1280, 720], [390, 844]]) {
                    await page.setViewportSize({ width, height });
                    // The shared dialog transitions its max-height/width on resize.
                    // Measure the finished layout rather than an intermediate animation frame.
                    await expect.poll(() => dialog.evaluate(element => {
                        const box = element.getBoundingClientRect();
                        return element.getAnimations().every(animation => animation.playState !== 'running') &&
                            box.x >= 0 && box.y >= 0 && box.right <= innerWidth + 1 && box.bottom <= innerHeight + 1 &&
                            element.scrollWidth <= element.clientWidth + 1;
                    }), { message: 'Evidence dialog settles inside the resized viewport', timeout: 3000, intervals: [16, 32, 64, 100] }).toBe(true);
                    const bounds = await dialog.evaluate(element => ({ width: element.clientWidth, contentWidth: element.scrollWidth, height: element.clientHeight, contentHeight: element.scrollHeight }));
                    assert(bounds.contentWidth <= bounds.width + 1, 'Evidence dialog has no horizontal overflow');
                    const box = await dialog.boundingBox();
                    assert(box.x >= 0 && box.y >= 0 && box.x + box.width <= width + 1 && box.y + box.height <= height + 1, 'Evidence stays inside viewport');
                    assert(await importance.locator('p').evaluateAll(elements => elements.every(element => element.scrollWidth <= element.clientWidth + 1 && Number.parseFloat(getComputedStyle(element).fontSize) >= 11)), 'Importance explanations wrap and remain readable');
                    await page.screenshot({ path: path.join(output, `priority-evidence-${candidate.priority.basis}-${width}.png`), fullPage: true });
                }
                receipt.evidence.push({ basis: candidate.priority.basis, postingLinks: await originalLinks.count(), onetReferences: onetCount, retainedPassages: await dialog.locator('blockquote').count() });
                await page.keyboard.press('Escape');
                assert(await trigger.evaluate(element => element === document.activeElement), 'Keyboard focus returns to existing inspection control');
                await skills.getByRole('button', { name: `Collapse ${category.label}`, exact: true }).click();
                saveReceipt();
            }
            // Category selection and a deliberate individual exclusion remain ordinary teacher choices.
            await page.setViewportSize({ width: 1440, height: 900 });
            const choice = categories.find(category => eligible.filter(candidate => candidate.category_id === category.category_id).length >= 2);
            assert(choice, 'Copied course requires a multi-member category for selection acceptance');
            const members = eligible.filter(candidate => candidate.category_id === choice.category_id).sort((a, b) => a.priority.display_order - b.priority.display_order);
            const excluded = members[0];
            const categoryCheckbox = skills.getByRole('checkbox', { name: `Select category ${choice.label} (${members.length} current members)`, exact: true });
            await categoryCheckbox.focus();
            if (await categoryCheckbox.isChecked()) await page.keyboard.press('Space');
            await page.keyboard.press('Space');
            assert(await categoryCheckbox.isChecked());
            await skills.getByRole('button', { name: `Expand ${choice.label}`, exact: true }).click();
            const previous = skills.getByRole('button', { name: `Previous ${choice.label} page`, exact: true });
            while (await previous.count() && await previous.isEnabled()) await previous.click();
            const beforeRows = await rowOrder();
            const checkbox = skills.getByRole('checkbox', { name: `Select ${excluded.display_name}`, exact: true });
            await checkbox.focus();
            await page.keyboard.press('Space');
            assert(!await checkbox.isChecked());
            assert(await checkbox.evaluate(element => element === document.activeElement), 'Selection retains keyboard focus');
            assert.deepEqual(await rowOrder(), beforeRows, 'Checking/unchecking never reorders visible rows');
            assert.deepEqual(await categoryOrder(), mountedOrder, 'Selection never reorders categories');
            assert.deepEqual(action('sql-readback').selected_candidate_ids, before.selected_candidate_ids, 'Dirty choices remain local until confirmation');
            const expectedSelected = new Set([...initial.selected_candidate_ids, ...members.map(candidate => candidate.candidate_id)].filter(id => id !== excluded.candidate_id));
            const expectedExcluded = new Set([...initial.excluded_candidate_ids.filter(id => !members.some(candidate => candidate.candidate_id === id)), excluded.candidate_id]);
            for (const [width, height] of [[1440, 900], [1280, 720], [390, 844]]) {
                await page.setViewportSize({ width, height });
                await geometry();
                await page.screenshot({ path: path.join(output, `priority-expanded-${width}.png`), fullPage: true });
            }
            // Only the external model transport is controlled; confirmation and persistence use real routes/SQL.
            action('model-queue', [{ content: 'Controlled acceptance reply after selection confirmation. Curriculum mapping was not performed.' }]);
            const confirmedPromise = page.waitForResponse(response => response.url().endsWith('/skill-review/selection-confirmation') && response.request().method() === 'POST');
            const chatPromise = page.waitForResponse(response => response.url() === `${base}/chat` && response.request().method() === 'POST');
            await skills.getByRole('button', { name: /^Confirm Selection/ }).click();
            const confirmed = await confirmedPromise;
            assert.equal(confirmed.status(), 200, 'Existing one-step confirmation saves the exact teacher draft');
            const chat = await chatPromise;
            assert.equal(chat.status(), 200);
            await chat.finished();
            requireCompletedMapping(await chat.text()); // Transport completion only; no assertion that mapping took place.
            const saved = action('sql-readback');
            assert.deepEqual(new Set(saved.selected_candidate_ids), expectedSelected);
            assert.deepEqual(new Set(saved.excluded_candidate_ids), expectedExcluded);
            requireConfirmation(saved.selection_confirmation, saved);
            assert.equal(saved.candidate_revision, before.candidate_revision);
            assert.equal(saved.publication_revision, before.publication_revision);
            assert.deepEqual(saved.approvals, before.approvals);
            const callsAfterConfirm = action('model-readback').length;
            assert.equal(callsAfterConfirm, callsBefore + 1, 'Only the explicitly confirmed workflow invokes the controlled model');
            await page.reload();
            await skills.waitFor();
            const restored = await fresh();
            assert.deepEqual(new Set(restored.selected_candidate_ids), expectedSelected);
            assert.deepEqual(new Set(restored.excluded_candidate_ids), expectedExcluded);
            assert.deepEqual(restored.priority_assessment, assessment, 'Read/reload returns the persisted assessment without inference');
            await skills.getByRole('button', { name: `Expand ${choice.label}`, exact: true }).click();
            assert(!await skills.getByRole('checkbox', { name: `Select ${excluded.display_name}`, exact: true }).isChecked(), 'Individual exclusion survives reload');
            for (const candidate of members.slice(1, 10)) assert(await skills.getByRole('checkbox', { name: `Select ${candidate.display_name}`, exact: true }).isChecked());
            assert.deepEqual(await categoryOrder(), mountedOrder, 'Saved guidance ordering survives reload');
            assert.equal(action('model-readback').length, callsAfterConfirm, 'Ordinary reads and reload never invoke inference');
            receipt.selection = { categoryMembers: members.length, selectedSkills: saved.selected_candidate_ids.length, exclusions: saved.excluded_candidate_ids.length, stableOnToggle: true, persistedOnReload: true, confirmationStatus: confirmed.status(), controlledReplyOnly: true, publicationRevision: saved.publication_revision };
            verifyConsole();
            receipt.status = 'passed';
            saveReceipt();
            console.log(`PASS priority labels/evidence/selection, ${scored.length}/${eligible.length} scored skills, 1440/1280/390 geometry; mapping/publication not exercised`);
            return;
        }
        if (phase === 'simple-boundary-negative') {
            const seeded = action('seed-simple-flow');
            fixtureManifest = '/tmp/teacher-workspace-simple.json';
            const headers = { Authorization: `Bearer ${fixture.teacher.access_token}` };
            const base = `${API}/courses/${seeded.course.id}/market-demand`;
            await page.goto(`${UI}/courses/${seeded.course.id}/market-analyst`);
            await page.getByRole('button', { name: 'Acknowledge available evidence', exact: true }).click();
            const decision = page.getByLabel('Current teacher decision', { exact: true });
            await decision.getByRole('button', { name: 'Continue', exact: true }).waitFor();
            const unconfirmed = action('sql-readback');
            assert.equal(unconfirmed.selection_confirmation, null);
            assert.throws(() => action('prepare-review'), /Existing current teacher selection confirmation is required/);
            assert.deepEqual(action('sql-readback'), unconfirmed, 'Rejected preparation must not write confirmation, review or publication');
            console.log('PASS real SQL missing-confirmation preparation rejected without mutation');
            action('model-queue', [{ exception: 'Controlled acceptance mapping terminal failure' }]);
            const responsePromise = page.waitForResponse(r => r.url() === `${base}/chat` && r.request().method() === 'POST');
            await decision.getByRole('button', { name: 'Continue', exact: true }).click();
            const response = await responsePromise;
            assert.equal(response.status(), 200);
            await response.finished();
            const body = await response.text();
            assert.match(body, /event: error/);
            assert.match(body, /event: stream_end\ndata:.*"outcome":\s*"failed"/);
            let preparationCalls = 0;
            await assert.rejects(async () => {
                await validateMappingResponse(response, base);
                await verifyBeforePreparation(base, headers, unconfirmed);
                preparationCalls++;
                action('prepare-review');
            }, /Mapping SSE contains an error event/);
            assert.equal(preparationCalls, 0);
            const failed = action('sql-readback');
            requireConfirmation(failed.selection_confirmation, unconfirmed);
            assert.equal(failed.integration_review, null);
            assert.equal(failed.publication_revision, 0);
            assert.deepEqual(failed.approvals, []);
            console.log('PASS real HTTP200 error/failed-terminal SSE rejected before preparation; confirmation retained, no review/approval/publication');
            return;
        }
        if (phase === 'simple-flow') {
            fs.mkdirSync(output, { recursive: true });
            const seeded = action('seed-simple-flow');
            fixtureManifest = '/tmp/teacher-workspace-simple.json';
            const headers = { Authorization: `Bearer ${fixture.teacher.access_token}` };
            const base = `${API}/courses/${seeded.course.id}/market-demand`;
            const fresh = async () => {
                const response = await context.request.get(`${base}/skill-review`, { headers });
                assert.equal(response.status(), 200);
                return response.json();
            };
            const initial = await fresh();
            const beforeExplainState = await (await context.request.get(`${base}/state`, { headers })).json();
            assert.equal(beforeExplainState.job_search_country, 'Uzbekistan');
            assert.equal(beforeExplainState.job_search_country_confirmed, true);
            assert.deepEqual(beforeExplainState.selected_onet_occupations, ['15-2051.00', '15-1252.00']);
            for (const outcome of Object.values(beforeExplainState.source_outcomes)) {
                assert(Array.isArray(outcome.warnings));
                assert.equal(typeof outcome.received_count, 'number');
                assert.equal(typeof outcome.usable_count, 'number');
            }
            const jobBackedIds = initial.candidates.filter(row => row.posting_support === 'supported').map(row => row.candidate_id);
            assert.equal(jobBackedIds.length, 58);
            assert.equal(initial.candidates.length - jobBackedIds.length, 394);
            const referenceExclusionId = seeded.candidate_ids[58];
            const etl = initial.candidates.find(row => row.display_name === 'ETL / ELT');
            const etlOriginalLinks = etl.evidence_references.map(ref => ref.original_url);
            assert.equal(new Set(etlOriginalLinks).size, 4);
            assert.equal(etl.evidence_references.length, 8);
            assert(etl.original_labels.includes('Create ETL') && etl.original_labels.includes('Develop ETL/ELT'));
            const studentBefore = action('seed-student');
            assert(studentBefore.path.total_selected_skills > 0);
            assert(studentBefore.path.chapters.some(chapter => chapter.selected_skills.some(skill => skill.readings.length > 0)));
            assert.match(JSON.stringify(studentBefore.reading), /Retained student resource/);
            assert.equal(studentBefore.quiz.previous_answers[seeded.student_question_id].answered_right, true);
            assert(studentBefore.path.chapters.some(chapter => chapter.correct_count > 0 && chapter.selected_skills.some(skill => skill.is_known)));
            fs.writeFileSync(path.join(output, 'student-before.json'), JSON.stringify(studentBefore, null, 2));
            const studentRead = async () => {
                const result = {};
                for (const [name, endpoint] of Object.entries({ path: 'path', quiz: 'chapters/1/quiz', reading: `readings/${seeded.student_reading_id}/content` })) {
                    const response = await context.request.get(`${API}/student-learning-path/${seeded.course.id}/${endpoint}`, { headers: { Authorization: `Bearer ${fixture.student.access_token}` } });
                    assert.equal(response.status(), 200);
                    result[name] = await response.json();
                }
                return result;
            };
            const decision = page.getByLabel('Current teacher decision', { exact: true });
            const skills = page.getByRole('region', { name: 'Choose skills', exact: true });
            const question = page.getByRole('textbox', { name: 'Question', exact: true });
            const navigate = async () => { await page.goto(`${UI}/courses/${seeded.course.id}/market-analyst`); await skills.waitFor(); };
            await navigate();
            const bounds = [];
            const capture = async (name, width, height, actionName) => {
                await page.setViewportSize({ width, height });
                await page.getByRole('button', { name: actionName, exact: true }).waitFor();
                const measured = await page.evaluate(({ actionName }) => {
                    const main = document.querySelector('main[aria-label="Evidence workspace"]');
                    const decision = document.querySelector('[aria-label="Current teacher decision"]');
                    const action = [...decision.querySelectorAll('button')].find(e => e.textContent === actionName);
                    const box = e => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height, bottom: r.bottom, right: r.right }; };
                    return { main: { ...box(main), clientHeight: main.clientHeight, scrollHeight: main.scrollHeight, scrollTop: main.scrollTop }, decision: box(decision), action: box(action), bodyWidth: document.body.scrollWidth, viewport: innerWidth, rows: document.querySelectorAll('[aria-label="Choose skills"] > ul > li').length };
                }, { actionName });
                assert(measured.rows <= 5);
                assert(measured.bodyWidth <= width + 1, `${name}: horizontal page overflow`);
                if (width >= 1024) {
                    assert(measured.main.scrollHeight <= measured.main.clientHeight + 1, `${name}: main scroll ${JSON.stringify(measured)}`);
                    assert(measured.action.bottom <= height && measured.decision.bottom <= height, `${name}: clipped current decision/action`);
                }
                bounds.push({ name, width, height, ...measured });
                await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
                if (width < 1024) {
                    const action = page.getByRole('button', { name: actionName, exact: true });
                    await action.scrollIntoViewIfNeeded();
                    await action.focus();
                    const visible = await action.boundingBox();
                    assert(visible.y >= 0 && visible.y + visible.height <= height, `${name}: mobile next action must be reachable`);
                    await page.screenshot({ path: path.join(output, `${name}-action.png`), fullPage: true });
                    await page.getByRole('main').evaluate(element => { element.scrollTop = 0; });
                }
            };
            for (const [width, height] of [[1280, 720], [1440, 900], [1024, 768], [390, 844], [320, 667]])
                await capture(`coverage-${width}`, width, height, 'Acknowledge available evidence');
            await page.setViewportSize({ width: 1280, height: 720 });
            await page.evaluate(() => document.documentElement.classList.add('dark'));
            await capture('coverage-dark', 1280, 720, 'Acknowledge available evidence');
            await page.evaluate(() => document.documentElement.classList.remove('dark'));
            const browse = async () => { await skills.getByRole('button', { name: /^(Browse skills|Review all \d+)$/ }).click(); return page.getByRole('dialog', { name: 'Browse skills', exact: true }); };
            let dialog = await browse();
            assert.equal(await dialog.getByRole('checkbox', { name: /^Select SYNTHETIC reference-only/ }).count(), 0);
            await dialog.getByRole('textbox', { name: 'Search skills', exact: true }).fill('SQL');
            const category = dialog.getByRole('checkbox', { name: 'Select category Data engineering (58 current members)', exact: true });
            await category.focus();
            await page.keyboard.press('Space');
            assert(await category.isChecked());
            await page.keyboard.press('Escape');
            assert.match(await skills.innerText(), /58 chosen/);
            assert.deepEqual(action('sql-readback').selected_candidate_ids, initial.selected_candidate_ids, 'Category selection is local');
            await skills.getByRole('button', { name: 'Save draft', exact: true }).click();
            await skills.getByRole('status').waitFor();
            assert.deepEqual(new Set(action('sql-readback').selected_candidate_ids), new Set(jobBackedIds), 'Category selects the exact 58 supported members across filters and pages');
            dialog = await browse();
            await dialog.getByRole('textbox', { name: 'Search skills', exact: true }).fill('');
            const visited = new Set();
            for (;;) {
                const rows = dialog.getByRole('checkbox', { name: /^Select (SQL|ETL|Critical Thinking|Communication|Python|Synthetic competency)/ });
                for (const row of await rows.all()) {
                    assert(await row.isChecked());
                    visited.add(await row.getAttribute('aria-label'));
                }
                const next = dialog.getByRole('button', { name: 'Next page', exact: true });
                if (await next.isDisabled())
                    break;
                await next.click();
            }
            assert.equal(visited.size, 58, 'Every supported member remains inspectable and selected across all pages');
            while (await dialog.getByRole('button', { name: 'Previous page', exact: true }).isEnabled())
                await dialog.getByRole('button', { name: 'Previous page', exact: true }).click();
            await dialog.getByRole('button', { name: 'Next page', exact: true }).click();
            const excludedName = await dialog.getByRole('checkbox', { name: /^Select Synthetic competency/ }).first().getAttribute('aria-label');
            await dialog.getByRole('checkbox', { name: excludedName, exact: true }).focus();
            await page.keyboard.press('Space');
            await page.keyboard.press('Escape');
            const beforeFailure = action('sql-readback');
            action('arm-save-failure');
            try {
                const failed = page.waitForEvent('requestfailed', r => r.url().endsWith('/skill-review/draft') && r.method() === 'PUT');
                await skills.getByRole('button', { name: 'Save draft', exact: true }).click();
                assert((await failed).failure(), 'Controlled SQL trigger must reject the actual browser save');
                await skills.getByRole('alert').filter({ hasText: 'Local choices retained' }).waitFor();
                assert.match(await skills.innerText(), /57 chosen/);
                assert.deepEqual(action('sql-readback'), beforeFailure);
                await capture('save-failure', 1280, 720, 'Acknowledge available evidence');
            }
            finally {
                action('disarm-save-failure');
            }
            await skills.getByRole('button', { name: 'Save draft', exact: true }).click();
            await skills.getByRole('status').waitFor();
            const saved = action('sql-readback');
            const savedSelectionIds = saved.selected_candidate_ids;
            assert.equal(savedSelectionIds.length, 57);
            assert(saved.excluded_candidate_ids.includes(referenceExclusionId));
            await page.reload();
            await skills.waitFor();
            const afterReload = await fresh();
            assert.deepEqual(afterReload.selected_candidate_ids, savedSelectionIds);
            assert(afterReload.excluded_candidate_ids.includes(referenceExclusionId));
            assert.match(await skills.innerText(), /57 chosen/);
            dialog = await browse();
            await dialog.getByRole('textbox', { name: 'Search skills', exact: true }).fill(excludedName.replace('Select ', ''));
            assert.equal(await dialog.getByRole('checkbox', { name: excludedName, exact: true }).isChecked(), false);
            await page.keyboard.press('Escape');
            await skills.getByRole('button', { name: 'Inspect ETL / ELT', exact: true }).click();
            dialog = page.getByRole('dialog', { name: 'Evidence for ETL / ELT', exact: true });
            await page.waitForFunction(() => [...document.querySelectorAll('[role=dialog] button')].filter(e => e.textContent === 'Reload full posting evidence').length === 4);
            assert.equal(await dialog.getByRole('link', { name: /^Original posting ·/ }).count(), 4);
            assert.equal(await dialog.getByText('Validated source passage: Create ETL pipelines', { exact: true }).count(), 4);
            assert.equal(await dialog.getByText('Validated source passage: Develop ETL/ELT services', { exact: true }).count(), 4);
            await page.screenshot({ path: path.join(output, 'etl-all-original-links.png'), fullPage: true });
            await page.keyboard.press('Escape');
            console.log('PASS saved58/57, off-page exclusion, failure/retry/reload, four original ETL postings/eight passages');
            const beforeCharts = mutations.length;
            await skills.getByRole('button', { name: 'Compare skills', exact: true }).click();
            dialog = page.getByRole('dialog', { name: 'Compare skills', exact: true });
            const chart = dialog.getByRole('img').first();
            await chart.locator('svg').waitFor();
            const options = await chart.evaluate(async (e, url) => { const core = await import(url); const i = core.getInstanceByDom(e); window.acceptanceChart = { i, e, core }; return i.getOption(); }, chartModuleURL);
            assert.equal(options.series.length, 1);
            assert(options.series[0].data.length <= 5);
            const mark = await chart.boundingBox();
            assert(mark && mark.width > 0);
            const pixel = await page.evaluate(() => window.acceptanceChart.i.convertToPixel({ seriesIndex: 0 }, [50, 0]));
            await page.mouse.click(mark.x + pixel[0], mark.y + pixel[1]);
            await dialog.locator('[aria-current="true"]').waitFor();
            assert.equal(mutations.length, beforeCharts);
            await dialog.getByRole('button', { name: 'O*NET importance', exact: true }).click();
            await dialog.getByRole('list', { name: 'Comparison values', exact: true }).waitFor();
            const values = await dialog.getByRole('list', { name: 'Comparison values', exact: true }).innerText();
            assert.match(values, /Programming/);
            assert.match(values, /4.2 \/ 5 importance/);
            assert.match(values, /Unavailable/);
            assert.equal(await dialog.locator('[aria-label="Comparison values"] strong').filter({ hasText: /^SQL$/ }).count(), 0, 'Related descriptor must never become an official SQL rating');
            assert.equal(await dialog.getByRole('combobox', { name: 'Confirmed occupation', exact: true }).locator('option').count(), 3);
            const importanceChart = dialog.getByRole('img').first();
            await importanceChart.locator('svg').waitFor();
            const importanceOptions = await importanceChart.evaluate(async (e, url) => (await import(url)).getInstanceByDom(e).getOption(), chartModuleURL);
            assert.deepEqual(importanceOptions.series[0].data.map(row => row.value), [4.2]);
            assert.match(JSON.stringify(importanceOptions.yAxis), /Programming/);
            await importanceChart.locator('svg text').filter({ hasText: /^Programming — related to SQL$/ }).waitFor();
            const renderedImportanceBar = await importanceChart.evaluate(async (e, url) => {
                const instance = (await import(url)).getInstanceByDom(e);
                const mark = instance.getModel().getSeriesByIndex(0).getData().getItemGraphicEl(0);
                return [...e.querySelectorAll('svg path')].some(path => {
                    const bounds = path.getBBox();
                    return path.getAttribute('fill') === mark.style.fill && bounds.width > 0 && bounds.height > 0;
                });
            }, chartModuleURL);
            assert(renderedImportanceBar, 'The new IM numeric bar must be rendered in the actual SVG');
            await page.screenshot({ path: path.join(output, 'onet-related-and-missing.png'), fullPage: true });
            await dialog.getByRole('button', { name: 'Collected jobs', exact: true }).click();
            await dialog.getByRole('button', { name: 'Ask about SQL', exact: true }).click();
            await page.getByLabel('Attached context', { exact: true }).waitFor();
            action('model-queue', [{ content: 'Synthetic explanation of SQL collected job evidence.', delay: 1 }]);
            const explainResponse = page.waitForResponse(r => r.url().endsWith('/chat'));
            await page.getByRole('button', { name: 'Send message', exact: true }).click();
            await question.fill('Retain my next question during streaming.');
            await (await explainResponse).finished();
            assert.equal(await question.inputValue(), 'Retain my next question during streaming.');
            const calls = action('model-readback');
            assert.deepEqual(calls.at(-1).tools, []);
            assert(calls.at(-1).evidence.candidates.some(c => c.display_name === 'SQL'));
            assert.deepEqual(action('sql-readback'), saved, 'Explain must not mutate selection/publication');
            await page.getByText('Review analysis setup before continuing.', { exact: true }).waitFor({ state: 'hidden' });
            const afterExplainState = await (await context.request.get(`${base}/state`, { headers })).json();
            for (const key of ['run_id', 'sources', 'evidence_sources', 'onet_release', 'selected_onet_occupations', 'job_search_country', 'job_search_country_confirmed'])
                assert.deepEqual(afterExplainState[key], beforeExplainState[key], `Explain preserves ${key}`);
            console.log('PASS actual SVG, related/missing ONet, readonly contextual Explain, streaming draft retention');
            await question.fill('');
            await skills.getByRole('button', { name: 'Acknowledge available evidence', exact: true }).count();
            await page.getByRole('button', { name: 'Acknowledge available evidence', exact: true }).click();
            await decision.getByRole('button', { name: 'Continue', exact: true }).waitFor();
            assert.equal(action('sql-readback').publication_revision, 0);
            action('model-queue', [{ content: 'Synthetic mapping work is ready for the controlled curriculum target resolver.' }]);
            const expectedConfirmation = action('sql-readback');
            assert.deepEqual(expectedConfirmation.selected_candidate_ids, savedSelectionIds);
            const confirmationResponse = page.waitForResponse(r => r.url() === `${base}/skill-review/selection-confirmation` && r.request().method() === 'POST');
            const mappingResponse = page.waitForResponse(r => r.url() === `${base}/chat` && r.request().method() === 'POST');
            await decision.getByRole('button', { name: 'Continue', exact: true }).click();
            const confirmed = await confirmationResponse;
            assert.equal(confirmed.status(), 200);
            assert.deepEqual(confirmed.request().postDataJSON(), {
                run_id: expectedConfirmation.run_id,
                expected_candidate_revision: expectedConfirmation.candidate_revision,
                expected_selection_revision: expectedConfirmation.selection_revision,
            });
            const confirmedReview = await confirmed.json();
            for (const key of ['run_id', 'candidate_revision', 'selection_revision', 'selected_candidate_ids', 'excluded_candidate_ids'])
                assert.deepEqual(confirmedReview[key], expectedConfirmation[key]);
            const mapped = await mappingResponse;
            const mappingEvents = await validateMappingResponse(mapped, base);
            await verifyBeforePreparation(base, headers, expectedConfirmation);
            console.log(`PASS UI selection-confirmation200 exact revisions/57IDs/exclusions/teacher; mapping200 terminal=${mappingEvents.at(-1).data.outcome}; authoritative confirmation idle/unpublished/noapproval before preparation`);
            const prepared = action('prepare-review');
            await page.reload();
            const integration = page.getByRole('region', { name: 'Final integration review', exact: true });
            await integration.waitFor();
            const beforeExplicitApproval = action('sql-readback');
            assert.equal(beforeExplicitApproval.publication_revision, 0);
            for (const [width, height] of [[1280, 720], [1440, 900]])
                await capture(`curriculum-${width}`, width, height, 'Approve and publish');
            assert.equal(await integration.getByRole('button', { name: 'Approve and publish', exact: true }).isEnabled(), true);
            const approvalResponse = page.waitForResponse(r => r.url().endsWith('/integration-approval') && r.request().method() === 'POST');
            await integration.getByRole('button', { name: 'Approve and publish', exact: true }).click();
            const approved = await approvalResponse;
            assert.equal(approved.status(), 200);
            assert.equal((await approved.json()).projection_status, 'projected');
            const sql = action('sql-readback');
            assert.equal(sql.publication_revision, 1);
            assert.equal(sql.approvals.length, 1);
            assert.equal(sql.approvals[0].review_digest, prepared.integration_review.review_digest);
            assert.deepEqual(approved.request().postDataJSON().approved_candidate_ids, savedSelectionIds);
            assert.equal(sql.approvals[0].items.length, savedSelectionIds.length);
            for (const item of sql.approvals[0].items)
                assert.equal(item.qualifying_posting_links.length, 4);
            const repeat = await context.request.post(`${base}/integration-approval`, { headers, data: approved.request().postDataJSON() });
            assert.equal(repeat.status(), 200);
            assert.equal(action('sql-readback').approvals.length, 1, 'Repeated explicit approval is idempotent');
            assert.equal((await fresh()).candidates.find(candidate => candidate.candidate_id === etl.candidate_id).evidence_references.length, 8);
            const archive = path.join(path.dirname(manifestPath), 'published-simple-manifest.json');
            execFileSync('/Applications/Docker.app/Contents/Resources/bin/docker', ['cp', `${backendContainer}:${fixtureManifest}`, archive]);
            fs.chmodSync(archive, 0o600);
            const afterStudent = await studentRead();
            fs.writeFileSync(path.join(path.dirname(manifestPath), 'approval-student-readback.json'), JSON.stringify({ sql, afterStudent }, null, 2));
            assert.deepEqual(afterStudent.path, studentBefore.path);
            assert.deepEqual(afterStudent.reading, studentBefore.reading);
            assert.deepEqual(afterStudent.quiz, studentBefore.quiz);
            await page.screenshot({ path: path.join(output, 'approved-disposable-fixture.png'), fullPage: true });
            assert.deepEqual(errors, []);
            fs.writeFileSync(path.join(output, 'simple-flow-summary.json'), JSON.stringify({ jobBacked: 58, referenceOnly: 394, etlDistinctLinks: 4, etlValidatedPassages: 8, bounds, selected: savedSelectionIds.length, publicationRevision: sql.publication_revision, studentPreserved: true }, null, 2));
            verifyConsole('/skill-review/draft');
            console.log('PASS simple-flow real SQL/auth/checkpoints/Neo4j, complete categories, saved exclusions, controlled save failure, SVG/ONet/provenance, explicit approval and student preservation');
            return;
        }
        if (phase === 'simple-contracts') {
            fs.mkdirSync(output, { recursive: true });
            const seeded = action('seed-simple-flow');
            fixtureManifest = '/tmp/teacher-workspace-simple.json';
            const headers = { Authorization: `Bearer ${fixture.teacher.access_token}` };
            const base = `${API}/courses/${seeded.course.id}/market-demand`;
            const fresh = async () => (await context.request.get(`${base}/skill-review`, { headers })).json();
            await page.goto(`${UI}/courses/${seeded.course.id}/market-analyst`);
            const skills = page.getByRole('region', { name: 'Choose skills', exact: true });
            await skills.waitFor();
            const initial = await fresh();
            const revision = { run_id: initial.run_id, expected_candidate_revision: initial.candidate_revision, expected_selection_revision: initial.selection_revision };
            const denied = await context.request.get(`${base}/skill-review`, { headers: { Authorization: `Bearer ${fixture.student.access_token}` } });
            assert.equal(denied.status(), 403);
            const otherEmail = `teacher-${Date.now()}@workspace-acceptance.example`;
            const otherPassword = require('node:crypto').randomBytes(24).toString('base64url');
            const registered = await context.request.post(`${API}/auth/register`, { data: { email: otherEmail, password: otherPassword, first_name: 'Synthetic', last_name: 'Other teacher', role: 'teacher' } });
            assert.equal(registered.status(), 201);
            const logged = await context.request.post(`${API}/auth/jwt/login`, { form: { username: otherEmail, password: otherPassword } });
            assert.equal(logged.status(), 200);
            const otherToken = (await logged.json()).access_token;
            const foreign = await context.request.get(`${base}/skill-review`, { headers: { Authorization: `Bearer ${otherToken}` } });
            assert([403, 404].includes(foreign.status()), 'Another teacher must not inspect this course');
            const stale = await context.request.put(`${base}/skill-review/draft`, { headers, data: { ...revision, expected_candidate_revision: 0, selected_candidate_ids: initial.selected_candidate_ids, excluded_candidate_ids: initial.excluded_candidate_ids } });
            assert.equal(stale.status(), 409);
            const blocked = await context.request.post(`${base}/skill-review/selection-confirmation`, { headers, data: revision });
            assert.equal(blocked.status(), 409);
            const callsBefore = action('model-readback').length;
            const attach = { kind: 'run_review', version: 1, intent: 'explain', ...revision, view: 'overview', focused_candidate_id: seeded.candidate_ids[0], candidate_ids: [], filters: { category_ids: [], search: '', scope: 'all' }, occupation_codes: [], metric: 'frequency', descriptor_choices: [], insight_kind: null, has_unsaved_changes: false };
            for (const change of [{ focused_candidate_id: '00000000-0000-0000-0000-000000009999' }, { expected_selection_revision: 0 }, { candidate_ids: seeded.candidate_ids.slice(0, 21) }]) {
                const response = await context.request.post(`${base}/chat`, { headers, data: { message: 'Reject before inference', workspace_context: { ...attach, ...change } } });
                assert([409, 422].includes(response.status()));
            }
            assert.equal(action('model-readback').length, callsBefore);
            const proposalChanges = [...initial.selected_candidate_ids.map(candidate_id => ({ candidate_id, action: 'remove', reason: 'Synthetic proposal for explicit teacher review' })), { candidate_id: seeded.candidate_ids[58], action: 'add', reason: 'Synthetic protected reference exclusion' }];
            action('model-queue', [{ tool_calls: [{ id: 'simple-proposal', name: 'propose_skill_selection', args: { changes: proposalChanges } }] }]);
            const suggestion = await context.request.post(`${base}/chat`, { headers, data: { message: 'Suggest changes for teacher review only', workspace_context: { ...attach, intent: 'propose_selection', candidate_ids: initial.selected_candidate_ids } } });
            assert.equal(suggestion.status(), 200);
            await suggestion.body();
            const proposed = await fresh();
            assert.deepEqual(proposed.selected_candidate_ids, initial.selected_candidate_ids);
            assert.equal(proposed.recommendations.length, 1);
            await page.reload();
            await skills.waitFor();
            await page.setViewportSize({ width: 1280, height: 720 });
            const proposalBounds = await page.getByRole('main').evaluate(e => ({ client: e.clientHeight, scroll: e.scrollHeight }));
            assert(proposalBounds.scroll <= proposalBounds.client + 1, 'Five rows plus proposals and required coverage gate must fit');
            assert.equal(await skills.locator(':scope > ul > li').count(), 5);
            await page.screenshot({ path: path.join(output, 'five-rows-proposals-coverage.png'), fullPage: true });
            await page.getByRole('button', { name: 'Review all 6 proposed changes', exact: true }).click();
            await page.getByRole('dialog', { name: 'Proposed draft changes', exact: true }).getByRole('button', { name: 'Apply proposal to draft', exact: true }).click();
            assert.deepEqual((await fresh()).selected_candidate_ids, initial.selected_candidate_ids, 'Applying advice stays local');
            assert.match(await skills.innerText(), /0 chosen/);
            await skills.getByRole('button', { name: 'Undo local change', exact: true }).click();
            assert.match(await skills.innerText(), /5 chosen/);
            assert((await fresh()).excluded_candidate_ids.includes(seeded.candidate_ids[58]));
            await skills.getByRole('button', { name: 'Remove SQL', exact: true }).click();
            await page.getByRole('link', { name: `← ${seeded.course.title}`, exact: true }).click();
            await page.getByRole('alertdialog').getByRole('heading', { name: 'Unsaved shortlist', exact: true }).waitFor();
            await page.getByRole('alertdialog').getByRole('button', { name: 'Cancel', exact: true }).click();
            assert.match(await skills.innerText(), /4 chosen/);
            await skills.getByRole('button', { name: 'Undo local change', exact: true }).click();
            // Repeated open/close uses the actual ECharts instance; no leaked handlers.
            for (let cycle = 0; cycle < 3; cycle++) {
                await skills.getByRole('button', { name: 'Compare skills', exact: true }).click();
                const chart = page.getByRole('dialog', { name: 'Compare skills', exact: true }).getByRole('img').first();
                await chart.locator('svg').waitFor();
                assert.equal(await chart.evaluate(async (e, url) => { const core = await import(url); const i = core.getInstanceByDom(e); window.disposalProbe = { i, e, core }; return i._$handlers.click.length; }, chartModuleURL), 1);
                await page.keyboard.press('Escape');
                assert(await page.evaluate(() => window.disposalProbe.i.isDisposed() && !window.disposalProbe.core.getInstanceByDom(window.disposalProbe.e)));
            }
            const isolated = await browser.newContext({ viewport: { width: 1280, height: 720 } });
            const fallback = await isolated.newPage();
            await fallback.addInitScript(t => { localStorage.setItem('access_token', t.access_token); localStorage.setItem('refresh_token', t.refresh_token); }, fixture.teacher);
            const imported = [];
            const importErrors = [];
            fallback.on('pageerror', e => importErrors.push(e.message));
            await fallback.route('**/*echarts_core*', route => { imported.push(route.request().url()); return route.abort('failed'); });
            await fallback.goto(`${UI}/courses/${seeded.course.id}/market-analyst`);
            await fallback.getByRole('button', { name: 'Compare skills', exact: true }).click();
            await fallback.getByRole('alert').filter({ hasText: 'Chart unavailable' }).waitFor();
            assert(imported.length > 0);
            assert.equal(await fallback.getByRole('list', { name: 'Comparison values', exact: true }).locator(':scope > li').count(), 5);
            await fallback.screenshot({ path: path.join(output, 'chart-import-failure.png'), fullPage: true });
            await fallback.keyboard.press('Escape');
            await fallback.getByRole('button', { name: /^(Browse skills|Review all \d+ chosen or proposed skills)$/ }).click();
            const fallbackDialog = fallback.getByRole('dialog', { name: 'Browse skills', exact: true });
            const checkbox = fallbackDialog.getByRole('checkbox', { name: 'Select SQL', exact: true });
            await checkbox.uncheck();
            assert(!await checkbox.isChecked());
            assert.deepEqual(importErrors, []);
            await isolated.close();
            // Closing transport never retries server work or drops the next question.
            action('model-queue', [{ content: 'Synthetic detached explanation completed.', delay: 3 }]);
            const question = page.getByRole('textbox', { name: 'Question', exact: true });
            await question.fill('Retain this question after detaching.');
            const streamed = page.waitForResponse(r => r.url().endsWith('/chat'));
            await page.getByRole('button', { name: 'Send message', exact: true }).click();
            await streamed;
            await page.getByRole('button', { name: 'Close live response', exact: true }).click();
            await page.getByText(/Live response closed\. Server work may continue/).waitFor();
            assert.equal(await question.inputValue(), 'Retain this question after detaching.');
            const chatCount = mutations.filter(row => row.url.endsWith('/chat')).length;
            for (let attempt = 0; attempt < 60; attempt++) {
                const state = await (await context.request.get(`${base}/execution-status`, { headers })).json();
                if (state.status === 'idle')
                    break;
                assert(attempt < 59);
                await page.waitForTimeout(100);
            }
            assert.equal(mutations.filter(row => row.url.endsWith('/chat')).length, chatCount, 'Detached transport must not resubmit');
            const attachment = page.getByLabel('Attached context', { exact: true });
            await attachment.locator('summary').click();
            await attachment.getByRole('button', { name: 'Refresh context', exact: true }).click();
            assert.equal(await question.inputValue(), 'Retain this question after detaching.');
            await question.fill('');
            // Recheck content availability on every inspector open; old passages must disappear.
            await skills.getByRole('button', { name: 'Inspect ETL / ELT', exact: true }).click();
            let dialog = page.getByRole('dialog', { name: 'Evidence for ETL / ELT', exact: true });
            await page.waitForFunction(() => [...document.querySelectorAll('[role=dialog] button')].filter(e => e.textContent === 'Reload full posting evidence').length === 4);
            assert.equal(await dialog.getByText('Validated source passage: Create ETL pipelines', { exact: true }).count(), 4);
            await page.keyboard.press('Escape');
            action('purge-first-posting', undefined, ['--snapshot-id', seeded.snapshot_ids[0]]);
            await skills.getByRole('button', { name: 'Inspect ETL / ELT', exact: true }).click();
            dialog = page.getByRole('dialog', { name: 'Evidence for ETL / ELT', exact: true });
            await dialog.getByText(/Posting content unavailable: purged/).waitFor();
            assert.equal(await dialog.getByText('Validated source passage: Create ETL pipelines', { exact: true }).count(), 3);
            assert.equal(await dialog.getByRole('link', { name: /^Original posting ·/ }).count(), 4);
            const purgedArticle = dialog.getByRole('article').filter({ hasText: 'Posting content unavailable: purged' });
            assert.equal(await purgedArticle.locator('blockquote').count(), 0);
            assert.equal(await purgedArticle.locator('details').count(), 0);
            await page.screenshot({ path: path.join(output, 'purged-posting-no-body.png'), fullPage: true });
            await page.keyboard.press('Escape');
            // Real revision change retains explicit conflict handling instead of silently selecting a merge.
            const recon = action('seed-reconciliation');
            await page.goto(`${UI}/courses/${recon.course.id}/market-analyst`);
            await skills.waitFor();
            const merged = action('merge-reconciliation');
            assert.equal(merged.review.candidate_revision, 2);
            assert.equal(merged.review.reconciliations.length, 1);
            await page.reload();
            await page.getByRole('region', { name: 'Candidate reconciliation', exact: true }).waitFor();
            const gate = page.getByRole('region', { name: 'Candidate reconciliation', exact: true });
            assert.equal(await gate.getByRole('button', { name: 'Save reviewed choices', exact: true }).isDisabled(), true);
            await gate.getByRole('checkbox').check();
            await gate.getByRole('button', { name: 'Save reviewed choices', exact: true }).click();
            await gate.waitFor({ state: 'detached' });
            const mergedRead = await (await context.request.get(`${API}/courses/${recon.course.id}/market-demand/skill-review`, { headers })).json();
            assert.deepEqual(mergedRead.selected_candidate_ids, []);
            await page.screenshot({ path: path.join(output, 'revised-candidates-reviewed.png'), fullPage: true });
            assert.deepEqual(errors, []);
            verifyConsole();
            console.log('PASS ownership/revisions/context rejection, chart disposal/import failure, purge availability recheck, explicit candidate reconciliation');
            return;
        }
        if (phase === 'simple-workflow') {
            fs.mkdirSync(output, { recursive: true });
            const headers = { Authorization: `Bearer ${fixture.teacher.access_token}` };
            const created = await context.request.post(`${API}/courses`, { headers, data: { title: `SYNTHETIC four decision workflow ${Date.now()}` } });
            assert.equal(created.status(), 201);
            const course = await created.json();
            await page.goto(`${UI}/courses/${course.id}/market-analyst`);
            await page.getByRole('button', { name: /History and setup/ }).click();
            let dialog = page.getByRole('dialog', { name: 'History and analysis setup', exact: true });
            await dialog.getByRole('combobox', { name: 'Market country', exact: true }).click();
            await page.getByRole('option', { name: 'Uzbekistan', exact: true }).click();
            for (const name of ['Indeed', 'LinkedIn'])
                await dialog.getByRole('checkbox', { name, exact: true }).uncheck();
            await dialog.getByRole('checkbox', { name: 'HeadHunter', exact: true }).check();
            await page.keyboard.press('Escape');
            const question = page.getByRole('textbox', { name: 'Question', exact: true });
            action('model-queue', [{ content: 'Search Terms: "Python developer", "Software engineer", "Data engineer", "SQL developer", "ETL developer". Confirm these search terms.', delay: 1 }]);
            const initialResponse = page.waitForResponse(r => r.url().endsWith('/chat'));
            await page.getByRole('button', { name: 'Start an analysis', exact: true }).click();
            await question.fill('Retain next question while collecting.');
            await (await initialResponse).finished();
            await page.getByRole('button', { name: 'Confirm search terms · History and setup', exact: true }).waitFor();
            assert.equal(await question.inputValue(), 'Retain next question while collecting.');
            await question.fill('');
            const decision = page.getByLabel('Current teacher decision', { exact: true });
            assert.equal(await decision.getByRole('checkbox').count(), 5);
            for (const [width, height] of [[1280, 720], [1440, 900]]) {
                await page.setViewportSize({ width, height });
                const measured = await page.getByRole('main').evaluate(e => ({ client: e.clientHeight, scroll: e.scrollHeight }));
                assert(measured.scroll <= measured.client + 1);
                const bound = await decision.getByRole('button', { name: 'Continue', exact: true }).boundingBox();
                assert(bound.y + bound.height <= height);
                await page.screenshot({ path: path.join(output, `search-terms-${width}.png`), fullPage: true });
            }
            action('model-queue', [{ tool_calls: [{ id: 'simple-handoff', name: 'transfer_to_skill_finder', args: {} }] }, { tool_calls: [{ id: 'simple-fetch', name: 'fetch_jobs', args: { search_terms: 'Python developer, Software engineer', country: 'Uzbekistan' } }] }, { content: 'Synthetic postings collected; choose the job group.' }]);
            await decision.getByRole('button', { name: 'Select all', exact: true }).click();
            await decision.getByRole('button', { name: 'Continue', exact: true }).click();
            await page.getByRole('button', { name: 'Choose job groups · History and setup', exact: true }).waitFor();
            action('model-queue', [{ tool_calls: [{ id: 'simple-select', name: 'select_jobs_by_group', args: { group_names: 'all' } }] }, { content: 'The teacher-confirmed job group is selected.' }]);
            await decision.getByRole('button', { name: 'Select all', exact: true }).click();
            await decision.getByRole('button', { name: 'Continue', exact: true }).click();
            await page.getByText('The teacher-confirmed job group is selected.', { exact: true }).waitFor();
            const state = await (await context.request.get(`${API}/courses/${course.id}/market-demand/state`, { headers })).json();
            assert.equal(state.fetched_jobs.length, 3);
            assert.equal(state.selected_jobs.length, 3);
            await page.getByRole('button', { name: /History and setup/ }).click();
            dialog = page.getByRole('dialog', { name: 'History and analysis setup', exact: true });
            await dialog.getByRole('button', { name: 'Analysis setup', exact: true }).click();
            assert.equal(await dialog.getByRole('combobox', { name: 'Market country', exact: true }).isDisabled(), true);
            await dialog.getByRole('button', { name: 'Stage workflow response', exact: true }).click();
            action('model-queue', [{ tool_calls: [{ id: 'simple-source-error', name: 'fetch_jobs', args: { search_terms: 'sourceerror', country: 'Uzbekistan' } }] }, { content: 'The synthetic source failed. No fallback source was used.' }]);
            await page.getByRole('button', { name: 'Send message', exact: true }).click();
            await page.getByText('The synthetic source failed. No fallback source was used.', { exact: true }).waitFor();
            await page.getByRole('region', { name: 'Source recovery', exact: true }).getByText(/collection failed/).waitFor();
            const failedState = await (await context.request.get(`${API}/courses/${course.id}/market-demand/state`, { headers })).json();
            assert.equal(failedState.source_outcomes.headhunter.status, 'error');
            assert.equal(failedState.fetched_jobs.length, 0);
            assert.deepEqual(failedState.sources, ['headhunter']);
            await page.screenshot({ path: path.join(output, 'source-failure-recovery.png'), fullPage: true });
            action('model-queue', [{ exception: 'Synthetic retry failure' }]);
            await page.getByRole('button', { name: 'Retry failed sources', exact: true }).click();
            await page.getByText('Work failed', { exact: true }).waitFor();
            assert.equal(mutations.filter(row => row.url.endsWith('/chat')).length, 5, 'A known failed source retry must not resubmit itself');
            await page.reload();
            await page.getByRole('region', { name: 'Source recovery', exact: true }).waitFor();
            assert.equal(action('model-readback').at(-1).human, 'Retry all providers and reassess the collected evidence');
            await question.fill('Retain this reset draft until acknowledged.');
            await page.getByRole('button', { name: /History and setup/ }).click();
            await page.getByRole('button', { name: 'New analysis', exact: true }).click();
            action('arm-reset-failure');
            try {
                await page.getByRole('alertdialog').getByRole('button', { name: 'Start new analysis', exact: true }).click();
                await page.getByRole('alertdialog').getByRole('alert').waitFor();
            }
            finally {
                action('disarm-reset-failure');
            }
            await page.getByRole('alertdialog').getByRole('button', { name: 'Cancel', exact: true }).click();
            assert.equal(await question.inputValue(), 'Retain this reset draft until acknowledged.');
            await page.getByRole('button', { name: 'Retry reset', exact: true }).click();
            await page.getByRole('alertdialog').getByRole('button', { name: 'Confirm reset retry', exact: true }).click();
            await page.getByText('Start an analysis to collect job evidence for this course.', { exact: true }).waitFor();
            assert.deepEqual(errors, []);
            fs.writeFileSync(path.join(output, 'workflow-summary.json'), JSON.stringify({ courseId: course.id, searchTerms: 5, selectedJobs: state.selected_jobs.length, sourceError: failedState.source_outcomes.headhunter.status, resetRecovered: true }, null, 2));
            verifyConsole('/market-demand/history');
            console.log('PASS real graph/checkpointer search terms and job groups, five-row layout, source locks/error, failed execution and explicit reset recovery');
            return;
        }
        if (phase === 'simple-corpus') {
            fs.mkdirSync(output, { recursive: true });
            const headers = { Authorization: `Bearer ${fixture.teacher.access_token}` };
            const corpus = action('seed-corpus');
            const checked = [];
            for (const item of corpus) {
                const canonical = patterns => patterns.map(({ coverage, ...fact }) => fact);
                assert.deepEqual(canonical(item.resolved.model_bundle.patterns), canonical(item.source_case.expected), `${item.name}: canonical backend facts`);
                const review = item.review;
                const base = `${API}/courses/${item.course.id}/market-demand`;
                const saved = await context.request.put(`${base}/skill-review/draft`, { headers, data: { run_id: review.run_id, expected_candidate_revision: review.candidate_revision, expected_selection_revision: review.selection_revision, selected_candidate_ids: review.candidates.map(c => c.candidate_id), excluded_candidate_ids: [] } });
                assert.equal(saved.status(), 200);
                await page.goto(`${UI}/courses/${item.course.id}/market-analyst`);
                await page.getByRole('button', { name: 'Compare skills', exact: true }).click();
                const dialog = page.getByRole('dialog', { name: 'Compare skills', exact: true });
                await dialog.getByRole('button', { name: 'O*NET importance', exact: true }).click();
                const roles = review.analysis_metadata.occupations;
                for (const role of roles) {
                    await dialog.getByRole('combobox', { name: 'Confirmed occupation', exact: true }).selectOption(role.soc_code);
                    if (item.name === 'explicit_descriptor_choice') {
                        const selector = dialog.getByRole('combobox', { name: `Descriptor for ${review.candidates[0].display_name}`, exact: true });
                        if (await selector.count())
                            await selector.selectOption(item.context.descriptor_choices[0].evidence_id);
                    }
                    const values = await dialog.getByRole('list', { name: 'Comparison values', exact: true }).innerText();
                    const descriptorValues = review.candidates.flatMap(candidate => {
                        const rows = candidate.onet_associations.filter(a => a.relation === 'equivalent' && ['essential', 'transferable'].includes(a.evidence.family) && a.evidence.soc_code === role.soc_code && a.evidence.release === review.analysis_metadata.onet_release);
                        const choice = item.context.descriptor_choices.find(c => c.candidate_id === candidate.candidate_id && rows.some(row => row.evidence.id === c.evidence_id));
                        const unique = [...new Set(rows.map(a => a.evidence.id))];
                        const row = choice ? rows.find(a => a.evidence.id === choice.evidence_id) : unique.length === 1 ? rows[0] : null;
                        const rating = row?.evidence.ratings.IM;
                        return row ? [{ key: [row.evidence.release, row.evidence.soc_code, row.evidence.family, row.evidence.element_id].join('|'), value: rating?.status === 'reported' && rating.value >= 1 && rating.value <= 5 ? rating.value : null }] : [];
                    });
                    const grouped = new Map();
                    for (const row of descriptorValues) {
                        if (!grouped.has(row.key))
                            grouped.set(row.key, new Set());
                        grouped.get(row.key).add(row.value);
                    }
                    const eligible = [...grouped.values()].filter(values => values.size === 1 && !values.has(null)).map(values => [...values][0]);
                    const chart = dialog.locator('[role=img]');
                    if (eligible.length) {
                        await chart.locator('svg').waitFor();
                        const actual = await chart.evaluate(async (e, url) => (await import(url)).getInstanceByDom(e).getOption().series[0].data.map(d => d.value), chartModuleURL);
                        assert.deepEqual(actual, eligible, `${item.name}/${role.soc_code}`);
                    }
                    else {
                        assert.equal(await chart.count(), 0);
                        assert.match(values, /Unavailable|Choose a descriptor/);
                    }
                }
                checked.push(item.name);
                await page.keyboard.press('Escape');
            }
            const metadata = action('metadata-compatibility');
            assert(metadata.approved_main_review_unchanged);
            assert.deepEqual(metadata.restored_config, metadata.original_config);
            const tooltip = action('seed-tooltip-five');
            const review = tooltip.review;
            const saved = await context.request.put(`${API}/courses/${tooltip.course.id}/market-demand/skill-review/draft`, { headers, data: { run_id: review.run_id, expected_candidate_revision: review.candidate_revision, expected_selection_revision: review.selection_revision, selected_candidate_ids: review.candidates.map(c => c.candidate_id), excluded_candidate_ids: [] } });
            assert.equal(saved.status(), 200);
            await page.goto(`${UI}/courses/${tooltip.course.id}/market-analyst`);
            await page.getByRole('region', { name: 'Choose skills', exact: true }).waitFor();
            for (const [width, height] of [[1280, 720], [1440, 900]]) {
                await page.setViewportSize({ width, height });
                const main = page.getByRole('main');
                const bounds = await main.evaluate(e => ({ client: e.clientHeight, scroll: e.scrollHeight, width: e.clientWidth, contentWidth: e.scrollWidth }));
                assert(bounds.scroll <= bounds.client + 1 && bounds.contentWidth <= bounds.width + 1, 'Unicode labels must not overflow the main decision');
                const decision = await page.getByLabel('Current teacher decision', { exact: true }).boundingBox();
                assert(decision.y + decision.height <= height);
                await page.screenshot({ path: path.join(output, `unicode-main-${width}.png`), fullPage: true });
            }
            await page.getByRole('button', { name: 'Browse skills', exact: true }).click();
            const browse = page.getByRole('dialog', { name: 'Browse skills', exact: true });
            for (const candidate of review.candidates) {
                const label = browse.getByText(candidate.display_name, { exact: false }).first();
                assert.equal(await label.evaluate(e => getComputedStyle(e).textOverflow), 'clip');
                assert(await label.evaluate(e => e.scrollWidth <= e.clientWidth + 1));
            }
            await page.keyboard.press('Escape');
            await page.getByRole('button', { name: 'Compare skills', exact: true }).click();
            const dialog = page.getByRole('dialog', { name: 'Compare skills', exact: true });
            await dialog.getByRole('button', { name: 'O*NET importance', exact: true }).click();
            assert.equal(await dialog.getByRole('combobox', { name: 'Confirmed occupation', exact: true }).locator('option').count(), 6);
            for (const [width, height] of [[1280, 720], [390, 844], [320, 667]]) {
                await page.setViewportSize({ width, height });
                assert(await dialog.evaluate(e => e.scrollWidth <= e.clientWidth + 1));
                const graph = dialog.locator('[role=img]');
                await graph.locator('svg').waitFor();
                const box = await graph.boundingBox();
                const point = await graph.evaluate(async (e, url) => (await import(url)).getInstanceByDom(e).convertToPixel({ seriesIndex: 0 }, [3, 0]), chartModuleURL);
                await page.mouse.move(box.x + point[0], box.y + point[1]);
                assert.equal(await dialog.locator('svg script, svg foreignObject').count(), 0);
                await page.screenshot({ path: path.join(output, `unicode-five-roles-${width}.png`), fullPage: true });
            }
            for (const role of review.analysis_metadata.occupations.slice(2)) {
                await dialog.getByRole('combobox', { name: 'Confirmed occupation', exact: true }).selectOption(role.soc_code);
                assert.equal(await dialog.locator('[role=img]').count(), 0);
                assert.match(await dialog.innerText(), /Unavailable/);
            }
            assert.deepEqual(errors, []);
            fs.writeFileSync(path.join(output, 'corpus-summary.json'), JSON.stringify({ checked, roles: 5 }, null, 2));
            verifyConsole();
            console.log('PASS retained numerical corpus, one-measure compact SVG values, missing/suppressed/software/ambiguous values, five roles and Unicode labels');
            return;
        }
        if (phase === 'simple-mapping') {
            fs.mkdirSync(output, { recursive: true });
            const headers = { Authorization: `Bearer ${fixture.teacher.access_token}` };
            const base = `${API}/courses/${fixture.course.id}/market-demand`;
            const get = async (endpoint) => { const response = await context.request.get(`${base}/${endpoint}`, { headers }); assert.equal(response.status(), 200); return response.json(); };
            const state = await get('state');
            assert.equal(state.job_search_country, 'Uzbekistan');
            assert.equal(state.job_search_country_confirmed, true);
            assert.deepEqual(state.selected_onet_occupations, ['15-2051.00', '15-1252.00']);
            for (const outcome of Object.values(state.source_outcomes)) {
                assert(Array.isArray(outcome.warnings));
                assert.equal(typeof outcome.received_count, 'number');
                assert.equal(typeof outcome.usable_count, 'number');
            }
            const before = action('sql-readback');
            assert.equal(before.publication_revision, 0);
            assert.equal(before.selected_candidate_ids.length, 57);
            const studentBefore = JSON.parse(fs.readFileSync(path.join(output, 'student-before.json')));
            assert.equal(studentBefore.path.course_id, fixture.course.id);
            assert.equal(studentBefore.path.total_selected_skills, 1);
            assert.equal(studentBefore.path.chapters[0].correct_count, 1);
            await page.goto(`${UI}/courses/${fixture.course.id}/market-analyst`);
            const mapping = page.waitForResponse(r => r.url().endsWith('/chat'));
            action('model-queue', [{ content: 'Synthetic curriculum mapping request completed.' }]);
            await page.getByRole('button', { name: 'Remap skills', exact: true }).click();
            const response = await mapping;
            assert.equal(response.status(), 200, await response.text());
            await response.finished();
            requireCompletedMapping(await response.text());
            await verifyBeforePreparation(base, headers, before);
            await page.getByText('Synthetic curriculum mapping request completed.', { exact: true }).waitFor();
            const prepared = action('prepare-review');
            await page.reload();
            const integration = page.getByRole('region', { name: 'Final integration review', exact: true });
            await integration.waitFor();
            const measured = [];
            for (const [width, height] of [[1280, 720], [1440, 900]]) {
                await page.setViewportSize({ width, height });
                const main = await page.getByRole('main').evaluate(e => ({ client: e.clientHeight, scroll: e.scrollHeight }));
                const decision = await page.getByLabel('Current teacher decision', { exact: true }).boundingBox();
                const action = await integration.getByRole('button', { name: 'Approve and publish', exact: true }).boundingBox();
                assert(main.scroll <= main.client + 1);
                assert(decision.y + decision.height <= height);
                assert(action.y + action.height <= height);
                measured.push({ width, height, main, action });
                await page.screenshot({ path: path.join(output, `curriculum-${width}.png`), fullPage: true });
            }
            assert.equal(action('sql-readback').publication_revision, 0);
            const approvedResponse = page.waitForResponse(r => r.url().endsWith('/integration-approval'));
            await integration.getByRole('button', { name: 'Approve and publish', exact: true }).click();
            const approved = await approvedResponse;
            assert.equal(approved.status(), 200);
            assert.equal((await approved.json()).projection_status, 'projected');
            assert.deepEqual(approved.request().postDataJSON().approved_candidate_ids, before.selected_candidate_ids);
            const sql = action('sql-readback');
            assert.equal(sql.publication_revision, 1);
            assert.equal(sql.approvals.length, 1);
            assert.equal(sql.approvals[0].review_digest, prepared.integration_review.review_digest);
            assert.equal(sql.approvals[0].items.length, 57);
            for (const item of sql.approvals[0].items)
                assert.equal(item.qualifying_posting_links.length, 4);
            const repeat = await context.request.post(`${base}/integration-approval`, { headers, data: approved.request().postDataJSON() });
            assert.equal(repeat.status(), 200);
            assert.equal(action('sql-readback').approvals.length, 1);
            assert.equal((await get('skill-review')).candidates.find(c => c.display_name === 'ETL / ELT').evidence_references.length, 8);
            const studentAfter = {};
            for (const [name, endpoint] of Object.entries({ path: 'path', quiz: 'chapters/1/quiz', reading: `readings/${fixture.student_reading_id}/content` })) {
                const response = await context.request.get(`${API}/student-learning-path/${fixture.course.id}/${endpoint}`, { headers: { Authorization: `Bearer ${fixture.student.access_token}` } });
                assert.equal(response.status(), 200);
                studentAfter[name] = await response.json();
            }
            assert.deepEqual(studentAfter, studentBefore);
            const archive = path.join(path.dirname(manifestPath), 'published-simple-manifest.json');
            execFileSync('/Applications/Docker.app/Contents/Resources/bin/docker', ['cp', `${backendContainer}:${fixtureManifest}`, archive]);
            fs.chmodSync(archive, 0o600);
            fs.writeFileSync(path.join(path.dirname(manifestPath), 'approval-student-readback.json'), JSON.stringify({ sql, afterStudent: studentAfter }, null, 2));
            fs.writeFileSync(path.join(output, 'mapping-summary.json'), JSON.stringify({ course: fixture.course.id, mappingStatus: 200, selected: 57, publicationRevision: 1, studentPreserved: true, measured }, null, 2));
            await page.screenshot({ path: path.join(output, 'approved-disposable-fixture.png'), fullPage: true });
            verifyConsole();
            console.log('PASS corrected state DTOs, mapping200, explicit57-ID/digest approval, idempotency, complete ETL provenance and nonempty student preservation');
            return;
        }
        if (phase === 'simple-keyboard') {
            await page.goto(`${UI}/courses/${fixture.course.id}/market-analyst`);
            await verifyInspectionFocus();
            console.log('PASS main SQL/ETL and Browse-to-inspect keyboard focus without stacked dialogs');
            return;
        }
        if (phase === 'simple-layout') {
            fs.mkdirSync(output, { recursive: true });
            const seeded = action('seed-simple-flow');
            fixtureManifest = '/tmp/teacher-workspace-simple.json';
            await page.goto(`${UI}/courses/${seeded.course.id}/market-analyst`);
            const skills = page.getByRole('region', { name: 'Choose skills', exact: true });
            await skills.waitFor();
            await verifyInspectionFocus();
            const checked = [];
            for (const [width, height] of [[320, 667], [390, 844], [1280, 720], [1440, 900]]) {
                await page.setViewportSize({ width, height });
                const main = await page.getByRole('main').evaluate(e => ({ client: e.clientHeight, scroll: e.scrollHeight, width: e.clientWidth, content: e.scrollWidth }));
                assert(main.content <= main.width + 1);
                if (width >= 1280)
                    assert(main.scroll <= main.client + 1);
                const action = page.getByRole('button', { name: 'Acknowledge available evidence', exact: true });
                const prompt = page.getByRole('alert').filter({ hasText: 'Some job evidence is incomplete.' }).locator('p');
                const p = await prompt.boundingBox(), a = await action.boundingBox();
                if (width < 640) {
                    assert(p.width >= 200);
                    assert(a.y >= p.y + p.height);
                }
                await action.scrollIntoViewIfNeeded();
                const reached = await action.boundingBox();
                assert(reached.y + reached.height <= height);
                await page.screenshot({ path: path.join(output, `review-layout-${width}.png`), fullPage: true });
                await skills.getByRole('button', { name: 'Browse skills', exact: true }).click();
                const dialog = page.getByRole('dialog', { name: 'Browse skills', exact: true });
                const d = await dialog.evaluate(e => ({ client: e.clientWidth, scroll: e.scrollWidth }));
                assert(d.scroll <= d.client + 1, `Browse ${width}: ${JSON.stringify(d)}`);
                await dialog.getByRole('button', { name: 'Next page', exact: true }).click();
                for (const name of ['Previous page', 'Next page']) {
                    const button = dialog.getByRole('button', { name, exact: true });
                    await button.scrollIntoViewIfNeeded();
                    const b = await button.boundingBox(), box = await dialog.boundingBox();
                    assert(b.x >= box.x && b.x + b.width <= box.x + box.width);
                }
                assert.equal(await dialog.getByRole('checkbox', { name: /^Select Synthetic competency/ }).count(), 10);
                await page.screenshot({ path: path.join(output, `review-browse-${width}.png`), fullPage: true });
                await dialog.getByRole('button', { name: 'Previous page', exact: true }).click();
                await page.keyboard.press('Escape');
                checked.push({ width, height, main, browse: d, promptWidth: p.width });
            }
            await skills.getByRole('button', { name: 'Inspect ETL / ELT', exact: true }).click();
            let evidence = page.getByRole('dialog', { name: 'Evidence for ETL / ELT', exact: true });
            await page.waitForFunction(() => [...document.querySelectorAll('[role=dialog] button')].filter(e => e.textContent === 'Reload full posting evidence').length === 4);
            const links = evidence.getByRole('link', { name: /^Original posting ·/ });
            assert.equal(await links.count(), 4);
            const labels = await links.allTextContents();
            assert(labels.every(label => label.includes('SYNTHETIC')));
            assert.equal(new Set(await links.evaluateAll(elements => elements.map(e => e.href))).size, 4);
            assert.equal(await evidence.locator('blockquote').count(), 8);
            await page.screenshot({ path: path.join(output, 'review-posting-identities.png'), fullPage: true });
            await page.keyboard.press('Escape');
            action('purge-first-posting', undefined, ['--snapshot-id', seeded.snapshot_ids[0]]);
            await skills.getByRole('button', { name: 'Inspect ETL / ELT', exact: true }).click();
            evidence = page.getByRole('dialog', { name: 'Evidence for ETL / ELT', exact: true });
            await evidence.getByText(/Posting content unavailable: purged/).waitFor();
            const purged = evidence.getByRole('article').filter({ hasText: 'Posting content unavailable: purged' });
            assert.match(await purged.getByRole('link', { name: /^Original posting ·/ }).innerText(), /^Original posting · Posting /);
            assert.equal(await purged.locator('blockquote, details').count(), 0);
            await page.screenshot({ path: path.join(output, 'review-purged-identity.png'), fullPage: true });
            verifyConsole();
            fs.writeFileSync(path.join(output, 'review-layout-summary.json'), JSON.stringify({ checked, postingLabels: labels, purgeWithholdsContent: true }, null, 2));
            console.log('PASS narrow/mobile coverage stack, complete Browse bounds and pagination, descriptive posting identities and purged fallback');
            return;
        }
        throw new Error(`Unknown acceptance scenario: ${phase}`);
    }
    catch (error) {
        fs.mkdirSync(output, { recursive: true });
        const receiptPath = path.join(output, 'skill-priority-summary.json');
        if (phase === 'skill-priority' && fs.existsSync(receiptPath)) {
            const receipt = JSON.parse(fs.readFileSync(receiptPath));
            fs.writeFileSync(receiptPath, JSON.stringify({ ...receipt, status: 'failed', error: safeError(error) }, null, 2));
        }
        await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true });
        fs.writeFileSync(path.join(output, 'failure.json'), JSON.stringify({ error: safeError(error), runtimeErrors: errors, mutations, url: page.url() }, null, 2));
        throw error;
    }
    finally {
        await context.request.dispose();
        await context.close();
        await browser.close();
    }
})().catch(error => { console.error(safeError(error.stack ?? error)); process.exitCode = 1; });
