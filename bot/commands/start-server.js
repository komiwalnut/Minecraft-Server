const { SlashCommandBuilder } = require('discord.js');
const { apiCall, denyIfNotAdmin, formatDuration } = require('../lib/api.js');

const READY_TIMEOUT_MS = 5 * 60 * 1000;
const POLL_INTERVAL_MS = 10 * 1000;

module.exports = {
    data: new SlashCommandBuilder()
        .setName('start-server')
        .setDescription('Boot the on-demand Minecraft server.')
        .addStringOption(opt =>
            opt.setName('tier')
                .setDescription('Which tier profile to boot (default: cpx21)')
                .setRequired(false)
                .addChoices(
                    { name: 'cpx21 (3 vCPU / 4 GB)', value: 'cpx21' },
                    { name: 'cpx31 (4 vCPU / 8 GB)', value: 'cpx31' },
                )),

    async execute(interaction) {
        if (await denyIfNotAdmin(interaction)) return;

        const tier = interaction.options.getString('tier') || 'cpx21';
        await interaction.deferReply();

        const start = await apiCall('POST', '/start', { tier });
        if (!start.ok) {
            return interaction.editReply(
                `Couldn't start the server (${start.status}): ${start.data.detail || 'unknown error'}`
            );
        }

        await interaction.editReply(`Booting **${tier}** — this usually takes 1–3 minutes. I'll edit this message when it's ready.`);

        const started = Date.now();
        while (Date.now() - started < READY_TIMEOUT_MS) {
            await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
            const s = await apiCall('GET', '/status');
            if (!s.ok) continue;

            if (s.data.state === 'running') {
                return interaction.editReply(
                    `Server is up on **${s.data.tier}**. Connect to \`localhost:25565\` (dev) `
                    + `or the VPS host (prod). Uptime: ${formatDuration(s.data.uptime_s)}.`
                );
            }
            if (s.data.state === 'error' || s.data.state === 'stopped') {
                return interaction.editReply(
                    `Server never reached ready state (last state: ${s.data.state}). ${s.data.message || ''}`
                );
            }
        }

        return interaction.editReply(
            `Server is still booting after ${READY_TIMEOUT_MS / 60000} min. `
            + `Run \`/server-status\` in a minute to check.`
        );
    },
};
