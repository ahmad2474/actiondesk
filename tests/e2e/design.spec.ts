import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { checkScreenshot } from "./visual.js";

test.describe("synthetic design previews", () => {
  for (const [screen, variant] of [["home", "current"], ["requests", "current"], ["detail", "long"], ["detail", "changes"], ["detail", "reversal"], ["detail", "service"], ["approvals", "current"], ["service", "current"], ["finance", "current"], ["create", "current"], ["revision", "current"]]) {
    test(`${screen} ${variant}: responsive, accessible, stable`, async ({ page }, info) => {
      const mutations: string[] = [];
      page.on("request", request => { if (request.method() === "POST" && request.url().includes("/api/actiondesk/")) mutations.push(request.url()); });
      await page.goto(`/preview?screen=${screen}&variant=${variant}`);
      await expect(page.getByText("Synthetic preview", { exact: true })).toBeVisible();
      if ((page.viewportSize()?.width ?? 0) < 1024) {
        for (const control of [page.getByRole("button", { name: "Open navigation" }), page.getByRole("button", { name: "Account menu" }), page.locator(".app-header .new-request")]) {
          const bounds = await control.boundingBox();
          expect(bounds?.width).toBeGreaterThanOrEqual(44);
          expect(bounds?.height).toBeGreaterThanOrEqual(44);
        }
      }
      if (screen === "home") {
        await expect(page.locator(".app-header .new-request")).toBeVisible();
        if ((page.viewportSize()?.width ?? 0) < 768) await expect(page.locator(".home-intro>.button")).toBeHidden();
        else await expect(page.locator(".home-intro>.button")).toBeVisible();
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
      await checkScreenshot(page, info, `${screen}-${variant}.png`);
      expect(mutations).toEqual([]);
      if (screen === "detail" && variant === "changes") {
        await expect(page.locator("#submitted")).toContainText("PKR 230,000.00");
        await expect(page.locator(".proposed-revision")).toContainText("PKR 248,500.00");
      }
      if (screen === "detail") {
        const workflow = page.locator(".workflow-panel");
        if ((page.viewportSize()?.width ?? 0) < 1024) {
          expect(await workflow.evaluate(element => element.previousElementSibling)).toBeNull();
          expect(await workflow.evaluate(element => getComputedStyle(element).position)).toBe("static");
        }
        if (variant === "long") await expect(page.getByText("Historical evidence. These approvals do not authorize the current submission.")).toBeHidden();
      }
    });
  }

  test("union navigation and admin do not create role modes", async ({ page }) => {
    async function navigation() {
      if ((page.viewportSize()?.width ?? 0) < 1024) await page.getByRole("button", { name: "Open navigation" }).click();
      return page.getByRole("navigation", { name: "Primary navigation" });
    }
    await page.goto("/preview");
    const nav = await navigation();
    await expect(nav.getByRole("link", { name: "Approvals", exact: true })).toHaveCount(1);
    await expect(nav.getByRole("link", { name: "Finance Processing" })).toHaveCount(1);
    await page.goto("/preview?role=admin");
    await expect((await navigation()).getByRole("link", { name: "Approvals", exact: true })).toHaveCount(0);
    await page.goto("/preview?role=employee");
    const employee = await navigation();
    await expect(employee.getByRole("link", { name: "Finance Processing" })).toHaveCount(0);
    await expect(employee.getByRole("link", { name: "Service Work" })).toHaveCount(1);
  });

  test("keyboard dialog containment, cancellation and focus restoration", async ({ page }, info) => {
    await page.goto("/preview?screen=detail");
    const trigger = page.getByRole("button", { name: "Approve · Preview", exact: true });
    await trigger.focus(); await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await expect(dialog).toContainText("No live request will change");
    await checkScreenshot(page, info, "approval-dialog.png", false);
    for (let index = 0; index < 8; index++) { await page.keyboard.press("Tab"); expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true); }
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden(); await expect(trigger).toBeFocused();
    await page.keyboard.press("Enter");
    await page.getByRole("button", { name: "Simulate preview only" }).click();
    await expect(page.getByRole("status")).toContainText("No live request was changed");
    await expect(trigger).toBeFocused();
  });

  test("tertiary identifiers expose and copy the unchanged full audit value", async ({ page, context }, info) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.goto("/preview?screen=detail&variant=long");
    await page.locator("#submitted summary", { hasText: "Request identifiers" }).click();
    const trigger = page.getByRole("button", { name: /Show full request id/ });
    await trigger.focus(); await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", { name: "Request ID", exact: true });
    await expect(dialog).toBeVisible();
    const value = "0000000a-0000-4000-8000-000000000010";
    const input = dialog.getByLabel("Full request id");
    await expect(input).toHaveValue(value);
    await expect(input).toBeFocused();
    await expect(input).toHaveAttribute("readonly", "");
    await expect(dialog).not.toContainText("preview"); // Shared inspection UI has no workflow/preview boilerplate.
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    // Verify autofocus above, then capture the keyboard-ready copy state. Chromium's
    // focused, selected native textarea can repaint rounded border/outline corners
    // between captures even with identical geometry and no running animations.
    await input.evaluate((element: HTMLTextAreaElement) => element.setSelectionRange(0, 0));
    await page.keyboard.press("Tab");
    await expect(dialog.getByRole("button", { name: "Close", exact: true })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(dialog.getByRole("button", { name: "Copy full identifier" })).toBeFocused();
    await checkScreenshot(page, info, "identifier-dialog.png", false);
    await dialog.getByRole("button", { name: "Copy full identifier" }).click();
    await expect(dialog.getByRole("status")).toContainText("Copied full identifier");
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(value);
    await page.evaluate(() => Object.defineProperty(navigator.clipboard, "writeText", { configurable: true, value: () => Promise.reject(new Error("Permission denied")) }));
    await dialog.getByRole("button", { name: "Copy full identifier" }).click();
    await expect(dialog.getByRole("status")).toContainText("copy it manually");
    await expect(input).toHaveValue(value);
    await page.keyboard.press("Escape");
    await expect(trigger).toBeFocused();
  });

  test("long evidence retains every event with explicit submission and cycle boundaries", async ({ page }) => {
    await page.goto("/preview?screen=detail&variant=long");
    await expect(page.locator(".timeline>li")).toHaveCount(10);
    await expect(page.locator(".timeline-boundary-label")).toHaveText(["Submission event 8 · Current", "Submission event 2 · Historical"]);
    await expect(page.locator("#revisions .evidence-current")).toHaveAttribute("open", "");
    const historical = page.locator("#revisions .evidence-historical");
    await historical.locator("summary").click();
    await expect(historical).toContainText("Historical evidence. These approvals do not authorize the current submission.");
    await expect(historical).toContainText("Initial equipment scope approved.");
    await page.goto("/preview?screen=detail&variant=service");
    await expect(page.locator(".timeline>li")).toHaveCount(8);
    await expect(page.locator(".timeline-boundary-label")).toHaveText(["Work cycle event 6 · Current", "Work cycle event 4 · Historical"]);
    await expect(page.locator("#service-cycles .evidence-current")).toContainText("Repaired the coolant connection and verified cooling under load.");
    const priorCycle = page.locator("#service-cycles .evidence-historical");
    await priorCycle.locator("summary").click();
    await expect(priorCycle).toContainText("Replaced the filter and tested the unit.");
    await expect(priorCycle).toContainText("The room is still warm after lunch. Please check the cooling circuit.");
  });

  test("navigation drawer and menu focus, keyboard-only", async ({ page }) => {
    await page.goto("/preview");
    await page.keyboard.press("Tab"); await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
    const trigger = page.getByRole("button", { name: "Open navigation" });
    if ((page.viewportSize()?.width ?? 0) < 1024) {
      await trigger.focus(); await page.keyboard.press("Enter");
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.keyboard.press("Escape"); await expect(trigger).toBeFocused();
    }
    const account = page.getByRole("button", { name: "Account menu" });
    await account.focus(); await page.keyboard.press("Enter");
    await expect(page.getByRole("menu")).toBeVisible();
    await page.keyboard.press("Escape"); await expect(account).toBeFocused();
    expect(await account.evaluate(element => getComputedStyle(element).outlineStyle)).not.toBe("none");
  });

  test("date-only and decimal form validation, reduced motion, alert dialog", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/preview?screen=create");
    await page.getByLabel("Request title").fill("Synthetic expense");
    await page.getByLabel("Vendor", { exact: true }).fill("Fictional supplier");
    await page.getByLabel("Amount", { exact: true }).fill("9007199254740991.99");
    await page.getByLabel("Purpose", { exact: true }).fill("Synthetic equipment");
    await page.getByLabel("Original context").fill("Synthetic intake");
    await page.getByRole("button", { name: "Preview submission" }).click();
    await expect(page.getByRole("status")).toContainText("No request was created");
    await page.getByRole("button", { name: "Leave", exact: true }).click();
    await page.getByLabel("Request title").fill("Synthetic leave");
    await page.getByLabel("Start date").fill("2026-11-05");
    await page.getByLabel("End date").fill("2026-11-04");
    await page.getByLabel("Leave type").fill("Annual");
    await page.getByLabel("Original context").fill("Synthetic intake");
    await page.getByRole("button", { name: "Preview submission" }).click();
    await expect(page.locator(".form-error")).toContainText("End date must be on or after");
    await page.getByRole("button", { name: "Discard preview", exact: true }).click();
    await expect(page.getByRole("alertdialog")).toBeVisible();
    await expect(page.getByRole("button", { name: "Keep editing" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", { name: "Discard preview", exact: true })).toBeFocused();
  });

  test("first-class loading, empty, error and conflict examples", async ({ page }) => {
    for (const variant of ["loading", "empty", "403", "404", "409", "422", "network"]) {
      await page.goto(`/preview?screen=states&variant=${variant}`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (!["loading", "empty"].includes(variant)) await expect(page.locator(".error-state")).toBeVisible();
    }
  });
});
