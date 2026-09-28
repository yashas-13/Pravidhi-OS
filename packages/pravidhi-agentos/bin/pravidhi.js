#!/usr/bin/env node

const API = (process.env.PRAVIDHI_API_URL || "https://pravidhisolutions.in/pravidhi/v3").replace(/\/$/, "");
const args = process.argv.slice(2);
const command = args[0] || "help";

function help() {
  console.log([
    "",
    "Pravidhi AgentOS CLI",
    "",
    "Usage:",
    "  npx pravidhi-agentos@latest <command>",
    "",
    "Commands:",
    "  health                 Check control-plane health",
    "  providers              Show authentication providers",
    "  status                  Show control-plane health and identity status",
    "  capabilities            Show documented agent capabilities",
    "  init                    Print secure agent setup instructions",
    "  login google           Show Google OAuth URL",
    "  login github           Show GitHub OAuth URL",
    "  version                Show CLI version",
    "  help                   Show this help",
    "",
    "Environment:",
    "  PRAVIDHI_API_URL       Override the control-plane URL",
    ""
  ].join("\n"));
}

async function request(path) {
  const headers = { accept: "application/json" };
  if (process.env.PRAVIDHI_API_KEY) headers.authorization = `Bearer ${process.env.PRAVIDHI_API_KEY}`;
  const res = await fetch(API + path, { headers });
  const body = await res.text();
  let data;
  try { data = JSON.parse(body); } catch { data = body; }
  if (!res.ok) {
    console.error(JSON.stringify({ status: res.status, response: data }, null, 2));
    process.exitCode = 1;
    return;
  }
  console.log(JSON.stringify(data, null, 2));
}

async function main() {
  if (command === "help" || command === "--help" || command === "-h") return help();
  if (command === "health") return request("/health");
  if (command === "providers") return request("/auth/providers");
  if (command === "status") return request("/health");
  if (command === "capabilities") {
    console.log(JSON.stringify({ capabilities: ["terminal","filesystem","screen","browser","application","mcp"], note: "Capabilities are policy-controlled and deployment-dependent." }, null, 2));
    return;
  }
  if (command === "init") {
    console.log(["","Pravidhi AgentOS secure setup","","1. Create/register a machine in your Pravidhi control plane.","2. Set PRAVIDHI_API_URL to the control-plane base URL.","3. Set PRAVIDHI_API_KEY using your secret manager; never commit it.","4. Run: npx pravidhi-agentos@latest health","5. Run: npx pravidhi-agentos@latest status","","Privileged API access is fail-closed when authentication is not configured.",""].join("\n"));
    return;
  }
  if (command === "version" || command === "--version" || command === "-v") {
    console.log("pravidhi-agentos 1.1.0");
    return;
  }
  if (command === "login") {
    const provider = args[1];
    if (!["google", "github"].includes(provider)) {
      console.error("Choose: google or github");
      process.exitCode = 2;
      return;
    }
    console.log(API.replace(/\/v3$/, "") + "/auth/" + provider);
    return;
  }
  console.error("Unknown command:", command);
  help();
  process.exitCode = 2;
}

main().catch(err => {
  console.error(err?.message || err);
  process.exitCode = 1;
});