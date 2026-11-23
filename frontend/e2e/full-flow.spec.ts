import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const FIXTURE = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures", "cohort.csv");

test("浏览器全流程：上传 → 讨论 → 类型确认 → 方案 → 拼图 → 交付 → 导出", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("MedSta")).toBeVisible();
  await expect(
    page.getByText("上传数据并确认方案后，数据画像与图表将展示在这里")
  ).toBeVisible();

  // 新建会话（上传入口只在会话激活后出现）
  await page.getByTitle("新建会话空间").click();
  await expect(page.getByRole("button", { name: /^会话 1/ })).toBeVisible();

  await page.locator('input[type="file"]').first().setInputFiles(FIXTURE);
  await expect(page.getByText(/数据「cohort.csv」已绑定当前会话/)).toBeVisible();

  const composer = page.getByPlaceholder("描述分析目标，或对方案提出修正意见…");
  await composer.fill("比较 A、B 两组的 value 差异，并先看分布");
  await page.getByRole("button", { name: /发送/ }).click();

  await expect(page.getByText("请敲定变量类型")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: /确认类型，开始讨论/ }).click();

  await expect(page.getByText("分析方案")).toBeVisible({ timeout: 30_000 });
  // 047：方案以流程图交付（节点=工具、边=依赖），再确认后可逐节点执行
  await expect(page.getByTestId("plan-flow")).toBeVisible();
  await expect(page.getByTestId("flow-node-0")).toContainText("分布统计");
  await expect(page.getByTestId("flow-node-1")).toContainText("组间比较");
  await page.getByRole("button", { name: "按此执行" }).click();

  await expect(page.getByText("出图前确认")).toBeVisible();
  await page.getByRole("button", { name: "同一画板拼图" }).click();
  await page.getByRole("button", { name: /按此配置执行/ }).click();

  await expect(page.getByText("执行完成，请审阅结果")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("link", { name: "查看图表" }).first()).toBeVisible();
  await page.getByRole("button", { name: /确认交付/ }).click();
  await expect(page.getByText(/结果已交付/)).toBeVisible();

  // 工作区：画像 + 两张统计表 + 拼图产物
  await page.getByRole("button", { name: /工作区（1）/ }).click();
  await expect(page.getByText("数据画像")).toBeVisible();
  await expect(page.getByText("统计表交付（2）")).toBeVisible();
  // 拼图布局下两步共用一张产物图，但图表数按步骤计
  await expect(page.getByText("图表交付（2）")).toBeVisible();

  const csvLink = page.getByRole("link", { name: "CSV" }).first();
  const href = await csvLink.getAttribute("href");
  expect(href).toBeTruthy();
  const download = await page.request.get(href as string);
  expect(download.status()).toBe(200);
  expect(download.headers()["content-type"]).toContain("text/csv");
  expect(await download.text()).toContain("column");

  // 窄屏：同一套 Tab 在单栏间切换
  await page.setViewportSize({ width: 700, height: 900 });
  const sections = page.locator("main > section");
  await page.getByRole("button", { name: /会话（1）/ }).click();
  await expect(sections.nth(0)).toBeVisible();
  await expect(sections.nth(1)).toBeHidden();

  await page.getByRole("button", { name: /工作区（1）/ }).click();
  await expect(sections.nth(1)).toBeVisible();
  await expect(sections.nth(0)).toBeHidden();

  // 刷新：自动回到该会话，右栏由工作区快照重建（此前刷新后左右两侧都空/不挂钩）
  await page.reload();
  await expect(page.getByRole("button", { name: /^会话（1）/ })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: /^工作区（1）/ }).click();
  await expect(page.getByText("数据画像")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("统计表交付（2）")).toBeVisible();
  await expect(page.getByText("图表交付（2）")).toBeVisible();
});

test("能力抽屉与上传失败提示（真实前后端契约）", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: /能力/ }).click();
  // 抽屉内的工具名与「工具装配」下拉项同名：作用域限定到 dialog，避免 strict 冲突
  const drawer = page.getByRole("dialog", { name: "统计能力披露" });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText("描述性统计")).toBeVisible();
  await expect(drawer.getByText("生存分析", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "关闭能力抽屉" }).click();
  await expect(drawer).toBeHidden();

  await page.getByTitle("新建会话空间").click();
  await page.locator('input[type="file"]').first().setInputFiles({
    name: "notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("not a table"),
  });

  await expect(page.getByText("上传失败", { exact: true })).toBeVisible();
  await expect(page.getByText(/不支持的文件类型/)).toBeVisible();
});
