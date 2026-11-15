async page => {
  const R = { checks: [], consoleErrors: [], failed: [] };
  const ok = (name, pass, info = '') => R.checks.push({ name, pass: !!pass, info: String(info).slice(0, 220) });
  page.on('console', m => { if (m.type() === 'error' && !/401 \(Unauthorized\)|404 \(Not Found\)/.test(m.text())) R.consoleErrors.push(m.text().slice(0, 200)); });
  page.on('pageerror', e => R.consoleErrors.push('PAGEERROR ' + e.message.slice(0, 200)));
  const base = 'http://localhost:5173';
  const shots = '/Users/adityakhanna/Developer/finora/docs/phase8-screenshots/';
  const wait = (ms) => page.waitForTimeout(ms);
  const api = async (path, opts) => page.evaluate(async ([p, o]) => { const c = document.cookie.split('; ').find(x => x.startsWith('finora_csrf='))?.slice(12) || '';
    const r = await fetch(p, { credentials: 'include', ...(o || {}), headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': decodeURIComponent(c) } }); let j = null; try { j = await r.json() } catch {} return { s: r.status, j } }, ['/api' + path, opts]);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.context().clearCookies();
  await page.goto(base + '/'); await wait(1500);
  await page.screenshot({ path: shots + '01-sign-in-desktop.png' });
  await page.getByRole('button', { name: /create an account/i }).click();
  const emailA = 'p8-resp-' + Date.now() + '@finora.test', pwA = 'Resp-Pass-' + Date.now() + '!';
  await page.getByLabel('Name (optional)').fill('Meera Shah');
  await page.getByLabel('E-mail').fill(emailA); await page.getByLabel('Password', { exact: true }).fill(pwA);
  await page.getByRole('button', { name: /^create account/i }).click();
  await page.getByRole('heading', { name: /welcome, meera/i }).waitFor({ timeout: 15000 });
  await page.screenshot({ path: shots + '02-start-desktop.png' });

  // ---- private profile: empty state, add data, persistence, isolation
  await page.getByRole('radio', { name: /start with my own data/i }).click();
  await page.getByLabel('Name').fill('Meera Shah'); await page.getByLabel('City (optional)').fill('Pune');
  await page.getByRole('button', { name: /create my private profile/i }).click();
  await page.waitForURL(/\/data\?tab=records/, { timeout: 30000 }).catch(() => {});
  await wait(2500);
  const priv = (await api('/profiles')).j.find(p => p.kind === 'private');
  ok('private profile created and opens Data → Records', priv && /tab=records/.test(page.url()), priv?.internal_id);
  await page.goto(base + '/'); await wait(2500);
  ok('empty private profile Home explains missing data (no invented figures)', await page.getByRole('heading', { name: /get your numbers in/i }).isVisible() && !(await page.locator('main').innerText()).match(/₹[1-9]/));
  await page.screenshot({ path: shots + '03-home-empty-private.png' });
  const inc = await api(`/profiles/${priv.internal_id}/records/income`, { method: 'POST', body: JSON.stringify({ source: 'Salary', amount: 90000, date: '2026-10-01' }) });
  ok('income record added via API for the private profile', inc.s >= 200 && inc.s < 300, JSON.stringify(inc.j).slice(0, 120));
  await page.reload(); await wait(3000);
  const recs = (await api(`/profiles/${priv.internal_id}/records/income`)).j;
  ok('record persists after refresh', recs.items?.length === 1);
  // second, independent account (new browser context = separate cookies)
  const ctxB = await page.context().browser().newContext();
  const pb = await ctxB.newPage();
  await pb.goto(base + '/');
  await pb.getByRole('button', { name: /create an account/i }).click();
  await pb.getByLabel('E-mail').fill('p8-other-' + Date.now() + '@finora.test'); await pb.getByLabel('Password', { exact: true }).fill('Other-Pass-' + Date.now() + '!');
  await pb.getByRole('button', { name: /^create account/i }).click(); await pb.waitForTimeout(2500);
  const probe = await pb.evaluate(async (id) => { const out = {}; for (const p of [`/api/profiles/${id}`, `/api/profiles/${id}/analysis`, `/api/profiles/${id}/records/income`, `/api/profiles/${id}/chat`, `/api/profiles/${id}/transactions`]) out[p] = (await fetch(p, { credentials: 'include' })).status; return out }, priv.internal_id);
  ok('other account gets 404 on every route of the private profile', Object.values(probe).every(s => s === 404), JSON.stringify(probe));
  const listB = await pb.evaluate(async () => (await fetch('/api/profiles', { credentials: 'include' })).json());
  ok("other account's profile list excludes it", !listB.some(p => p.internal_id === priv.internal_id));
  await pb.evaluate((id) => sessionStorage.setItem('finora.profile', id), priv.internal_id); await pb.reload(); await pb.waitForTimeout(3000);
  ok('forcing the id in the browser does not open it', !(await pb.getByText('Meera Shah').count()));
  await ctxB.close();
  // demo copy for the rest
  await page.goto(base + '/settings?tab=profiles'); await wait(1500);
  await page.getByRole('button', { name: /switch or create profile/i }).click(); await wait(1500);
  await page.getByRole('radio', { name: /explore a demo person/i }).click();
  await page.getByRole('button', { name: /riya kapoor/i }).click();
  await page.getByRole('heading', { name: /good to see you/i }).waitFor({ timeout: 60000 });
  ok('demo and private profiles coexist on one account', (await api('/profiles')).j.filter(p => p.kind !== 'template').length === 2);

  // ---- responsive + a11y sweep
  const VP = [['desktop', 1440, 900], ['laptop', 1280, 800], ['tablet', 768, 1024], ['mobile', 390, 844]];
  const PAGES = [['home', '/'], ['plan', '/plan'], ['money', '/money?tab=transactions'], ['spending', '/money?tab=spending'], ['future', '/future'], ['models', '/models'], ['lab', '/models?tab=lab'], ['ask', '/ask'], ['data', '/data?tab=import'], ['settings', '/settings']];
  for (const [vn, w, h] of VP) {
    await page.setViewportSize({ width: w, height: h });
    for (const [pn, path] of PAGES) {
      await page.goto(base + path); await wait(1800);
      const m = await page.evaluate(() => {
        const vw = document.documentElement.clientWidth;
        const over = [...document.querySelectorAll('body *')].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.right > vw + 1 && getComputedStyle(e).position !== 'fixed' && !e.closest('[class*=overflow-x-auto],[class*=overflow-auto],[class*=overflow-x]') })
          .slice(0, 3).map(e => e.tagName + '.' + String(e.className).slice(0, 40));
        const unnamedBtn = [...document.querySelectorAll('button,[role=button],a[href]')].filter(b => b.offsetParent && !(b.innerText.trim() || b.getAttribute('aria-label') || b.getAttribute('title') || b.querySelector('img[alt]'))).length;
        const unlabelled = [...document.querySelectorAll('input:not([type=hidden]):not([hidden]),select,textarea')].filter(i => i.offsetParent && !(i.labels?.length || i.getAttribute('aria-label') || i.getAttribute('aria-labelledby'))).map(i => i.name || i.type).slice(0, 4);
        return { scroll: document.documentElement.scrollWidth - vw, over, h1: document.querySelectorAll('h1').length, unnamedBtn, unlabelled,
          aside: Math.round(document.querySelector('aside[aria-label=Main]')?.getBoundingClientRect().width || 0) };
      });
      const navOk = w >= 1280 ? m.aside >= 220 : w >= 768 ? m.aside > 60 && m.aside < 90 : m.aside === 0 && await page.getByRole('button', { name: 'Open navigation' }).isVisible();
      ok(`${vn} ${pn}`, m.scroll <= 1 && !m.over.length && m.h1 === 1 && !m.unnamedBtn && !m.unlabelled.length && navOk,
        `scroll+${m.scroll} over=${m.over.join('|')} h1=${m.h1} unnamedBtn=${m.unnamedBtn} unlabelled=${m.unlabelled.join(',')} aside=${m.aside}`);
      if (['home', 'money', 'ask', 'models', 'plan', 'spending', 'lab', 'data', 'settings', 'future'].includes(pn) && (vn === 'desktop' || (vn === 'mobile' && ['home', 'money', 'ask', 'plan'].includes(pn)) || (vn === 'tablet' && pn === 'home')))
        await page.screenshot({ path: `${shots}${vn}-${pn}.png` });
    }
  }
  try {
  // mobile drawer navigation
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(base + '/'); await wait(1500);
  await page.getByRole('button', { name: 'Open navigation' }).click();
  const dlg = page.getByRole('dialog', { name: 'Navigation' });
  ok('mobile nav drawer opens', await dlg.isVisible());
  await dlg.getByRole('link', { name: 'Future' }).click(); await wait(1500);
  ok('mobile drawer link navigates and closes', /\/future/.test(page.url()) && !(await page.getByRole('dialog', { name: 'Navigation' }).count()));
  // keyboard: skip link
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(base + '/plan'); await wait(2000);
  await page.keyboard.press('Tab');
  const skip = await page.evaluate(() => document.activeElement?.textContent);
  await page.keyboard.press('Enter'); await wait(200);
  ok('first Tab reaches "Skip to content" and Enter moves focus to main', /skip to content/i.test(skip) && await page.evaluate(() => document.activeElement?.id === 'main'), skip);
  // keyboard: tabs arrow keys
  await page.getByRole('tab', { name: 'Priorities' }).focus(); await page.keyboard.press('ArrowRight'); await wait(800);
  ok('tabs: ArrowRight moves to next tab and updates URL', /tab=actions/.test(page.url()));
  // focus visible
  const ring = await page.evaluate(() => { const b = document.querySelector('[role=tab][aria-selected=true]'); b.focus(); return getComputedStyle(b).outlineStyle + ' ' + getComputedStyle(b).outlineWidth });
  ok('focused control shows a visible outline', !/none/.test(ring), ring);
  // logout + protected
  await page.getByRole('button', { name: 'Account menu' }).click();
  await page.getByRole('menuitem', { name: 'Sign out' }).click(); await wait(1500);
  await page.goto(base + '/money?tab=transactions'); await wait(1500);
  ok('after sign-out a protected URL shows sign-in', await page.getByRole('heading', { name: /sign in to finora/i }).isVisible());
  await page.getByLabel('E-mail').fill(emailA); await page.getByLabel('Password', { exact: true }).fill(pwA);
  await page.getByRole('button', { name: /^sign in/i }).click(); await wait(3000);
  ok('signing back in works and profiles persist', (await page.getByText(/continue where you left off/i).count()) === 1 && (await page.getByText('Meera Shah').count()) >= 1);
  } catch (e) { ok('SECTION tail', false, e.message.split('\n')[0]) }
  R.summary = `${R.checks.filter(c => c.pass).length}/${R.checks.length} passed`;
  R.fails = R.checks.filter(c => !c.pass);
  delete R.checks;
  return JSON.stringify(R, null, 1);
}
