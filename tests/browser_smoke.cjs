/* Optional browser integration test. npm install --no-save playwright first. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
(async () => {
  const launch = { headless: true };
  if (process.env.CHROMIUM_EXECUTABLE) {
    launch.executablePath = process.env.CHROMIUM_EXECUTABLE;
    launch.args = ["--no-sandbox"];
  }
  const browser = await chromium.launch(launch);
  const base = process.env.VIDEOTRUST_TEST_URL || "http://127.0.0.1:8000";
  const token = process.env.VIDEOTRUST_TEST_TOKEN;
  assert(
    token,
    "Set VIDEOTRUST_TEST_TOKEN to the running demo server researcher token",
  );
  const out = process.env.SCREENSHOT_DIR;
  if (out) fs.mkdirSync(out, { recursive: true });
  const errors = [];
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1100 },
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(base);
  await page.waitForFunction(() =>
    document.getElementById("consent-text").textContent.includes("fictional"),
  );
  assert(await page.locator("#start").isDisabled());
  if (out)
    await page.screenshot({
      path: path.join(out, "welcome-desktop.png"),
      fullPage: true,
    });
  await page.locator("#consent").check();
  await page.locator("#start").click();
  await page.locator("#task").waitFor({ state: "visible" });
  const first = await page.locator("#video-title").textContent();
  await page.reload();
  await page.locator("#task").waitFor({ state: "visible" });
  assert.equal(
    await page.locator("#video-title").textContent(),
    first,
    "Session did not resume its assignment",
  );
  for (let i = 0; i < 3; i++) {
    await page.waitForFunction(
      () => document.querySelector("#video").readyState >= 2,
    );
    await page.locator("#video").evaluate((v) => v.play());
    await page.waitForFunction(
      () => document.querySelector("#video").currentTime > 0.4,
    );
    await page.locator("#video").evaluate((v) => v.pause());
    const title = await page.locator("#video-title").textContent();
    const score = title.includes("garden")
      ? 8
      : title.includes("habit")
        ? 2
        : 6;
    await page.locator(`input[name=trust][value="${score}"]`).check();
    await page
      .locator("#reason")
      .fill("Browser integration test: a synthetic demonstration response.");
    await page.locator("#confidence").selectOption("8");
    if (i === 0 && out)
      await page.screenshot({
        path: path.join(out, "survey-desktop.png"),
        fullPage: true,
      });
    await page.locator("#submit").click();
    if (i < 2)
      await page.waitForFunction(
        (previous) =>
          document.getElementById("video-title").textContent !== previous,
        title,
      );
  }
  await page.locator("#done").waitFor({ state: "visible" });
  await page.goto(base + "/researcher");
  await page.locator("#admin-token").fill(token);
  await page.locator("#login button").click();
  await page.locator("#results").waitFor({ state: "visible" });
  assert.equal(await page.locator("#paired").textContent(), "3");
  assert(await page.locator("#demo-note").isVisible());
  assert.equal(await page.locator("#chart circle").count(), 3);
  if (out)
    await page.screenshot({
      path: path.join(out, "dashboard-desktop.png"),
      fullPage: true,
    });
  const downloadPromise = page.waitForEvent("download");
  await page.locator("#export").click();
  const download = await downloadPromise;
  assert.equal(download.suggestedFilename(), "human_responses.csv");
  const mobile = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  const mp = await mobile.newPage();
  mp.on("pageerror", (e) => errors.push(e.message));
  await mp.goto(base);
  await mp.locator("#consent").check();
  await mp.locator("#start").click();
  await mp.locator("#task").waitFor({ state: "visible" });
  await mp.waitForFunction(
    () => document.querySelector("#video").readyState >= 2,
  );
  await mp.locator("#video").evaluate((v) => v.play());
  await mp.waitForFunction(
    () => document.querySelector("#video").currentTime > 1.2,
  );
  await mp.locator("#video").evaluate((v) => v.pause());
  await mp.locator('input[name=trust][value="0"]').check();
  assert(
    await mp.locator("#submit").isEnabled(),
    "Zero score should allow submission",
  );
  const size = await mp.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    width: innerWidth,
  }));
  assert(size.scroll <= size.width, "Mobile layout overflows horizontally");
  if (out)
    await mp.screenshot({
      path: path.join(out, "survey-mobile.png"),
      fullPage: true,
    });
  assert.deepEqual(errors, [], "Browser JavaScript errors");
  console.log(
    JSON.stringify({
      status: "passed",
      browser: await browser.version(),
      checks: [
        "consent",
        "resume",
        "real MP4 playback",
        "three saved ratings",
        "protected dashboard",
        "scatter plot",
        "CSV download",
        "mobile 390px",
        "valid zero score",
        "no JavaScript errors",
      ],
    }),
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
