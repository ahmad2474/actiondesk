import { existsSync } from "node:fs";
import { writeFile } from "node:fs/promises";
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
    if (!second.equals(first)) {
      // Persist paths as well as reporter attachments: the default list reporter
      // does not write inline buffers into the directory uploaded by CI.
      for (const [label, body] of [["first", first], ["second", second]] as const) {
        const path = info.outputPath(`unstable-${label}-${name}`);
        await writeFile(path, body);
        await info.attach(`unstable-${label}-${name}`, { path, contentType: "image/png" });
      }
    }
    expect(second.equals(first), "Repeated screenshots must be stable on this platform").toBe(true);
    await info.attach(`unbaselined-${name}`, { body: first, contentType: "image/png" });
  }
}
