import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// dev 代理必须覆盖前端实际调用的全部 REST/WS 前缀：缺一条，该功能在
// `python main.py` dev 模式下即 404（登录 / 报告导出 / 模板曾因此部署即坏）。
// vitest 以 frontend/ 为 cwd，直接按根相对路径读取 vite.config.ts。
const text = readFileSync(resolve(process.cwd(), "vite.config.ts"), "utf-8");

const proxied = Array.from(text.matchAll(/^\s+"(\/[a-z]+)":/gm)).map((m) => m[1]);

describe("vite dev 代理完整性", () => {
  it("覆盖 client / builder / panel 实际调用的全部前缀", () => {
    for (const prefix of [
      "/sessions",
      "/capabilities",
      "/export",
      "/data",
      "/auth",
      "/report",
      "/templates",
      "/ws",
    ]) {
      expect(proxied, `vite proxy 缺少 ${prefix}`).toContain(prefix);
    }
  });
});
