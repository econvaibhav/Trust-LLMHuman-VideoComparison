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
      viewport: { width: 1440, height: 1100 },
    }),
    errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error" && m.text().includes("Content Security Policy"))
      errors.push(m.text());
  });
  const base = process.env.VIDEOTRUST_TEST_URL;
  await page.goto(base);
  await page.locator("#consent").check();
  await page.locator("#start").click();
  await page.waitForFunction(
    () => document.querySelector("#video").readyState >= 3,
  );
  const first = await page.locator("#video-title").textContent();
  await page.locator('input[name=trust][value="0"]').check();
  await page
    .locator("#reason")
    .fill("My own initial view, before the interview.");
  await page.reload();
  await page.waitForFunction(
    () => document.querySelector("#video").readyState >= 3,
  );
  assert(await page.locator('input[name=trust][value="0"]').isChecked());
  assert.equal(
    await page.locator("#reason").inputValue(),
    "My own initial view, before the interview.",
  );
  await page.locator("#submit").click();
  await page.locator("#interview-form").waitFor({ state: "visible" });
  assert.equal(await page.locator("#video-title").textContent(), first);
  await page
    .locator("#interview-answer")
    .fill("The claim needs a named source.");
  await page.reload();
  await page.waitForFunction(
    () => document.querySelector("#video").readyState >= 3,
  );
  assert.equal(
    await page.locator("#interview-answer").inputValue(),
    "The claim needs a named source.",
  );
  // Lose the response AFTER the server has saved the answer. The client must recover.
  await page.route(
    "**/api/interview/answer",
    async (route) => {
      await route.fetch();
      await route.abort("failed");
    },
    { times: 1 },
  );
  await page.locator("#send-answer").click();
  await page.waitForFunction(
    () => document.querySelectorAll("#conversation p").length === 3,
  );
  const sessionToken = await page.evaluate(() =>
    sessionStorage.getItem("vt-session"),
  );
  const state = await (
    await page.request.get(base + "/api/session", {
      headers: { Authorization: "Bearer " + sessionToken },
    })
  ).json();
  assert.equal(state.interview.answered, 1);
  assert.equal(await page.locator("#interview-answer").inputValue(), "");
  if (process.env.SCREENSHOT_DIR)
    await page.screenshot({
      path: path.join(process.env.SCREENSHOT_DIR, "paired-interview.png"),
      fullPage: true,
    });
  await page.locator("#finish-interview").click();
  await page.waitForFunction(
    () => document.querySelector("#step-label").textContent === "Video 2 of 3",
  );
  await page.goto(base + "/researcher");
  await page.locator("#admin-token").fill(process.env.VIDEOTRUST_TEST_TOKEN);
  await page.locator("#login button").click();
  await page.locator("#results").waitFor({ state: "visible" });
  assert.equal(await page.locator("#responses").textContent(), "1");
  assert.equal(await page.locator("#measure").inputValue(), "direct_rating");
  assert(
    (await page.locator("#agreement-value").textContent()).includes(
      "mean absolute gap 5.0",
    ),
  );
  await page.locator("#measure").selectOption("interview_inferred");
  await page.waitForFunction(
    () =>
      document.querySelector("#participant-column").textContent === "Inferred",
  );
  assert.equal(await page.locator("#responses").textContent(), "1");
  assert.equal(await page.locator("#chart circle").count(), 1);
  await page.locator("#tab-evidence").click();
  await page.waitForFunction(
    () => document.querySelectorAll("#panel-evidence img").length === 2,
  );
  await page.waitForFunction(() =>
    [...document.querySelectorAll("#panel-evidence img")].every(
      (i) => i.complete && i.naturalWidth > 0,
    ),
  );
  await page.locator("#tab-responses").click();
  await page.locator("#panel-responses summary").click();
  assert(
    (await page.locator("#panel-responses").textContent()).includes(
      "The claim needs a named source.",
    ),
  );
  const download = page.waitForEvent("download");
  await page.locator("#export-comparison").click();
  assert.equal((await download).suggestedFilename(), "comparison.csv");
  await page.locator("#search").fill("no video has this title");
  assert(await page.locator("#list-empty").isVisible());
  await page.locator("#search").fill("");
  if (process.env.SCREENSHOT_DIR)
    await page.screenshot({
      path: path.join(process.env.SCREENSHOT_DIR, "dashboard-paired.png"),
      fullPage: true,
    });
  await page.setViewportSize({ width: 390, height: 844 });
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    "Dashboard overflows on mobile",
  );
  if (process.env.SCREENSHOT_DIR)
    await page.screenshot({
      path: path.join(process.env.SCREENSHOT_DIR, "dashboard-mobile.png"),
      fullPage: true,
    });
  await page.goto(base);
  await page.route("**/media/**", (r) => r.abort());
  await page.reload();
  await page.locator("#media-error").waitFor({ state: "visible" });
  await page.locator('input[name=trust][value="5"]').check();
  assert(
    await page.locator("#submit").isDisabled(),
    "Broken video must block response",
  );
  await page.unroute("**/media/**");
  await page.reload();
  await page.waitForFunction(
    () => document.querySelector("#video").readyState >= 3,
  );
  await page.locator("#submit").click();
  await page.locator("#interview-form").waitFor({ state: "visible" });
  await page.route("**/media/**", (r) => r.abort());
  await page.reload();
  await page.locator("#media-error").waitFor({ state: "visible" });
  assert(
    await page.locator("#send-answer").isDisabled(),
    "Broken video must block interview too",
  );
  assert.deepEqual(errors, []);
  console.log(
    JSON.stringify({
      status: "passed",
      checks: [
        "paired rating before interview",
        "draft recovery",
        "lost-response recovery without duplicate",
        "matched participant measures",
        "protected frames render",
        "measure switching",
        "comparison CSV",
        "video search",
        "mobile dashboard",
        "broken playback blocks both forms",
      ],
    }),
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
