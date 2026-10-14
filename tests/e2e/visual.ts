import { existsSync } from "node:fs";
import { expect, type Page, type TestInfo } from "@playwright/test";
/** Baselines are OS-specific because the approved system font differs by platform. */
export async function checkScreenshot(page: Page, info: TestInfo, name: string, fullPage = true): Promise<void> {
  if (existsSync(info.snapshotPath(name)) || ["all", "changed"].includes(info.config.updateSnapshots)) {
    await expect(page).toHaveScreenshot(name, { fullPage, animations: "disabled" });
  } else {
    // A new platform still checks stable rendering and emits reviewable screenshots;
    // it never silently creates a reference or compares incompatible system fonts.
    const first = await page.screenshot({ fullPage, animations: "disabled" });
    const second = await page.screenshot({ fullPage, animations: "disabled" });
    expect(second.equals(first), "Repeated screenshots must be stable on this platform").toBe(true);
    await info.attach(`unbaselined-${name}`, { body: first, contentType: "image/png" });
  }
}
