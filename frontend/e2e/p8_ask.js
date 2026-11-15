async page => {
  const R = { checks: [], consoleErrors: [], failed: [] };
  const ok = (name, pass, info = '') => R.checks.push({ name, pass: !!pass, info: String(info).slice(0, 220) });
  const reqs = [];
  page.on('console', m => { if (m.type() === 'error' && !/401 \(Unauthorized\)|500 \(Internal Server Error\)/.test(m.text())) R.consoleErrors.push(m.text().slice(0, 200)); });
  page.on('pageerror', e => R.consoleErrors.push('PAGEERROR ' + e.message.slice(0, 200)));
  page.on('response', r => { const u = new URL(r.url()); if (u.pathname.startsWith('/api/')) reqs.push({ m: r.request().method(), p: u.pathname, s: r.status() }); });
  const base = 'http://localhost:5173';
  const wait = (ms) => page.waitForTimeout(ms);
  const api = async (path) => page.evaluate(async (p) => (await fetch(p, { credentials: 'include' })).json(), '/api' + path);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.context().clearCookies();
  await page.goto(base + '/');
  await page.getByRole('button', { name: /create an account/i }).click();
  await page.getByLabel('E-mail').fill('p8-ask-' + Date.now() + '@finora.test'); await page.getByLabel('Password', { exact: true }).fill('Ask-Pass-' + Date.now() + '!');
  await page.getByRole('button', { name: /^create account/i }).click();
  await page.getByRole('button', { name: /aarav mehta/i }).click();
  await page.getByRole('heading', { name: /good to see you/i }).waitFor({ timeout: 60000 });
  const pid = (await api('/profiles')).find(p => p.kind === 'sandbox').internal_id;

  try {
  // 1. Ask page: suggestion → streaming stages → final checked answer
  await page.goto(base + '/ask'); await page.getByRole('heading', { name: /ask anything about money/i }).waitFor({ timeout: 15000 });
  ok('Ask empty state with suggestions', (await page.getByRole('button', { name: /dining last month/i }).count()) === 1);
  const stages = new Set();
  const poll = setInterval(async () => { try { const t = await page.locator('section[aria-label=Conversation]').innerText(); for (const s of ['Understanding your question', 'Fetching your data', 'Writing the answer', 'Correcting the draft', 'Draft, being checked']) if (t.includes(s)) stages.add(s) } catch {} }, 150);
  await page.getByRole('button', { name: /how much did i spend on dining last month/i }).click();
  ok('Stop button appears while streaming', await page.getByRole('button', { name: /stop answering/i }).isVisible({ timeout: 5000 }).catch(() => false));
  await page.getByRole('button', { name: /send question/i }).waitFor({ timeout: 120000 });
  clearInterval(poll);
  const conv = await page.locator('section[aria-label=Conversation]').innerText();
  ok('progress stages were shown while streaming', stages.has('Understanding your question') && stages.size >= 2, [...stages].join(' > '));
  ok('final answer has ₹ figure, interpretation and checked badge', /₹\s?[\d,]+/.test(conv) && /Understood as:/.test(conv) && /Figures checked/.test(conv), conv.slice(-260));
  ok('stream request used /chat/stream', reqs.some(r => r.m === 'POST' && /chat\/stream$/.test(r.p) && r.s === 200));
  // 2. follow-up keeps context
  await page.getByLabel('Your question').fill('What about the month before?');
  await page.keyboard.press('Enter');
  await page.getByRole('button', { name: /stop answering/i }).waitFor({ timeout: 5000 }).catch(() => {});
  await page.getByRole('button', { name: /send question/i }).waitFor({ timeout: 120000 });
  const conv2 = await page.locator('section[aria-label=Conversation]').innerText();
  const last = conv2.split('What about the month before?').pop();
  ok('follow-up answered in context (Dining, earlier month)', /dining/i.test(last) && /₹/.test(last), last.slice(0, 200));
  // 3. Stop: nothing saved
  const before = (await api(`/profiles/${pid}/chat`)).length;
  await page.getByLabel('Your question').fill('Give me a detailed overview of my finances and net worth.');
  await page.keyboard.press('Enter');
  await wait(1200); await page.keyboard.press('Escape'); await wait(1500);
  const conv3 = await page.locator('section[aria-label=Conversation]').innerText();
  ok('Esc stops: "Nothing from this answer was saved"', /Stopped\. Nothing from this answer was saved/.test(conv3));
  await wait(8000);
  const after = (await api(`/profiles/${pid}/chat`)).length;
  ok('stopped answer not persisted (server count unchanged)', after === before, `${before} → ${after}`);
  // 4. history after reload
  await page.reload(); await wait(3000);
  const conv4 = await page.locator('section[aria-label=Conversation]').innerText();
  ok('history reloads (2 Q&A, no stopped answer)', after === 4 && /dining last month/i.test(conv4) && /month before/i.test(conv4) && !/detailed overview/.test(conv4), `messages=${after}`);
  // 5. error handling (simulated backend failure)
  await page.route('**/chat/stream', (r) => r.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Simulated failure for testing' }) }));
  await page.getByLabel('Your question').fill('Test error'); await page.keyboard.press('Enter'); await wait(1500);
  ok('backend error shown clearly, input usable again', /I could not answer that: Simulated failure/.test(await page.locator('section[aria-label=Conversation]').innerText()) && await page.getByLabel('Your question').isEnabled());
  await page.unroute('**/chat/stream');
  // 6. panel from header + Ask about this prefill (not sent)
  await page.goto(base + '/money?tab=overview'); await wait(2000);
  await page.getByRole('button', { name: 'Ask Finora' }).click(); await page.locator('div#ask-panel').getByText(/dining/i).first().waitFor({ timeout: 15000 }).catch(() => {});
  ok('header Ask opens panel with history', await page.locator('div#ask-panel').isVisible() && /dining/i.test(await page.locator('div#ask-panel').innerText()));
  await page.getByRole('button', { name: /close ask panel/i }).click();
  await page.goto(base + '/'); await wait(2500);
  const n0 = reqs.filter(r => /chat\/stream/.test(r.p)).length;
  await page.getByRole('button', { name: /ask about this/i }).first().click(); await wait(800);
  const val = await page.locator('#ask-panel textarea').inputValue();
  ok('"Ask about this" pre-fills, does not send', /Explain this finding/.test(val) && reqs.filter(r => /chat\/stream/.test(r.p)).length === n0, val);
  } catch (e) { ok('SECTION', false, e.message.split('\n')[0]) }
  R.summary = `${R.checks.filter(c => c.pass).length}/${R.checks.length} passed`;
  R.fails = R.checks.filter(c => !c.pass); R.all = R.checks.map(c => `${c.pass ? 'PASS' : 'FAIL'} ${c.name} ${c.info}`);
  delete R.checks;
  return JSON.stringify(R, null, 1);
}
