async page => {
  const R = { checks: [], consoleErrors: [], failed: [] };
  const ok = (name, pass, info = '') => R.checks.push({ name, pass: !!pass, info: String(info).slice(0, 200) });
  const reqs = [];
  page.on('console', m => { if (m.type() === 'error' && !/401 \(Unauthorized\)/.test(m.text())) R.consoleErrors.push(m.text().slice(0, 200)); });
  page.on('pageerror', e => R.consoleErrors.push('PAGEERROR ' + e.message.slice(0, 200)));
  page.on('response', r => { const u = new URL(r.url()); if (!u.pathname.startsWith('/api/')) return;
    reqs.push({ m: r.request().method(), p: u.pathname, q: u.search, s: r.status() });
    if (r.status() >= 400 && !(r.status() === 401 && u.pathname === '/api/auth/me')) R.failed.push(`${r.status()} ${r.request().method()} ${u.pathname}`); });
  const saw = (m, re, s = 200) => reqs.some(x => x.m === m && re.test(x.p + x.q) && x.s === s);
  const mark = () => reqs.length;
  const since = (i, m, re) => reqs.slice(i).find(x => x.m === m && re.test(x.p + x.q));
  const base = 'http://localhost:5173';
  const api = async (path) => page.evaluate(async (p) => (await fetch(p, { credentials: 'include' })).json(), '/api' + path);
  const wait = (ms) => page.waitForTimeout(ms);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.context().clearCookies();
  await page.goto(base + '/');
  await page.getByRole('button', { name: /create an account/i }).click();
  const email = 'p8-func-' + Date.now() + '@finora.test', pw = 'Func-Pass-' + Math.random().toString(36).slice(2, 8) + '9!';
  await page.getByLabel('E-mail').fill(email); await page.getByLabel('Password', { exact: true }).fill(pw);
  await page.getByRole('button', { name: /^create account/i }).click();
  await page.getByRole('button', { name: /aarav mehta/i }).click();
  await page.getByRole('heading', { name: /good to see you/i }).waitFor({ timeout: 60000 });
  const pid = (await api('/profiles')).find(p => p.kind === 'sandbox').internal_id;
  ok('demo sandbox created', /^SB_/.test(pid), pid);

  // ---------------- Transactions: search, sort, pagination, drawer, recategorise + persistence
  try {
  await page.goto(base + '/money?tab=transactions'); await page.getByRole('heading', { name: 'Money' }).waitFor();
  await wait(1500);
  let i = mark();
  await page.getByLabel('Search').fill('Haldiram'); await wait(1500);
  const sreq = since(i, 'GET', /transactions\?.*search=Haldiram/);
  const rows = await page.locator('tbody tr').allInnerTexts();
  ok('search sends ?search= and filters rows', sreq && rows.length > 0 && rows.every(t => /haldiram/i.test(t)), `${rows.length} rows; url q=${/q=Haldiram/.test(page.url())}`);
  await page.getByLabel('Search').fill(''); await wait(1200);
  i = mark();
  await page.getByLabel('Sort').selectOption('amount_desc'); await wait(1200);
  const amts = (await page.locator('tbody tr td:last-child').allInnerTexts()).map(t => Number(t.replace(/[^\d.]/g, '')));
  ok('sort=amount_desc requested and rows descending', since(i, 'GET', /sort=amount_desc/) && amts.length > 3 && amts.every((v, k) => k === 0 || amts[k - 1] >= v), amts.slice(0, 4).join(','));
  i = mark();
  await page.getByRole('button', { name: 'Next' }).click(); await wait(1200);
  ok('pagination requests offset=25 and URL page=2', since(i, 'GET', /offset=25/) && /page=2/.test(page.url()));
  await page.getByLabel('Sort').selectOption('date_desc'); await wait(1200);
  await page.getByLabel('Category').selectOption('Dining'); await wait(1200);
  const first = page.locator('tbody tr').first();
  const merchant = (await first.locator('td').nth(1).innerText()).split('\n')[0];
  await first.click();
  const drawer = page.getByRole('dialog');
  await drawer.waitFor();
  ok('row opens detail drawer', await drawer.getByRole('heading', { name: merchant }).isVisible(), merchant);
  i = mark();
  await drawer.getByLabel('Category').selectOption('Entertainment'); await wait(2500);
  const patched = since(i, 'PATCH', /\/transactions\/\d+$/);
  ok('recategorise sends PATCH 200', patched && patched.s === 200, JSON.stringify(patched));
  const txId = patched?.p.split('/').pop();
  await page.keyboard.press('Escape'); await wait(400);
  ok('Esc closes drawer', !(await page.getByRole('dialog').count()));
  await page.reload(); await wait(2500);
  const persisted = (await api(`/profiles/${pid}/transactions?search=${encodeURIComponent(merchant)}&limit=100`)).items.find(x => String(x.id) === txId);
  ok('category change persists after refresh (API)', persisted?.category === 'Entertainment' && persisted.category_source === 'user', persisted?.category);
  // restore
  await page.evaluate(async ([p, t]) => { const c = document.cookie.split('; ').find(x => x.startsWith('finora_csrf='))?.slice(12) || '';
    await fetch(`/api/profiles/${p}/transactions/${t}`, { method: 'PATCH', credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': decodeURIComponent(c) }, body: JSON.stringify({ category: 'Dining' }) }) }, [pid, txId]);

  } catch (e) { ok('SECTION Transactions: search, sort, pagination, drawer, recategorise + persistence', false, e.message.split('\n')[0]) }
  // ---------------- Add transaction drawer (moved here from Profile & Data)
  try {
  await page.goto(base + '/money?tab=transactions'); await wait(2500);
  await page.getByRole('button', { name: 'Add transaction' }).first().click();
  const ad = page.getByRole('dialog', { name: 'Add a transaction' }); await ad.waitFor();
  await ad.getByLabel('Amount (₹)').fill('432');
  await ad.getByLabel('Description as on the statement').fill('UPI/DR/998877665544/ZOMATO/HDFC/zomato@ybl P8TEST');
  i = mark(); await ad.getByRole('button', { name: 'Add transaction' }).click(); await wait(4000);
  const post = since(i, 'POST', new RegExp(`/profiles/${pid}/transactions$`));
  const found = (await api(`/profiles/${pid}/transactions?search=P8TEST&limit=10`)).items;
  ok('add transaction POST 2xx, categorised, persisted', post && post.s < 300 && found.length === 1 && !!found[0].category, `${post?.s} ${found[0]?.category}/${found[0]?.category_source}`);
  if (found[0]) {
    await page.getByLabel('Search').fill('P8TEST'); await wait(1500);
    await page.locator('tbody tr').first().click(); await page.getByRole('dialog').waitFor();
    await page.getByRole('button', { name: 'Delete transaction' }).click();
    const md = page.getByRole('dialog', { name: /delete this transaction/i }); await md.waitFor();
    i = mark(); await md.getByRole('button', { name: 'Delete transaction' }).click(); await wait(3000);
    ok('delete transaction via confirm modal DELETE 2xx + gone', (since(i, 'DELETE', /transactions\/\d+$/)?.s || 999) < 300 && (await api(`/profiles/${pid}/transactions?search=P8TEST&limit=10`)).items.length === 0);
  }
  } catch (e) { ok('SECTION add transaction', false, e.message.split('\n')[0]) }

  // ---------------- Spending segmented view + filter
  try {
  await page.goto(base + '/money?tab=spending'); await wait(2500);
  await page.getByRole('radio', { name: 'Who I pay' }).click(); await wait(500);
  ok('spending view switch updates URL and content', /view=merchants/.test(page.url()) && await page.getByText('Largest merchants').isVisible());
  i = mark();
  await page.getByLabel('Period').selectOption('3'); await wait(2000);
  ok('period filter requests insights?months=3', !!since(i, 'GET', /insights\?.*months=3/));

  } catch (e) { ok('SECTION Spending segmented view + filter', false, e.message.split('\n')[0]) }
  // ---------------- Plan: accept a recommendation, persists, reopen
  try {
  await page.goto(base + '/plan?tab=actions'); await wait(3000);
  const acc = page.getByRole('button', { name: /^Accept$/ }).first();
  if (await acc.count()) {
    i = mark(); await acc.click(); await wait(1500);
    const pr = since(i, 'PATCH', /recommendations\/\d+$/);
    ok('accept recommendation PATCH 200', pr && pr.s === 200);
    const recs = await api(`/profiles/${pid}/recommendations`);
    ok('accepted status persisted', recs.some(r => r.status === 'accepted'));
    await page.getByRole('radio', { name: 'Accepted' }).click(); await wait(800);
    await page.getByRole('button', { name: /Reopen/ }).first().click(); await wait(1500);
    ok('reopen restores open status', (await api(`/profiles/${pid}/recommendations`)).every(r => r.status !== 'accepted'));
  } else ok('accept recommendation button present', false);

  } catch (e) { ok('SECTION Plan: accept a recommendation, persists, reopen', false, e.message.split('\n')[0]) }
  // ---------------- Tax calculator
  try {
  await page.goto(base + '/plan?tab=tax'); await wait(2000);
  i = mark();
  await page.getByLabel('Gross annual income (₹)').fill('1800000');
  await page.getByRole('button', { name: 'Compare regimes' }).click(); await wait(1500);
  ok('tax compare POST /tax/compare 200', !!since(i, 'POST', /tax\/compare/) && await page.getByText(/costs less/i).isVisible());
  await page.getByLabel('Gross annual income (₹)').fill('');
  await page.getByRole('button', { name: 'Compare regimes' }).click(); await wait(500);
  ok('tax validation message on empty income', await page.getByText(/enter your gross annual income/i).isVisible());

  } catch (e) { ok('SECTION Tax calculator', false, e.message.split('\n')[0]) }
  // ---------------- Goals: add via drawer, persists, delete via confirm modal
  try {
  await page.goto(base + '/plan?tab=goals'); await wait(2500);
  const beforeGoals = (await api(`/profiles/${pid}/records/goals`)).items.length;
  await page.getByRole('button', { name: /^Add$/ }).click();
  const gd = page.getByRole('dialog'); await gd.waitFor();
  const inputs = gd.locator('input:not([type=checkbox]), select');
  const n = await inputs.count();
  for (let k = 0; k < n; k++) {
    const el = inputs.nth(k); const type = await el.getAttribute('type'); const tag = await el.evaluate(e => e.tagName);
    if (tag === 'SELECT') { const opts = await el.locator('option').allInnerTexts(); if (opts.length > 1) await el.selectOption({ index: 1 }); continue; }
    if (type === 'date') await el.fill('2030-06-30'); else if (type === 'number') await el.fill(k === 1 ? '500000' : '100000'); else await el.fill('Phase 8 test goal');
  }
  i = mark();
  await gd.getByRole('button', { name: /save/i }).click(); await wait(4000);
  const created = since(i, 'POST', /records\/goals$/);
  const afterGoals = (await api(`/profiles/${pid}/records/goals`)).items;
  ok('add goal POST 2xx + persisted', created?.s >= 200 && created?.s < 300 && afterGoals.length === beforeGoals + 1, `status ${created?.s}`);
  const g = afterGoals.find(x => /Phase 8 test goal/.test(x._title || x.name || ''));
  if (g) {
    // edit: change the target amount; the backend recalculates the monthly figure; persists after refresh
    const before = (await api(`/profiles/${pid}/analysis`)).goals.find(x => /Phase 8 test goal/.test(x.name));
    await page.getByRole('button', { name: new RegExp('Edit ' + (g._title || 'Phase 8 test goal')) }).click();
    const ed = page.getByRole('dialog'); await ed.waitFor();
    const amt = ed.getByLabel(/^Target \(₹\)/);
    await amt.fill(String(Math.round((before?.target || 500000) * 2)));
    i = mark(); await ed.getByRole('button', { name: /save changes/i }).click(); await wait(4500);
    await page.reload(); await wait(3000);
    const after = (await api(`/profiles/${pid}/analysis`)).goals.find(x => /Phase 8 test goal/.test(x.name));
    ok('edit goal PATCH 2xx, target doubled, monthly need recalculated, persisted', (since(i, 'PATCH', /records\/goals\/\d+/)?.s || 999) < 300 && after && after.target === Math.round((before?.target || 500000) * 2) && after.monthly_needed > before.monthly_needed,
      `${before?.target}->${after?.target} need ${before?.monthly_needed}->${after?.monthly_needed}`);
    ok('goal progress shown on Plan → Goals', await page.getByText(/7% assumed growth/).first().isVisible());
    await page.getByRole('button', { name: new RegExp('Delete ' + (g._title || 'Phase 8 test goal')) }).click();
    const md = page.getByRole('dialog'); await md.waitFor();
    ok('delete asks in an accessible modal', await md.getByRole('heading', { name: /delete/i }).isVisible());
    i = mark(); await md.getByRole('button', { name: /^Delete$/ }).click(); await wait(3500);
    ok('delete goal DELETE 2xx + gone', (since(i, 'DELETE', /records\/goals\/\d+/)?.s || 0) < 300 && (await api(`/profiles/${pid}/records/goals`)).items.length === beforeGoals);
  }

  } catch (e) { ok('SECTION Goals: add via drawer, persists, delete via confirm modal', false, e.message.split('\n')[0]) }
  // ---------------- Future: what-if decision, retirement inputs, debts payoff
  try {
  await page.goto(base + '/future?tab=what-if'); await wait(2000);
  i = mark(); await page.getByRole('button', { name: /should i buy it/i }).click(); await wait(2500);
  ok('decision simulator POST /decision 200', since(i, 'POST', /\/decision$/)?.s === 200);
  await page.goto(base + '/future?tab=retirement'); await wait(2500);
  i = mark(); const num = page.locator('[role=tabpanel] input[type=number], [role=tabpanel] input[type=range]').first();
  if (await num.count()) { await num.focus(); await page.keyboard.press('ArrowUp'); await wait(1500); }
  ok('retirement input change POST /fire', !!since(i, 'POST', /\/fire$/));
  await page.goto(base + '/money?tab=debts'); await wait(2500);
  ok('debts payoff simulation POST /payoff', saw('POST', /\/payoff$/));

  } catch (e) { ok('SECTION Future: what-if decision, retirement inputs, debts payoff', false, e.message.split('\n')[0]) }
  // ---------------- Risk & Models: credit score form, categoriser try, lab deep link
  try {
  await page.goto(base + '/models?tab=credit-risk'); await wait(2500);
  i = mark(); await page.getByRole('button', { name: 'Score with the model' }).click(); await wait(2500);
  ok('credit-risk score POST 200 + result', since(i, 'POST', /credit-risk\/score/)?.s === 200 && await page.getByText(/test ROC-AUC/).isVisible());
  await page.goto(base + '/models?tab=categoriser'); await wait(2500);
  i = mark(); await page.getByRole('button', { name: /^Categorise$/ }).click(); await wait(2000);
  ok('categoriser try POST /categorise 200', since(i, 'POST', /\/categorise$/)?.s === 200 && (await page.getByText(/confident|bank rule/).count()) > 0);
  await page.goto(base + '/models?tab=lab&model=forecast'); await wait(3000);
  ok('Model Lab ?model= opens that model', await page.locator('#model-body-forecast').isVisible());

  } catch (e) { ok('SECTION Risk & Models: credit score form, categoriser try, lab deep link', false, e.message.split('\n')[0]) }
  // ---------------- the six ML capabilities: identity, algorithm, explanation, real data
  try {
  const MODELS = [['/models?tab=credit-risk', 'XGBoost + SHAP', /payment/i], ['/models?tab=peers', 'K-Means clustering', /closest to/i], ['/models?tab=categoriser', 'TF-IDF \\+ logistic regression', /suggest/i],
    ['/models?tab=unusual', 'Isolation Forest', /look unusual|unusual for you/i], ['/future?tab=cash-flow', 'XGBoost regression', /likely to spend/i]];
  for (const [url, algo, answer] of MODELS) {
    await page.goto(base + url); await wait(2500);
    const chip = await page.getByText('Model: ' + algo.replace(/\\/g, ''), { exact: false }).first().isVisible().catch(() => false);
    await page.getByRole('button', { name: 'How it works' }).first().click();
    const dr = page.getByRole('dialog'); const open = await dr.isVisible().catch(() => false);
    const txt = open ? await dr.innerText() : '';
    await page.keyboard.press('Escape'); await wait(300);
    ok(`model ${algo.replace(/\\/g, '')}: identity chip, explainer, answer`, chip && /What it looks at/.test(txt) && /How it works/.test(txt) && answer.test(await page.locator('[role=tabpanel]').innerText()), url);
  }
  await page.goto(base + '/models'); await wait(2500);
  const ov = await page.locator('[role=tabpanel]').innerText();
  ok('overview lists all six capabilities with algorithms', ['Credit Risk', 'Peer Benchmarking', 'Transaction Categoriser', 'Anomaly Detection Scanner', 'Cash-Flow Forecast', 'Model Lab'].every(n => ov.includes(n))
    && ['XGBoost + SHAP', 'K-Means', 'TF-IDF', 'Isolation Forest', 'XGBoost regression'].every(n => ov.includes(n)));
  const ui = (await page.locator('body').innerText()).toLowerCase();
  ok('no development-stage or academic wording on Risk & Models', !/experimental|human-validated|acceptance criteria|academic|educational|licensed/.test(ui));
  } catch (e) { ok('SECTION models', false, e.message.split('\n')[0]) }

  // ---------------- Data: import synthetic sample end-to-end
  try {
  await page.goto(base + '/data?tab=import'); await wait(2000);
  i = mark(); await page.getByRole('button', { name: /try a synthetic sample/i }).click();
  await page.waitForTimeout(4000);
  ok('import preview POST /imports 2xx', (since(i, 'POST', /\/imports$/)?.s || 0) < 300 && since(i, 'POST', /\/imports$/)?.s >= 200);
  const startBtn = page.getByRole('button', { name: /^(Import|Start import)/i }).first();
  const target = page.locator('[role=tabpanel] select').first();
  if (await target.count()) { const opts = await target.locator('option').evaluateAll(os => os.map(o => o.value).filter(Boolean)); if (opts.length) await target.selectOption(opts[0]); }
  const sb = await startBtn.count() ? startBtn : page.getByRole('button', { name: /import \d|import rows|import this/i }).first();
  ok('import start button present', await sb.count(), await page.locator('[role=tabpanel]').innerText().then(t => t.slice(0, 160)));
  if (await sb.count()) {
    i = mark(); await sb.click();
    await page.getByText(/imported|done|added/i).first().waitFor({ timeout: 120000 }).catch(() => {});
    await wait(2000);
    const st = since(i, 'POST', /imports\/\d+\/start/);
    const hist = await api(`/profiles/${pid}/imports`);
    const last = (hist.items || [])[0];
    ok('import completes (backend status done)', st?.s >= 200 && st?.s < 300 && last?.status === 'done', `${st?.s} ${last?.status}`);
    if (last?.status === 'done') {
      const undoBtn = page.getByRole('button', { name: /undo this import/i });
      if (await undoBtn.count()) { await undoBtn.click(); const md = page.getByRole('dialog'); await md.waitFor();
        i = mark(); await md.getByRole('button', { name: /undo import/i }).click(); await wait(4000);
        ok('undo import via modal DELETE 2xx', (since(i, 'DELETE', /imports\/\d+$/)?.s || 999) < 300); }
    }
  }

  } catch (e) { ok('SECTION Data: import synthetic sample end-to-end', false, e.message.split('\n')[0]) }
  // ---------------- Settings: edit profile persists; activity loads
  try {
  await page.goto(base + '/settings?tab=profiles'); await wait(2000);
  await page.getByRole('button', { name: 'Edit details' }).click();
  await page.getByLabel('City').fill('Udaipur');
  i = mark(); await page.getByRole('button', { name: 'Save details' }).click(); await wait(5000);
  ok('profile edit PATCH 200', since(i, 'PATCH', new RegExp(`/profiles/${pid}$`))?.s === 200);
  await page.reload(); await wait(3000);
  ok('profile edit persists after refresh', (await api(`/profiles/${pid}`)).city === 'Udaipur' && await page.getByText('Udaipur').first().isVisible());
  await page.goto(base + '/settings?tab=security'); await wait(2000);
  ok('security activity loads from /auth/activity', saw('GET', /auth\/activity/) && (await page.locator('tbody tr').count()) > 0);
  await page.goto(base + '/settings?tab=account'); await wait(800);
  ok('settings shows unavailable capabilities honestly', await page.getByText(/no endpoint for it yet/i).isVisible());

  } catch (e) { ok('SECTION Settings: edit profile persists; activity loads', false, e.message.split('\n')[0]) }
  R.summary = `${R.checks.filter(c => c.pass).length}/${R.checks.length} passed`;
  R.fails = R.checks.filter(c => !c.pass);
  R.passed = R.checks.filter(c => c.pass).map(c => c.name);
  R.account = email; R.profile = pid;
  delete R.checks;
  return JSON.stringify(R, null, 1);
}
