#!/usr/bin/env node

import { existsSync, mkdirSync, writeFileSync, chmodSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { homedir, platform } from "node:os";
import { join } from "node:path";

const API = (process.env.PRAVIDHI_API_URL || "https://pravidhisolutions.in/pravidhi/v3").replace(/\/$/, "");
const CONTROL = (process.env.PRAVIDHI_CONTROL_URL || "https://mcp.pravidhisolutions.in").replace(/\/$/, "");
const VERSION = "1.2.0";
const args = process.argv.slice(2);
const command = args[0] || "help";

function run(bin, argv, options = {}) {
  console.log(`→ ${bin} ${argv.join(" ")}`);
  return execFileSync(bin, argv, {
    stdio: "inherit",
    env: { ...process.env, ...options.env },
  });
}

function capture(bin, argv) {
  try {
    return execFileSync(bin, argv, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
}

function help() {
  console.log([
    "",
    "Pravidhi AgentOS CLI",
    "",
    "Usage:",
    "  npx pravidhi-agentos@latest <command>",
    "",
    "Commands:",
    "  termux                Install and configure the full Pravidhi Termux agent",
    "  health                 Check control-plane health",
    "  providers              Show authentication providers",
    "  status                 Show control-plane health and identity status",
    "  capabilities           Show documented agent capabilities",
    "  init                    Print secure agent setup instructions",
    "  login google           Show Google OAuth URL",
    "  login github           Show GitHub OAuth URL",
    "  version                Show CLI version",
    "  help                   Show this help",
    "",
    "Termux installer options:",
    "  --control-url URL      Override the Pravidhi control plane",
    "  --agent-id ID          Agent identity (default: ANDROID-TERMUX)",
    "  --agent-name NAME      Agent display name",
    "  --pairing-code CODE    One-time pairing code",
    "",
    "Environment:",
    "  PRAVIDHI_CONTROL_URL   Termux control-plane URL",
    "  PRAVIDHI_AGENT_TOKEN   Existing agent token (never printed)",
    "  PRAVIDHI_AGENT_PAIRING_CODE  One-time pairing code",
    "  PRAVIDHI_AGENT_BOOTSTRAP_TOKEN Bootstrap credential",
    ""
  ].join("\n"));
}

function request(path) {
  return fetch(API + path, {
    headers: {
      accept: "application/json",
      ...(process.env.PRAVIDHI_API_KEY ? { authorization: `Bearer ${process.env.PRAVIDHI_API_KEY}` } : {})
    }
  }).then(async res => {
    const body = await res.text();
    let data;
    try { data = JSON.parse(body); } catch { data = body; }
    if (!res.ok) throw new Error(JSON.stringify({ status: res.status, response: data }, null, 2));
    console.log(JSON.stringify(data, null, 2));
  });
}

function option(name, fallback = "") {
  const i = args.indexOf(name);
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
}

function installer() {
  if (platform() !== "android" && !process.env.TERMUX_VERSION && !process.env.PREFIX) {
    throw new Error("The termux command must be run inside Termux on Android.");
  }

  const home = homedir();
  const prefix = process.env.PREFIX || "/data/data/com.termux/files/usr";
  const repoDir = join(home, "Pravidhi-OS");
  const configDir = join(home, ".pravidhi");
  const envFile = join(configDir, "termux-agent.env");
  const tokenFile = join(configDir, "agent-token.json");
  const serviceRoot = join(prefix, "var", "service");
  const mcpService = join(serviceRoot, "termux-mcp");
  const agentService = join(serviceRoot, "pravidhi-termux");
  const bootDir = join(home, ".termux", "boot");
  const bootFile = join(bootDir, "pravidhi-agent");

  const agentId = option("--agent-id", process.env.PRAVIDHI_AGENT_ID || "ANDROID-TERMUX");
  const agentName = option("--agent-name", process.env.PRAVIDHI_AGENT_NAME || agentId);
  const pairingCode = option("--pairing-code", process.env.PRAVIDHI_AGENT_PAIRING_CODE || "");
  const bootstrap = process.env.PRAVIDHI_AGENT_BOOTSTRAP_TOKEN || "";
  const controlUrl = option("--control-url", process.env.PRAVIDHI_CONTROL_URL || CONTROL);

  console.log("\n🚀 Pravidhi AgentOS — Termux installer\n");

  run("pkg", ["update", "-y"]);
  run("pkg", ["install", "-y", "python", "termux-services", "git", "curl"]);
  run("python", ["-m", "pip", "install", "-U", "termux-mcp"]);

  if (existsSync(join(repoDir, ".git"))) {
    run("git", ["-C", repoDir, "fetch", "--depth", "1", "origin", "main"]);
    run("git", ["-C", repoDir, "reset", "--hard", "origin/main"]);
  } else {
    run("git", ["clone", "--depth", "1", "https://github.com/yashas-13/Pravidhi-OS.git", repoDir]);
  }

  mkdirSync(configDir, { recursive: true });
  mkdirSync(mcpService, { recursive: true });
  mkdirSync(agentService, { recursive: true });
  mkdirSync(join(prefix, "var", "service"), { recursive: true });
  mkdirSync(bootDir, { recursive: true });

  const env = [
    `export PRAVIDHI_CONTROL_URL='${controlUrl.replace(/'/g, "'\\''")}'`,
    "export PRAVIDHI_TENANT_ID='default'",
    `export PRAVIDHI_AGENT_ID='${agentId.replace(/'/g, "'\\''")}'`,
    `export PRAVIDHI_AGENT_NAME='${agentName.replace(/'/g, "'\\''")}'`,
    "export PRAVIDHI_AGENT_VERSION='1.2.0'",
    "export PRAVIDHI_AGENT_HEARTBEAT_SECONDS='30'",
    "export PRAVIDHI_AGENT_POLL_SECONDS='1'",
    "export PRAVIDHI_AGENT_MAX_RESULT_BYTES='200000'",
    "export PRAVIDHI_TERMUX_MCP_URL='http://127.0.0.1:8080'",
    "export PRAVIDHI_AGENT_TOKEN_FILE='$HOME/.pravidhi/agent-token.json'",
    `export PRAVIDHI_AGENT_CAPABILITIES='["filesystem.read","terminal.bash","android.termux","termux.terminal","termux.filesystem.read"]'`,
    "export TERMUX_MCP_HOST='127.0.0.1'",
    "export TERMUX_MCP_PORT='8080'",
    "export TERMUX_MCP_MAX_OUTPUT='200000'",
    ...(pairingCode ? [`export PRAVIDHI_AGENT_PAIRING_CODE='${pairingCode.replace(/'/g, "'\\''")}'`] : []),
    ...(bootstrap ? [`export PRAVIDHI_AGENT_BOOTSTRAP_TOKEN='${bootstrap.replace(/'/g, "'\\''")}'`] : []),
    ""
  ].join("\n");
  writeFileSync(envFile, env, { mode: 0o600 });
  try { chmodSync(envFile, 0o600); } catch {}

  writeFileSync(join(mcpService, "run"), `#!/data/data/com.termux/files/usr/bin/sh
set -eu
. "$HOME/.pravidhi/termux-agent.env"
exec termux-mcp
`);
  writeFileSync(join(agentService, "run"), `#!/data/data/com.termux/files/usr/bin/sh
set -eu
. "$HOME/.pravidhi/termux-agent.env"
cd "$HOME/Pravidhi-OS"
exec python agents/pravidhi_agent.py
`);
  chmodSync(join(mcpService, "run"), 0o755);
  chmodSync(join(agentService, "run"), 0o755);

  writeFileSync(bootFile, `#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock
mkdir -p "$PREFIX/var/service"
if ! pgrep -f "$PREFIX/bin/runsvdir $PREFIX/var/service" >/dev/null 2>&1; then
  nohup runsvdir "$PREFIX/var/service" >/dev/null 2>&1 &
  sleep 1
fi
sv up termux-mcp >/dev/null 2>&1 || true
sv up pravidhi-termux >/dev/null 2>&1 || true
`);
  chmodSync(bootFile, 0o755);

  if (!existsSync(tokenFile) && process.env.PRAVIDHI_AGENT_TOKEN) {
    writeFileSync(tokenFile, JSON.stringify({
      agent_id: agentId,
      agent_token: process.env.PRAVIDHI_AGENT_TOKEN,
      control_url: controlUrl
    }, null, 2), { mode: 0o600 });
    try { chmodSync(tokenFile, 0o600); } catch {}
  }

  const runsv = join(prefix, "bin", "runsvdir");
  if (!existsSync(runsv)) throw new Error("runsvdir was not installed by termux-services.");
  if (!capture("pgrep", ["-f", `${prefix}/bin/runsvdir ${serviceRoot}`])) {
    execFileSync("sh", ["-c", `nohup "${runsv}" "${serviceRoot}" >/dev/null 2>&1 &`]);
  }
  run("sv", ["up", "termux-mcp"]);
  run("sv", ["up", "pravidhi-termux"]);

  console.log("\n✅ Termux services installed.");
  console.log(`   MCP: http://127.0.0.1:8080`);
  console.log(`   Agent: ${agentId}`);
  console.log(`   Repo: ${repoDir}`);
  console.log(`   Boot: ${bootFile}`);

  if (existsSync(tokenFile)) {
    console.log("🔐 Existing agent token detected; activation is preserved.");
  } else if (pairingCode || bootstrap) {
    console.log("🔐 Registration credentials supplied; the agent service will register automatically.");
  } else {
    console.log("\n⚠️ Installation is complete, but this device is not paired yet.");
    console.log("   Supply a one-time pairing code on the next run:");
    console.log("   npx --yes pravidhi-agentos@latest termux --pairing-code YOUR_CODE");
    console.log("   Or set PRAVIDHI_AGENT_PAIRING_CODE before running the installer.");
  }

  console.log("\n🔎 Verification:");
  console.log("   sv status termux-mcp pravidhi-termux");
  console.log("   curl -s http://127.0.0.1:8080/health");
  console.log("");
}

async function main() {
  if (command === "help" || command === "--help" || command === "-h") return help();
  if (command === "termux") return installer();
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
    console.log(`pravidhi-agentos ${VERSION}`);
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
  console.error("❌", err?.message || err);
  process.exitCode = 1;
});
