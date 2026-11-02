/**
 * Gemini 4 Cache-Aware Custom Router for `musistudio/claude-code-router` (CCR v2/v3)
 * =================================================================================
 * Solves both core coexistence caveats for Claude Code (Nov 2026):
 *   1. ZERO MID-THREAD CACHE THRASHING: Pins multi-turn root sessions to their initial
 *      model so the host session's prefix cache never suffers a $5.00/M Opus 5.5
 *      cache-write invalidation or 728-char `tool_use.id` / `thought_signature` 400 error.
 *   2. ZERO-INTERVENTION DYNAMIC OFFLOADING:
 *      - Background / Haiku / indexing -> `gemini,gemini-3.5-flash-lite` (454 tok/s, $0.30/M)
 *      - `<CCR-SUBAGENT-MODEL>` tags & routine Task subagents -> `gemini,gemini-3.8-flash`
 *        (133 tok/s, $0.75/M, 89.4% Terminal-Bench 2.1)
 *      - >150K long-context synthesis, deep reasoning & CWE security -> `gemini,gemini-4-argon`
 *        (GA #1 Cursor Agent Security League; auto-upgrades if `GEMINI4_FAIRWIND_CARBON_MODEL` set)
 *      - Primary 429 / 5-hour quota lockout -> sticky-pins session to `gemini,gemini-4-argon`
 *
 * NOTE: Requires a Paid Tier 1+ Google AI Studio key or Vertex AI IAM (Google retired
 * free-tier Studio quota for frontier models in Dec 2025).
 */

const sessionPins = new Map();

const SUBAGENT_TAG_RE = /<CCR-SUBAGENT-MODEL>\s*([^<\s]+)\s*<\/CCR-SUBAGENT-MODEL>/i;
const SECURITY_INTENT_RE =
  /\b(cve-\d+|cwe-\d+|security\s+audit|vulnerability|auth\s+bypass|sql\s+injection|ssrf|xss|race\s+condition|deadlock|taint|cryptograph|privilege\s+escalation)\b/i;
const DEEP_SWE_INTENT_RE =
  /\b(migrate\s+all|full\s+test\s+suite|refactor\s+across|rewrite\s+module|monorepo\s+scan|64k|architecture\s+synthesis)\b/i;

function resolveSecurityModel() {
  const fairwindCarbon = (process.env.GEMINI4_FAIRWIND_CARBON_MODEL || "").trim();
  if (fairwindCarbon) {
    return fairwindCarbon.includes(",") ? fairwindCarbon : `gemini,${fairwindCarbon}`;
  }
  return "gemini,gemini-4-argon";
}

module.exports = async function router(req, config) {
  const body = req.body || {};
  const messages = Array.isArray(body.messages) ? body.messages : [];
  const turnCount = messages.length;
  const reqModel = String(body.model || "").toLowerCase();
  const tokenCount = Number(req.tokenCount || 0);

  const sessionId =
    (body.metadata && body.metadata.user_id) ||
    (req.headers && req.headers["x-session-id"]) ||
    "default-root-session";

  const lastMsg = messages[messages.length - 1];
  const lastText = lastMsg
    ? typeof lastMsg.content === "string"
      ? lastMsg.content
      : JSON.stringify(lastMsg.content)
    : "";
  const firstTwoText = JSON.stringify(messages.slice(0, 2));

  // 1. Explicit `<CCR-SUBAGENT-MODEL>` override inside an isolated subagent prompt
  const tagMatch = lastText.match(SUBAGENT_TAG_RE) || firstTwoText.match(SUBAGENT_TAG_RE);
  if (tagMatch) {
    if (lastMsg && typeof lastMsg.content === "string") {
      lastMsg.content = lastMsg.content.replace(SUBAGENT_TAG_RE, "").trim();
    }
    return tagMatch[1].replace("/", ",");
  }

  // 2. Haiku / background loops -> Gemini 3.5 Flash-Lite (454 tok/s, $0.30/M)
  if (reqModel.includes("haiku") || reqModel.includes("3.5-flash-lite")) {
    return "gemini,gemini-3.5-flash-lite";
  }

  // 3. Routine subagent / compaction -> Gemini 3.8 Flash (133 tok/s, $0.75/M)
  if (body.isSubagent || reqModel.includes("3.8-flash")) {
    if (SECURITY_INTENT_RE.test(lastText)) {
      return resolveSecurityModel();
    }
    if (tokenCount > 150000 || DEEP_SWE_INTENT_RE.test(lastText)) {
      return "gemini,gemini-4-argon";
    }
    return "gemini,gemini-3.8-flash";
  }

  // 4. Multi-turn Root Session Cache Guard: NEVER switch models mid-thread!
  if (turnCount > 2 && sessionPins.has(sessionId)) {
    return sessionPins.get(sessionId);
  }

  // 5. Turn-1 Classification for Brand-New Sessions
  let initialRoute;
  if (tokenCount > 150000) {
    initialRoute = "gemini,gemini-4-argon";
  } else if (SECURITY_INTENT_RE.test(lastText)) {
    initialRoute = resolveSecurityModel();
  } else if (DEEP_SWE_INTENT_RE.test(lastText)) {
    initialRoute = "gemini,gemini-4-argon";
  } else {
    initialRoute =
      (config && config.Router && config.Router.default) ||
      "anthropic,claude-opus-5-5";
  }

  sessionPins.set(sessionId, initialRoute);
  return initialRoute;
};
