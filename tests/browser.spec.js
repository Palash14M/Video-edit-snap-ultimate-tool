const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const { mkdtempSync, rmSync, readFileSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
let mediaDir, video;
let ownedProjects = new Set(), ownedJobs = new Set();
test.beforeEach(() => { ownedProjects = new Set(); ownedJobs = new Set(); });
test.afterEach(async ({ page }) => {
  for (const id of ownedJobs) await page.request.post(`/api/jobs/${id}/cancel`);
  for (const id of ownedProjects) {
    const response = await page.request.delete(`/api/projects/${id}`);
    expect([200, 404]).toContain(response.status());
  }
});
test.beforeAll(() => {
  mediaDir = mkdtempSync(join(tmpdir(), 'studio-browser-'));
  video = join(mediaDir, 'example.mp4');
  execFileSync('ffmpeg', ['-v','error','-f','lavfi','-i','testsrc2=size=320x240:rate=24',
    '-f','lavfi','-i','sine=frequency=440','-t','3','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac', video]);
});
test.afterAll(() => { if (mediaDir) rmSync(mediaDir, { recursive: true, force: true }); });
async function openStudio(page) {
  await page.goto('/');
  await expect(page.locator('#login:visible, #app:visible')).toHaveCount(1);
  const password = page.getByLabel('Access password');
  if (await password.isVisible()) {
    await password.fill(process.env.STUDIO_TEST_PASSWORD || 'browser-test-password');
    await page.getByRole('button', { name: 'Open studio', exact: true }).click();
  }
  await expect(page.getByRole('heading', { name: 'Make the cut.', exact: true })).toBeVisible();
}
async function uploadVideo(page) {
  const previous = await page.evaluate(() => sessionStorage.getItem('studio-project'));
  const uploading = page.waitForResponse(response => response.url().endsWith('/api/projects/upload') && response.request().method() === 'POST');
  await page.getByLabel('Upload a video file').setInputFiles(video);
  const response = await uploading;
  expect(response.status()).toBe(202);
  const jobId = (await response.json()).job_id;
  ownedJobs.add(jobId);
  const job = await page.request.get(`/api/jobs/${jobId}`);
  ownedProjects.add((await job.json()).project_id);
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('studio-project')), { timeout: 20000 }).not.toBe(previous);
  await expect(page.getByLabel('Clip end 1')).toBeVisible({ timeout: 20000 });
}
test('real upload, timeline edit and downloadable rendered clip', async ({ page }, testInfo) => {
  const browserErrors = [];
  page.on('pageerror', error => browserErrors.push(error.message));
  await openStudio(page);
  await uploadVideo(page);
  await expect.poll(() => page.locator('#video-player').evaluate(video => video.readyState), { timeout: 20000 }).toBeGreaterThanOrEqual(2);
  await page.locator('#video-player').evaluate(video => video.play());
  await expect.poll(() => page.locator('#video-player').evaluate(video => video.currentTime)).toBeGreaterThan(0.1);
  await page.locator('#video-player').evaluate(video => video.pause());
  await page.getByLabel('Clip end 1').fill('1.2');
  await page.getByLabel('Clip end 1').blur();
  await page.getByLabel('Aspect ratio').selectOption('9:16');
  await page.getByRole('button', { name: 'Export clip', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Download MP4', exact: true }).first()).toBeVisible({ timeout: 50000 });
  await expect.poll(() => page.locator('.clip-card video').first().evaluate(video => video.readyState), { timeout: 20000 }).toBeGreaterThanOrEqual(2);
  await page.locator('.clip-card video').first().evaluate(video => video.play());
  await expect.poll(() => page.locator('.clip-card video').first().evaluate(video => video.currentTime)).toBeGreaterThan(0.1);
  await page.locator('.clip-card video').first().evaluate(video => video.pause());
  const [download] = await Promise.all([
    page.waitForEvent('download'), page.getByRole('link', { name: 'Download MP4', exact: true }).first().click()
  ]);
  expect(await download.failure()).toBeNull();
  expect(download.suggestedFilename()).toMatch(/\.mp4$/);
  await expect(page.getByRole('link', { name: 'Download all ZIP', exact: true })).toBeVisible();
  const [archive] = await Promise.all([
    page.waitForEvent('download'), page.getByRole('link', { name: 'Download all ZIP', exact: true }).click()
  ]);
  expect(await archive.failure()).toBeNull();
  expect(archive.suggestedFilename()).toBe('clips.zip');
  expect(browserErrors).toEqual([]);
  await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0, 0); });
  await page.screenshot({ path: testInfo.outputPath('desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath('mobile.png'), fullPage: true });
});
test('mobile navigation, editable theme and no horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openStudio(page);
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await page.getByLabel('Appearance').selectOption('dark');
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
  await page.getByRole('button', { name: 'Feature coverage', exact: true }).click();
  await page.getByLabel('Search features').fill('caption');
  await expect(page.locator('#feature-list')).toContainText(/caption/i);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});
test('invalid import gives actionable feedback without losing input', async ({ page }) => {
  await openStudio(page);
  await page.getByLabel('Video URL').fill('https://example.com/not-a-video');
  await page.getByRole('button', { name: 'Import video', exact: true }).click();
  await expect(page.locator('#notice')).toBeVisible();
  await expect(page.getByLabel('Video URL')).toHaveValue('https://example.com/not-a-video');
});
test('detected scenes require explicit application before changing the timeline', async ({ page }) => {
  await openStudio(page);
  await uploadVideo(page);
  await page.getByLabel('Clip end 1').fill('1.2');
  await page.getByLabel('Clip end 1').blur();
  await page.getByRole('button', { name: 'Detect scenes', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Use detected sections', exact: true })).toBeVisible({ timeout: 20000 });
  await expect(page.getByLabel('Clip end 1')).toHaveValue('1.2');
  await page.getByRole('button', { name: 'Use detected sections', exact: true }).click();
  expect(Number(await page.getByLabel('Clip end 1').inputValue())).toBeGreaterThan(2.8);
});
test('refresh while an import is queued restores progress and completes safely', async ({ page }) => {
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await openStudio(page); await uploadVideo(page);
  const previous = await page.evaluate(() => sessionStorage.getItem('studio-project'));
  const rendering = await page.request.post(`/api/projects/${previous}/export`, { data: {
    segments: Array.from({ length: 20 }, () => ({ start: 0, end: 2.8 })),
    aspect: '9:16', resolution: 1080, fit: 'contain'
  }});
  expect(rendering.status()).toBe(202);
  const renderingJob = (await rendering.json()).job_id;
  ownedJobs.add(renderingJob);
  const importing = await page.request.post('/api/projects/upload', { multipart: {
    file: { name: 'queued-source.mp4', mimeType: 'video/mp4', buffer: readFileSync(video) }
  }});
  expect(importing.status()).toBe(202);
  const importJob = (await importing.json()).job_id;
  ownedJobs.add(importJob);
  const queued = await page.request.get(`/api/jobs/${importJob}`);
  const queuedJob = await queued.json();
  ownedProjects.add(queuedJob.project_id);
  expect(queuedJob.status).toBe('queued');
  await page.reload();
  await expect(page.locator('#source-job')).toBeVisible();
  await page.request.post(`/api/jobs/${renderingJob}/cancel`);
  await expect(page.getByLabel('Clip end 1')).toBeVisible({ timeout: 30000 });
  expect(await page.evaluate(() => sessionStorage.getItem('studio-project'))).not.toBe(previous);
  expect(errors).toEqual([]);
});
