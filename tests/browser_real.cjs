const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const path = require("node:path");
(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROMIUM_EXECUTABLE
      ? {
          executablePath: process.env.CHROMIUM_EXECUTABLE,
          args: ["--no-sandbox"],
        }
      : {}),
  });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } }),
    errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const base = process.env.VIDEOTRUST_TEST_URL;
  await page.goto(base);
  await page.locator("#consent").check();
  await page.locator("#start").click();
  await page.waitForFunction(
    () => document.querySelector("#video").readyState >= 3,
  );
  const info = await page.locator("#video").evaluate(async (v) => {
    v.muted = true;
    await v.play();
    return { width: v.videoWidth, height: v.videoHeight, duration: v.duration };
  });
  await page.waitForFunction(
    () => document.querySelector("#video").currentTime > 1.5,
  );
  await page.locator("#video").evaluate((v) => v.pause());
  assert(info.duration > 0 && info.width > 0 && info.height > 0);
  await page.locator('input[name=trust][value="0"]').check();
  await page
    .locator("#reason")
    .fill("Synthetic playback test; this is not a research judgment.");
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  );
  if (process.env.SCREENSHOT_DIR)
    await page.screenshot({
      path: path.join(process.env.SCREENSHOT_DIR, "real-video-mobile.png"),
      fullPage: true,
    });
  await page.locator("#submit").click();
  await page.locator("#done").waitFor({ state: "visible" });
  await page.goto(base + "/researcher");
  await page.locator("#admin-token").fill(process.env.VIDEOTRUST_TEST_TOKEN);
  await page.locator("#login button").click();
  await page.locator("#results").waitFor({ state: "visible" });
  assert.equal(await page.locator("#responses").textContent(), "1");
  assert.equal(await page.locator("#paired").textContent(), "0");
  assert.equal(await page.locator("#gap").textContent(), "—");
  assert.equal(await page.locator("#chart circle").count(), 0);
  assert(await page.locator("#demo-note").isHidden());
  await page.locator("#tab-model").click();
  assert(
    (await page.locator("#panel-model").textContent()).includes(
      "No completed model",
    ),
  );
  if (process.env.VIDEOTRUST_EXPECT_EVIDENCE === "1") {
    await page.locator("#tab-evidence").click();
    await page.waitForFunction(
      () => document.querySelectorAll("#panel-evidence img").length === 6,
    );
    await page.waitForFunction(() =>
      [...document.querySelectorAll("#panel-evidence img")].every(
        (i) => i.complete && i.naturalWidth > 0,
      ),
    );
    assert((await page.locator(".transcript").textContent()).length > 20);
  }
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  );
  assert.deepEqual(errors, []);
  console.log(
    JSON.stringify({
      status: "passed",
      media: info,
      checks: [
        "uploaded video playback",
        "portrait mobile layout",
        "response save",
        "missing model stays missing",
        "real transcript and protected frames when supplied",
        "no JavaScript errors",
      ],
    }),
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
