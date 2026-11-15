async page => {
  // Phase 9: a loan whose EMI does not cover its interest is shown as "never paid off" (before the fix the planner showed
  // "600 months to debt-free" with crores of interest). Entered through the UI's own record form.
  const R = { checks: [] };
  const ok = (name, pass, info = '') => R.checks.push(`${pass ? 'PASS' : 'FAIL'} ${name} ${String(info).slice(0, 160)}`);
  const base = 'http://localhost:5173', dir = '/Users/adityakhanna/Developer/finora/docs/phase8-screenshots/';
  const wait = (ms) => page.waitForTimeout(ms);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.context().clearCookies();
  await page.goto(base + '/');
  await page.getByRole('button', { name: /create an account/i }).click();
  await page.getByLabel('E-mail').fill('p9-debt-' + Date.now() + '@finora.test');
  await page.getByLabel('Password', { exact: true }).fill('Debt-Edge-' + Date.now() + '!');
  await page.getByRole('button', { name: /^create account/i }).click();
  await page.getByRole('heading', { name: /welcome/i }).waitFor({ timeout: 15000 });
  const pid = await page.evaluate(async () => (await (await fetch('/api/profiles', { method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': document.cookie.match(/csrf[^=]*=([^;]+)/)?.[1] || '' },
    body: JSON.stringify({ name: 'Edge Debt', age: 34 }) })).json()).profile.internal_id);
  const made = await page.evaluate(async (id) => (await fetch(`/api/profiles/${id}/records/loans`, { method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': document.cookie.match(/csrf[^=]*=([^;]+)/)?.[1] || '' },
    body: JSON.stringify({ loan_type: 'Personal Loan', lender: 'Bajaj Finance', principal: 500000, balance: 300000, emi: 2000, interest_rate: 14,
                           tenure_months: 360, remaining_months: 300 }) })).status, pid);
  ok('loan with EMI below the monthly interest is accepted (₹2,000 EMI on ₹3,00,000 at 14%)', made === 201, made);
  await page.goto(base + '/'); await wait(2000);
  await page.getByRole('button', { name: /edge debt/i }).first().click(); await wait(3000);
  await page.goto(base + '/money?tab=debts'); await wait(3500);
  const t = await page.locator('main').innerText();
  ok('Debts shows "never paid off" instead of a 600-month payoff', /never paid off/i.test(t) && !/\b600\b/.test(t), t.match(/At these payments[^.]*\./)?.[0]);
  ok('Loans table says the loan is never cleared instead of an "interest still to pay" figure', /never cleared at this emi/i.test(t));
  await page.getByText(/never paid off/i).first().scrollIntoViewIfNeeded();
  await page.screenshot({ path: dir + 'p9-43-debt-never-paid-off.png' });
  await page.getByLabel('Extra payment per month').fill('10000'); await wait(2500);
  const t2 = await page.locator('main').innerText();
  ok('with ₹10,000 extra a month the planner shows a real debt-free month count', /months to debt-free/i.test(t2) && !/never paid off/i.test(t2));
  await page.screenshot({ path: dir + 'p9-44-debt-with-extra-payment.png' });
  R.pid = pid; R.summary = `${R.checks.filter(c => c.startsWith('PASS')).length}/${R.checks.length} passed`;
  return JSON.stringify(R, null, 1);
}
