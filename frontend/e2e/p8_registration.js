async page => {
  const R = { checks: [], consoleErrors: [] };
  const ok = (name, pass, info = '') => R.checks.push({ name, pass: !!pass, info: String(info).slice(0, 200) });
  page.on('pageerror', e => R.consoleErrors.push('PAGEERROR ' + e.message.slice(0, 200)));
  const base = 'http://localhost:5173';
  const stamp = Date.now(), pw = 'Present-Pass-' + stamp + '!';
  const made = [];
  for (let i = 1; i <= 20; i++) {
    await page.context().clearCookies();
    await page.goto(base + '/'); await page.getByRole('button', { name: /create an account/i }).click();
    const email = `p8-reg-${stamp}-${i}@finora.test`;
    await page.getByLabel('E-mail').fill(email); await page.getByLabel('Password', { exact: true }).fill(pw);
    await page.getByRole('button', { name: /^create account/i }).click();
    const okNow = await page.getByRole('heading', { name: /welcome/i }).waitFor({ timeout: 10000 }).then(() => true).catch(() => false);
    const err = okNow ? '' : (await page.locator('[role=alert]').allInnerTexts()).join(' | ');
    made.push({ email, ok: okNow, err });
  }
  const good = made.filter(m => m.ok).length;
  ok('20 consecutive registrations from one IP through the sign-up form', good === 20, `${good}/20 ${made.filter(m => !m.ok).map(m => m.err).join(' ; ')}`);
  // duplicate e-mail rejected with a clear message
  await page.context().clearCookies();
  await page.goto(base + '/'); await page.getByRole('button', { name: /create an account/i }).click();
  await page.getByLabel('E-mail').fill(made[0].email); await page.getByLabel('Password', { exact: true }).fill(pw);
  await page.getByRole('button', { name: /^create account/i }).click(); await page.waitForTimeout(1500);
  const dup = (await page.locator('[role=alert]').allInnerTexts()).join(' ');
  ok('duplicate e-mail rejected with a clear message', /already|exists|registered/i.test(dup), dup);
  // independent sign-in + isolation: account 1 creates a private profile; account 2 cannot see it
  await page.context().clearCookies(); await page.goto(base + '/');
  await page.getByLabel('E-mail').fill(made[0].email); await page.getByLabel('Password', { exact: true }).fill(pw);
  await page.getByRole('button', { name: /^sign in/i }).click();
  await page.getByRole('heading', { name: /welcome/i }).waitFor({ timeout: 10000 });
  const pid = await page.evaluate(async () => { const c = document.cookie.split('; ').find(x => x.startsWith('finora_csrf='))?.slice(12) || '';
    const r = await fetch('/api/profiles', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': decodeURIComponent(c) }, body: JSON.stringify({ name: 'Account One', age: 31 }) });
    return (await r.json()).profile.internal_id });
  ok('account 1 signs in and creates its private profile', /^FP_|^U|[A-Z]/.test(pid || ''), pid);
  await page.getByRole('button', { name: /sign out/i }).click(); await page.waitForTimeout(1000);
  await page.goto(base + '/data'); await page.waitForTimeout(800);
  ok('after sign-out a protected URL shows sign-in', await page.getByRole('heading', { name: /sign in to finora/i }).isVisible());
  await page.getByLabel('E-mail').fill(made[1].email); await page.getByLabel('Password', { exact: true }).fill(pw);
  await page.getByRole('button', { name: /^sign in/i }).click(); await page.getByRole('heading', { name: /welcome/i }).waitFor({ timeout: 10000 });
  const probe = await page.evaluate(async (id) => ({ profile: (await fetch(`/api/profiles/${id}`, { credentials: 'include' })).status, list: (await (await fetch('/api/profiles', { credentials: 'include' })).json()).some(p => p.internal_id === id) }), pid);
  ok("account 2 cannot read account 1's private profile", probe.profile === 404 && !probe.list, JSON.stringify(probe));
  R.summary = `${R.checks.filter(c => c.pass).length}/${R.checks.length} passed`;
  R.fails = R.checks.filter(c => !c.pass); R.all = R.checks.map(c => `${c.pass ? 'PASS' : 'FAIL'} ${c.name} ${c.info}`);
  delete R.checks;
  return JSON.stringify(R, null, 1);
}
