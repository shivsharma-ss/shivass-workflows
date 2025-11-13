import { expect, test } from '@playwright/test';

const summaryResponse = {
  items: [
    {
      analysisId: 'alpha',
      email: 'demo@example.com',
      cvDocId: 'cv123',
      status: 'completed',
      lastError: null,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    },
  ],
};

const statusResponse = {
  analysisId: 'alpha',
  status: 'completed',
  lastError: null,
  payload: { summary: 'Ready' },
};

const artifactsResponse = [
  {
    analysisId: 'alpha',
    artifactType: 'suggestions',
    content: '{"takeaway":"Great fit"}',
    createdAt: new Date().toISOString(),
  },
];

test('CV submission workflow happy path', async ({ page }) => {
  await page.route('**/v1/analyses?**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(summaryResponse),
    });
  });

  await page.route('**/v1/analyses/alpha', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(statusResponse),
    });
  });

  await page.route('**/v1/analyses/alpha/artifacts', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(artifactsResponse),
    });
  });

  await page.route('**/v1/analyses', async (route) => {
    if (route.request().method() !== 'POST') {
      return route.continue();
    }
    const body = route.request().postDataJSON();
    expect(body.cvDocId).toBe('abc123456789012345678901234567890123456789');
    expect(body.preferredYoutubeChannels.length).toBeGreaterThan(0);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ analysisId: 'beta', status: 'pending' }),
    });
  });

  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Workflow control center' })).toBeVisible();

  await page.getByLabel('Notification email *').fill('candidate@example.com');
  await page
    .getByLabel('CV Google Doc ID *')
    .fill('https://docs.google.com/document/d/abc123456789012345678901234567890123456789/edit');
  await page.getByPlaceholder('Paste the job description text...').fill('Deliver insights');

  const chip = page.getByRole('button', { name: /freeCodeCamp\.org/ });
  await chip.click();
  const slider = page.locator('input[type=range]').first();
  await slider.evaluate((element, value) => {
    element.value = value;
    element.dispatchEvent(new Event('input', { bubbles: true }));
  }, '1.60');
  await page.getByRole('button', { name: 'Done' }).click();

  await page.getByRole('button', { name: /Start workflow/i }).click();
  await expect(page.getByText(/Workflow queued successfully/)).toBeVisible();

  const themeToggle = page.getByRole('button', { name: /Switch to dark mode/i });
  await themeToggle.click();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.theme)).toBe('dark');
  await page.reload();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.theme)).toBe('dark');
});
