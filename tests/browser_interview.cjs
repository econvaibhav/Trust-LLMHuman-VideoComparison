/* Run against a fresh interview demo; see README.md. */
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
  const page = await browser.newPage({
      viewport: { width: 1280, height: 1000 },
    }),
    errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const base = process.env.VIDEOTRUST_TEST_URL || "http://127.0.0.1:8001";
  await page.goto(base);
  await page.locator("#consent").check();
  await page.locator("#start").click();
  await page.locator("#interview-form").waitFor({ state: "visible" });
  assert(await page.locator("#rating-form").isHidden());
  await page.waitForFunction(
    () => document.querySelector("#video").readyState >= 2,
  );
  await page.locator("#video").evaluate((v) => v.play());
  await page.waitForFunction(
    () => document.querySelector("#video").currentTime > 0.3,
  );
  await page.locator("#video").evaluate((v) => v.pause());
  await page
    .locator("#interview-answer")
    .fill("The video provides little evidence for the claim.");
  await page.locator("#send-answer").click();
  await page.waitForFunction(
    () => document.querySelectorAll("#conversation p").length === 3,
  );
  await page.reload();
  await page.waitForFunction(
    () => document.querySelectorAll("#conversation p").length === 3,
  );
  if (process.env.SCREENSHOT_DIR)
    await page.screenshot({
      path: path.join(process.env.SCREENSHOT_DIR, "interview-desktop.png"),
      fullPage: true,
    });
  for (let turn = 1; turn < 3; turn++) {
    await page.locator("#interview-answer").fill(`Answer ${turn}: I would look for a named source.`);
    await page.locator("#send-answer").click();
    if (turn < 2) await page.waitForFunction(() => document.querySelectorAll("#conversation p").length === 5);
  }
  await page.locator("#done").waitFor({ state: "visible" });
  await page.goto(base + "/researcher");
  await page.locator("#admin-token").fill(process.env.VIDEOTRUST_TEST_TOKEN);
  await page.locator("#login button").click();
  await page.locator("#results").waitFor({ state: "visible" });
  assert(
    (await page.locator("#measure-note").textContent()).includes("inferred"),
  );
  assert.equal(await page.locator("#paired").textContent(), "0");
  const download = page.waitForEvent("download");
  await page.locator("#export-interviews").click();
  assert.equal((await download).suggestedFilename(), "interviews.json");
  assert.deepEqual(errors, []);
  console.log(
    JSON.stringify({
      status: "passed",
      checks: [
        "interview video playback",
        "neutral follow-up flow",
        "resume saved answers",
        "automatic finish",
        "score measure separation",
        "interview export",
        "no JavaScript errors",
      ],
    }),
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
