async page => {
  // Phase 9 real-browser walkthrough: every major area, checkpoint screenshots (initial → interaction → result → error),
  // and on-screen figures compared with the API that produced them. Screenshots: docs/phase8-screenshots/p9-*.png
  const R = { checks: [], consoleErrors: [], failed: [], shots: [] };
  const ok = (name, pass, info = '') => R.checks.push({ name, pass: !!pass, info: String(info).slice(0, 220) });
  const reqs = [];
  page.on('console', m => { if (m.type() === 'error' && !/401 \(Unauthorized\)|422 \(Unprocessable|404 \(Not Found\)/.test(m.text())) R.consoleErrors.push(m.text().slice(0, 200)); });
  page.on('pageerror', e => R.consoleErrors.push('PAGEERROR ' + e.message.slice(0, 200)));
  page.on('response', r => { const u = new URL(r.url()); if (!u.pathname.startsWith('/api/')) return;
    reqs.push({ m: r.request().method(), p: u.pathname, q: u.search, s: r.status() });
    if (r.status() >= 500) R.failed.push(`${r.status()} ${r.request().method()} ${u.pathname}`); });
  const mark = () => reqs.length;
  const since = (i, m, re) => reqs.slice(i).find(x => x.m === m && re.test(x.p + x.q));
  const base = 'http://localhost:5173';
  const dir = '/Users/adityakhanna/Developer/finora/docs/phase8-screenshots/';
  const shot = async (name, full = false) => { await page.screenshot({ path: dir + 'p9-' + name + '.png', fullPage: full }); R.shots.push('p9-' + name + '.png'); };
  const api = async (path) => page.evaluate(async (p) => (await fetch(p, { credentials: 'include' })).json(), '/api' + path);
  const wait = (ms) => page.waitForTimeout(ms);
  const panel = () => page.locator('main').innerText();
  // every rupee figure on screen, in rupees (₹4,28,400 · ₹4.28 L · ₹1.2 Cr · −₹5,000)
  const rupees = (t) => [...t.matchAll(/₹\s?([\d,]+(?:\.\d+)?)\s*(L|Cr|K)?\b/g)].map(m => Number(m[1].replace(/,/g, '')) * ({ L: 1e5, Cr: 1e7, K: 1e3 }[m[2]] || 1));
  const shows = (t, v, tol = 0.006) => rupees(t).some(x => Math.abs(x - Math.abs(v)) <= Math.max(1, Math.abs(v) * tol));
  const section = async (name, fn) => { try { await fn() } catch (e) { ok(name + ' (section)', false, e.message.split('\n')[0]) } };

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.context().clearCookies();
  const email = 'p9-walk-' + Date.now() + '@finora.test', pw = 'Walk-Pass-' + Math.random().toString(36).slice(2, 8) + '9!';
  let pid, priv;

  await section('sign-in and registration', async () => {
    await page.goto(base + '/'); await page.getByRole('heading', { name: /sign in to finora/i }).waitFor({ timeout: 15000 });
    await shot('01-sign-in');
    await page.getByRole('button', { name: /^sign in/i }).click();
    ok('sign-in validation error shown', await page.getByText(/enter an e-mail address/i).isVisible());
    await shot('02-sign-in-validation-error');
    await page.getByRole('button', { name: /create an account/i }).click();
    await page.getByLabel('Name (optional)').fill('Walk Through');
    await page.getByLabel('E-mail').fill(email); await page.getByLabel('Password', { exact: true }).fill(pw);
    await shot('03-registration-filled');
    await page.getByRole('button', { name: /^create account/i }).click();
    await page.getByRole('heading', { name: /welcome, walk/i }).waitFor({ timeout: 15000 });
    ok('registration → onboarding Start screen', true);
    await shot('04-onboarding-start');
  });

  await section('home', async () => {
    await page.getByRole('button', { name: /aarav mehta/i }).click();
    await page.getByRole('heading', { name: /good to see you/i }).waitFor({ timeout: 60000 }); await wait(1500);
    pid = (await api('/profiles')).find(p => p.kind === 'sandbox').internal_id;
    ok('demo copy opened on Home', /^SB_/.test(pid), pid);
    await shot('05-home');
  });
  const A = await api(`/profiles/${pid}/analysis`);

  await section('plan', async () => {
    await page.goto(base + '/plan'); await page.locator('[role=tabpanel]').waitFor(); await wait(1500);
    ok('Plan priorities render', (await panel()).length > 200);
    await shot('06-plan-priorities');
  });

  await section('goals', async () => {
    await page.goto(base + '/plan?tab=goals'); await wait(2500);
    await shot('07-goals-initial');
    const t = await panel();
    const g = A.goals?.[0];
    if (g) ok('Goals: on-screen monthly figures equal the API (7% and 0%)', shows(t, g.monthly_needed_at_7pct, 0.01) && shows(t, g.monthly_needed, 0.01), `${g.name}: ${g.monthly_needed_at_7pct} / ${g.monthly_needed}`);
    await page.getByRole('button', { name: /^Add$/ }).click();
    const d = page.getByRole('dialog'); await d.waitFor();
    await d.getByLabel(/^name/i).fill('Walkthrough goal');
    await d.getByLabel(/^target \(₹\)/i).fill('240000');
    await d.getByLabel(/^target date/i).fill('2020-01-01');
    await d.getByRole('button', { name: /^save/i }).click(); await wait(1500);
    ok('Goals: past target date shows a validation error', /future/i.test(await d.innerText()));
    await shot('08-goals-validation-error');
    await d.getByLabel(/target date/i).fill('2027-10-31');
    await shot('09-goals-add-drawer');
    const i = mark();
    await d.getByRole('button', { name: /^save/i }).click(); await wait(3500);
    ok('Goals: goal created (POST 201)', since(i, 'POST', /records\/goals$/)?.s === 201);
    const g2 = (await api(`/profiles/${pid}/analysis`)).goals.find(x => x.name === 'Walkthrough goal');
    const t2 = await panel();
    ok('Goals: new goal\'s monthly figures on screen equal the API', g2 && shows(t2, g2.monthly_needed_at_7pct, 0.01) && shows(t2, g2.monthly_needed, 0.01), g2 && `${g2.monthly_needed_at_7pct} / ${g2.monthly_needed} over ${g2.months_left} months`);
    await shot('10-goals-result');
  });

  await section('money', async () => {
    await page.goto(base + '/money'); await wait(2500);
    ok('Money overview shows the API net worth', shows(await panel(), A.net_worth.net_worth, 0.006), A.net_worth.net_worth);
    await shot('11-money-overview');
    await page.goto(base + '/money?tab=accounts'); await wait(2000);
    const acc = await api(`/profiles/${pid}/accounts`);
    const t = await panel();
    ok('Accounts: every bank balance on screen equals the API', acc.accounts.every(a => shows(t, a.balance, 0.006)), acc.accounts.map(a => a.balance).join(','));
    await shot('12-accounts');
    await page.goto(base + '/money?tab=transactions'); await wait(2000);
    await page.getByLabel('Search').fill('Haldiram'); await wait(1500);
    await shot('13-transactions-search');
    await page.locator('tbody tr').first().click(); await page.getByRole('dialog').waitFor();
    await shot('14-transaction-drawer');
    await page.keyboard.press('Escape');
    await page.goto(base + '/money?tab=spending'); await wait(2000); await shot('15-spending');
    await page.goto(base + '/money?tab=investments'); await wait(2000);
    ok('Investments: current value equals the API', shows(await panel(), A.investments.current_value ?? A.investments.total_current_value ?? 0, 0.006), A.investments.current_value);
    await shot('16-investments');
  });

  await section('debts', async () => {
    await page.goto(base + '/money?tab=debts'); await wait(3000);
    const p = await page.evaluate(async (u) => (await fetch(u, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': document.cookie.match(/csrf[^=]*=([^;]+)/)?.[1] || '' }, body: '{}' })).json(), `/api/profiles/${pid}/payoff`);
    const t = await panel();
    if (p.has_debt) ok('Debts: payoff months on screen equal the API', t.includes(String(p.avalanche.months_to_debt_free)) && p.avalanche.paid_off !== undefined, `${p.avalanche.months_to_debt_free} months, paid_off=${p.avalanche.paid_off}`);
    else ok('Debts: no-debt state', /no debt/i.test(t));
    await shot('17-debts-payoff');
  });

  await section('future', async () => {
    await page.goto(base + '/future?tab=cash-flow'); await wait(2500);
    const f = A.ml.forecast;
    ok('Cash flow: forecast and range on screen equal the API', shows(await panel(), f.predicted_total_expense, 0.006) && shows(await panel(), f.range.low, 0.01) && shows(await panel(), f.range.high, 0.01), `${f.predicted_total_expense} (${f.range.low}–${f.range.high})`);
    await shot('18-cash-flow');
    await page.goto(base + '/future?tab=retirement'); await wait(2500);
    await shot('19-retirement');
    await page.goto(base + '/future?tab=what-if'); await wait(2000);
    await shot('20-what-if-initial');
    await page.getByLabel('Price (₹)').fill('');
    await page.getByRole('button', { name: /should i buy it/i }).click(); await wait(800);
    await shot('21-what-if-validation');
    await page.getByLabel('Price (₹)').fill('900000'); await page.getByLabel('Down payment (₹)').fill('200000');
    const i = mark();
    await page.getByRole('button', { name: /should i buy it/i }).click(); await wait(3500);
    ok('What-if: POST /decision and a verdict shown', since(i, 'POST', /decision$/)?.s === 200 && /affordable|stretch|not advisable/i.test(await panel()));
    await shot('22-what-if-result', true);
  });

  await section('models', async () => {
    await page.goto(base + '/models'); await wait(2500);
    const t = await panel();
    ok('Risk & Models lists all six capabilities with algorithms', ['XGBoost', 'K-Means', 'TF-IDF', 'Isolation Forest', 'Model Lab'].every(x => t.includes(x)));
    await shot('23-models-overview', true);
    await page.goto(base + '/models?tab=credit-risk'); await wait(2500);
    ok('Credit risk: probability on screen equals the API', (await panel()).includes(String(A.ml.credit_risk.overall_default_probability_pct)), A.ml.credit_risk.overall_default_probability_pct);
    await shot('24-credit-risk');
    await page.getByRole('button', { name: /how it works/i }).first().click(); await page.getByRole('dialog').waitFor();
    await shot('25-how-it-works'); await page.keyboard.press('Escape');
    await page.goto(base + '/models?tab=peers'); await wait(2500); await shot('26-peers');
    await page.goto(base + '/models?tab=categoriser'); await wait(2500); await shot('27-categoriser');
    await page.goto(base + '/models?tab=unusual'); await wait(2500);
    ok('Unusual: flagged count on screen equals the API', (await panel()).includes(String(A.ml.anomaly.flagged_count)), A.ml.anomaly.flagged_count);
    await shot('28-unusual');
    await page.goto(base + '/models?tab=lab'); await wait(2500); await shot('29-model-lab', true);
  });

  await section('ask', async () => {
    await page.goto(base + '/ask'); await page.getByRole('heading', { name: /ask anything about money/i }).waitFor({ timeout: 15000 });
    await shot('30-ask-initial');
    await page.getByLabel('Your question').fill('What is my net worth?'); await page.keyboard.press('Enter');
    await page.getByRole('button', { name: /send question/i }).waitFor({ timeout: 120000 }); await wait(500);
    const conv = await page.locator('section[aria-label=Conversation]').innerText();
    ok('Ask: answer states the API net worth', shows(conv, A.net_worth.net_worth, 0.006), conv.slice(-200));
    await shot('31-ask-answer');
    await page.getByLabel('Your question').fill('Which mutual funds should I buy?'); await page.keyboard.press('Enter');
    await page.getByRole('button', { name: /send question/i }).waitFor({ timeout: 120000 }); await wait(500);
    ok('Ask: no specific fund picks', /don't pick individual stocks or funds/.test(await page.locator('section[aria-label=Conversation]').innerText()));
    await shot('32-ask-no-picks');
  });

  await section('data', async () => {
    await page.goto(base + '/data?tab=import'); await wait(2000);
    await shot('33-import-initial');
    await page.locator('input[type=file]').setInputFiles({ name: 'notes.csv', mimeType: 'text/csv', buffer: Buffer.from('Name,Address\nA,B\n') });
    await wait(2500);
    ok('Import: a file without a statement header is refused with a reason', /header row/i.test(await panel()));
    await shot('34-import-error');
    await page.goto(base + '/data?tab=import'); await wait(1500);
    await page.getByRole('button', { name: /try a synthetic sample/i }).click(); await wait(4000);
    await shot('35-import-preview');
    await page.goto(base + '/data?tab=review'); await wait(2500); await shot('36-review');
    await page.goto(base + '/data?tab=records'); await wait(2500); await shot('37-records');
    await page.goto(base + '/data?tab=reports'); await wait(2000);
    const i = mark();
    await page.getByRole('button', { name: /generate pdf/i }).first().click(); await wait(6000);
    ok('Reports: PDF generated (GET report.pdf 200)', since(i, 'GET', /report\.pdf/)?.s === 200);
    await shot('38-reports');
    await page.goto(base + '/data?tab=profile'); await wait(2000); await shot('39-profile-privacy');
    await page.goto(base + '/settings'); await wait(2000); await shot('40-settings');
  });

  await section('logout and isolation', async () => {
    priv = (await page.evaluate(async () => { const r = await fetch('/api/profiles', { method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': document.cookie.match(/csrf[^=]*=([^;]+)/)?.[1] || '' },
      body: JSON.stringify({ name: 'Private Walk', age: 33 }) }); return r.json() })).profile?.internal_id;
    await page.getByRole('button', { name: /account menu|walk through/i }).first().click(); await wait(400);
    await page.getByRole('menuitem', { name: /sign out/i }).click();
    await page.getByRole('heading', { name: /sign in to finora/i }).waitFor({ timeout: 15000 });
    ok('sign out returns to sign-in', true);
    await shot('41-signed-out');
    await page.goto(base + '/money'); await wait(1500);
    ok('protected page after sign-out shows sign-in', await page.getByRole('heading', { name: /sign in to finora/i }).isVisible());
    await page.getByRole('button', { name: /create an account/i }).click();
    await page.getByLabel('E-mail').fill('p9-walk-b-' + Date.now() + '@finora.test'); await page.getByLabel('Password', { exact: true }).fill(pw);
    await page.getByRole('button', { name: /^create account/i }).click(); await page.getByRole('heading', { name: /welcome/i }).waitFor({ timeout: 15000 });
    const st = await page.evaluate(async (id) => [(await fetch(`/api/profiles/${id}`, { credentials: 'include' })).status,
      (await fetch(`/api/profiles/${id}/transactions`, { credentials: 'include' })).status], priv);
    ok('second account: first account\'s private profile is 404', st.every(s => s === 404), JSON.stringify(st));
    const list = (await api('/profiles')).map(p => p.internal_id);
    ok('second account: profile list excludes the first account\'s profiles', !list.includes(priv) && !list.includes(pid));
    await shot('42-second-account-start');
  });

  R.summary = `${R.checks.filter(c => c.pass).length}/${R.checks.length} passed`;
  R.fails = R.checks.filter(c => !c.pass); R.all = R.checks.map(c => `${c.pass ? 'PASS' : 'FAIL'} ${c.name} ${c.info}`);
  R.shotCount = R.shots.length; delete R.checks; delete R.shots;
  return JSON.stringify(R, null, 1);
}
