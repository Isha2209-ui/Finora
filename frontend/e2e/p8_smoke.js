async page => {
  const R = { checks: [], consoleErrors: [], failed: [] };
  const ok = (name, pass, info = '') => R.checks.push({ name, pass: !!pass, info: String(info).slice(0, 160) });
  page.on('console', m => { if (m.type() === 'error' && !/401 \(Unauthorized\)/.test(m.text())) R.consoleErrors.push(m.text().slice(0, 200)); });
  page.on('pageerror', e => R.consoleErrors.push('PAGEERROR ' + e.message.slice(0, 200)));
  page.on('response', r => { const u = new URL(r.url()); if (u.pathname.startsWith('/api/') && r.status() >= 400 && !(r.status() === 401 && u.pathname === '/api/auth/me') && !(u.pathname === '/api/auth/login' && r.status() === 401))
    R.failed.push(`${r.status()} ${r.request().method()} ${u.pathname}`); });
  const base = 'http://localhost:5173';
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.context().clearCookies();
  await page.goto(base + '/');
  await page.getByRole('heading', { name: /sign in to finora/i }).waitFor({ timeout: 15000 });
  ok('sign-in page renders', true);
  // client validation
  await page.getByRole('button', { name: /^sign in/i }).click();
  ok('empty submit shows inline e-mail error', await page.getByText(/enter an e-mail address/i).isVisible());
  await page.getByLabel('E-mail').fill('nobody-' + Date.now() + '@finora.test');
  await page.getByLabel('Password', { exact: true }).fill('wrong-password-123');
  await page.getByRole('button', { name: /^sign in/i }).click();
  await page.getByRole('alert').filter({ hasText: /invalid|incorrect|wrong|not match/i }).first().waitFor({ timeout: 8000 }).catch(() => {});
  ok('invalid credentials show server error', await page.getByRole('alert').filter({ hasText: /invalid|incorrect|wrong|not match/i }).count());
  // register
  await page.getByRole('button', { name: /create an account/i }).click();
  const email = 'p8-smoke-' + Date.now() + '@finora.test', pw = 'Smoke-Pass-' + Math.random().toString(36).slice(2, 8) + '9!';
  await page.getByLabel('Name (optional)').fill('Priya Tester');
  await page.getByLabel('E-mail').fill(email);
  await page.getByLabel('Password', { exact: true }).fill('short');
  await page.getByRole('button', { name: /^create account/i }).click();
  ok('short password rejected inline', await page.getByText(/at least 10 characters/i).first().isVisible());
  await page.getByLabel('Password', { exact: true }).fill(pw);
  await page.getByRole('button', { name: /^create account/i }).click();
  await page.getByRole('heading', { name: /welcome, priya/i }).waitFor({ timeout: 15000 }).catch(() => {});
  ok('register → Start screen greets by name', await page.getByRole('heading', { name: /welcome, priya/i }).isVisible());
  // demo path
  await page.getByRole('button', { name: /aarav mehta/i }).click();
  await page.getByRole('heading', { name: /good to see you, aarav/i }).waitFor({ timeout: 60000 }).catch(() => {});
  ok('demo copy opens Home', await page.getByRole('heading', { name: /good to see you, aarav/i }).isVisible(), page.url());
  ok('Home shows priorities', await page.getByRole('heading', { name: /what needs your attention/i }).isVisible());
  // every area and tab
  const areas = { '/plan': ['priorities', 'actions', 'plan', 'health', 'goals', 'tax'], '/money': ['overview', 'accounts', 'transactions', 'spending', 'investments', 'debts'],
    '/future': ['cash-flow', 'retirement', 'what-if', 'savings'], '/models': ['overview', 'credit-risk', 'peers', 'categoriser', 'unusual', 'lab'],
    '/data': ['import', 'review', 'records', 'reports', 'profile'], '/settings': ['account', 'security', 'profiles'] };
  for (const [area, tabs] of Object.entries(areas)) {
    for (const t of tabs) {
      await page.goto(`${base}${area}?tab=${t}`);
      await page.waitForSelector('[role=tabpanel]', { timeout: 30000 }).catch(() => {});
      await page.waitForTimeout(700);
      const crash = await page.getByText(/could not be shown/i).count();
      const sel = await page.locator('[role=tab][aria-selected=true]').innerText().catch(() => '');
      const h1 = await page.locator('main h1').count();
      const empty = (await page.locator('[role=tabpanel]').innerText().catch(() => '')).trim().length < 20;
      ok(`${area}?tab=${t}`, !crash && sel && h1 === 1 && !empty, `selected="${sel}" h1=${h1}${crash ? ' CRASH' : ''}${empty ? ' EMPTY' : ''}`);
    }
  }
  for (const p of ['/ask', '/models/review']) {
    await page.goto(base + p); await page.waitForTimeout(1500);
    ok(p, !(await page.getByText(/could not be shown/i).count()) && (await page.locator('h1').count()) >= 1);
  }
  // redirects
  const red = { '/identity': '/money?tab=overview', '/insights': '/money?tab=spending', '/budget': '/money?tab=spending&view=budget', '/credit': '/models?tab=credit-risk',
    '/forecast': '/future?tab=cash-flow', '/fire': '/future?tab=retirement', '/decision': '/future?tab=what-if', '/cfo': '/ask', '/recommendations': '/plan?tab=actions',
    '/statements': '/data?tab=import', '/review?import=7': '/data?tab=review&import=7', '/records': '/data?tab=records', '/reports': '/data?tab=reports', '/accounts': '/money?tab=accounts',
    '/investments': '/money?tab=investments', '/transactions': '/money?tab=transactions', '/scanner': '/models?tab=unusual', '/peers': '/models?tab=peers' };
  for (const [from, to] of Object.entries(red)) {
    await page.goto(base + from); await page.waitForURL((u) => u.pathname + u.search === to, { timeout: 30000 }).catch(() => {});
    const u = new URL(page.url()); ok(`redirect ${from}`, u.pathname + u.search === to, u.pathname + u.search);
  }
  // back/forward + refresh on a tab URL
  await page.goto(base + '/money?tab=spending'); await page.waitForTimeout(800);
  await page.getByRole('tab', { name: /investments/i }).click(); await page.waitForTimeout(500);
  await page.goBack(); await page.waitForTimeout(800);
  ok('back restores previous tab', /tab=spending/.test(page.url()), page.url());
  await page.goForward(); await page.waitForTimeout(800);
  ok('forward restores next tab', /tab=investments/.test(page.url()), page.url());
  await page.reload(); await page.waitForSelector('[role=tab][aria-selected=true]', { timeout: 30000 });
  ok('refresh keeps tab', /investments/i.test(await page.locator('[role=tab][aria-selected=true]').innerText()));
  R.summary = `${R.checks.filter(c => c.pass).length}/${R.checks.length} passed`;
  R.fails = R.checks.filter(c => !c.pass);
  R.account = email;
  delete R.checks;
  return JSON.stringify(R, null, 1);
}
