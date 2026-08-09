// Thin HTTP client for the control-API. All commands call through this.
// Env vars consumed:
//   CONTROL_API_URL    default: http://localhost:8080
//   CONTROL_API_TOKEN  default: changeme_local_only
//   MC_ADMIN_ROLE_ID   default: 1535796235376795728

const API_URL   = (process.env.CONTROL_API_URL || 'http://localhost:8080').replace(/\/$/, '');
const API_TOKEN = process.env.CONTROL_API_TOKEN || 'changeme_local_only';
const ADMIN_ROLE_ID = process.env.MC_ADMIN_ROLE_ID || '1535796235376795728';

async function apiCall(method, endpointPath, body = null, timeoutMs = 15000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const res = await fetch(`${API_URL}${endpointPath}`, {
            method,
            headers: {
                'Authorization': `Bearer ${API_TOKEN}`,
                'Content-Type':  'application/json',
            },
            body: body ? JSON.stringify(body) : undefined,
            signal: controller.signal,
        });
        const text = await res.text();
        let data;
        try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }
        return { ok: res.ok, status: res.status, data };
    } catch (err) {
        if (err.name === 'AbortError') {
            return { ok: false, status: 0, data: { detail: `Timeout after ${timeoutMs}ms` } };
        }
        return { ok: false, status: 0, data: { detail: `Network error: ${err.message}` } };
    } finally {
        clearTimeout(timer);
    }
}

function isAdmin(interaction) {
    if (!interaction.inGuild()) return false;
    return interaction.member?.roles?.cache?.has(ADMIN_ROLE_ID) ?? false;
}

async function denyIfNotAdmin(interaction) {
    if (isAdmin(interaction)) return false;
    await interaction.reply({
        content: `You need the required role to run this command.`,
        ephemeral: true,
    });
    return true;
}

function formatDuration(seconds) {
    if (seconds == null) return 'unknown';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
}

module.exports = { apiCall, isAdmin, denyIfNotAdmin, formatDuration, API_URL, ADMIN_ROLE_ID };
