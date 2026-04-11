const { firefox } = require("playwright");

(async () => {
  const browser = await firefox.launch();

  // ── Mobile 390×844 ────────────────────────────────────────────────────────
  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await mobile.goto("http://127.0.0.1:8765/");
  await mobile.waitForTimeout(3000);

  await mobile.screenshot({ path: "screenshots/04-mobile-initial.png" });
  console.log("04-mobile-initial.png");

  await mobile.click("#toggle-nodes-drawer");
  await mobile.waitForTimeout(500);
  await mobile.screenshot({ path: "screenshots/05-mobile-drawer-closed.png" });
  console.log("05-mobile-drawer-closed.png");

  await mobile.click("#toggle-traffic-drawer");
  await mobile.waitForTimeout(500);
  await mobile.screenshot({ path: "screenshots/06-mobile-traffic-open.png" });
  console.log("06-mobile-traffic-open.png");

  await mobile.close();

  // Desktop: verify traffic drawer
  const desktop = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await desktop.goto("http://127.0.0.1:8765/");
  await desktop.waitForTimeout(3000);
  await desktop.click("#toggle-traffic-drawer");
  await desktop.waitForTimeout(600);
  await desktop.screenshot({ path: "screenshots/07-desktop-traffic-alone.png" });
  console.log("07-desktop-traffic-alone.png");

  await desktop.close();
  await browser.close();
  console.log("\nDone.");
})();
